import base64, hashlib, hmac, json, logging, os, re, secrets, time, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response, Depends, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from argon2 import PasswordHasher
from .core import HANDOFF_DIR, EVIDENCE_DIR, SECRET_KEY, fernet
from .db import Session, User, Role, Camera, Rule, Incident, IncidentStatus, Transition, Notification, Lease, now

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s %(levelname)s %(name)s %(message)s")
log=logging.getLogger("vigilon.api"); hasher=PasswordHasher(); app=FastAPI(title="Vigilon",version="0.1.0",description="Authorized existing-CCTV incident review. Simulated demo events are labeled.")
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
    name:str=Field(min_length=1,max_length=120); location:str=""; source_type:str="synthetic"; connection:str=""; enabled:bool=True; scenario:str="normal"; processing_fps:int=Field(default=2,ge=1,le=15); resize_limit:int=Field(default=1280,ge=160,le=3840); timeout_seconds:int=Field(default=5,ge=1,le=30); reconnect_min_seconds:int=Field(default=1,ge=1,le=30); reconnect_max_seconds:int=Field(default=30,ge=2,le=300)
    @model_validator(mode="after")
    def reconnect_bounds(self):
        if self.reconnect_min_seconds>self.reconnect_max_seconds:raise ValueError("Reconnect minimum must not exceed maximum")
        return self
class RuleIn(BaseModel): event_type:str; enabled:bool=True; min_duration:int=Field(default=2,ge=1,le=3600); cooldown:int=Field(default=30,ge=0,le=86400); zone:dict={}; timezone:str="Asia/Bangkok"
class ActionIn(BaseModel): status:IncidentStatus; note:str=Field(default="",max_length=500)
class UserIn(BaseModel): username:str=Field(min_length=3,max_length=80); password:str=Field(min_length=12,max_length=256); role:Role

@app.middleware("http")
async def security(request,call_next):
    try: csrf(request); response=await call_next(request)
    except HTTPException as e: return Response(e.detail,status_code=e.status_code)
    response.headers["X-Content-Type-Options"]="nosniff"; response.headers["Referrer-Policy"]="no-referrer"; response.headers["X-Frame-Options"]="DENY"
    return response

@app.get("/",response_class=HTMLResponse)
def home(): return (FRONTEND/"index.html").read_text()
@app.get("/api/health")
def health(): return {"status":"ok","database":"configured","simulation":"SIMULATED scenarios only"}
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
        return {"worker":worker,"cameras":[camera_dict(x) for x in cameras],"active_incidents":active}
def camera_dict(c): return {"id":c.id,"name":c.name,"location":c.location,"source_type":c.source_type,"enabled":c.enabled,"simulated":c.simulated,"scenario":c.scenario if c.simulated else None,"processing_fps":c.processing_fps,"resize_limit":c.resize_limit,"timeout_seconds":c.timeout_seconds,"reconnect_min_seconds":c.reconnect_min_seconds,"reconnect_max_seconds":c.reconnect_max_seconds,"status":c.status,"error_category":c.error_category,"preview_stale":not c.last_frame or (now()-c.last_frame.replace(tzinfo=timezone.utc) if c.last_frame.tzinfo is None else now()-c.last_frame).total_seconds()>8,"last_frame":utc_iso(c.last_frame),"reconnects":c.reconnects,"processed":c.processed,"dropped":c.dropped}
@app.get("/api/cameras")
def cameras(user=Depends(current_user)):
    with Session() as db: return [camera_dict(c) for c in db.scalars(select(Camera).order_by(Camera.id))]
@app.post("/api/cameras")
def create_camera(data:CameraIn,user=Depends(require_admin)):
    if data.source_type not in ("synthetic","file","rtsp"): raise HTTPException(422,"Unsupported source type")
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
    response=FileResponse(p,media_type="image/jpeg",headers={"Cache-Control":"no-store","X-Captured-At":meta["captured_at"],"X-Frame-Width":str(meta["width"]),"X-Frame-Height":str(meta["height"]),"X-Simulation":"SIMULATED" if meta["simulated"] else "REAL SOURCE"})
    return response
@app.get("/api/cameras/{camera_id}/rules")
def rules(camera_id:int,user=Depends(current_user)):
    with Session() as db:
        if not db.get(Camera,camera_id): raise HTTPException(404,"Camera not found")
        return [{"id":r.id,"event_type":r.event_type,"enabled":r.enabled,"min_duration":r.min_duration,"cooldown":r.cooldown,"zone":r.zone,"timezone":r.config.get("timezone","Asia/Bangkok")} for r in db.scalars(select(Rule).where(Rule.camera_id==camera_id))]
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
    try: ZoneInfo(data.timezone)
    except (ZoneInfoNotFoundError,ValueError): raise HTTPException(422,"Invalid schedule timezone")
    with Session.begin() as db:
        rule=db.get(Rule,rule_id)
        if not rule: raise HTTPException(404,"Rule not found")
        if data.event_type!=rule.event_type: raise HTTPException(422,"Rule event type cannot be changed")
        rule.enabled=data.enabled;rule.min_duration=data.min_duration;rule.cooldown=data.cooldown;rule.zone=data.zone;rule.config={"timezone":data.timezone}
        return {"id":rule.id,"event_type":rule.event_type,"enabled":rule.enabled,"min_duration":rule.min_duration,"cooldown":rule.cooldown,"zone":rule.zone,"timezone":data.timezone}
@app.get("/api/incidents")
def incidents(status:IncidentStatus|None=None,limit:int=Query(default=50,ge=1,le=100),offset:int=Query(default=0,ge=0),user=Depends(current_user)):
    with Session() as db:
        q=select(Incident).order_by(Incident.last_seen.desc()).limit(limit).offset(offset)
        if status: q=q.where(Incident.status==status)
        return [incident_dict(db,x) for x in db.scalars(q)]
def incident_dict(db,i):
    c=db.get(Camera,i.camera_id)
    return {"id":i.id,"camera_id":i.camera_id,"camera":c.name if c else "Unknown","location":c.location if c else "","event_type":i.event_type,"status":i.status.value,"severity":i.severity,"simulated":i.simulated,"first_seen":utc_iso(i.first_seen),"last_seen":utc_iso(i.last_seen),"snapshot_available":not i.evidence_expired and (EVIDENCE_DIR/i.snapshot).is_file(),"evidence_expired":i.evidence_expired,"metadata":i.metadata_json,"history":[{"actor":t.username,"from":h.from_status,"to":h.to_status,"note":h.note,"at":utc_iso(h.at)} for h in db.scalars(select(Transition).where(Transition.incident_id==i.id).join(User,Transition.actor_id==User.id).with_only_columns(Transition)) for t in [db.get(User,h.actor_id)]]}
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
