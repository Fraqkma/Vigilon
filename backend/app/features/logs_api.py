"""Unified, searchable history: incidents, operator actions and camera health changes.

`GET /api/logs` merges three existing sources (no new event table): `incidents`, `transitions`
(operator acknowledge/resolve/false alarm with actor and note) and `camera_health_events`.
`GET /api/logs/export.csv` returns the same filtered rows as CSV (capped at 5,000).
Detail views use `GET /api/incidents/{id}` from `incidents_api.py`.
"""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import or_, select

from ..db import Camera, CameraHealthEvent, Incident, IncidentStatus, Session, Transition, User
from ..services.health_service import RECORDED_STATES, aware

KINDS = ("INCIDENT", "ACTION", "HEALTH")
MAX_OFFSET = 5000
EXPORT_LIMIT = 5000


def _time(value: str | None, name: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, f"{name} must be an ISO timestamp")
    if parsed.tzinfo is None:
        raise HTTPException(422, f"{name} must include a timezone (for example Z)")
    return parsed.astimezone(timezone.utc)  # SQLite compares stored UTC text; normalise offsets first


class LogFilter:
    """Validated query parameters shared by the list and CSV routes."""

    def __init__(self, kinds: str = Query(default="INCIDENT,ACTION,HEALTH", max_length=40),
                 camera_id: int | None = Query(default=None, gt=0), event_type: str | None = Query(default=None, max_length=32),
                 status: IncidentStatus | None = None, severity: str | None = Query(default=None, max_length=16),
                 source_mode: str | None = None, health_status: str | None = None,
                 start: str | None = None, end: str | None = None, search: str | None = Query(default=None, max_length=120)):
        self.kinds = {k.strip().upper() for k in kinds.split(",") if k.strip()}
        if not self.kinds or self.kinds - set(KINDS):
            raise HTTPException(422, "kinds must be a comma list of INCIDENT, ACTION, HEALTH")
        if source_mode not in (None, "LIVE", "SIMULATED"):
            raise HTTPException(422, "source_mode must be LIVE or SIMULATED")
        if health_status not in (None, *RECORDED_STATES):
            raise HTTPException(422, "health_status must be ONLINE, OFFLINE, DISABLED or UNKNOWN")
        self.camera_id, self.event_type, self.status, self.severity = camera_id, event_type, status, severity
        self.source_mode, self.health_status, self.search = source_mode, health_status, (search or "").strip()
        self.start, self.end = _time(start, "start"), _time(end, "end")
        # Incident-only filters cannot apply to health rows, and a health-only filter excludes incident rows
        self.incident_filters = bool(event_type or status or severity or source_mode)


