import os
from pathlib import Path
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test-vigilon.db")
os.environ.setdefault("VIGILON_SECRET_KEY", "test-signing-key-that-is-local-only")
os.environ.setdefault("VIGILON_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from fastapi.testclient import TestClient
from argon2 import PasswordHasher
from sqlalchemy import select
from app.main import app, valid_zone
from app.adapters import SyntheticAdapter
from app.rules import TemporalRuleEvaluator
from app.db import Base, engine, Session, User, Role, Camera, Rule, Incident, IncidentStatus, Notification, Lease, FloorPlan, CameraPlacement, now
from app.worker import process, acquire_lease

def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(User(username="admin",password_hash=PasswordHasher().hash("test-admin-password"),role=Role.ADMIN))
        db.add(User(username="operator",password_hash=PasswordHasher().hash("test-operator-password"),role=Role.OPERATOR))
        camera=Camera(name="Test demo",location="Lab",source_type="synthetic",enabled=True,simulated=True,scenario="obstruction");db.add(camera);db.flush()
        db.add(Rule(camera_id=camera.id,event_type="OBSTRUCTION",enabled=True,min_duration=0,cooldown=30,zone={"type":"polygon","points":[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]}))

def test_demo_frame_to_authenticated_evidence_and_operator_history():
    with Session() as db: camera=db.scalar(select(Camera))
    process(camera,SyntheticAdapter("obstruction").read(),TemporalRuleEvaluator())
    event_state=TemporalRuleEvaluator()
    process(camera,SyntheticAdapter("obstruction").read(),event_state)
    process(camera,SyntheticAdapter("obstruction").read(),event_state)
    with Session() as db:
        assert len(db.scalars(select(Incident)).all())==1
        assert len(db.scalars(select(Notification)).all())==1
    with Session() as db: incident_id=db.scalar(select(Incident).where(Incident.camera_id==camera.id)).id
    with TestClient(app) as anon:
        assert anon.get(f"/api/cameras/{camera.id}/preview").status_code==401
        assert anon.get(f"/api/incidents/{incident_id}/evidence").status_code==401
    client=TestClient(app)
    assert client.post("/api/auth/login",json={"username":"operator","password":"test-operator-password"}).status_code==200
    preview=client.get(f"/api/cameras/{camera.id}/preview")
    assert preview.status_code==200 and preview.headers["content-type"]=="image/jpeg" and preview.headers["x-simulation"]=="SIMULATED"
    incident=client.get("/api/incidents").json()[0]
    assert incident["simulated"] is True and incident["snapshot_available"]
    evidence=client.get(f"/api/incidents/{incident['id']}/evidence")
    assert evidence.status_code==200 and evidence.content[:2]==b"\xff\xd8"
    assert client.post(f"/api/incidents/{incident['id']}/action",json={"status":"ACKNOWLEDGED","note":"Operator reviewed"}).status_code==200
    assert client.post(f"/api/incidents/{incident['id']}/action",json={"status":"RESOLVED","note":"Scene checked"}).status_code==200
    updated=client.get("/api/incidents").json()[0]
    assert updated["status"]=="RESOLVED" and [x["to"] for x in updated["history"]]==["ACKNOWLEDGED","RESOLVED"]
    assert any(item["id"]==incident["id"] for item in client.get("/api/incidents?source_mode=SIMULATED&search=Test%20demo").json())
    assert client.get("/api/incidents?source_mode=UNKNOWN").status_code==422
    assert client.get("/api/incidents?start=2026-01-01T00:00:00").status_code==422
    assert client.post(f"/api/incidents/{incident['id']}/action",json={"status":"FALSE_ALARM"}).status_code==409
    with Session() as db:
        assert db.scalar(select(Incident).where(Incident.id==incident["id"])) is not None
        assert db.scalar(select(Notification).where(Notification.incident_id==incident["id"])) is not None
    with Session() as db: camera=db.get(Camera,incident["camera_id"])
    process(camera,SyntheticAdapter("obstruction").read(),TemporalRuleEvaluator())
    with Session() as db: assert len(db.scalars(select(Incident).where(Incident.camera_id==camera.id)).all())==1

def test_control_center_floor_plan_placements_image_and_context_permissions():
    import cv2, numpy as np
    admin=TestClient(app);admin.post("/api/auth/login",json={"username":"admin","password":"test-admin-password"})
    operator=TestClient(app);operator.post("/api/auth/login",json={"username":"operator","password":"test-operator-password"})
    assert admin.get("/api/plans").status_code==200
    assert operator.post("/api/plans",json={"name":"Denied"}).status_code==403
    created=admin.post("/api/plans",json={"name":"North Wing","location_label":"Building A · Level 2"})
    assert created.status_code==201,created.text
    plan_id=created.json()["id"]
    with Session() as db: camera_id=db.scalar(select(Camera).where(Camera.name=="Test demo")).id
    image=np.full((40,80,3),220,dtype=np.uint8);ok,encoded=cv2.imencode(".png",image);assert ok
    uploaded=admin.post(f"/api/plans/{plan_id}/image?revision=1&placement_policy=keep",content=encoded.tobytes(),headers={"Content-Type":"image/png"})
    assert uploaded.status_code==200 and uploaded.json()["image_width"]==80 and uploaded.json()["revision"]==2
    assert operator.post(f"/api/plans/{plan_id}/image?revision=2",content=encoded.tobytes()).status_code==403
    saved=admin.put(f"/api/plans/{plan_id}/placements",json={"revision":2,"placements":[{"camera_id":camera_id,"x":0.25,"y":0.75}]})
    assert saved.status_code==200 and saved.json()["placements"]==[{"camera_id":camera_id,"x":0.25,"y":0.75}] and saved.json()["revision"]==3
    assert admin.get("/api/plans").json()[0]["placements"][0]["x"]==0.25
    assert admin.get(f"/api/plans/{plan_id}/image").content[:8]==b"\x89PNG\r\n\x1a\n"
    assert operator.put(f"/api/plans/{plan_id}/placements",json={"revision":3,"placements":[]}).status_code==403
    assert admin.put(f"/api/plans/{plan_id}/placements",json={"revision":3,"placements":[{"camera_id":camera_id,"x":1.1,"y":0}]}).status_code==422
    assert admin.put(f"/api/plans/{plan_id}/placements",content=f'{{"revision":3,"placements":[{{"camera_id":{camera_id},"x":NaN,"y":0}}]}}',headers={"Content-Type":"application/json"}).status_code==422
    assert admin.put(f"/api/plans/{plan_id}/placements",json={"revision":3,"placements":[{"camera_id":9999,"x":0.2,"y":0.3}]}).status_code==422
    duplicate={"revision":3,"placements":[{"camera_id":camera_id,"x":0.2,"y":0.3},{"camera_id":camera_id,"x":0.4,"y":0.5}]}
    assert admin.put(f"/api/plans/{plan_id}/placements",json=duplicate).status_code==422
    assert admin.put(f"/api/plans/{plan_id}/placements",json={"revision":2,"placements":[]}).status_code==409
    second=admin.post("/api/plans",json={"name":"Other Wing"}).json()
    assert admin.put(f"/api/plans/{second['id']}/placements",json={"revision":second['revision'],"placements":[{"camera_id":camera_id,"x":0.3,"y":0.4}]}).status_code==409
    keep=admin.post(f"/api/plans/{plan_id}/image?revision=3&placement_policy=keep",content=encoded.tobytes(),headers={"Content-Type":"image/png"})
    assert keep.status_code==200 and keep.json()["placements"][0]["camera_id"]==camera_id
    before=admin.get(f"/api/plans/{plan_id}/image").content
    stale_upload=admin.post(f"/api/plans/{plan_id}/image?revision=3&placement_policy=clear",content=encoded.tobytes(),headers={"Content-Type":"image/png"})
    assert stale_upload.status_code==409 and admin.get(f"/api/plans/{plan_id}/image").content==before
    cleared=admin.post(f"/api/plans/{plan_id}/image?revision=4&placement_policy=clear",content=encoded.tobytes(),headers={"Content-Type":"image/png"})
    assert cleared.status_code==200 and cleared.json()["placements"]==[] and cleared.json()["revision"]==5
    from PIL import Image
    from io import BytesIO
    oriented=Image.new("RGB",(80,40),(20,30,40));exif=oriented.getexif();exif[274]=6;output=BytesIO();oriented.save(output,format="JPEG",exif=exif)
    oriented_upload=admin.post(f"/api/plans/{plan_id}/image?revision=5&placement_policy=keep",content=output.getvalue(),headers={"Content-Type":"image/jpeg"})
    assert oriented_upload.status_code==200 and (oriented_upload.json()["image_width"],oriented_upload.json()["image_height"])==(40,80)
    with Image.open(BytesIO(admin.get(f"/api/plans/{plan_id}/image").content)) as normalized:assert normalized.getexif().get(274,1)==1
    assert admin.put(f"/api/cameras/{camera_id}/context",json={"manufacturer":"Example","model":"Camera X","responsible_contact":"Facilities","response_notes":"Check north entrance"}).status_code==200
    assert admin.get("/api/cameras").json()[0]["manufacturer"]=="Example"
    assert operator.put(f"/api/cameras/{camera_id}/context",json={}).status_code==403
    with Session.begin() as db:
        rule=db.scalar(select(Rule).where(Rule.camera_id==camera_id))
        preserved=Incident(camera_id=camera_id,rule_id=rule.id,event_type=rule.event_type,status=IncidentStatus.RESOLVED,severity="LOW",simulated=True,snapshot="map-test.jpg",metadata_json={},config_snapshot={})
        db.add(preserved);db.flush();preserved_id=preserved.id
    assert admin.delete(f"/api/plans/{plan_id}").status_code==204
    assert len(admin.get("/api/plans").json())==1
    assert admin.delete(f"/api/plans/{second['id']}").status_code==204
    assert admin.get("/api/plans").json()==[]
    with Session() as db:
        assert db.get(Camera,camera_id) is not None
        assert db.get(Incident,preserved_id) is not None
        assert db.scalar(select(CameraPlacement).where(CameraPlacement.camera_id==camera_id)) is None

def test_roles_zone_geometry_and_simulated_camera_secret_boundaries():
    assert valid_zone({"type":"polygon","points":[[0,0],[1,0],[1,1],[0,1]]})
    assert not valid_zone({"type":"polygon","points":[[.2,.2],[.2,.2],[.2,.2]]})
    assert valid_zone({"type":"rectangle","points":[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]})
    assert not valid_zone({"type":"rectangle","points":[[0,0],[1,1],[.5,.7]]})
    client=TestClient(app);client.post("/api/auth/login",json={"username":"operator","password":"test-operator-password"})
    assert client.post("/api/cameras",json={"name":"Denied","source_type":"synthetic"}).status_code==403
    client=TestClient(app);client.post("/api/auth/login",json={"username":"admin","password":"test-admin-password"})
    response=client.post("/api/cameras",json={"name":"Authorized RTSP","location":"Lab","source_type":"rtsp","connection":"rtsp://viewer:secret@192.168.1.20:554/live"})
    assert response.status_code==200
    assert "viewer" not in response.text and "secret" not in response.text
    with Session() as db:
        row=db.scalar(select(Camera).where(Camera.name=="Authorized RTSP"))
        assert row.connection=="" and row.secret!="" and "viewer" not in row.secret
        rule=db.scalar(select(Rule).where(Rule.camera_id==1))
    saved_secret=row.secret
    assert client.patch(f"/api/cameras/{row.id}",json={"name":row.name,"location":row.location,"source_type":"rtsp","connection":"","enabled":True,"scenario":"normal"}).status_code==200
    with Session() as db:assert db.get(Camera,row.id).secret==saved_secret
    update_body={"event_type":"OBSTRUCTION","enabled":True,"min_duration":3,"cooldown":15,"zone":{"type":"rectangle","points":[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]},"timezone":"Asia/Bangkok"}
    assert client.put(f"/api/rules/{rule.id}",json=update_body).status_code==200
    update_body["zone"]={"type":"polygon","points":[[.2,.2],[.2,.2],[.2,.2]]}
    assert client.put(f"/api/rules/{rule.id}",json=update_body).status_code==422

def test_ai_hub_catalog_assignment_and_admin_validation_are_authenticated(monkeypatch):
    client=TestClient(app);client.post("/api/auth/login",json={"username":"admin","password":"test-admin-password"})
    catalog=client.get("/api/ai/modules")
    assert catalog.status_code==200 and catalog.json()["hub_status"]=="HUB_INFRA_READY"
    assert {x["status"] for x in catalog.json()["modules"]}=={"MISSING_WEIGHTS"}
    model_source=client.post("/api/cameras",json={"name":"Model source","source_type":"rtsp","connection":"rtsp://viewer:secret@192.168.1.20:554/live"})
    assert model_source.status_code==200
    camera_id=model_source.json()["id"]
    unavailable=client.put(f"/api/cameras/{camera_id}/modules",json={"modules":["people_vehicle"]})
    assert unavailable.status_code==409 and "MISSING_WEIGHTS" in unavailable.text
    from app.main import hub
    monkeypatch.setattr(hub,"list",lambda:[{"module_id":"people_vehicle","status":"READY"},{"module_id":"fire_smoke","status":"MISSING_WEIGHTS"}])
    assigned=client.put(f"/api/cameras/{camera_id}/modules",json={"modules":["people_vehicle"]})
    assert assigned.status_code==200 and assigned.json()["modules"]==["people_vehicle"]
    monkeypatch.undo()
    validated=client.post("/api/admin/ai/modules/people_vehicle/validate",json={"mode":"runtime"})
    assert validated.status_code==200 and validated.json()["status"]=="MISSING_WEIGHTS"
    assert any(row.get("last_validation",{}).get("status")=="MISSING_WEIGHTS" for row in client.get("/api/ai/modules").json()["modules"])
    assert client.post("/api/admin/ai/modules/people_vehicle/reload",json={}).json()["status"]=="RELOAD_QUEUED"
    operator=TestClient(app);operator.post("/api/auth/login",json={"username":"operator","password":"test-operator-password"})
    assert operator.post("/api/admin/ai/modules/people_vehicle/reload",json={}).status_code==403

def test_bounded_video_import_preview_authorization_and_job_path(monkeypatch):
    import tempfile
    from pathlib import Path
    import cv2, numpy as np
    from app.core import IMPORT_DIR
    with tempfile.TemporaryDirectory(dir="sample_data") as folder:
        video=Path(folder)/"importable.avi"
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*"MJPG"),5,(32,24))
        assert writer.isOpened()
        for value in (40,120,220):writer.write(np.full((24,32,3),value,dtype=np.uint8))
        writer.release()
        admin=TestClient(app);admin.post("/api/auth/login",json={"username":"admin","password":"test-admin-password"})
        response=admin.post("/api/ai/imports",content=video.read_bytes(),headers={"X-File-Name":"hallway.avi","Content-Type":"application/octet-stream"})
        assert response.status_code==200,response.text
        imported=response.json()
        assert imported["input_path"].startswith("imports/") and imported["width"]==32 and imported["height"]==24 and abs(imported["duration_seconds"]-0.6)<0.01
        assert admin.get(f"/api/ai/imports/{imported['import_id']}/frame").status_code==200
        assert admin.get(f"/api/ai/imports/{imported['import_id']}/media").status_code==200
        assert TestClient(app).get(f"/api/ai/imports/{imported['import_id']}/frame").status_code==401
        assert admin.post("/api/ai/imports",content=b"bad",headers={"X-File-Name":"../../bad.exe"}).status_code==415
        job=admin.post("/api/ai/jobs",json={"input_path":imported["input_path"],"modules":["fire_smoke"]})
        assert job.status_code==200 and job.json()["status"]=="QUEUED",job.text
        assert admin.post(f"/api/ai/jobs/{job.json()['job_id']}/cancel",json={}).json()["status"]=="CANCELLED"
        admin.delete(f"/api/ai/jobs/{job.json()['job_id']}")
        (IMPORT_DIR/f"{imported['import_id']}.jpg").unlink(missing_ok=True)
        (IMPORT_DIR/Path(imported["input_path"]).name).unlink(missing_ok=True)

