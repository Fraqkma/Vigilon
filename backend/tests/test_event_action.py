"""Incident evidence records the frame size so the detection box can be drawn (branch: feature/event-action-evidence)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test-vigilon.db")
os.environ.setdefault("VIGILON_SECRET_KEY", "test-signing-key-that-is-local-only")
os.environ.setdefault("VIGILON_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters import SyntheticAdapter
from app.db import Base, Camera, Incident, Role, Rule, Session, User, engine
from app.main import app
from app.rules import TemporalRuleEvaluator
from app.worker import process

ZONE = {"type": "polygon", "points": [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]}


def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(User(username="operator", password_hash=PasswordHasher().hash("test-operator-password"), role=Role.OPERATOR))
        lobby = Camera(name="Lobby", location="Level 1", source_type="synthetic", simulated=True, scenario="smoke_fire"); db.add(lobby); db.flush()
        db.add(Rule(camera_id=lobby.id, event_type="SMOKE_FIRE", enabled=True, min_duration=0, cooldown=30, zone=ZONE))


def test_incident_metadata_has_frame_size_for_box_overlay():
    with Session() as db: lobby = db.scalar(select(Camera).where(Camera.name == "Lobby"))
    state = TemporalRuleEvaluator()
    for _ in range(2): process(lobby, SyntheticAdapter("smoke_fire").read(), state)
    with Session() as db:
        incident = db.scalar(select(Incident).where(Incident.camera_id == lobby.id))
        meta = incident.metadata_json
    assert meta["frame_size"] == [960, 540] and meta["geometry"]["normalized"] == [0.25, 0.4, 0.75, 0.75]
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": "operator", "password": "test-operator-password"}).status_code == 200
    listed = next(i for i in client.get("/api/incidents").json() if i["id"] == incident.id)
    assert listed["metadata"]["frame_size"] == [960, 540]          # the browser receives what it needs to place the box
