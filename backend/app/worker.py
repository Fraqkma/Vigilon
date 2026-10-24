import json, logging, os, queue, socket, threading, time, uuid
import cv2
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import select, update
from .adapters import OpenCVAdapter, SyntheticAdapter
from .core import HANDOFF_DIR, MEDIA_DIR, fernet
from .db import Camera, Lease, Rule, Session, now
from .detection import FrameContext, SimulatedScenarioPlugin
from .detection import DetectionResult
from .ai_hub import hub, report_worker_status, report_operation
from .rules import TemporalRuleEvaluator
from .scenario_rules import keep_candidate, needs_track
from .services.incident_service import persist_detection

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s %(levelname)s %(name)s %(message)s")
log=logging.getLogger("vigilon.worker")
OWNER=f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
SIMULATED_DETECTOR=SimulatedScenarioPlugin()

def acquire_lease():
    with Session.begin() as db:
        row=db.scalar(select(Lease).where(Lease.id==1).with_for_update()); t=now()
        expiry=row.expires.replace(tzinfo=timezone.utc) if row and row.expires.tzinfo is None else (row.expires if row else None)
        if row and expiry>t and row.owner!=OWNER: raise RuntimeError(f"worker lease held by {row.owner}")
        if row: row.owner=OWNER; row.expires=t+timedelta(seconds=15)
        else: db.add(Lease(id=1,owner=OWNER,expires=t+timedelta(seconds=15)))

def _replace_retry(source,target,attempts=6,pause=.02):
    """Windows refuses os.replace while the API process has the target open (PermissionError).
    Retry briefly instead of failing the whole frame, which also skipped AI for that frame."""
    for attempt in range(attempts):
        try: source.replace(target); return True
        except PermissionError:
            if attempt==attempts-1: return False
            time.sleep(pause*(attempt+1))

def _mtime(path):
    try: return path.stat().st_mtime
    except OSError: return 0.0

def write_preview(camera_id,frame,scenario,resize_limit):
    path=HANDOFF_DIR/f"camera-{camera_id}-{frame.sequence}.jpg"; tmp=path.with_suffix(".tmp")
    if hasattr(frame.image,"save"): image=frame.image
    else:
        from PIL import Image
        image=Image.fromarray(cv2.cvtColor(frame.image,cv2.COLOR_BGR2RGB))
    image.thumbnail((resize_limit,resize_limit)); image.save(tmp,format="JPEG",quality=82)
    if not _replace_retry(tmp,path): raise PermissionError("preview_jpeg_locked")
    meta={"captured_at":datetime.fromtimestamp(frame.captured_at,timezone.utc).isoformat(),"width":image.width,"height":image.height,"sequence":frame.sequence,"simulated":scenario!="real","file":path.name}
    manifest=HANDOFF_DIR/f"camera-{camera_id}.json"
    temp=manifest.with_suffix(".tmp");temp.write_text(json.dumps(meta))
    # A locked manifest only delays the preview by one frame; the JPEG above is still valid evidence.
    if not _replace_retry(temp,manifest): log.warning("source=%s preview_manifest_locked",camera_id)
    # Retain a tiny handoff window so an API response that just read the previous
    # manifest can still open its JPEG while the next frame arrives.
    candidates=sorted(HANDOFF_DIR.glob(f"camera-{camera_id}-*.jpg"),key=_mtime,reverse=True)
    for old in candidates[3:]:
        try: old.unlink(missing_ok=True)
        except PermissionError: pass   # still being served by the API; removed on a later frame
    return path

