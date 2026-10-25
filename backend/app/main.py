import base64, hashlib, hmac, json, logging, mimetypes, os, re, secrets, threading, time, uuid, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response, Depends, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from argon2 import PasswordHasher
from .core import HANDOFF_DIR, EVIDENCE_DIR, SECRET_KEY, fernet, MEDIA_DIR, MEDIA_ROOTS, IMPORT_DIR, FLOOR_PLAN_DIR
from .db import Session, User, Role, Camera, Rule, Incident, IncidentStatus, Transition, Notification, Lease, FloorPlan, CameraPlacement, now
from .ai_hub import hub, PackageError, BUILTINS, report_operation

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s %(levelname)s %(name)s %(message)s")
log=logging.getLogger("vigilon.api"); hasher=PasswordHasher(); app=FastAPI(title="Vigilon",version="0.1.0",description="Authorized existing-CCTV incident review. Simulated demo events are labeled.")
PROBE_LIMIT=threading.BoundedSemaphore(2)
FRONTEND=Path(__file__).resolve().parents[2]/"frontend"
app.mount("/assets",StaticFiles(directory=FRONTEND),name="assets")

def token(uid):
    body=base64.urlsafe_b64encode(json.dumps({"uid":uid,"exp":int(time.time())+8*3600},separators=(",",":")).encode()).decode().rstrip("=")
    sig=base64.urlsafe_b64encode(hmac.new(SECRET_KEY.encode(),body.encode(),hashlib.sha256).digest()).decode().rstrip("=")
    return body+"."+sig
