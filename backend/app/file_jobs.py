"""Bounded, persistent FILE analysis jobs in the shared handoff volume."""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .ai_hub import BUILTINS, hub, report_worker_status
from .core import HANDOFF_DIR, MEDIA_DIR
from .adapters import OpenCVAdapter
from .scenario_rules import ScenarioEvaluator

JOB_DIR=HANDOFF_DIR/"file-jobs"
JOB_DIR.mkdir(parents=True,exist_ok=True)


def _job_path(job_id:str)->Path:
    if not job_id or any(ch not in "0123456789abcdef-" for ch in job_id):raise ValueError("Invalid job ID")
    return JOB_DIR/f"{job_id}.json"


def result_path(job_id:str)->Path:
    _job_path(job_id)
    return JOB_DIR/f"{job_id}-results.json"


def _write(path:Path,value:dict):
    temp=path.with_suffix(".tmp");temp.write_text(json.dumps(value,indent=2),encoding="utf-8");temp.replace(path)


def read_job(job_id:str)->dict|None:
    path=_job_path(job_id)
    if not path.is_file():return None
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):return None


def list_jobs(limit:int=10000)->list[dict]:
    rows=[]
    for path in sorted(JOB_DIR.glob("*.json"),key=lambda x:x.stat().st_mtime,reverse=True)[:limit]:
        try:rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError,ValueError):continue
    return rows


def create_job(input_path:str,modules:list[str],scenario_config:dict|None=None)->dict:
    jobs=list_jobs()
    if sum(row["status"] in ("QUEUED","RUNNING") for row in jobs)>=20:raise ValueError("FILE job queue is full (maximum 20 queued/running jobs)")
    if len(jobs)>=100:raise ValueError("FILE job history is full (100 jobs); delete completed jobs before adding more")
    root=MEDIA_DIR.resolve();candidate=Path(input_path)
    candidate=(candidate if candidate.is_absolute() else root/candidate).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():raise ValueError("Input video must be an existing file beneath VIGILON_MEDIA_DIR")
    if not modules or len(set(modules))!=len(modules) or any(m not in BUILTINS for m in modules):raise ValueError("Select one or both supported model modules")
    overrides=scenario_config or {}
    if not isinstance(overrides,dict):raise ValueError("scenario_config must be an object")
    for value in overrides.values():
        if not isinstance(value,dict) or set(value)-{"zone","line","direction","minimum_observation_seconds","dwell_seconds","hysteresis_pixels"}:raise ValueError("Unsupported scenario configuration field")
        if any(key in value and (isinstance(value[key],bool) or not isinstance(value[key],(int,float)) or not math.isfinite(value[key]) or value[key]<0) for key in ("minimum_observation_seconds","dwell_seconds","hysteresis_pixels")):raise ValueError("Scenario timing and hysteresis values must be finite nonnegative numbers")
        if value.get("direction","A_TO_B") not in ("A_TO_B","B_TO_A"):raise ValueError("direction must be A_TO_B or B_TO_A")
        if "line" in value:
            line=value["line"]
            if not isinstance(line,list) or len(line)!=2 or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(x,(int,float)) or not 0<=x<=1 for x in p) for p in line) or line[0]==line[1]:raise ValueError("line needs two distinct normalized endpoints")
        if "zone" in value:
            zone=value["zone"];points=zone.get("points") if isinstance(zone,dict) else None
            if not isinstance(points,list) or len(points)<3 or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(x,(int,float)) or not 0<=x<=1 for x in p) for p in points):raise ValueError("zone needs normalized polygon points")
            if abs(sum(points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points)))/2)==0:raise ValueError("zone must have nonzero area")
    job_id=uuid.uuid4().hex
    row={"job_id":job_id,"input_name":candidate.name,"input_path":str(candidate),"modules":modules,"scenario_config":overrides,
         "status":"QUEUED","progress_frames":0,"total_frames":None,"events":0,"created_at":datetime.now(timezone.utc).isoformat(),
         "started_at":None,"completed_at":None,"error":None,"result_file":str(result_path(job_id).resolve())}
    _write(_job_path(job_id),row)
    _write(result_path(job_id),{"job_id":job_id,"status":"QUEUED","timestamp_origin":"media","modules":modules,"frames":0,"events":[],"events_truncated":False})
    return row


def cancel_job(job_id:str)->dict|None:
    row=read_job(job_id)
    if not row:return None
    if row["status"]=="QUEUED":
        row["status"]="CANCELLED";row["completed_at"]=datetime.now(timezone.utc).isoformat();_write(_job_path(job_id),row)
        result=result_path(job_id)
        if result.is_file():body=json.loads(result.read_text(encoding="utf-8"));body.update(status="CANCELLED",completed_at=row["completed_at"]);_write(result,body)
    elif row["status"]=="RUNNING":(_job_path(job_id).with_suffix(".cancel")).write_text("cancel",encoding="utf-8")
    return row


def delete_job(job_id:str)->bool:
    row=read_job(job_id)
    if not row:return False
    if row["status"] in ("QUEUED","RUNNING"):raise ValueError("Cancel the active FILE job before deleting it")
    result_path(job_id).unlink(missing_ok=True);_job_path(job_id).unlink(missing_ok=True);_job_path(job_id).with_suffix(".cancel").unlink(missing_ok=True)
    return True


