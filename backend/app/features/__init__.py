"""Feature API routers, discovered automatically.

Every module in this package that defines `build_router(deps)` is mounted once at startup by
`register_features(app, FeatureDeps(...))` in main.py. A new feature is therefore one new file here;
it does not edit main.py. Routers receive the shared API helpers through `FeatureDeps` instead of
importing `app.main`, which avoids circular imports. Modules are mounted in name order and must not
redefine an existing route.
"""
import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class FeatureDeps:
    current_user: Callable      # FastAPI dependency: any signed-in user
    require_admin: Callable     # FastAPI dependency: ADMIN only
    utc_iso: Callable           # datetime -> canonical UTC ISO string
    incident_dict: Callable     # (db, Incident) -> public incident shape (same as /api/incidents)
    camera_dict: Callable       # Camera -> public camera shape (same as /api/cameras)


def register_features(app, deps: FeatureDeps) -> list[str]:
    """Mount every feature router; returns the mounted module names (useful in tests and logs)."""
    mounted = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        build = getattr(module, "build_router", None)
        if callable(build):
            app.include_router(build(deps))
            mounted.append(info.name)
    return mounted


APP_SCRIPT_MARKER = '<script src="/assets/app.js'


def inject_feature_scripts(html: str, frontend: Path) -> str:
    """Frontend counterpart of `register_features`: load every `frontend/features/*.js` that index.html
    does not list yet, just before app.js, so a feature branch never edits index.html.

    Deferred scripts run in document order, so injected features register on `window.VisorPages` /
    `window.VisorServices` before the shell starts. Test files (`*.test.js`) are skipped.
    """
    if APP_SCRIPT_MARKER not in html:
        return html
    tags = []
    for path in sorted((frontend / "features").glob("*.js")):
        src = f"/assets/features/{path.name}"
        if path.name.endswith(".test.js") or f'"{src}"' in html or f'"{src}?' in html:
            continue
        tags.append(f'<script src="{src}" defer></script>\n  ')
    return html.replace(APP_SCRIPT_MARKER, "".join(tags) + APP_SCRIPT_MARKER, 1)