def test_camera_connectivity_probe_is_admin_only_and_redacts_source_url(monkeypatch):
    from app.adapters import OpenCVAdapter
    monkeypatch.setattr(OpenCVAdapter,"open",lambda self:True)
    monkeypatch.setattr(OpenCVAdapter,"read",lambda self:object())
    admin=TestClient(app);admin.post("/api/auth/login",json={"username":"admin","password":"test-admin-password"})
    response=admin.post("/api/cameras/test-connection",json={"source_type":"rtsp","connection":"rtsp://viewer:private@192.168.1.20:554/live","timeout_seconds":1})
    assert response.status_code==200 and response.json()["reachable"]
    assert "viewer" not in response.text and "private" not in response.text
    operator=TestClient(app);operator.post("/api/auth/login",json={"username":"operator","password":"test-operator-password"})
    assert operator.post("/api/cameras/test-connection",json={"source_type":"rtsp","connection":"rtsp://viewer:private@192.168.1.20:554/live"}).status_code==403

def test_generated_simulated_analysis_uses_persistent_file_worker():
    client=TestClient(app);client.post("/api/auth/login",json={"username":"admin","password":"test-admin-password"})
    response=client.post("/api/ai/demo-jobs",json={"scenario":"obstruction"})
    assert response.status_code==200,response.text
    job=response.json();assert job["status"]=="QUEUED" and job["input_name"].startswith("SIMULATED demo")
    from app.file_jobs import _run_job,result_path,delete_job
    import threading,json
    _run_job(job["job_id"],threading.Event())
    result=json.loads(result_path(job["job_id"]).read_text(encoding="utf-8"))
    assert result["status"]=="COMPLETED" and result["simulated"] is True
    assert result["events"] and all(event["simulated"] is True for event in result["events"])
    assert client.get(f"/api/ai/jobs/{job['job_id']}/results").json()["events"]
    assert delete_job(job["job_id"])