def collect(db, f: LogFilter, need: int) -> list[dict]:
    """Newest-first merged rows; each source fetches at most `need` rows."""
    rows: list[dict] = []
    like = f"%{f.search}%" if f.search else None

    if "INCIDENT" in f.kinds and not f.health_status:
        q = select(Incident, Camera).join(Camera, Incident.camera_id == Camera.id)
        if f.camera_id: q = q.where(Incident.camera_id == f.camera_id)
        if f.event_type: q = q.where(Incident.event_type == f.event_type)
        if f.status: q = q.where(Incident.status == f.status)
        if f.severity: q = q.where(Incident.severity == f.severity)
        if f.source_mode: q = q.where(Incident.simulated.is_(f.source_mode == "SIMULATED"))
        if f.start: q = q.where(Incident.first_seen >= f.start)
        if f.end: q = q.where(Incident.first_seen <= f.end)
        if like: q = q.where(or_(Camera.name.ilike(like), Camera.location.ilike(like), Incident.event_type.ilike(like)))
        for incident, camera in db.execute(q.order_by(Incident.first_seen.desc(), Incident.id.desc()).limit(need)):
            rows.append({"kind": "INCIDENT", "id": incident.id, "at": aware(incident.first_seen), "camera_id": camera.id, "camera": camera.name,
                         "location": camera.location, "event_type": incident.event_type, "status": incident.status.value,
                         "severity": incident.severity, "simulated": incident.simulated, "incident_id": incident.id,
                         "summary": f"{incident.event_type.replace('_', ' ')} detected"})

    if "ACTION" in f.kinds and not f.health_status:
        q = (select(Transition, Incident, Camera, User).join(Incident, Transition.incident_id == Incident.id)
             .join(Camera, Incident.camera_id == Camera.id).join(User, Transition.actor_id == User.id))
        if f.camera_id: q = q.where(Incident.camera_id == f.camera_id)
        if f.event_type: q = q.where(Incident.event_type == f.event_type)
        if f.status: q = q.where(Transition.to_status == f.status.value)
        if f.severity: q = q.where(Incident.severity == f.severity)
        if f.source_mode: q = q.where(Incident.simulated.is_(f.source_mode == "SIMULATED"))
        if f.start: q = q.where(Transition.at >= f.start)
        if f.end: q = q.where(Transition.at <= f.end)
        if like: q = q.where(or_(Camera.name.ilike(like), Incident.event_type.ilike(like), User.username.ilike(like), Transition.note.ilike(like)))
        for t, incident, camera, actor in db.execute(q.order_by(Transition.at.desc(), Transition.id.desc()).limit(need)):
            rows.append({"kind": "ACTION", "id": t.id, "at": aware(t.at), "camera_id": camera.id, "camera": camera.name, "location": camera.location,
                         "event_type": incident.event_type, "status": t.to_status, "severity": incident.severity, "simulated": incident.simulated,
                         "incident_id": incident.id, "actor": actor.username, "note": t.note, "from_status": t.from_status, "to_status": t.to_status,
                         "summary": f"{t.from_status} → {t.to_status} by {actor.username}"})

    if "HEALTH" in f.kinds and not f.incident_filters:
        q = select(CameraHealthEvent, Camera).join(Camera, CameraHealthEvent.camera_id == Camera.id)
        if f.camera_id: q = q.where(CameraHealthEvent.camera_id == f.camera_id)
        if f.health_status: q = q.where(CameraHealthEvent.to_status == f.health_status)
        if f.start: q = q.where(CameraHealthEvent.at >= f.start)
        if f.end: q = q.where(CameraHealthEvent.at <= f.end)
        if like: q = q.where(or_(Camera.name.ilike(like), Camera.location.ilike(like), CameraHealthEvent.error_category.ilike(like)))
        for e, camera in db.execute(q.order_by(CameraHealthEvent.at.desc(), CameraHealthEvent.id.desc()).limit(need)):
            rows.append({"kind": "HEALTH", "id": e.id, "at": aware(e.at), "camera_id": camera.id, "camera": camera.name, "location": camera.location,
                         "status": e.to_status, "from_status": e.from_status, "to_status": e.to_status, "error_category": e.error_category,
                         "summary": f"{e.from_status or '—'} → {e.to_status}" + (f" ({e.error_category})" if e.error_category else "")})

    rank = {"INCIDENT": 2, "ACTION": 1, "HEALTH": 0}
    rows.sort(key=lambda r: (r["at"], rank[r["kind"]], r["id"]), reverse=True)
    return rows


def _csv_cell(value) -> str:
    """Neutralise spreadsheet formulas (CSV injection) in exported text cells."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def build_router(deps) -> APIRouter:
    router = APIRouter(tags=["logs"])

    def public(row: dict) -> dict:
        return {**row, "at": deps.utc_iso(row["at"])}

    @router.get("/api/logs")
    def logs(f: LogFilter = Depends(), limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0, le=MAX_OFFSET),
             user=Depends(deps.current_user)):
        with Session() as db:
            rows = collect(db, f, offset + limit + 1)
        page = rows[offset:offset + limit]
        return {"items": [public(r) for r in page], "offset": offset, "limit": limit, "has_more": len(rows) > offset + limit}

    @router.get("/api/logs/export.csv")
    def export_logs(f: LogFilter = Depends(), user=Depends(deps.current_user)):
        with Session() as db:
            rows = collect(db, f, EXPORT_LIMIT)[:EXPORT_LIMIT]
        out = io.StringIO()
        writer = csv.writer(out)
        columns = ["at", "kind", "camera", "location", "event_type", "status", "severity", "simulated", "summary", "actor", "note", "error_category", "incident_id"]
        writer.writerow(columns)
        for row in rows:
            row = public(row)
            writer.writerow([_csv_cell(row.get(c)) for c in columns])
        return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="vigilon-logs.csv"', "Cache-Control": "private, no-store"})

    return router