def current_user(request:Request):
    val=request.cookies.get("vigilon_session","")
    try:
        body,sig=val.split(".",1); expected=base64.urlsafe_b64encode(hmac.new(SECRET_KEY.encode(),body.encode(),hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(sig,expected): raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(body+"="*((4-len(body)%4)%4)))
        if data["exp"]<time.time(): raise ValueError()
        with Session() as db: user=db.get(User,data["uid"]); role=user.role if user and user.active else None; uid=user.id if user and user.active else None; name=user.username if user and user.active else None
        if not role: raise ValueError()
        return {"id":uid,"username":name,"role":role}
    except Exception: raise HTTPException(401,"Authentication required")
def require_admin(user=Depends(current_user)):
    if user["role"]!=Role.ADMIN: raise HTTPException(403,"Administrator role required")
    return user
def utc_iso(value):
    if value is None:return None
    if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
def csrf(request:Request):
    if request.method in ("GET","HEAD","OPTIONS"): return
    origin=request.headers.get("origin")
    if origin and origin.rstrip("/")!=str(request.base_url).rstrip("/"): raise HTTPException(403,"Cross-origin request denied")

class Login(BaseModel): username:str=Field(min_length=1,max_length=80); password:str=Field(min_length=1,max_length=256)
class CameraIn(BaseModel):
    name:str=Field(min_length=1,max_length=120); location:str=Field(default="",max_length=160); source_type:str="synthetic"; connection:str=""; clear_connection:bool=False; enabled:bool=True; scenario:str="normal"; processing_fps:int=Field(default=2,ge=1,le=15); resize_limit:int=Field(default=1280,ge=160,le=3840); timeout_seconds:int=Field(default=5,ge=1,le=30); reconnect_min_seconds:int=Field(default=1,ge=1,le=30); reconnect_max_seconds:int=Field(default=30,ge=2,le=300)
    @model_validator(mode="after")
    def reconnect_bounds(self):
        if self.reconnect_min_seconds>self.reconnect_max_seconds:raise ValueError("Reconnect minimum must not exceed maximum")
        return self
class RuleIn(BaseModel): event_type:str; enabled:bool=True; min_duration:int=Field(default=2,ge=1,le=3600); cooldown:int=Field(default=30,ge=0,le=86400); zone:dict={}; timezone:str="Asia/Bangkok"; line:list[list[float]]|None=None; direction:str="A_TO_B"
class ActionIn(BaseModel): status:IncidentStatus; note:str=Field(default="",max_length=500)
class UserIn(BaseModel): username:str=Field(min_length=3,max_length=80); password:str=Field(min_length=12,max_length=256); role:Role
class FileJobIn(BaseModel): input_path:str=Field(min_length=1,max_length=2048); modules:list[str]=Field(min_length=1,max_length=2); scenario_config:dict={}
class ConnectionTestIn(BaseModel): source_type:str; connection:str=Field(min_length=1,max_length=2048); timeout_seconds:int=Field(default=5,ge=1,le=10)
class FloorPlanIn(BaseModel):
    name:str=Field(min_length=1,max_length=120); location_label:str=Field(default="",max_length=160)
    @model_validator(mode="after")
    def trim_name(self):
        self.name=self.name.strip();self.location_label=self.location_label.strip()
        if not self.name:raise ValueError("Plan name cannot be blank")
        return self
class PlacementIn(BaseModel):
    camera_id:int=Field(gt=0); x:float; y:float
    @model_validator(mode="after")
    def finite_coordinates(self):
        if not math.isfinite(self.x) or not math.isfinite(self.y) or not 0<=self.x<=1 or not 0<=self.y<=1:raise HTTPException(422,"Placement coordinates must be finite normalized values in [0,1]")
        return self
class PlacementsIn(BaseModel): revision:int=Field(ge=1); placements:list[PlacementIn]=Field(max_length=500)
class CameraContextIn(BaseModel): manufacturer:str|None=Field(default=None,max_length=120); model:str|None=Field(default=None,max_length=120); specifications:str|None=Field(default=None,max_length=500); responsible_contact:str|None=Field(default=None,max_length=200); response_notes:str|None=Field(default=None,max_length=1000)

@app.middleware("http")
async def security(request,call_next):
    try: csrf(request); response=await call_next(request)
    except HTTPException as e: return Response(e.detail,status_code=e.status_code)
    response.headers["X-Content-Type-Options"]="nosniff"; response.headers["Referrer-Policy"]="no-referrer"; response.headers["X-Frame-Options"]="DENY"
    # Frontend assets revalidate on every load (cheap 304 via ETag), so merged feature branches never run stale cached JS/CSS
    if request.url.path.startswith("/assets/"): response.headers["Cache-Control"]="no-cache"
    return response

@app.get("/",response_class=HTMLResponse)
def home(): return inject_feature_scripts((FRONTEND/"index.html").read_text(encoding="utf-8"),FRONTEND)  # adds feature scripts not listed in index.html
@app.get("/api/health")
def health(): return {"status":"ok","database":"configured","simulation":"SIMULATED scenarios only"}
@app.get("/api/ai/modules")
def ai_modules(user=Depends(current_user)):
    """Authenticated model readiness catalog; metadata readiness is not runtime readiness."""
    return {"hub_status":"HUB_INFRA_READY","real_model_validated":False,"camera_validated":False,"modules":hub.list()}

@app.post("/api/cameras/test-connection")
def test_camera_connection(data:ConnectionTestIn,user=Depends(require_admin)):
    """Bounded probe using the exact configured address and the existing source policy."""
    if data.source_type not in ("rtsp","file","webcam"):
        raise HTTPException(422,"Connectivity test supports RTSP/RTSPS, local media and local webcams only")
    from .adapters import OpenCVAdapter
    from .webcam_adapter import WebcamAdapter
    if not PROBE_LIMIT.acquire(blocking=False):raise HTTPException(429,"Two bounded source probes are already running")
    outcome=[]
    def probe():
        adapter=None
        try:
            adapter=WebcamAdapter(data.connection,timeout=data.timeout_seconds) if data.source_type=="webcam" else OpenCVAdapter(data.source_type,data.connection,MEDIA_ROOTS,timeout=data.timeout_seconds)
            if not adapter.open():outcome.append({"reachable":False,"message":"Source did not open within the configured timeout."});return
            frame=adapter.read();outcome.append({"reachable":bool(frame),"message":"Connected and decoded a frame." if frame else "Connected, but no frame was decoded."})
        except Exception as exc:
            category=str(exc) if isinstance(exc,ValueError) else type(exc).__name__;outcome.append({"reachable":False,"message":category[:120]})
        finally:
            if adapter:adapter.close()
            PROBE_LIMIT.release()
    thread=threading.Thread(target=probe,name="bounded-source-probe",daemon=True);thread.start();thread.join(data.timeout_seconds+2)
    if thread.is_alive():return {"reachable":False,"message":"Probe exceeded the configured time limit and is closing."}
    return outcome[0] if outcome else {"reachable":False,"message":"Probe ended without a result."}

@app.post("/api/ai/imports")
async def import_video(request:Request,user=Depends(require_admin)):
    """Stream a bounded upload to the private import root and verify OpenCV decoding."""
    from urllib.parse import unquote
    maximum=512*1024*1024
    existing=list(IMPORT_DIR.glob("*")) if IMPORT_DIR.exists() else []
    if len(existing)>=100 or sum(item.stat().st_size for item in existing if item.is_file())+maximum>5*1024*1024*1024:raise HTTPException(409,"Private video import storage is full; remove imported videos before uploading")
    length=request.headers.get("content-length")
    if length and (not length.isdigit() or int(length)>maximum):raise HTTPException(413,"Video exceeds the 512 MiB upload limit")
    raw_name=unquote(request.headers.get("x-file-name","video"))
    suffix=Path(raw_name).suffix.lower()
    if suffix not in {".mp4",".mov",".mkv",".avi",".webm",".m4v"}:raise HTTPException(415,"Supported video extensions: MP4, MOV, MKV, AVI, WEBM, M4V")
    IMPORT_DIR.mkdir(parents=True,exist_ok=True);target=IMPORT_DIR/f"{uuid.uuid4().hex}{suffix}"
    total=0
    try:
        with target.open("xb") as stream:
            async for chunk in request.stream():
                total+=len(chunk)
                if total>maximum:raise HTTPException(413,"Video exceeds the 512 MiB upload limit")
                stream.write(chunk)
        if total==0:raise HTTPException(400,"Uploaded video is empty")
        import cv2, math
        capture=cv2.VideoCapture(str(target),cv2.CAP_FFMPEG,[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,5000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,5000])
        try:
            opened=capture.isOpened();ok,frame=capture.read() if opened else (False,None)
            if not ok or frame is None:raise HTTPException(415,"Video could not be decoded by the configured OpenCV build")
            fps=float(capture.get(cv2.CAP_PROP_FPS) or 0);count=float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            width,height=frame.shape[1],frame.shape[0];duration=count/fps if fps>0 and math.isfinite(count) and count>0 else None
            preview_path=IMPORT_DIR/f"{target.stem}.jpg"
            if not cv2.imwrite(str(preview_path),frame):raise HTTPException(500,"Could not write private preview frame")
        finally:capture.release()
        return {"import_id":target.stem,"name":Path(raw_name).name[:200],"input_path":f"imports/{target.name}","bytes":total,"duration_seconds":duration,"width":width,"height":height,"browser_playback_mime":{ ".mp4":"video/mp4",".m4v":"video/mp4",".webm":"video/webm",".ogg":"video/ogg"}.get(suffix)}
    except Exception:
        target.unlink(missing_ok=True);(IMPORT_DIR/f"{target.stem}.jpg").unlink(missing_ok=True)
        raise
def file_job_public(job):
    public={key:job.get(key) for key in ("job_id","input_name","modules","package_versions","simulated_demo","status","progress_frames","progress_media_time","total_frames","duration_seconds","fps","events","created_at","started_at","completed_at","error")}
    if job.get("job_id"):
        from .core import HANDOFF_DIR
        public["cancel_requested"]=(HANDOFF_DIR/"file-jobs"/f"{job['job_id']}.cancel").exists()
    return public
@app.post("/api/ai/jobs")
def create_ai_job(data:FileJobIn,user=Depends(require_admin)):
    from .file_jobs import create_job
    try:return file_job_public(create_job(data.input_path,data.modules,data.scenario_config))
    except ValueError as exc:raise HTTPException(422,str(exc))
class SimulatedDemoJobIn(BaseModel):
    scenario:str=Field(pattern="^(obstruction|person_down|smoke_fire)$")
@app.post("/api/ai/demo-jobs")
def create_simulated_demo_job(data:SimulatedDemoJobIn,user=Depends(require_admin)):
    """Opt-in generated fixture only; never runs simulated observations on uploaded footage."""
    from .adapters import SyntheticAdapter
    from .file_jobs import create_job
    import cv2
    IMPORT_DIR.mkdir(parents=True,exist_ok=True)
    target=IMPORT_DIR/f"visor-simulated-{uuid.uuid4().hex}.avi"
    source=SyntheticAdapter(data.scenario);writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*"MJPG"),4.0,(960,540))
    try:
        if not writer.isOpened():raise HTTPException(503,"OpenCV cannot create the generated AVI demo fixture")
        source.open()
        for _ in range(12):
            frame=source.read();writer.write(cv2.cvtColor(__import__("numpy").array(frame.image),cv2.COLOR_RGB2BGR))
        writer.release()
        job=create_job(f"imports/{target.name}",[],simulated_scenario=data.scenario)
        job["generated_demo"]=True;job["generated_media_path"]=str(target.resolve())
        from .file_jobs import _job_path,_write
        _write(_job_path(job["job_id"]),job)
        return file_job_public(job)
    except HTTPException:
        target.unlink(missing_ok=True);raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        if isinstance(exc,ValueError):raise HTTPException(422,str(exc))
        raise HTTPException(503,f"Could not create generated demo job: {type(exc).__name__}")
    finally:
        writer.release();source.close()