class SourceRunner:
    """One daemon reader and one replace-oldest frame slot per configured source."""
    def __init__(self,camera):
        self.camera=camera; self.frames=queue.Queue(maxsize=1); self.stop_event=threading.Event()
        self.status="CONNECTING";self.error_category="";self.last_frame=camera.last_frame;self.reconnects=camera.reconnects or 0;self.processed=camera.processed or 0;self.dropped=camera.dropped or 0
        self.thread=threading.Thread(target=self.run,name=f"source-{camera.id}",daemon=True)
    def start(self): self.thread.start()
    def stop(self): self.stop_event.set()
    def join(self,timeout=6): self.thread.join(timeout)
    def adapter(self):
        c=self.camera
        if c.source_type=="synthetic": return SyntheticAdapter(c.scenario)
        if c.source_type=="webcam":
            from .webcam_adapter import WebcamAdapter
            return WebcamAdapter(c.connection,timeout=c.timeout_seconds)
        connection=fernet.decrypt(c.secret.encode()).decode() if c.secret else c.connection
        return OpenCVAdapter(c.source_type,connection,MEDIA_DIR,timeout=c.timeout_seconds)
    def run(self):
        delay=self.camera.reconnect_min_seconds
        while not self.stop_event.is_set():
            adapter=None
            try:
                adapter=self.adapter()
                if not adapter.open(): raise RuntimeError("source_unavailable")
                self.status="ONLINE";self.error_category="";delay=1
                interval=1/max(1,self.camera.processing_fps or 2)
                # Live RTSP: keep pulling packets at the camera's own frame rate and only convert one
                # frame per processing slot. Sleeping between reads (the file/synthetic path below)
                # lets packets back up, so a "fresh" frame can actually be seconds old.
                drain=self.camera.source_type=="rtsp" and hasattr(adapter,"grab")
                next_emit=time.monotonic()
                while not self.stop_event.is_set():
                    started=time.monotonic()
                    if drain:
                        if not adapter.grab(): raise EOFError("source_eof")
                        if time.monotonic()<next_emit: continue
                        frame=adapter.retrieve(); next_emit=time.monotonic()+interval
                    else: frame=adapter.read()
                    if frame is None: raise EOFError("source_eof")
                    self.last_frame=datetime.fromtimestamp(frame.captured_at,timezone.utc);self.processed+=1
                    try: self.frames.put_nowait(frame)
                    except queue.Full:
                        try: self.frames.get_nowait()
                        except queue.Empty: pass
                        self.dropped+=1
                        try: self.frames.put_nowait(frame)
                        except queue.Full: self.dropped+=1
                    if not drain:
                        pace=max(0,interval-(time.monotonic()-started))
                        self.stop_event.wait(pace)
            except Exception as e:
                self.status="OFFLINE";self.reconnects+=1
                self.error_category=(str(e) if isinstance(e,ValueError) else "source_eof" if isinstance(e,EOFError) else "source_unavailable" if isinstance(e,RuntimeError) else "decoder_error")[:48]
                log.warning("source=%s state=offline category=%s retry_in=%s",self.camera.id,self.error_category,delay)
            finally:
                if adapter: adapter.close()
            if not self.stop_event.is_set(): self.stop_event.wait(delay);delay=min(delay*2,self.camera.reconnect_max_seconds)
        self.status="DISABLED";self.error_category="disabled"

def process(camera,frame,evaluator):
    path=write_preview(camera.id,frame,"synthetic" if camera.simulated else "real",camera.resize_limit)
    camera.last_frame=datetime.fromtimestamp(frame.captured_at,timezone.utc);camera.status="ONLINE"
    context=FrameContext(camera.id,camera.last_frame.isoformat(),frame.width,frame.height,frame.sequence)
    if camera.simulated:
        detections=SIMULATED_DETECTOR.detect(context,camera.scenario)
        detection=detections[0] if detections else None
        if not detection: evaluator.clear(camera.id); return
        with Session.begin() as db:
            rule=db.scalar(select(Rule).where(Rule.camera_id==camera.id,Rule.event_type==detection.event_type,Rule.enabled.is_(True)))
            if rule and evaluator.accepts(camera,rule): persist_detection(db,camera,frame,path,detection,rule)
        return
    with Session() as db:
        rules=db.scalars(select(Rule).where(Rule.camera_id==camera.id,Rule.enabled.is_(True))).all()
        selected=sorted({module for rule in rules for module in (rule.config or {}).get("modules", [])})
    # A module load or inference error is contained to this module and frame.
    for module_id in selected:
        try:
            package=hub.activate(module_id)
            report_worker_status(package)
            if package.status not in ("READY","RUNNING"): continue
            observations=hub.detect(module_id,frame.image,f"live-{camera.id}",camera.id)
            report_worker_status(package)
            present={item["label"] for item in observations}
            for scenario_id,scenario in package.scenarios.items():
                required=scenario.get("required_classes",[])
                if scenario.get("class_mode","any")=="all" and not set(required)<=present: continue
                for observation in observations:
                    if observation["label"] not in required: continue
                    event_type=scenario["event_type"]
                    rule=next((r for r in rules if r.event_type==event_type),None)
                    if not rule: continue
                    # Untracked boxes cannot drive entry/crossing/dwell; they would share one state key.
                    if needs_track(event_type,getattr(package,"tracker",None) is not None,observation["track_id"]): continue
                    track_id=str(observation["track_id"] if observation["track_id"] is not None else f"det-{observation['class_id']}")
                    defaults=package.scenario_defaults
                    if defaults.get("anchor","bottom_center")=="center":anchor=((observation["xyxy"][0]+observation["xyxy"][2])/2/frame.width,(observation["xyxy"][1]+observation["xyxy"][3])/2/frame.height)
                    else:anchor=((observation["xyxy"][0]+observation["xyxy"][2])/2/frame.width,observation["xyxy"][3]/frame.height)
                    minimum=float((rule.config or {}).get("minimum_observation_seconds",rule.min_duration))
                    event_time=time.monotonic()
                    zone=rule.zone.get("points") if rule.zone and event_type in ("ZONE_ENTRY","DWELL") else None
                    line=(rule.config or {}).get("line") if event_type=="LINE_CROSSING" else None
                    state=evaluator.scenario(camera.id,module_id,scenario_id,float(scenario.get("disappearance_grace_seconds",defaults.get("disappearance_grace_seconds",1))),float(scenario.get("cooldown_seconds",defaults.get("cooldown_seconds",10))))
                    hysteresis=float(scenario.get("hysteresis_pixels",0))/max(frame.width,frame.height)
                    dwell=scenario.get("dwell_seconds",minimum) if event_type in ("DWELL","SMOKE_DETECTED","FIRE_DETECTED","SMOKE_FIRE","PERSON_DETECTED","VEHICLE_DETECTED") else None
                    candidates=state.update(track_id,anchor,event_time,zone=zone,line=line,direction=(rule.config or {}).get("direction",scenario.get("direction","A_TO_B")),dwell_seconds=dwell,minimum=minimum,event_prefix=f"{module_id}:{scenario_id}",hysteresis=hysteresis)
                    # A DWELL rule with a zone also yields an ENTRY candidate after `minimum` seconds;
                    # only the kind that matches this rule may open an incident.
                    confirmed=any(keep_candidate(event_type,c) for c in candidates)
                    if not confirmed: continue
                    detection=DetectionResult(camera.id,camera.last_frame.isoformat(),frame.width,frame.height,event_type,
                        {"type":"rectangle","xyxy":observation["xyxy"],"coordinate_space":"original_pixels"},
                        observation["track_id"],
                        f"vigilon.ultralytics.{module_id}",str(package.manifest["package_version"]),observation["score"],
                        {"label":observation["label"],"class_id":observation["class_id"],"module_id":module_id,"scenario_id":scenario_id},False)
                    with Session.begin() as db:
                        db_rule=db.get(Rule,rule.id)
                        if db_rule: persist_detection(db,camera,frame,path,detection,db_rule)
        except Exception as exc:
            log.exception("source=%s module=%s inference_failure=%s",camera.id,module_id,type(exc).__name__)