def test_file_job_ordered_progress_results_cancellation_and_path_boundary(monkeypatch):
    import tempfile, threading
    from pathlib import Path
    from types import SimpleNamespace
    import cv2
    import numpy as np
    from app.ai_hub import hub
    from app import file_jobs
    from app.file_jobs import _run_job, create_job, read_job
    with tempfile.TemporaryDirectory(dir="sample_data") as folder:
        video=Path(folder)/"ordered.avi"
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*"MJPG"),5,(32,24))
        assert writer.isOpened()
        for value in (40,120,220):writer.write(np.full((24,32,3),value,dtype=np.uint8))
        writer.release()
        admin=TestClient(app);admin.post("/api/auth/login",json={"username":"admin","password":"test-admin-password"})
        response=admin.post("/api/ai/jobs",json={"input_path":str(video.resolve()),"modules":["fire_smoke"],"scenario_config":{"fire_episode":{"minimum_observation_seconds":0}}})
        assert response.status_code==200 and response.json()["status"]=="QUEUED"
        media_response=admin.get(f"/api/ai/jobs/{response.json()['job_id']}/media")
        assert media_response.status_code==200 and len(media_response.content)>0
        anon=TestClient(app)
        assert anon.get(f"/api/ai/jobs/{response.json()['job_id']}/media").status_code==401
        operator=TestClient(app);operator.post("/api/auth/login",json={"username":"operator","password":"test-operator-password"})
        assert operator.post("/api/ai/jobs",json={"input_path":str(video.resolve()),"modules":["fire_smoke"]}).status_code==403
        package=SimpleNamespace(module_id="fire_smoke",status="READY",error=None,manifest={"package_version":"test"},scenarios={"fire_episode":{"event_type":"FIRE_DETECTED","required_classes":["fire"]}},scenario_defaults={},trackers={},lock=threading.RLock())
        monkeypatch.setitem(hub.packages,"fire_smoke",package)
        monkeypatch.setattr(hub,"activate",lambda module:package)
        monkeypatch.setattr(hub,"detect",lambda module,image,job,source:[{"label":"fire","class_id":1,"track_id":"t1","xyxy":[2,2,18,23],"simulated":False}])
        monkeypatch.setattr(file_jobs,"report_worker_status",lambda package:None)
        _run_job(response.json()["job_id"],threading.Event())
        final=admin.get(f"/api/ai/jobs/{response.json()['job_id']}").json()
        assert final["status"]=="COMPLETED" and final["progress_frames"]==3, final
        result=admin.get(f"/api/ai/jobs/{response.json()['job_id']}/results").json()
        assert result["frames"]==3 and result["timestamp_origin"]=="media"
        assert result["events"] and result["events"][0]["frame_id"]==1 and result["events"][0]["simulated"] is False
        assert admin.delete(f"/api/ai/jobs/{response.json()['job_id']}").status_code==204
        queued=create_job(str(video.resolve()),["fire_smoke"])
        cancelled=admin.post(f"/api/ai/jobs/{queued['job_id']}/cancel",json={})
        assert cancelled.status_code==200 and cancelled.json()["status"]=="CANCELLED"
        assert admin.get(f"/api/ai/jobs/{queued['job_id']}/results").json()["status"]=="CANCELLED"
        assert admin.delete(f"/api/ai/jobs/{queued['job_id']}").status_code==204
        try:create_job(str(Path(folder).parent.parent/"outside.avi"),["fire_smoke"])
        except ValueError as error:assert "beneath VIGILON_MEDIA_DIR" in str(error)
        else:raise AssertionError("media-root escape was accepted")

