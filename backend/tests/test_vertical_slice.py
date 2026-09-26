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
from app.db import Base, engine, Session, User, Role, Camera, Rule, Incident, IncidentStatus, Notification, Lease, now
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
    assert client.post(f"/api/incidents/{incident['id']}/action",json={"status":"FALSE_ALARM"}).status_code==409
    with Session() as db:
        assert db.scalar(select(Incident).where(Incident.id==incident["id"])) is not None
        assert db.scalar(select(Notification).where(Notification.incident_id==incident["id"])) is not None
    with Session() as db: camera=db.get(Camera,incident["camera_id"])
    process(camera,SyntheticAdapter("obstruction").read(),TemporalRuleEvaluator())
    with Session() as db: assert len(db.scalars(select(Incident).where(Incident.camera_id==camera.id)).all())==1

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
    update_body={"event_type":"OBSTRUCTION","enabled":True,"min_duration":3,"cooldown":15,"zone":{"type":"rectangle","points":[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]},"timezone":"Asia/Bangkok"}
    assert client.put(f"/api/rules/{rule.id}",json=update_body).status_code==200
    update_body["zone"]={"type":"polygon","points":[[.2,.2],[.2,.2],[.2,.2]]}
    assert client.put(f"/api/rules/{rule.id}",json=update_body).status_code==422

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
        assert [adapter.read().sequence for _ in range(3)]==[0,0,0]
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