@app.get("/api/ai/jobs")
def list_ai_jobs(user=Depends(current_user)):
    from .file_jobs import list_jobs
    return [file_job_public(x) for x in list_jobs(100)]
@app.get("/api/ai/jobs/{job_id}")
def get_ai_job(job_id:str,user=Depends(current_user)):
    from .file_jobs import read_job
    row=read_job(job_id)
    if not row:raise HTTPException(404,"FILE job not found")
    return file_job_public(row)
@app.post("/api/ai/jobs/{job_id}/cancel")
def cancel_ai_job(job_id:str,user=Depends(require_admin)):
    from .file_jobs import cancel_job,read_job
    row=cancel_job(job_id)
    if not row:raise HTTPException(404,"FILE job not found")
    return file_job_public(read_job(job_id))
@app.delete("/api/ai/jobs/{job_id}",status_code=204)
def delete_ai_job(job_id:str,user=Depends(require_admin)):
    from .file_jobs import delete_job
    try:deleted=delete_job(job_id)
    except ValueError as exc:raise HTTPException(409,str(exc))
    if not deleted:raise HTTPException(404,"FILE job not found")
@app.get("/api/ai/jobs/{job_id}/results")
def ai_job_results(job_id:str,user=Depends(current_user)):
    from .file_jobs import read_job,result_path
    row=read_job(job_id)
    if not row:raise HTTPException(404,"FILE job not found")
    path=result_path(job_id)
    if not path.is_file():raise HTTPException(404,"Results are not available yet")
    return json.loads(path.read_text(encoding="utf-8"))