def test_file_adapter_eof_and_path_boundary():
    import tempfile
    import cv2
    from pathlib import Path
    from app.adapters import OpenCVAdapter
    with tempfile.TemporaryDirectory(dir=".data") as folder:
        root=Path(folder).resolve(); video=root/"fixture.avi"
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*"MJPG"),5,(32,24))
        assert writer.isOpened(),"OpenCV video writer is unavailable"
        for value in (20,100,220):writer.write(__import__("numpy").full((24,32,3),value,dtype="uint8"))
        writer.release()
        adapter=OpenCVAdapter("file",str(video),root,timeout=1)
        assert adapter.open()
        frames=[adapter.read() for _ in range(3)]
        assert [frame.sequence for frame in frames]==[1,2,3]
        assert all(frame.timestamp_origin=="media" and frame.media_time is not None for frame in frames)
        assert [frame.media_time for frame in frames]==sorted(set(frame.media_time for frame in frames))
        assert adapter.read() is None
        adapter.close()
        denied=OpenCVAdapter("file",str(root.parent/"outside.avi"),root,timeout=1)
        try:denied.open()
        except ValueError as error:assert "media_path_denied" in str(error)
        else:raise AssertionError("path traversal was accepted")

def test_rtsp_policy_rejects_loopback_and_service_ports(monkeypatch):
    import socket
    from pathlib import Path
    from app.adapters import OpenCVAdapter
    monkeypatch.setattr(socket,"gethostbyname",lambda host:host)
    loopback=OpenCVAdapter("rtsp","rtsp://127.0.0.1:554/live",Path("sample_data").resolve())
    try:loopback._validate()
    except ValueError as error:assert "not_private_lan" in str(error)
    else:raise AssertionError("loopback destination was accepted")
    service=OpenCVAdapter("rtsp","rtsp://192.168.1.9:5432/live",Path("sample_data").resolve())
    try:service._validate()
    except ValueError as error:assert "port_denied" in str(error)
    else:raise AssertionError("database service port was accepted")

