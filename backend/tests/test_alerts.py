"""In-app alert feed: cursors, incident details, health changes and read state (branch: feature/alerts)."""
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
from app.services.health_service import record_transition
from app.worker import process

ZONE = {"type": "polygon", "points": [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]}


def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(User(username="operator", password_hash=PasswordHasher().hash("test-operator-password"), role=Role.OPERATOR))
        lobby = Camera(name="Lobby", location="Level 1", source_type="synthetic", simulated=True, scenario="smoke_fire"); db.add(lobby)
        db.add(Camera(name="Gate", location="Car park", source_type="synthetic", simulated=True, scenario="normal")); db.flush()
        db.add(Rule(camera_id=lobby.id, event_type="SMOKE_FIRE", enabled=True, min_duration=0, cooldown=30, zone=ZONE))


def login():
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": "operator", "password": "test-operator-password"}).status_code == 200
    return client


def make_incident():
    """Real pipeline: synthetic frame -> rule -> incident + notification (same path the worker uses)."""
    with Session() as db: lobby = db.scalar(select(Camera).where(Camera.name == "Lobby"))
    state = TemporalRuleEvaluator()
    for _ in range(2): process(lobby, SyntheticAdapter("smoke_fire").read(), state)
    with Session() as db: return db.scalar(select(Incident).where(Incident.camera_id == lobby.id).order_by(Incident.id.desc()))


def test_alert_feed_cursor_details_and_mark_read():
    operator = login()
    start = operator.get("/api/alerts/feed").json()
    incident = make_incident()
    feed = operator.get(f"/api/alerts/feed?after_notification={start['cursor']['notification']}&after_health={start['cursor']['health']}").json()
    assert len(feed["notifications"]) == 1
    note = feed["notifications"][0]
    assert note["incident_id"] == incident.id and note["incident"]["camera"] == "Lobby"
    assert note["incident"]["event_type"] == "SMOKE_FIRE" and note["incident"]["simulated"] is True and note["read"] is False
    again = operator.get(f"/api/alerts/feed?after_notification={feed['cursor']['notification']}&after_health={feed['cursor']['health']}").json()
    assert again["notifications"] == [] and again["health"] == []
    assert operator.post("/api/alerts/read", json={"notification_ids": [note["id"]]}).json()["unread"] == feed["unread"] - 1
    assert operator.post("/api/alerts/read", json={"all": True}).json()["unread"] == 0
    assert TestClient(app).get("/api/alerts/feed").status_code == 401
    assert TestClient(app).post("/api/alerts/read", json={"all": True}).status_code in (401, 403)


def test_alert_feed_reports_camera_offline_and_recovery():
    operator = login()
    cursor = operator.get("/api/alerts/feed").json()["cursor"]
    with Session() as db: gate = db.scalar(select(Camera).where(Camera.name == "Gate")).id
    with Session.begin() as db:
        record_transition(db, gate, None, "ONLINE")
    with Session.begin() as db:
        record_transition(db, gate, "ONLINE", "OFFLINE", "source_unavailable")
    feed = operator.get(f"/api/alerts/feed?after_notification={cursor['notification']}&after_health={cursor['health']}").json()
    assert [h["to_status"] for h in feed["health"]] == ["OFFLINE", "ONLINE"]      # newest first
    assert feed["health"][0]["camera"] == "Gate" and feed["health"][0]["error_category"] == "source_unavailable"
    assert operator.get("/api/alerts/feed?limit=500").status_code == 422