@app.get("/api/ai/jobs/{job_id}/media")
def ai_job_media(job_id:str,user=Depends(current_user)):
    from .file_jobs import read_job
    from .core import MEDIA_ROOTS
    row=read_job(job_id)
    if not row:raise HTTPException(404,"FILE job not found")
    path=Path(row["input_path"]).resolve()
    if not any(path.is_relative_to(Path(root).resolve()) for root in MEDIA_ROOTS) or not path.is_file():raise HTTPException(404,"Source media unavailable")
    return FileResponse(path,media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",headers={"Cache-Control":"private, no-store","X-Playback-Note":"Browser codec support depends on the source media format."})
@app.get("/api/ai/imports/{import_id}/media")
def imported_video_media(import_id:str,user=Depends(current_user)):
    if not re.fullmatch(r"[0-9a-f]{32}",import_id):raise HTTPException(404,"Imported media not found")
    paths=[path for path in IMPORT_DIR.glob(import_id+".*") if path.suffix.lower()!=".jpg"]
    if len(paths)!=1 or not paths[0].is_file() or paths[0].resolve().parent!=IMPORT_DIR.resolve():raise HTTPException(404,"Imported media not found")
    return FileResponse(paths[0],media_type=mimetypes.guess_type(paths[0].name)[0] or "application/octet-stream",headers={"Cache-Control":"private, no-store"})
@app.get("/api/ai/imports/{import_id}/frame")
def imported_video_frame(import_id:str,user=Depends(current_user)):
    if not re.fullmatch(r"[0-9a-f]{32}",import_id):raise HTTPException(404,"Imported media not found")
    path=IMPORT_DIR/f"{import_id}.jpg"
    if not path.is_file() or path.resolve().parent!=IMPORT_DIR.resolve():raise HTTPException(404,"Preview frame unavailable")
    return FileResponse(path,media_type="image/jpeg",headers={"Cache-Control":"private, no-store"})
@app.delete("/api/ai/imports/{import_id}",status_code=204)
def delete_imported_video(import_id:str,user=Depends(require_admin)):
    if not re.fullmatch(r"[0-9a-f]{32}",import_id):raise HTTPException(404,"Imported media not found")
    paths=list(IMPORT_DIR.glob(import_id+".*"));video=[path for path in paths if path.suffix.lower()!=".jpg"]
    if len(video)!=1 or video[0].resolve().parent!=IMPORT_DIR.resolve():raise HTTPException(404,"Imported media not found")
    from .file_jobs import list_jobs
    if any(Path(row.get("input_path","")).resolve()==video[0].resolve() for row in list_jobs()):raise HTTPException(409,"This import is referenced by an analysis job. Delete its job history first.")
    for path in paths:
        if path.is_file() and path.resolve().parent==IMPORT_DIR.resolve():path.unlink(missing_ok=True)
@app.post("/api/admin/ai/modules/{module_id}/validate")
def validate_ai_module(module_id:str, data:dict, user=Depends(require_admin)):
    mode=data.get("mode","metadata")
    if mode not in ("metadata","runtime"): raise HTTPException(422,"mode must be metadata or runtime")
    try:
        result=hub.validate(module_id,runtime=mode=="runtime").public();report_operation(module_id,"last_validation",result["status"],result.get("error"));return result
    except PackageError as exc:
        report_operation(module_id,"last_validation",exc.status,str(exc));raise HTTPException(422,{"status":exc.status,"detail":str(exc)})
@app.post("/api/admin/ai/modules/{module_id}/reload")
def reload_ai_module(module_id:str,user=Depends(require_admin)):
    if module_id not in BUILTINS: raise HTTPException(404,"Unknown built-in module")
    requested=utc_iso(now());request=HANDOFF_DIR/f"reload-{module_id}.json"; temp=request.with_suffix(".tmp")
    temp.write_text(json.dumps({"module_id":module_id,"requested_at":requested}),encoding="utf-8");temp.replace(request);report_operation(module_id,"last_reload","RELOAD_QUEUED",requested_at=requested)
    return {"module_id":module_id,"status":"RELOAD_QUEUED","requested_at":requested,"runtime":"worker","note":"The worker validates and swaps this package at its next control-loop boundary."}
@app.put("/api/cameras/{camera_id}/modules")
def assign_ai_modules(camera_id:int,data:dict,user=Depends(require_admin)):
    modules=data.get("modules")
    if not isinstance(modules,list) or len(modules)>len(BUILTINS) or len(set(modules))!=len(modules) or any(m not in BUILTINS for m in modules):
        raise HTTPException(422,"modules must be a unique list of built-in module IDs")
    with Session.begin() as db:
        camera=db.get(Camera,camera_id)
        if not camera: raise HTTPException(404,"Camera not found")
        if camera.simulated: raise HTTPException(422,"Real model modules cannot be assigned to simulated sources")
        if camera.source_type not in ("rtsp","webcam"): raise HTTPException(422,"Live module assignment requires an RTSP/RTSPS or local webcam source; use analyze-video for ordered FILE analysis")
        readiness={row["module_id"]:row for row in hub.list()}
        unavailable=[m for m in modules if readiness.get(m,{}).get("status") not in ("READY","RUNNING")]
        if unavailable:raise HTTPException(409,{"detail":"Runtime-ready module required","modules":[readiness.get(m,{"module_id":m,"status":"UNKNOWN"}) for m in unavailable]})
        rules=db.scalars(select(Rule).where(Rule.camera_id==camera_id)).all()
        existing={r.event_type for r in rules}
        for rule in rules: rule.config={**(rule.config or {}),"modules":modules}
        for module in modules:
            try: package=hub.validate(module,runtime=False)
            except PackageError as exc: raise HTTPException(422,str(exc))
            for event_type in package.manifest["supported_events"]:
                if event_type not in existing:
                    scenario=next((value for value in package.scenarios.values() if value["event_type"]==event_type),{})
                    minimum=int(scenario.get("minimum_observation_seconds",package.scenario_defaults.get("minimum_observation_seconds",2)))
                    cooldown=int(scenario.get("cooldown_seconds",package.scenario_defaults.get("cooldown_seconds",30)))
                    db.add(Rule(camera_id=camera_id,event_type=event_type,enabled=True,min_duration=max(1,minimum),cooldown=max(0,cooldown),zone={},config={"module_id":module,"modules":modules}))
                    existing.add(event_type)
        return {"camera_id":camera_id,"modules":modules,"status":"CONFIGURED","note":"Explicitly reload the Hub in the worker after replacing package files."}
@app.get("/api/cameras/{camera_id}/modules")
def camera_ai_modules(camera_id:int,user=Depends(current_user)):
    with Session() as db:
        camera=db.get(Camera,camera_id)
        if not camera: raise HTTPException(404,"Camera not found")
        rules=db.scalars(select(Rule).where(Rule.camera_id==camera_id)).all()
        selected=sorted({module for rule in rules for module in (rule.config or {}).get("modules",[])})
        return {"camera_id":camera_id,"modules":selected,"simulated":camera.simulated}
@app.get("/api/settings/public")
def public_settings(user=Depends(current_user)):return {"display_timezone":os.getenv("VIGILON_TIMEZONE","Asia/Bangkok")}
@app.post("/api/auth/login")
def login(data:Login,response:Response):
    with Session() as db: user=db.scalar(select(User).where(User.username==data.username))
    if not user or not user.active:
        raise HTTPException(401,"Invalid credentials")
    try: hasher.verify(user.password_hash,data.password)
    except Exception: raise HTTPException(401,"Invalid credentials")
    response.set_cookie("vigilon_session",token(user.id),httponly=True,secure=os.getenv("VIGILON_COOKIE_SECURE","false").lower()=="true",samesite="strict",max_age=28800,path="/")
    return {"id":user.id,"username":user.username,"role":user.role.value}
@app.post("/api/auth/logout")
def logout(response:Response,user=Depends(current_user)): response.delete_cookie("vigilon_session",path="/"); return {"ok":True}
@app.get("/api/auth/session")
def session_check(request:Request):
    try:return {**current_user(request),"authenticated":True}
    except HTTPException:return {"authenticated":False}
@app.get("/api/auth/me")
def me(user=Depends(current_user)): return user
@app.get("/api/overview")
def overview(user=Depends(current_user)):
    with Session() as db:
        cameras=db.scalars(select(Camera)).all(); active=db.scalar(select(func.count()).select_from(Incident).where(Incident.status.in_([IncidentStatus.NEW,IncidentStatus.ACKNOWLEDGED]))) or 0
        lease=db.get(Lease,1)
        expiry=lease.expires.replace(tzinfo=timezone.utc) if lease and lease.expires.tzinfo is None else (lease.expires if lease else None)
        worker="ONLINE" if expiry and expiry>now() else "OFFLINE"
        from .file_jobs import list_jobs
        jobs=list_jobs(100)
        return {"worker":worker,"cameras":[camera_dict(x) for x in cameras],"active_incidents":active,
                "incident_counts":{status.value:db.scalar(select(func.count()).select_from(Incident).where(Incident.status==status)) or 0 for status in IncidentStatus},
                "source_counts":{"online":sum(c.enabled and c.status=="ONLINE" for c in cameras),"offline":sum(c.enabled and c.status!="ONLINE" for c in cameras),"disabled":sum(not c.enabled for c in cameras)},
                "recent_incidents":[incident_dict(db,x) for x in db.scalars(select(Incident).order_by(Incident.last_seen.desc()).limit(5))],
                "jobs":{"running":sum(x["status"]=="RUNNING" for x in jobs),"queued":sum(x["status"]=="QUEUED" for x in jobs),"completed":sum(x["status"]=="COMPLETED" for x in jobs),"failed":sum(x["status"] in ("FAILED","PARTIAL") for x in jobs)},"modules":hub.list()}
def camera_dict(c): return {"id":c.id,"name":c.name,"location":c.location,"source_type":c.source_type,"enabled":c.enabled,"simulated":c.simulated,"scenario":c.scenario if c.simulated else None,"processing_fps":c.processing_fps,"resize_limit":c.resize_limit,"timeout_seconds":c.timeout_seconds,"reconnect_min_seconds":c.reconnect_min_seconds,"reconnect_max_seconds":c.reconnect_max_seconds,"status":c.status,"error_category":c.error_category,"preview_stale":not c.last_frame or (now()-c.last_frame.replace(tzinfo=timezone.utc) if c.last_frame.tzinfo is None else now()-c.last_frame).total_seconds()>8,"last_frame":utc_iso(c.last_frame),"reconnects":c.reconnects,"processed":c.processed,"dropped":c.dropped,"manufacturer":c.manufacturer,"model":c.model,"specifications":c.specifications,"responsible_contact":c.responsible_contact,"response_notes":c.response_notes}

def floor_plan_dict(db, plan):
    placements=db.scalars(select(CameraPlacement).where(CameraPlacement.plan_id==plan.id)).all()
    return {"id":plan.id,"name":plan.name,"location_label":plan.location_label,"has_image":bool(plan.image_name),"image_width":plan.image_width,"image_height":plan.image_height,"revision":plan.revision,"placements":[{"camera_id":p.camera_id,"x":p.x,"y":p.y} for p in placements]}

@app.get("/api/plans")
def list_floor_plans(user=Depends(current_user)):
    with Session() as db:return [floor_plan_dict(db,p) for p in db.scalars(select(FloorPlan).order_by(FloorPlan.id)).all()]

@app.post("/api/plans",status_code=201)
def create_floor_plan(data:FloorPlanIn,user=Depends(require_admin)):
    with Session.begin() as db:
        plan=FloorPlan(name=data.name.strip(),location_label=data.location_label.strip());db.add(plan);db.flush();return floor_plan_dict(db,plan)

@app.patch("/api/plans/{plan_id}")
def update_floor_plan(plan_id:int,data:FloorPlanIn,user=Depends(require_admin)):
    with Session.begin() as db:
        plan=db.get(FloorPlan,plan_id)
        if not plan:raise HTTPException(404,"Floor plan not found")
        plan.name=data.name.strip();plan.location_label=data.location_label.strip();return floor_plan_dict(db,plan)

@app.put("/api/plans/{plan_id}/placements")
def save_plan_placements(plan_id:int,data:PlacementsIn,user=Depends(require_admin)):
    if len({p.camera_id for p in data.placements})!=len(data.placements):raise HTTPException(422,"A camera can appear only once on a floor plan")
    try:
        with Session.begin() as db:
            plan=db.get(FloorPlan,plan_id)
            if not plan:raise HTTPException(404,"Floor plan not found")
            changed=db.execute(update(FloorPlan).where(FloorPlan.id==plan_id,FloorPlan.revision==data.revision).values(revision=FloorPlan.revision+1))
            if changed.rowcount!=1:raise HTTPException(409,"Floor plan changed since it was loaded. Reload and reapply your placement edits.")
            requested={p.camera_id for p in data.placements}
            camera_ids={c.id for c in db.scalars(select(Camera).where(Camera.id.in_(requested))).all()} if requested else set()
            if camera_ids!=requested:raise HTTPException(422,"Placement references an unknown camera")
            existing_elsewhere=[p.camera_id for p in db.scalars(select(CameraPlacement).where(CameraPlacement.camera_id.in_(requested),CameraPlacement.plan_id!=plan_id)).all()] if requested else []
            if existing_elsewhere:raise HTTPException(409,"A camera is already placed on another plan. Remove it there before moving it.")
            db.query(CameraPlacement).filter(CameraPlacement.plan_id==plan_id).delete(synchronize_session=False)
            for item in data.placements:db.add(CameraPlacement(plan_id=plan_id,camera_id=item.camera_id,x=item.x,y=item.y))
            db.flush();plan=db.get(FloorPlan,plan_id);db.refresh(plan);return floor_plan_dict(db,plan)
    except IntegrityError as exc:
        raise HTTPException(409,"A camera placement changed concurrently. Reload both plans and reapply the edit.") from exc

@app.post("/api/plans/{plan_id}/image")
async def upload_plan_image(plan_id:int,request:Request,placement_policy:str=Query(default="keep",pattern="^(keep|clear)$"),revision:int=Query(ge=1),user=Depends(require_admin)):
    raw=await request.body()
    if not raw or len(raw)>8*1024*1024:raise HTTPException(413,"Floor plan image must be between 1 byte and 8 MiB")
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):extension="png"
    elif raw.startswith(b"\xff\xd8\xff"):extension="jpg"
    else:raise HTTPException(415,"Only decoded PNG and JPEG floor plans are supported")
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ("PNG","JPEG"):raise HTTPException(415,"Only PNG and JPEG floor plans are supported")
            width,height=image.size
            if width<1 or height<1 or width*height>20_000_000:raise HTTPException(413,"Floor plan image exceeds the 20 megapixel limit")
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            orientation=image.getexif().get(274,1)
            image.load()
            if orientation!=1:
                from PIL import ImageOps
                corrected=ImageOps.exif_transpose(image);width,height=corrected.size;output=BytesIO()
                if extension=="jpg":corrected.convert("RGB").save(output,format="JPEG",quality=95,optimize=True)
                else:corrected.save(output,format="PNG",optimize=True)
                raw=output.getvalue()
                if len(raw)>8*1024*1024:raise HTTPException(413,"Normalized floor plan image exceeds the 8 MiB limit")
    except HTTPException:raise
    except Image.DecompressionBombError:raise HTTPException(413,"Floor plan image exceeds the 20 megapixel limit")
    except (UnidentifiedImageError,OSError,ValueError):raise HTTPException(415,"Image could not be decoded")
    if width<1 or height<1 or width*height>20_000_000:raise HTTPException(413,"Floor plan image exceeds the 20 megapixel limit")
    filename=f"{uuid.uuid4().hex}.{extension}";target=FLOOR_PLAN_DIR/filename;old_filename=None
    target.write_bytes(raw)
    try:
        with Session.begin() as db:
            plan=db.get(FloorPlan,plan_id)
            if not plan:raise HTTPException(404,"Floor plan not found")
            changed=db.execute(update(FloorPlan).where(FloorPlan.id==plan_id,FloorPlan.revision==revision).values(revision=FloorPlan.revision+1))
            if changed.rowcount!=1:raise HTTPException(409,"Floor plan changed since it was loaded. Reload before replacing its image.")
            old_filename=plan.image_name
            if placement_policy=="clear":db.query(CameraPlacement).filter(CameraPlacement.plan_id==plan_id).delete(synchronize_session=False)
            plan.image_name=filename;plan.image_width=width;plan.image_height=height
            db.flush();db.refresh(plan)
            result=floor_plan_dict(db,plan)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if old_filename and re.fullmatch(r"[0-9a-f]{32}\.(png|jpg)",old_filename) and old_filename!=filename:
        try:(FLOOR_PLAN_DIR/old_filename).unlink(missing_ok=True)
        except OSError:log.warning("orphaned_floor_plan_image plan_id=%s",plan_id)
    return result

