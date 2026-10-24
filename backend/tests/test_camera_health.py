"""Camera health history, uptime and API (branch: feature/camera-health)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test-vigilon.db")
os.environ.setdefault("VIGILON_SECRET_KEY", "test-signing-key-that-is-local-only")
os.environ.setdefault("VIGILON_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from datetime import timedelta
from pathlib import Path

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, Camera, CameraHealthEvent, Lease, Role, Session, User, engine, now
from app.main import app
from app.services.health_service import record_gap_after_crash, record_transition, summarize, worker_state


def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(User(username="operator", password_hash=PasswordHasher().hash("test-operator-password"), role=Role.OPERATOR))
        for name, location in (("Lobby", "Level 1"), ("Gate", "Car park"), ("Dock", "Dock 1")):
            db.add(Camera(name=name, location=location, source_type="synthetic", simulated=True, scenario="normal"))


def login(name):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": name, "password": f"test-{name}-password"}).status_code == 200
    return client


def camera_id(name):
    with Session() as db: return db.scalar(select(Camera).where(Camera.name == name)).id


def test_health_transitions_ignore_connecting_and_duplicates():
    cam = camera_id("Gate")
    with Session.begin() as db:
        assert record_transition(db, cam, "OFFLINE", "CONNECTING") is None        # start-up state is not history
        assert record_transition(db, cam, "CONNECTING", "ONLINE") is not None
    with Session.begin() as db:
        assert record_transition(db, cam, "CONNECTING", "ONLINE") is None         # same as last stored state
        offline = record_transition(db, cam, "ONLINE", "OFFLINE", "source_unavailable")
        assert offline.from_status == "ONLINE" and offline.error_category == "source_unavailable"
    with Session() as db:
        assert [e.to_status for e in db.scalars(select(CameraHealthEvent).where(CameraHealthEvent.camera_id == cam))] == ["ONLINE", "OFFLINE"]


def test_uptime_counts_only_known_time_and_unknown_after_worker_stops():
    cam = camera_id("Lobby")
    t0 = now() - timedelta(hours=2)
    with Session.begin() as db:
        db.add(CameraHealthEvent(camera_id=cam, at=t0, from_status="", to_status="ONLINE"))
        db.add(CameraHealthEvent(camera_id=cam, at=t0 + timedelta(minutes=90), from_status="ONLINE", to_status="OFFLINE", error_category="source_eof"))
    at = t0 + timedelta(hours=2)
    with Session() as db:
        online = summarize(db, [cam], 24, at, {"status": "ONLINE", "last_seen": at})[cam]
        assert online["uptime_pct"] == 75.0 and online["offline_events"] == 1           # 90 of 120 known minutes
        assert online["known_seconds"] == 7200
        # Worker's last heartbeat 10 min after the OFFLINE change: 90 min online + 10 min offline known, rest unknown
        stopped = summarize(db, [cam], 24, at, {"status": "OFFLINE", "last_seen": t0 + timedelta(minutes=100)})[cam]
        assert stopped["uptime_pct"] == 90.0 and stopped["known_seconds"] == 6000
        assert stopped["timeline"][-1]["status"] == "UNKNOWN"
        assert worker_state(db)["status"] == "OFFLINE"                                   # no lease row in this test DB


def test_uptime_ignores_worker_stopped_and_disabled_periods():
    cam = camera_id("Dock")
    t0 = now() - timedelta(hours=3)
    with Session.begin() as db:
        for minutes, frm, to in ((0, "", "ONLINE"), (60, "ONLINE", "UNKNOWN"), (90, "UNKNOWN", "ONLINE"), (120, "ONLINE", "DISABLED"), (150, "DISABLED", "ONLINE")):
            db.add(CameraHealthEvent(camera_id=cam, at=t0 + timedelta(minutes=minutes), from_status=frm, to_status=to))
    at = t0 + timedelta(minutes=180)
    with Session() as db:
        result = summarize(db, [cam], 24, at, {"status": "ONLINE", "last_seen": at})[cam]
    assert result["uptime_pct"] == 100.0 and result["known_seconds"] == 120 * 60   # only the 120 monitored minutes count
    assert [s["status"] for s in result["timeline"]][-5:] == ["ONLINE", "UNKNOWN", "ONLINE", "DISABLED", "ONLINE"]
    assert result["history_since"] is not None


def test_camera_health_api_shape_and_auth():
    assert TestClient(app).get("/api/camera-health").status_code == 401
    operator = login("operator")
    body = operator.get("/api/camera-health?hours=24").json()
    assert body["window_hours"] == 24 and body["worker"]["status"] == "OFFLINE"
    row = next(c for c in body["cameras"] if c["name"] == "Lobby")
    assert row["derived_state"] == "UNKNOWN"          # worker not running: never report last stored status as live
    assert "uptime_pct" in row and isinstance(row["timeline"], list)
    assert operator.get("/api/camera-health?hours=0").status_code == 422
    with Session.begin() as db:
        db.merge(Lease(id=1, owner="test-worker", expires=now() + timedelta(seconds=15)))
        db.get(Camera, camera_id("Gate")).status = "OFFLINE"
    gate = next(c for c in operator.get("/api/camera-health").json()["cameras"] if c["name"] == "Gate")
    assert gate["derived_state"] == "OFFLINE"
    events = operator.get(f"/api/camera-health/{camera_id('Gate')}/events").json()
    assert events[0]["to_status"] == "OFFLINE"
    assert operator.get("/api/camera-health/9999/events").status_code == 404
    with Session.begin() as db:
        db.merge(Lease(id=1, owner="", expires=now() - timedelta(seconds=1)))   # leave the worker "stopped" for later tests


def test_crash_gap_is_marked_unknown_once():
    """A worker that died without recording leaves a gap; the next worker marks it UNKNOWN exactly once."""
    heartbeat = now()
    with Session.begin() as db:
        assert record_gap_after_crash(db, heartbeat) >= 1
    with Session.begin() as db:
        assert record_gap_after_crash(db, heartbeat) == 0
        assert record_gap_after_crash(db, None) == 0
    with Session() as db:
        last = db.scalar(select(CameraHealthEvent).where(CameraHealthEvent.camera_id == camera_id("Gate")).order_by(CameraHealthEvent.id.desc()))
        assert last.to_status == "UNKNOWN" and last.from_status == "OFFLINE"


def test_migration_chain_is_linear_after_map_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini")); config.set_main_option("script_location", str(backend / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1                                   # one linear chain, no merge needed
    assert script.get_revision("0006_camera_health_events").down_revision == "0005_map_revision"
