import json, logging, os, queue, socket, threading, time, uuid
import cv2
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import select, update
from .adapters import OpenCVAdapter, SyntheticAdapter
from .core import HANDOFF_DIR, MEDIA_DIR, fernet
from .db import Camera, Lease, Rule, Session, now
from .detection import FrameContext, SimulatedScenarioPlugin
from .rules import TemporalRuleEvaluator
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

def write_preview(camera_id,frame,scenario,resize_limit):
    path=HANDOFF_DIR/f"camera-{camera_id}-{frame.sequence}.jpg"; tmp=path.with_suffix(".tmp")
    if hasattr(frame.image,"save"): image=frame.image
    else:
        from PIL import Image
        image=Image.fromarray(cv2.cvtColor(frame.image,cv2.COLOR_BGR2RGB))
    image.thumbnail((resize_limit,resize_limit)); image.save(tmp,format="JPEG",quality=82); tmp.replace(path)
    meta={"captured_at":datetime.fromtimestamp(frame.captured_at,timezone.utc).isoformat(),"width":image.width,"height":image.height,"sequence":frame.sequence,"simulated":scenario!="real","file":path.name}
    manifest=HANDOFF_DIR/f"camera-{camera_id}.json"
    temp=manifest.with_suffix(".tmp");temp.write_text(json.dumps(meta));temp.replace(manifest)
    # Retain a tiny handoff window so an API response that just read the previous
    # manifest can still open its JPEG while the next frame arrives.
    candidates=sorted(HANDOFF_DIR.glob(f"camera-{camera_id}-*.jpg"),key=lambda f:f.stat().st_mtime,reverse=True)
    for old in candidates[3:]:old.unlink(missing_ok=True)
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
                while not self.stop_event.is_set():
                    started=time.monotonic();frame=adapter.read()
                    if frame is None: raise EOFError("source_eof")
                    self.last_frame=datetime.fromtimestamp(frame.captured_at,timezone.utc);self.processed+=1
                    try: self.frames.put_nowait(frame)
                    except queue.Full:
                        try: self.frames.get_nowait()
                        except queue.Empty: pass
                        self.dropped+=1
                        try: self.frames.put_nowait(frame)
                        except queue.Full: self.dropped+=1
                    pace=max(0,1/max(1,self.camera.processing_fps or 2)-(time.monotonic()-started))
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
    detections=SIMULATED_DETECTOR.detect(context,camera.scenario) if camera.simulated else []
    detection=detections[0] if detections else None
    if not detection:
        evaluator.clear(camera.id)
        return
    with Session.begin() as db:
        rule=db.scalar(select(Rule).where(Rule.camera_id==camera.id,Rule.event_type==detection.event_type,Rule.enabled.is_(True)))
        if not rule:
            evaluator.clear(camera.id)
            return
        if not evaluator.accepts(camera,rule):return
        persist_detection(db,camera,frame,path,detection,rule)

def config_key(c): return (c.source_type,c.connection,c.secret,c.scenario,c.simulated,c.processing_fps,c.resize_limit,c.timeout_seconds,c.reconnect_min_seconds,c.reconnect_max_seconds)
def main():
    acquire_lease();runners={};keys={};evaluator=TemporalRuleEvaluator()
    log.info("worker_started owner=%s",OWNER)
    try:
        while True:
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
        with Session.begin() as db:db.execute(update(Lease).where(Lease.id==1,Lease.owner==OWNER).values(expires=now(),owner=""))

if __name__=="__main__":main()