@app.get("/api/plans/{plan_id}/image")
def get_plan_image(plan_id:int,user=Depends(current_user)):
    with Session() as db:plan=db.get(FloorPlan,plan_id);filename=plan.image_name if plan else None
    if not filename or not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg)",filename):raise HTTPException(404,"Floor plan image not found")
    path=(FLOOR_PLAN_DIR/filename).resolve()
    if path.parent!=FLOOR_PLAN_DIR or not path.is_file():raise HTTPException(404,"Floor plan image not found")
    return FileResponse(path,media_type="image/png" if path.suffix==".png" else "image/jpeg",headers={"Cache-Control":"private, no-store"})

@app.delete("/api/plans/{plan_id}",status_code=204)
def delete_floor_plan(plan_id:int,user=Depends(require_admin)):
    with Session.begin() as db:
        plan=db.get(FloorPlan,plan_id)
        if not plan:raise HTTPException(404,"Floor plan not found")
        db.query(CameraPlacement).filter(CameraPlacement.plan_id==plan_id).delete(synchronize_session=False)
        filename=plan.image_name;db.delete(plan)
    if filename and re.fullmatch(r"[0-9a-f]{32}\.(png|jpg)",filename):(FLOOR_PLAN_DIR/filename).unlink(missing_ok=True)