def test_rule_minimum_duration_holds_before_creating_event():
    with Session.begin() as db:
        rule=db.scalar(select(Rule).where(Rule.event_type=="OBSTRUCTION"));rule.min_duration=1;rule.cooldown=0
        camera=db.scalar(select(Camera).where(Camera.id==rule.camera_id))
        before=len(db.scalars(select(Incident)).all())
    clock=[100.0];evaluator=TemporalRuleEvaluator(clock=lambda:clock[0])
    process(camera,SyntheticAdapter("obstruction").read(),evaluator)
    with Session() as db: assert len(db.scalars(select(Incident)).all())==before
    clock[0]+=1.5
    process(camera,SyntheticAdapter("obstruction").read(),evaluator)
    with Session() as db: assert len(db.scalars(select(Incident)).all())==before+1

def test_source_reader_buffer_is_bounded_and_retention_keeps_reference():
    import time
    from datetime import timedelta
    from app.worker import SourceRunner
    from app.db import now
    from app.core import EVIDENCE_DIR
    from app.retention import main as cleanup
    with Session() as db: camera=db.scalar(select(Camera))
    camera.processing_fps=15
    runner=SourceRunner(camera);runner.start();time.sleep(.5)
    assert runner.status=="ONLINE" and runner.frames.maxsize==1 and runner.dropped>0
    broken=Camera(id=999,name="Broken",source_type="file",connection="../outside.avi",enabled=True,processing_fps=2,timeout_seconds=1,reconnect_min_seconds=1,reconnect_max_seconds=2)
    broken_runner=SourceRunner(broken);broken_runner.start();time.sleep(.15)
    assert broken_runner.status=="OFFLINE" and broken_runner.error_category=="media_path_denied"
    assert runner.status=="ONLINE" and not runner.frames.empty()
    broken_runner.stop();broken_runner.join(2);assert not broken_runner.thread.is_alive()
    frame=runner.frames.get_nowait();assert frame.width==960 and frame.height==540
    runner.stop();runner.join(2);assert not runner.thread.is_alive()
    with Session.begin() as db:
        rule=db.scalar(select(Rule).where(Rule.camera_id==camera.id))
        evidence_name="incident-expired-test.jpg";(EVIDENCE_DIR/evidence_name).write_bytes(b"expired")
        incident=Incident(camera_id=camera.id,rule_id=rule.id,event_type="OBSTRUCTION",status=IncidentStatus.RESOLVED,severity="LOW",simulated=True,first_seen=now()-timedelta(days=400),last_seen=now()-timedelta(days=400),snapshot=evidence_name,metadata_json={},config_snapshot={})
        db.add(incident);db.flush();incident_id=incident.id
    cleanup()
    with Session() as db:
        expired=db.get(Incident,incident_id);assert expired.evidence_expired and not (EVIDENCE_DIR/evidence_name).exists()

def test_worker_lease_rejects_second_owner():
    from datetime import timedelta
    with Session.begin() as db:db.add(Lease(id=1,owner="other-process",expires=now()+timedelta(seconds=30)))
    try:
        try:acquire_lease()
        except RuntimeError as error:assert "other-process" in str(error)
        else:raise AssertionError("a second worker acquired a fresh lease")
    finally:
        with Session.begin() as db:db.query(Lease).filter_by(id=1).delete()
