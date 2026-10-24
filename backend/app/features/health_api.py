"""Camera health overview: current derived state, frame age, uptime and recorded state changes."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..db import Camera, CameraHealthEvent, Session, now
from ..services.health_service import aware, summarize, worker_state

STALE_SECONDS = 8  # same freshness limit as camera_dict()["preview_stale"]


def derived_state(camera, worker_online: bool, frame_age: float | None) -> str:
    """One honest label per camera; connection, freshness and worker heartbeat stay distinguishable."""
    if not camera.enabled:
        return "DISABLED"
    if not worker_online:
        return "UNKNOWN"          # worker is not running, stored status is only the last known value
    if camera.status == "ONLINE":
        return "STALE" if frame_age is None or frame_age > STALE_SECONDS else "ONLINE"
    return camera.status or "OFFLINE"   # OFFLINE or CONNECTING


def build_router(deps) -> APIRouter:
    router = APIRouter(prefix="/api/camera-health", tags=["camera-health"])

    @router.get("")
    def camera_health(hours: int = Query(default=24, ge=1, le=168), user=Depends(deps.current_user)):
        at = now()
        with Session() as db:
            cameras = db.scalars(select(Camera).order_by(Camera.id)).all()
            worker = worker_state(db, at)
            history = summarize(db, [c.id for c in cameras], hours, at, worker)
            rows = []
            for camera in cameras:
                last_frame = aware(camera.last_frame)
                age = round((at - last_frame).total_seconds(), 1) if last_frame else None
                summary = history[camera.id]
                rows.append({
                    **deps.camera_dict(camera),
                    "derived_state": derived_state(camera, worker["status"] == "ONLINE", age),
                    "frame_age_seconds": age,
                    "uptime_pct": summary["uptime_pct"],
                    "known_seconds": summary["known_seconds"],
                    "offline_events": summary["offline_events"],
                    "last_change": deps.utc_iso(summary["last_change"]),
                    "history_since": deps.utc_iso(summary["history_since"]),
                    "timeline": [{"status": s["status"], "start": deps.utc_iso(s["start"]), "end": deps.utc_iso(s["end"])} for s in summary["timeline"]],
                })
            return {"generated_at": deps.utc_iso(at), "window_hours": hours,
                    "worker": {"status": worker["status"], "last_seen": deps.utc_iso(worker["last_seen"])}, "cameras": rows}

    @router.get("/{camera_id}/events")
    def camera_health_events(camera_id: int, limit: int = Query(default=50, ge=1, le=200), user=Depends(deps.current_user)):
        with Session() as db:
            if not db.get(Camera, camera_id):
                raise HTTPException(404, "Camera not found")
            events = db.scalars(select(CameraHealthEvent).where(CameraHealthEvent.camera_id == camera_id)
                                .order_by(CameraHealthEvent.id.desc()).limit(limit)).all()
            return [{"id": e.id, "at": deps.utc_iso(e.at), "from_status": e.from_status, "to_status": e.to_status,
                     "error_category": e.error_category} for e in events]

    return router