@app.put("/api/cameras/{camera_id}/context")
def update_camera_context(camera_id:int,data:CameraContextIn,user=Depends(require_admin)):
    with Session.begin() as db:
        camera=db.get(Camera,camera_id)
        if not camera:raise HTTPException(404,"Camera not found")
        for key,value in data.model_dump().items():setattr(camera,key,value.strip() if value else None)
        return camera_dict(camera)
@app.get("/api/cameras")
def cameras(user=Depends(current_user)):
    with Session() as db: return [camera_dict(c) for c in db.scalars(select(Camera).order_by(Camera.id))]
@app.post("/api/cameras")
def create_camera(data:CameraIn,user=Depends(require_admin)):
    if data.source_type not in ("synthetic","file","rtsp","webcam"): raise HTTPException(422,"Unsupported source type")
    if data.source_type=="webcam":
        from .webcam_adapter import parse_webcam_index
        try:data.connection=str(parse_webcam_index(data.connection or "0"))
        except ValueError:raise HTTPException(422,"Webcam source needs a device index from 0 to 9")
    if data.source_type=="synthetic" and data.scenario not in ("normal","obstruction","person_down","smoke_fire"): raise HTTPException(422,"Unknown simulated scenario")
    if data.source_type!="synthetic" and data.scenario!="normal": raise HTTPException(422,"Simulated scenarios cannot be enabled on real sources")
    if data.source_type=="file" and not data.connection: raise HTTPException(422,"Media path is required")
    if data.source_type=="rtsp" and not data.connection.lower().startswith(("rtsp://","rtsps://")): raise HTTPException(422,"Only RTSP/RTSPS sources are supported")
    with Session.begin() as db:
        camera=Camera(name=data.name,location=data.location,source_type=data.source_type,connection=data.connection if data.source_type!="rtsp" else "",secret=fernet.encrypt(data.connection.encode()).decode() if data.source_type=="rtsp" else "",enabled=data.enabled,simulated=data.source_type=="synthetic",scenario=data.scenario,processing_fps=data.processing_fps,resize_limit=data.resize_limit,timeout_seconds=data.timeout_seconds,reconnect_min_seconds=data.reconnect_min_seconds,reconnect_max_seconds=data.reconnect_max_seconds); db.add(camera); db.flush()
        if camera.simulated:
            for event in ("OBSTRUCTION","PERSON_DOWN","SMOKE_FIRE"): db.add(Rule(camera_id=camera.id,event_type=event,enabled=data.scenario!="normal" and event=={"obstruction":"OBSTRUCTION","person_down":"PERSON_DOWN","smoke_fire":"SMOKE_FIRE"}.get(data.scenario),min_duration=2,cooldown=30,zone={"type":"polygon","points":[[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]]}))
        return camera_dict(camera)
