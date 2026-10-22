"""Explicit, local-only provisioning for the optional RTSP setup source."""

import socket
from urllib.parse import quote, urlsplit, urlunsplit

from dotenv import dotenv_values
from sqlalchemy import select

from .adapters import OpenCVAdapter
from .core import MEDIA_ROOTS, ROOT, fernet
from .db import Camera, Session


class CameraSetupError(ValueError):
    """A sanitized provisioning error that never includes supplied values."""


def _build_connection(base_url: str, username: str, password: str) -> str:
    if not base_url or not username or not password:
        missing = []
        if not base_url:
            missing.append("VIGILON_SETUP_CAMERA_URL")
        if not username:
            missing.append("VIGILON_SETUP_CAMERA_USERNAME")
        if not password:
            missing.append("VIGILON_SETUP_CAMERA_PASSWORD")
        raise CameraSetupError("Fill in these local .env fields before provisioning: " + ", ".join(missing) + ".")
    if any(ord(char) < 32 for char in base_url + username + password):
        raise CameraSetupError("Camera setup values contain unsupported control characters.")
    try:
        parts = urlsplit(base_url)
        host, port = parts.hostname, parts.port
    except ValueError:
        raise CameraSetupError("VIGILON_SETUP_CAMERA_URL is not a valid sanitized RTSP address.") from None
    if (
        parts.scheme not in ("rtsp", "rtsps")
        or not host
        or not port
        or not parts.path
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        raise CameraSetupError(
            "VIGILON_SETUP_CAMERA_URL must be an RTSP/RTSPS address with host, port and path, without embedded credentials or a fragment."
        )
    encoded_user = quote(username, safe="")
    encoded_password = quote(password, safe="")
    netloc_host = f"[{host}]" if ":" in host else host
    netloc = f"{encoded_user}:{encoded_password}@{netloc_host}:{port}"
    connection = urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))
    if len(connection) > 2048:
        raise CameraSetupError("The configured RTSP address and credentials exceed the supported length.")
    return connection


def _endpoint(connection: str) -> tuple[str, str, int | None, str, str]:
    parts = urlsplit(connection)
    return (parts.scheme.lower(), (parts.hostname or "").lower(), parts.port, parts.path, parts.query)


def _validate_with_existing_rtsp_policy(connection: str) -> None:
    try:
        OpenCVAdapter("rtsp", connection, MEDIA_ROOTS, timeout=5)._validate()
    except (OSError, ValueError, socket.error):
        raise CameraSetupError("Camera address failed the existing RTSP destination policy; no source was created.") from None
    except Exception:
        raise CameraSetupError("Camera address could not be validated; no source was created.") from None


def provision_camera(db, name: str, base_url: str, username: str, password: str, *, validate=True):
    """Create or reuse one exact RTSP source without changing existing records."""
    if not name or not name.strip():
        raise CameraSetupError("VIGILON_SETUP_CAMERA_NAME must not be blank.")
    if len(name) > 120:
        raise CameraSetupError("VIGILON_SETUP_CAMERA_NAME must be at most 120 characters.")
    connection = _build_connection(base_url.strip(), username, password)
    if validate:
        _validate_with_existing_rtsp_policy(connection)

    target = _endpoint(connection)
    for camera in db.scalars(select(Camera).where(Camera.source_type == "rtsp")).all():
        if camera.secret:
            try:
                existing_connection = fernet.decrypt(camera.secret.encode()).decode()
            except Exception:
                raise CameraSetupError("An existing RTSP source could not be checked with the current encryption key; no source was changed.") from None
        else:
            existing_connection = camera.connection
        if not existing_connection:
            continue
        try:
            same_endpoint = _endpoint(existing_connection) == target
        except Exception:
            same_endpoint = False
        if same_endpoint:
            if existing_connection == connection:
                return camera, False
            raise CameraSetupError("An RTSP source already exists for this camera address/path with different credentials; no source was changed.")

    same_name = db.scalar(select(Camera).where(Camera.name == name))
    if same_name:
        raise CameraSetupError("The requested camera name already belongs to another source; no source was changed.")

    camera = Camera(
        name=name,
        location="",
        source_type="rtsp",
        connection="",
        secret=fernet.encrypt(connection.encode()).decode(),
        enabled=True,
        simulated=False,
        scenario="normal",
        processing_fps=2,
        resize_limit=1280,
        timeout_seconds=5,
        reconnect_min_seconds=1,
        reconnect_max_seconds=30,
    )
    db.add(camera)
    db.flush()
    return camera, True


def provision_from_environment(env_file=None):
    values = dotenv_values(env_file or ROOT / ".env", interpolate=False)
    name = (values.get("VIGILON_SETUP_CAMERA_NAME") or "Hikvision Test Camera").strip()
    base_url = (values.get("VIGILON_SETUP_CAMERA_URL") or "").strip()
    username = values.get("VIGILON_SETUP_CAMERA_USERNAME") or "admin"
    password = values.get("VIGILON_SETUP_CAMERA_PASSWORD") or ""
    with Session.begin() as db:
        camera, created = provision_camera(db, name, base_url, username, password)
        result = {"camera_id": camera.id, "name": camera.name, "status": "CREATED" if created else "ALREADY_CONFIGURED"}
    return result
