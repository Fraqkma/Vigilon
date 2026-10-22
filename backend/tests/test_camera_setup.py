import pytest
from pathlib import Path
from uuid import uuid4
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session as OrmSession

from app import camera_setup
from app.camera_setup import CameraSetupError, provision_camera
from app.db import Base, Camera
from app.core import fernet


@pytest.fixture
def camera_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with OrmSession(engine) as db:
        yield db
    engine.dispose()


def test_camera_setup_is_idempotent_and_keeps_credentials_encrypted(camera_db, monkeypatch):
    monkeypatch.setattr(camera_setup, "_validate_with_existing_rtsp_policy", lambda _connection: None)
    args = ("Hikvision Test Camera", "rtsp://192.168.1.102:554/Streaming/Channels/101", "admin", "pw #$ with spaces")

    first, created = provision_camera(camera_db, *args)
    camera_db.commit()
    second, created_again = provision_camera(camera_db, *args)

    assert created is True
    assert created_again is False
    assert second.id == first.id
    assert camera_db.scalar(select(func.count()).select_from(Camera)) == 1
    assert second.connection == ""
    stored = fernet.decrypt(second.secret.encode()).decode()
    assert second.secret != stored
    assert "pw%20%23%24%20with%20spaces" in stored
    assert second.simulated is False and second.enabled is True


def test_camera_setup_rejects_blank_password_without_creating_source(camera_db, monkeypatch):
    monkeypatch.setattr(camera_setup, "_validate_with_existing_rtsp_policy", lambda _connection: None)
    with pytest.raises(CameraSetupError) as error:
        provision_camera(
            camera_db,
            "Hikvision Test Camera",
            "rtsp://192.168.1.102:554/Streaming/Channels/101",
            "admin",
            "",
        )

    assert "VIGILON_SETUP_CAMERA_PASSWORD" in str(error.value)
    assert camera_db.scalar(select(func.count()).select_from(Camera)) == 0


def test_camera_setup_never_overwrites_or_echoes_credentials(camera_db, monkeypatch):
    monkeypatch.setattr(camera_setup, "_validate_with_existing_rtsp_policy", lambda _connection: None)
    provision_camera(
        camera_db,
        "Hikvision Test Camera",
        "rtsp://192.168.1.102:554/Streaming/Channels/101",
        "admin",
        "original-secret",
    )
    camera_db.commit()

    with pytest.raises(CameraSetupError) as error:
        provision_camera(
            camera_db,
            "Hikvision Test Camera",
            "rtsp://192.168.1.102:554/Streaming/Channels/101",
            "admin",
            "replacement-secret",
        )

    assert "original-secret" not in str(error.value)
    assert "replacement-secret" not in str(error.value)
    assert camera_db.scalar(select(func.count()).select_from(Camera)) == 1
    existing = camera_db.scalar(select(Camera))
    assert "original-secret" in fernet.decrypt(existing.secret.encode()).decode()


def test_camera_setup_does_not_replace_unrelated_camera_with_same_name(camera_db, monkeypatch):
    monkeypatch.setattr(camera_setup, "_validate_with_existing_rtsp_policy", lambda _connection: None)
    camera_db.add(Camera(name="Hikvision Test Camera", source_type="synthetic", connection="", simulated=True))
    camera_db.commit()

    with pytest.raises(CameraSetupError, match="already belongs to another source"):
        provision_camera(
            camera_db,
            "Hikvision Test Camera",
            "rtsp://192.168.1.102:554/Streaming/Channels/101",
            "admin",
            "camera-secret",
        )

    rows = camera_db.scalars(select(Camera)).all()
    assert len(rows) == 1
    assert rows[0].source_type == "synthetic"


def test_camera_setup_runs_existing_destination_policy_before_write(camera_db, monkeypatch):
    def reject(_connection):
        raise CameraSetupError("Camera address failed the existing RTSP destination policy; no source was created.")

    monkeypatch.setattr(camera_setup, "_validate_with_existing_rtsp_policy", reject)
    with pytest.raises(CameraSetupError, match="existing RTSP destination policy"):
        provision_camera(
            camera_db,
            "Hikvision Test Camera",
            "rtsp://192.168.1.102:554/Streaming/Channels/101",
            "admin",
            "camera-secret",
        )
    assert camera_db.scalar(select(func.count()).select_from(Camera)) == 0


def test_provision_command_output_does_not_include_camera_credentials(camera_db, monkeypatch, capsys):
    from app import commands

    monkeypatch.setattr(camera_setup, "Session", sessionmaker(bind=camera_db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(camera_setup, "_validate_with_existing_rtsp_policy", lambda _connection: None)
    env_path = Path(".data") / f"camera-setup-test-{uuid4().hex}.env"
    env_path.write_text(
        "VIGILON_SETUP_CAMERA_NAME='Hikvision Test Camera'\n"
        "VIGILON_SETUP_CAMERA_URL=rtsp://192.168.1.102:554/Streaming/Channels/101\n"
        "VIGILON_SETUP_CAMERA_USERNAME=admin\n"
        "VIGILON_SETUP_CAMERA_PASSWORD='do-not-print-${TOKEN} # password'\n",
        encoding="utf-8",
    )
    original_provision_from_environment = camera_setup.provision_from_environment
    monkeypatch.setattr(camera_setup, "provision_from_environment", lambda: original_provision_from_environment(env_path))
    monkeypatch.setattr("sys.argv", ["app.commands", "provision-camera"])

    try:
        commands.main()
    finally:
        env_path.unlink(missing_ok=True)
    output = capsys.readouterr().out

    assert "CREATED" in output
    assert "do-not-print-${TOKEN}" not in output
    assert "rtsp://" not in output
    stored = camera_db.scalar(select(Camera))
    assert "do-not-print-%24%7BTOKEN%7D%20%23%20password" in fernet.decrypt(stored.secret.encode()).decode()
