"""Feature router registry, single-incident read and asset revalidation header (branch: feature/registry-navigation)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test-vigilon.db")
os.environ.setdefault("VIGILON_SECRET_KEY", "test-signing-key-that-is-local-only")
os.environ.setdefault("VIGILON_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from pathlib import Path

from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters import SyntheticAdapter
from app.db import Base, Camera, Incident, Role, Rule, Session, User, engine
from app.features import FeatureDeps, inject_feature_scripts, register_features
from app.main import app
from app.rules import TemporalRuleEvaluator
from app.worker import process

ZONE = {"type": "polygon", "points": [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]}


def setup_module():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(User(username="operator", password_hash=PasswordHasher().hash("test-operator-password"), role=Role.OPERATOR))
        camera = Camera(name="Registry lobby", location="Level 1", source_type="synthetic", simulated=True, scenario="smoke_fire")
        db.add(camera); db.flush()
        db.add(Rule(camera_id=camera.id, event_type="SMOKE_FIRE", enabled=True, min_duration=0, cooldown=30, zone=ZONE))


def make_incident():
    """Real pipeline: synthetic frame -> rule -> incident (same path the worker uses)."""
    with Session() as db: camera = db.scalar(select(Camera).where(Camera.name == "Registry lobby"))
    state = TemporalRuleEvaluator()
    for _ in range(2): process(camera, SyntheticAdapter("smoke_fire").read(), state)
    with Session() as db: return db.scalar(select(Incident).where(Incident.camera_id == camera.id)).id


def test_incident_detail_matches_list_shape_and_requires_login():
    incident_id = make_incident()
    with TestClient(app) as anon:
        assert anon.get(f"/api/incidents/{incident_id}").status_code == 401
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": "operator", "password": "test-operator-password"}).status_code == 200
    detail = client.get(f"/api/incidents/{incident_id}")
    assert detail.status_code == 200
    listed = next(item for item in client.get("/api/incidents").json() if item["id"] == incident_id)
    assert detail.json() == listed                                   # same public shape as the list endpoint
    assert detail.json()["simulated"] is True
    assert client.get("/api/incidents/999999").status_code == 404


def test_register_features_mounts_feature_modules_once():
    probe = FastAPI()
    deps = FeatureDeps(current_user=lambda: None, require_admin=lambda: None, utc_iso=str, incident_dict=dict, camera_dict=dict)
    mounted = register_features(probe, deps)
    assert "incidents_api" in mounted
    assert mounted == sorted(mounted)                                # deterministic order, independent of merge order
    paths = [route.path for route in app.routes]
    assert paths.count("/api/incidents/{incident_id}") == 1           # no duplicate route on the real app


def test_frontend_assets_revalidate_but_api_is_untouched():
    client = TestClient(app)
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200 and asset.headers["cache-control"] == "no-cache"
    assert client.get("/api/health").headers.get("cache-control") != "no-cache"


def test_feature_scripts_are_injected_once_before_app_js(tmp_path):
    (tmp_path / "features").mkdir()
    for name in ("listed.js", "zeta.js", "alpha.js", "maps.test.js"):
        (tmp_path / "features" / name).write_text("")
    html = ('<script src="/assets/features/listed.js?v=1" defer></script>\n'
            '  <script src="/assets/app.js?v=1" defer></script>')
    out = inject_feature_scripts(html, tmp_path)
    assert out.count("/assets/features/listed.js") == 1                # already listed: not duplicated
    assert "maps.test.js" not in out                                    # tests never load in the browser
    assert out.index("features/alpha.js") < out.index("features/zeta.js") < out.index("/assets/app.js")
    assert inject_feature_scripts("<p>no shell</p>", tmp_path) == "<p>no shell</p>"


def test_home_page_lists_every_shipped_feature_script_exactly_once():
    html = TestClient(app).get("/").text
    for path in (Path(__file__).resolve().parents[2] / "frontend" / "features").glob("*.js"):
        expected = 0 if path.name.endswith(".test.js") else 1
        assert html.count(f"/assets/features/{path.name}") == expected, path.name