@app.patch("/api/cameras/{camera_id}")
def update_camera(camera_id:int,data:CameraIn,user=Depends(require_admin)):
    with Session.begin() as db:
        c=db.get(Camera,camera_id)
        if not c: raise HTTPException(404,"Camera not found")
        if c.source_type!=data.source_type: raise HTTPException(422,"Changing source type requires creating a new camera")
        c.name=data.name;c.location=data.location;c.enabled=data.enabled;c.processing_fps=data.processing_fps;c.resize_limit=data.resize_limit;c.timeout_seconds=data.timeout_seconds;c.reconnect_min_seconds=data.reconnect_min_seconds;c.reconnect_max_seconds=data.reconnect_max_seconds
        if c.source_type=="rtsp":
            if data.connection:
                if not data.connection.lower().startswith(("rtsp://","rtsps://")):raise HTTPException(422,"Only RTSP/RTSPS sources are supported")
                c.secret=fernet.encrypt(data.connection.encode()).decode()
            elif data.clear_connection:c.secret=""
        elif c.source_type=="file" and data.connection:
            from .adapters import OpenCVAdapter
            try:OpenCVAdapter("file",data.connection,MEDIA_ROOTS,timeout=data.timeout_seconds)._validate()
            except Exception:raise HTTPException(422,"File source must resolve to a file beneath an authorized media root")
            c.connection=data.connection
        elif c.source_type=="webcam" and data.connection:
            from .webcam_adapter import parse_webcam_index
            try:c.connection=str(parse_webcam_index(data.connection))
            except ValueError:raise HTTPException(422,"Webcam source needs a device index from 0 to 9")
        if c.simulated:
            if data.scenario not in ("normal","obstruction","person_down","smoke_fire"): raise HTTPException(422,"Unknown simulated scenario")
            c.scenario=data.scenario
            for rule in db.scalars(select(Rule).where(Rule.camera_id==c.id)): rule.enabled=rule.event_type=={"obstruction":"OBSTRUCTION","person_down":"PERSON_DOWN","smoke_fire":"SMOKE_FIRE"}.get(data.scenario)
        return camera_dict(c)
@app.get("/api/cameras/{camera_id}/preview")
def preview(camera_id:int,user=Depends(current_user)):
    with Session() as db: c=db.get(Camera,camera_id)
    if not c: raise HTTPException(404,"Camera not found")
    m=HANDOFF_DIR/f"camera-{camera_id}.json"
    if not c.enabled or not m.exists(): raise HTTPException(503,"Preview offline")
    try: meta=json.loads(m.read_text())
    except Exception: raise HTTPException(503,"Preview metadata unavailable")
    filename=Path(meta.get("file","" )).name
    if not filename.startswith(f"camera-{camera_id}-") or not filename.endswith(".jpg"): raise HTTPException(503,"Preview metadata invalid")
    p=HANDOFF_DIR/filename
    if not p.is_file(): raise HTTPException(503,"Preview offline")
    try:
        captured=datetime.fromisoformat(str(meta["captured_at"]).replace("Z","+00:00"))
        if captured.tzinfo is None: captured=captured.replace(tzinfo=timezone.utc)
        sequence=int(meta["sequence"])
        frame_id=f"{sequence}:{captured.timestamp():.6f}"
        age_ms=max(0,int((now()-captured.astimezone(timezone.utc)).total_seconds()*1000))
        width=int(meta["width"]);height=int(meta["height"]);simulated=bool(meta["simulated"])
        if width<1 or height<1: raise ValueError("invalid dimensions")
    except (KeyError,TypeError,ValueError,OverflowError): raise HTTPException(503,"Preview metadata invalid")
    response=FileResponse(p,media_type="image/jpeg",headers={"Cache-Control":"no-store","X-Captured-At":captured.astimezone(timezone.utc).isoformat(),"X-Frame-ID":frame_id,"X-Frame-Age-Ms":str(age_ms),"X-Frame-Width":str(width),"X-Frame-Height":str(height),"X-Simulation":"SIMULATED" if simulated else "REAL SOURCE"})
    return response
@app.get("/api/cameras/{camera_id}/rules")
def rules(camera_id:int,user=Depends(current_user)):
    with Session() as db:
        if not db.get(Camera,camera_id): raise HTTPException(404,"Camera not found")
        return [{"id":r.id,"event_type":r.event_type,"enabled":r.enabled,"min_duration":r.min_duration,"cooldown":r.cooldown,"zone":r.zone,"timezone":(r.config or {}).get("timezone","Asia/Bangkok"),"line":(r.config or {}).get("line"),"direction":(r.config or {}).get("direction","A_TO_B")} for r in db.scalars(select(Rule).where(Rule.camera_id==camera_id))]
def valid_zone(z):
    if z.get("type") not in ("polygon","rectangle"): return False
    pts=z.get("points")
    if not isinstance(pts,list) or len(pts)<3 or len(pts)>64: return False
    try:
        if any(len(p)!=2 or not all(0<=float(v)<=1 for v in p) for p in pts): return False
        pts=[(float(p[0]),float(p[1])) for p in pts]
        if len(set(pts))!=len(pts):return False
        if z["type"]=="rectangle":
            if len(pts)!=4:return False
            xs=sorted({p[0] for p in pts});ys=sorted({p[1] for p in pts})
            if len(xs)!=2 or len(ys)!=2 or set(pts)!={(xs[0],ys[0]),(xs[0],ys[1]),(xs[1],ys[0]),(xs[1],ys[1])}:return False
        area=abs(sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts)))/2)
        if area==0:return False
        def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        n=len(pts)
        for i in range(n):
            a,b=pts[i],pts[(i+1)%n]
            for j in range(i+1,n):
                if j==i or j==(i+1)%n or (j+1)%n==i:continue
                c,d=pts[j],pts[(j+1)%n]
                if orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0:return False
        return True
    except (TypeError,ValueError): return False
@app.put("/api/rules/{rule_id}")
def update_rule(rule_id:int,data:RuleIn,user=Depends(require_admin)):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    if not valid_zone(data.zone): raise HTTPException(422,"Zone must have normalized, nonzero-area polygon points")
    if data.direction not in ("A_TO_B","B_TO_A"): raise HTTPException(422,"direction must be A_TO_B or B_TO_A")
    if data.line is not None and (len(data.line)!=2 or any(len(p)!=2 or any(not 0<=v<=1 for v in p) for p in data.line) or data.line[0]==data.line[1]): raise HTTPException(422,"line must contain two distinct normalized endpoints")
    try: ZoneInfo(data.timezone)
    except (ZoneInfoNotFoundError,ValueError): raise HTTPException(422,"Invalid schedule timezone")
    with Session.begin() as db:
        rule=db.get(Rule,rule_id)
        if not rule: raise HTTPException(404,"Rule not found")
        if data.event_type!=rule.event_type: raise HTTPException(422,"Rule event type cannot be changed")
        rule.enabled=data.enabled;rule.min_duration=data.min_duration;rule.cooldown=data.cooldown;rule.zone=data.zone;rule.config={**(rule.config or {}),"timezone":data.timezone,"line":data.line,"direction":data.direction}
        return {"id":rule.id,"event_type":rule.event_type,"enabled":rule.enabled,"min_duration":rule.min_duration,"cooldown":rule.cooldown,"zone":rule.zone,"timezone":data.timezone,"line":data.line,"direction":data.direction}
