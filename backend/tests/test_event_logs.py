"""Unified event log search, pagination and CSV export (branch: feature/event-logs)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test-vigilon.db")
os.environ.setdefault("VIGILON_SECRET_KEY", "test-signing-key-that-is-local-only")
os.environ.setdefault("VIGILON_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from datetime import timedelta

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters import SyntheticAdapter
from app.db import Base, Camera, Incident, Role, Rule, Session, User, engine, now
from app.main import app
from app.rules import TemporalRuleEvaluator
from app.services.health_service import record_transition
from app.worker import process

ZONE = {"type": "polygon", "points": [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]}


def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(User(username="admin", password_hash=PasswordHasher().hash("test-admin-password"), role=Role.ADMIN))
        lobby = Camera(name="Lobby", location="Level 1", source_type="synthetic", simulated=True, scenario="smoke_fire"); db.add(lobby)
        gate = Camera(name="Gate", location="Car park", source_type="synthetic", simulated=True, scenario="normal"); db.add(gate); db.flush()
        db.add(Rule(camera_id=lobby.id, event_type="SMOKE_FIRE", enabled=True, min_duration=0, cooldown=30, zone=ZONE))
        record_transition(db, gate.id, None, "ONLINE")
    with Session.begin() as db:
        record_transition(db, gate.id, "ONLINE", "OFFLINE", "source_unavailable")


def login(name):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": name, "password": f"test-{name}-password"}).status_code == 200
    return client


def camera_id(name):
    with Session() as db: return db.scalar(select(Camera).where(Camera.name == name)).id


def make_incident():
    """Real pipeline: synthetic frame -> rule -> incident (same path the worker uses)."""
    with Session() as db: lobby = db.scalar(select(Camera).where(Camera.name == "Lobby"))
    state = TemporalRuleEvaluator()
    for _ in range(2): process(lobby, SyntheticAdapter("smoke_fire").read(), state)
    with Session() as db: return db.scalar(select(Incident).where(Incident.camera_id == lobby.id).order_by(Incident.id.desc()))


def test_logs_merge_filter_paginate_and_export():
    admin = login("admin")
    incident = make_incident()
    assert admin.post(f"/api/incidents/{incident.id}/action", json={"status": "ACKNOWLEDGED", "note": "=HYPERLINK(\"x\")"}).status_code == 200
    everything = admin.get("/api/logs?limit=200").json()["items"]
    kinds = {row["kind"] for row in everything}
    assert kinds == {"INCIDENT", "ACTION", "HEALTH"}
    assert [row["at"] for row in everything] == sorted((row["at"] for row in everything), reverse=True)
    action = next(row for row in everything if row["kind"] == "ACTION")
    assert action["actor"] == "admin" and action["to_status"] == "ACKNOWLEDGED" and action["incident_id"] == incident.id
    # Incident-only filter drops health rows; health-only filter drops incident/action rows
    assert {r["kind"] for r in admin.get("/api/logs?event_type=SMOKE_FIRE&limit=200").json()["items"]} == {"INCIDENT", "ACTION"}
    assert {r["kind"] for r in admin.get("/api/logs?health_status=OFFLINE").json()["items"]} == {"HEALTH"}
    assert all(r["camera"] == "Gate" for r in admin.get(f"/api/logs?camera_id={camera_id('Gate')}").json()["items"])
    future = (now() + timedelta(days=1)).isoformat()
    assert admin.get(f"/api/logs?start={future.replace('+00:00', 'Z')}").json()["items"] == []
    page = admin.get("/api/logs?limit=1").json()
    assert len(page["items"]) == 1 and page["has_more"] is True
    for bad in ("kinds=NOPE", "source_mode=x", "health_status=BAD", "start=yesterday", "start=2026-10-01T00:00:00"):
        assert admin.get(f"/api/logs?{bad}").status_code == 422, bad
    csv = admin.get("/api/logs/export.csv?kinds=ACTION")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.splitlines()
    assert lines[0].startswith("at,kind,camera") and "'=HYPERLINK" in csv.text  # formula neutralised
    assert TestClient(app).get("/api/logs").status_code == 401
    assert TestClient(app).get("/api/logs/export.csv").status_code == 401


def test_logs_search_matches_camera_and_note():
    admin = login("admin")
    assert {r["camera"] for r in admin.get("/api/logs?search=Car%20park").json()["items"]} == {"Gate"}
    assert all(r["kind"] == "ACTION" for r in admin.get("/api/logs?search=HYPERLINK").json()["items"])
