"""Local webcam source: device index validation and API gates (branch: feature/webcam-source)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test-vigilon.db")
os.environ.setdefault("VIGILON_SECRET_KEY", "test-signing-key-that-is-local-only")
os.environ.setdefault("VIGILON_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.db import Base, Camera, Role, Session, User, engine
from app.main import app
from app.webcam_adapter import WebcamAdapter, parse_webcam_index
from app.worker import SourceRunner


def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(User(username="admin", password_hash=PasswordHasher().hash("test-admin-password"), role=Role.ADMIN))
        db.add(User(username="operator", password_hash=PasswordHasher().hash("test-operator-password"), role=Role.OPERATOR))


def login(name):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": name, "password": f"test-{name}-password"}).status_code == 200
    return client


def test_webcam_index_accepts_only_0_to_9():
    assert parse_webcam_index("0") == 0 and parse_webcam_index(" 3 ") == 3 and parse_webcam_index(9) == 9
    for bad in ("-1", "10", "abc", "../dev/video0", "0; rm", "", "1.5", "rtsp://x"):
        with pytest.raises(ValueError):
            parse_webcam_index(bad)


def test_webcam_camera_api_validation_and_permissions():
    admin = login("admin")
    made = admin.post("/api/cameras", json={"name": "Laptop cam", "source_type": "webcam", "connection": "1"})
    assert made.status_code == 200 and made.json()["source_type"] == "webcam" and made.json()["simulated"] is False
    default = admin.post("/api/cameras", json={"name": "Default cam", "source_type": "webcam"})
    assert default.status_code == 200                                           # blank index means device 0
    with Session() as db: assert db.get(Camera, default.json()["id"]).connection == "0"
    assert admin.post("/api/cameras", json={"name": "Bad cam", "source_type": "webcam", "connection": "/dev/video0"}).status_code == 422
    assert admin.post("/api/cameras", json={"name": "Sim cam", "source_type": "webcam", "connection": "0", "scenario": "smoke_fire"}).status_code == 422
    # Webcam passes the source-type gate; assignment then requires a runtime-ready module (none in tests)
    assert admin.put(f"/api/cameras/{made.json()['id']}/modules", json={"modules": ["people_vehicle"]}).status_code == 409
    assert login("operator").post("/api/cameras", json={"name": "x", "source_type": "webcam", "connection": "0"}).status_code == 403


def test_worker_builds_a_webcam_adapter_without_opening_the_device():
    with Session() as db:
        camera = db.query(Camera).filter(Camera.name == "Laptop cam").one()
    adapter = SourceRunner.adapter(type("Runner", (), {"camera": camera})())
    assert isinstance(adapter, WebcamAdapter) and adapter.index == 1 and adapter.cap is None