@app.get("/api/incidents")
def incidents(status:IncidentStatus|None=None,limit:int=Query(default=50,ge=1,le=100),offset:int=Query(default=0,ge=0),camera_id:int|None=None,event_type:str|None=None,severity:str|None=None,source_mode:str|None=None,start:str|None=None,end:str|None=None,search:str|None=Query(default=None,max_length=120),user=Depends(current_user)):
    with Session() as db:
        if source_mode not in (None,"LIVE","SIMULATED"):raise HTTPException(422,"source_mode must be LIVE or SIMULATED")
        q=select(Incident).join(Camera,Incident.camera_id==Camera.id).order_by(Incident.last_seen.desc())
        if status: q=q.where(Incident.status==status)
        if camera_id:q=q.where(Incident.camera_id==camera_id)
        if event_type:q=q.where(Incident.event_type==event_type)
        if severity:q=q.where(Incident.severity==severity)
        if source_mode=="SIMULATED":q=q.where(Incident.simulated.is_(True))
        elif source_mode=="LIVE":q=q.where(Incident.simulated.is_(False))
        if start or end:
            try:
                if start:
                    start_at=datetime.fromisoformat(start.replace("Z","+00:00"))
                    if start_at.tzinfo is None:raise ValueError("timezone required")
                    q=q.where(Incident.last_seen>=start_at)
                if end:
                    end_at=datetime.fromisoformat(end.replace("Z","+00:00"))
                    if end_at.tzinfo is None:raise ValueError("timezone required")
                    q=q.where(Incident.last_seen<=end_at)
            except ValueError:raise HTTPException(422,"Incident date filters must be ISO timestamps")
        if search:
            pattern=f"%{search.strip()}%";q=q.where((Camera.name.ilike(pattern))|(Camera.location.ilike(pattern))|(Incident.event_type.ilike(pattern)))
        q=q.limit(limit).offset(offset)
        return [incident_dict(db,x) for x in db.scalars(q)]
def incident_dict(db,i):
    c=db.get(Camera,i.camera_id)
    return {"id":i.id,"camera_id":i.camera_id,"camera":c.name if c else "Unknown","location":c.location if c else "","event_type":i.event_type,"status":i.status.value,"severity":i.severity,"simulated":i.simulated,"first_seen":utc_iso(i.first_seen),"last_seen":utc_iso(i.last_seen),"snapshot_available":not i.evidence_expired and (EVIDENCE_DIR/i.snapshot).is_file(),"evidence_expired":i.evidence_expired,"metadata":i.metadata_json,"config_snapshot":i.config_snapshot,"history":[{"actor":t.username,"from":h.from_status,"to":h.to_status,"note":h.note,"at":utc_iso(h.at)} for h in db.scalars(select(Transition).where(Transition.incident_id==i.id).join(User,Transition.actor_id==User.id).with_only_columns(Transition)) for t in [db.get(User,h.actor_id)]]}
@app.post("/api/incidents/{incident_id}/action")
def action(incident_id:int,data:ActionIn,user=Depends(current_user)):
    allowed={IncidentStatus.NEW:{IncidentStatus.ACKNOWLEDGED,IncidentStatus.FALSE_ALARM,IncidentStatus.RESOLVED},IncidentStatus.ACKNOWLEDGED:{IncidentStatus.RESOLVED,IncidentStatus.FALSE_ALARM},IncidentStatus.RESOLVED:set(),IncidentStatus.FALSE_ALARM:set()}
    with Session.begin() as db:
        incident=db.get(Incident,incident_id)
        if not incident: raise HTTPException(404,"Incident not found")
        old=incident.status
        if data.status not in allowed[old]: raise HTTPException(409,f"Cannot transition {old.value} to {data.status.value}")
        result=db.execute(update(Incident).where(Incident.id==incident_id,Incident.status==old).values(status=data.status))
        if result.rowcount!=1: raise HTTPException(409,"Incident changed concurrently; refresh and retry")
        db.add(Transition(incident_id=incident_id,actor_id=user["id"],from_status=old.value,to_status=data.status.value,note=data.note)); return {"id":incident_id,"status":data.status.value}
@app.get("/api/incidents/{incident_id}/evidence")
def evidence(incident_id:int,user=Depends(current_user)):
    with Session() as db: incident=db.get(Incident,incident_id)
    if not incident: raise HTTPException(404,"Incident not found")
    if incident.evidence_expired: raise HTTPException(410,"Evidence expired")
    path=EVIDENCE_DIR/Path(incident.snapshot).name
    if not path.is_file() or path.resolve().parent!=EVIDENCE_DIR.resolve(): raise HTTPException(404,"Evidence unavailable")
    return FileResponse(path,media_type="image/jpeg",headers={"Cache-Control":"private, no-store","X-Simulation":"SIMULATED" if incident.simulated else "REAL SOURCE"})
@app.get("/api/notifications")
def notifications(user=Depends(current_user)):
    with Session() as db:
        return [{"id":n.id,"incident_id":n.incident_id,"kind":n.kind,"created_at":utc_iso(n.created_at),"read":n.read} for n in db.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(100))]
@app.post("/api/admin/users")
def create_user(data:UserIn,user=Depends(require_admin)):
    try:
        with Session.begin() as db: row=User(username=data.username,password_hash=hasher.hash(data.password),role=data.role);db.add(row);db.flush();return {"id":row.id,"username":row.username,"role":row.role.value}
    except IntegrityError: raise HTTPException(409,"Username already exists")

# Feature routers: every module in backend/app/features/ with build_router(deps). See docs/features/navigation-registry.md
from .features import FeatureDeps, inject_feature_scripts, register_features
register_features(app,FeatureDeps(current_user=current_user,require_admin=require_admin,utc_iso=utc_iso,incident_dict=incident_dict,camera_dict=camera_dict))