def _process_module_frame(module,package,frame,media_time,job_id,states,overrides,result):
    observations=hub.detect(module,frame.image,job_id,0);report_worker_status(package);present={x["label"] for x in observations}
    for scenario_id,scenario in package.scenarios.items():
        required=scenario.get("required_classes",[])
        if scenario.get("class_mode","any")=="all" and not set(required)<=present:continue
        config={**scenario,**overrides.get(scenario_id,{})};defaults=package.scenario_defaults
        state=states.setdefault((module,scenario_id),ScenarioEvaluator(float(config.get("disappearance_grace_seconds",defaults.get("disappearance_grace_seconds",1))),float(config.get("cooldown_seconds",defaults.get("cooldown_seconds",10)))))
        for detection in observations:
            if detection["label"] not in required:continue
            box=detection["xyxy"]
            anchor=((box[0]+box[2])/2/frame.width,(box[1]+box[3])/2/frame.height) if defaults.get("anchor")=="center" else ((box[0]+box[2])/2/frame.width,box[3]/frame.height)
            minimum=float(config.get("minimum_observation_seconds",defaults.get("minimum_observation_seconds",0)))
            candidates=state.update(str(detection["track_id"] if detection["track_id"] is not None else detection["class_id"]),anchor,media_time,
                zone=(config.get("zone") or {}).get("points"),line=config.get("line"),direction=config.get("direction","A_TO_B"),dwell_seconds=config.get("dwell_seconds",minimum),
                minimum=minimum,event_prefix=f"{module}:{scenario_id}",hysteresis=float(config.get("hysteresis_pixels",0))/max(frame.width,frame.height))
            for event in candidates:
                if len(result["events"])<10000:result["events"].append({"media_time":media_time,"frame_id":frame.sequence,"event_type":config["event_type"],"scenario_id":scenario_id,"candidate":event,"detection":detection,"simulated":False})
                else:result["events_truncated"]=True


def _run_job(job_id:str,stop:threading.Event):
    path=_job_path(job_id);row=read_job(job_id)
    if not row or row["status"]!="QUEUED":return
    row.update(status="RUNNING",started_at=datetime.now(timezone.utc).isoformat());_write(path,row)
    result={"job_id":job_id,"status":"RUNNING","timestamp_origin":"media","modules":row["modules"],"frames":0,"events":[],"events_truncated":False}
    output_path=result_path(job_id);_write(output_path,result)
    source=None;states={};cancel_path=path.with_suffix(".cancel");module_failures={};active=[]
    try:
        for module in row["modules"]:
            try:
                package=hub.activate(module)
                report_worker_status(package)
                if package.status not in ("READY","RUNNING"):raise RuntimeError(f"{package.status}: {package.error or 'unavailable'}")
                active.append(module)
            except Exception as exc:module_failures[module]=f"{type(exc).__name__}: {exc}"
        known={name for module in active for name in hub.packages[module].scenarios}
        unknown=set(row["scenario_config"])-known
        if unknown:raise ValueError("Unknown scenario IDs: "+", ".join(sorted(unknown)))
        if not active:raise RuntimeError("No selected module is runtime-ready: "+json.dumps(module_failures))
        source=OpenCVAdapter("file",row["input_path"],MEDIA_DIR)
        if not source.open():raise RuntimeError("video_decode_failed")
        raw_total=float(source.cap.get(7) or 0)
        result["total_frames"]=int(raw_total) if math.isfinite(raw_total) and raw_total>0 else None
        while True:
            if stop.is_set() or cancel_path.exists():result["status"]="CANCELLED";break
            frame=source.read()
            if frame is None:break
            result["frames"]+=1
            media_time=frame.media_time if frame.media_time is not None else (frame.sequence-1)/max(source.fps,1)
            for module in active:
                if module in module_failures:continue
                try:_process_module_frame(module,hub.packages[module],frame,media_time,job_id,states,row["scenario_config"],result)
                except Exception as exc:module_failures[module]=f"{type(exc).__name__}: {exc}"
            if result["frames"]%10==0:
                _write(output_path,result);current=read_job(job_id) or row
                current.update(status="RUNNING",progress_frames=result["frames"],total_frames=result["total_frames"],events=len(result["events"]));_write(path,current)
        if result["status"]=="RUNNING":
            if result["frames"]==0:raise RuntimeError("no_decodable_frames")
            if module_failures:raise RuntimeError("One or more modules failed: "+json.dumps(module_failures))
            result["status"]="COMPLETED"
    except Exception as exc:
        result.update(status="FAILED",error=f"{type(exc).__name__}: {exc}",module_failures=module_failures)
    finally:
        if source:source.close()
        result["completed_at"]=datetime.now(timezone.utc).isoformat();_write(output_path,result)
        current=read_job(job_id) or row
        current.update(status=result["status"],progress_frames=result["frames"],total_frames=result.get("total_frames"),events=len(result["events"]),error=result.get("error"),completed_at=result["completed_at"])
        _write(path,current);cancel_path.unlink(missing_ok=True);hub.close_session(job_id)


class FileJobRunner:
    """One background FILE job at a time; the existing LIVE worker loop continues independently."""
    def __init__(self):self.stop_event=threading.Event();self.thread=threading.Thread(target=self._loop,name="file-job-runner",daemon=True)
    def start(self):
        for row in list_jobs():
            if row["status"]=="RUNNING":
                row.update(status="FAILED",error="worker_interrupted",completed_at=datetime.now(timezone.utc).isoformat());_write(_job_path(row["job_id"]),row)
                result=result_path(row["job_id"])
                if result.is_file():body=json.loads(result.read_text(encoding="utf-8"));body.update(status="FAILED",error="worker_interrupted",completed_at=row["completed_at"]);_write(result,body)
        self.thread.start()
    def _loop(self):
        while not self.stop_event.is_set():
            row=next((item for item in reversed(list_jobs()) if item["status"]=="QUEUED"),None)
            if row:_run_job(row["job_id"],self.stop_event)
            else:self.stop_event.wait(.5)
    def close(self):self.stop_event.set();self.thread.join(10);return not self.thread.is_alive()
