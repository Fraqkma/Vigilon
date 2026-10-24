"""Optional device photo per camera (branch: feature/device-image)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test-vigilon.db")
os.environ.setdefault("VIGILON_SECRET_KEY", "test-signing-key-that-is-local-only")
os.environ.setdefault("VIGILON_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from io import BytesIO

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.db import Base, Camera, Role, Session, User, engine
from app.features.devices_api import DEVICE_IMAGE_DIR
from app.main import app


def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(User(username="admin", password_hash=PasswordHasher().hash("test-admin-password"), role=Role.ADMIN))
        db.add(User(username="operator", password_hash=PasswordHasher().hash("test-operator-password"), role=Role.OPERATOR))
        db.add(Camera(name="Photo cam", location="Lab", source_type="synthetic", simulated=True, scenario="normal"))


def teardown_module():
    for path in DEVICE_IMAGE_DIR.glob("camera-*"):
        path.unlink(missing_ok=True)


def login(name):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": name, "password": f"test-{name}-password"}).status_code == 200
    return client


def camera_id():
    with Session() as db: return db.scalar(select(Camera).where(Camera.name == "Photo cam")).id


def jpeg_with_exif(size=(3000, 2000)) -> bytes:
    image = Image.new("RGB", size, (40, 90, 140))
    exif = Image.Exif(); exif[0x010F] = "PhoneMaker"; exif[0x0131] = "private-app 1.0"   # metadata that must not survive
    out = BytesIO(); image.save(out, format="JPEG", exif=exif); return out.getvalue()


def test_upload_replace_read_and_remove_device_photo():
    admin, cam = login("admin"), camera_id()
    row = next(c for c in admin.get("/api/cameras").json() if c["id"] == cam)
    assert row["device_image_version"] is None
    assert admin.get(f"/api/cameras/{cam}/device-image").status_code == 404

    saved = admin.post(f"/api/cameras/{cam}/device-image", content=jpeg_with_exif(), headers={"Content-Type": "image/jpeg"})
    assert saved.status_code == 200 and saved.json()["device_image_version"]
    photo = login("operator").get(f"/api/cameras/{cam}/device-image")            # operators can view
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    with Image.open(BytesIO(photo.content)) as stored:
        assert max(stored.size) == 1280                                            # shrunk to a reference photo
        assert not dict(stored.getexif())                                           # EXIF (maker, GPS, ...) stripped by re-encoding
    assert next(c for c in admin.get("/api/cameras").json() if c["id"] == cam)["device_image_version"] == saved.json()["device_image_version"]

    png = BytesIO(); Image.new("RGBA", (64, 48), (0, 0, 0, 0)).save(png, format="PNG")
    assert admin.post(f"/api/cameras/{cam}/device-image", content=png.getvalue()).status_code == 200
    assert admin.get(f"/api/cameras/{cam}/device-image").headers["content-type"] == "image/png"
    assert sorted(p.name for p in DEVICE_IMAGE_DIR.glob(f"camera-{cam}.*")) == [f"camera-{cam}.png"]   # old JPEG replaced

    assert admin.delete(f"/api/cameras/{cam}/device-image").status_code == 204
    assert admin.get(f"/api/cameras/{cam}/device-image").status_code == 404


def test_device_photo_rejects_bad_input_and_non_admins():
    admin, cam = login("admin"), camera_id()
    assert admin.post(f"/api/cameras/{cam}/device-image", content=b"GIF89a....").status_code == 415
    assert admin.post(f"/api/cameras/{cam}/device-image", content=b"\xff\xd8\xff not really a jpeg").status_code == 415
    assert admin.post(f"/api/cameras/{cam}/device-image", content=b"").status_code == 413
    assert admin.post("/api/cameras/9999/device-image", content=jpeg_with_exif((10, 10))).status_code == 404
    operator = login("operator")
    assert operator.post(f"/api/cameras/{cam}/device-image", content=jpeg_with_exif((10, 10))).status_code == 403
    assert operator.delete(f"/api/cameras/{cam}/device-image").status_code == 403
    assert TestClient(app).get(f"/api/cameras/{cam}/device-image").status_code == 401
    assert admin.post(f"/api/cameras/{cam}/device-image", content=jpeg_with_exif((10, 10)), headers={"Origin": "https://evil.example"}).status_code == 403