def config_key(c): return (c.source_type,c.connection,c.secret,c.scenario,c.simulated,c.processing_fps,c.resize_limit,c.timeout_seconds,c.reconnect_min_seconds,c.reconnect_max_seconds)
def process_hub_reload_requests():
    for request in HANDOFF_DIR.glob("reload-*.json"):
        module_id=request.stem.removeprefix("reload-")
        requested_at=None
        try:
            try:requested_at=json.loads(request.read_text(encoding="utf-8")).get("requested_at")
            except (OSError,ValueError):requested_at=None
            package=hub.reload(module_id)
            report_worker_status(package)
            report_operation(module_id,"last_reload",package.status,package.error,requested_at)
            log.info("module_reload module=%s status=%s error=%s",module_id,package.status,package.error or "none")
        except Exception as exc:
            report_worker_status(None,module_id,"ERROR",str(exc)[:300])
            report_operation(module_id,"last_reload","ERROR",str(exc)[:300],requested_at)
            log.exception("module_reload module=%s status=ERROR category=%s",module_id,type(exc).__name__)
        finally:
            request.unlink(missing_ok=True)
def main():
    from .file_jobs import FileJobRunner
    acquire_lease();runners={};keys={};evaluator=TemporalRuleEvaluator();file_jobs=FileJobRunner();file_jobs.start()
    log.info("worker_started owner=%s",OWNER)
    try:
        while True:
            process_hub_reload_requests()
            with Session() as db: cameras=db.scalars(select(Camera).where(Camera.enabled.is_(True))).all()
            active={c.id for c in cameras}
            for camera_id in set(runners)-active:
                runners.pop(camera_id).stop();keys.pop(camera_id,None)
                with Session.begin() as db:db.execute(update(Camera).where(Camera.id==camera_id).values(status="DISABLED",error_category="disabled"))
            for camera in cameras:
                key=config_key(camera)
                if camera.id in runners and keys[camera.id]!=key:
                    runners.pop(camera.id).stop()
                    evaluator.clear(camera.id)
                if camera.id not in runners:
                    runner=SourceRunner(camera);runners[camera.id]=runner;keys[camera.id]=key;runner.start()
                runner=runners[camera.id]
                try:frame=runner.frames.get_nowait()
                except queue.Empty:frame=None
                if frame:
                    try:process(camera,frame,evaluator)
                    except Exception as e:log.exception("source=%s processing_error category=%s",camera.id,type(e).__name__)
                with Session.begin() as db:
                    db.execute(update(Camera).where(Camera.id==camera.id).values(status=runner.status,error_category=runner.error_category,last_frame=runner.last_frame,reconnects=runner.reconnects,processed=runner.processed,dropped=runner.dropped))
            with Session.begin() as db:db.execute(update(Lease).where(Lease.id==1,Lease.owner==OWNER).values(expires=now()+timedelta(seconds=15)))
            time.sleep(.1)
    except KeyboardInterrupt:log.info("worker_stopping")
    finally:
        for runner in runners.values():runner.stop()
        for runner in runners.values():runner.join()
        file_jobs_stopped=file_jobs.close()
        with Session.begin() as db:db.execute(update(Lease).where(Lease.id==1,Lease.owner==OWNER).values(expires=now(),owner=""))
        if file_jobs_stopped:hub.close()
        else:log.error("file_job_shutdown_timeout worker_exit=runtime_left_for_process_cleanup")

if __name__=="__main__":main()
