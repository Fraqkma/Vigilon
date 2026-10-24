"""In-app alert feed: new incident notifications plus camera health changes.

The browser polls `GET /api/alerts/feed` with the last ids it has seen and gets only newer rows.
Notifications are the existing `notifications` table (one row per created incident); health rows
come from `camera_health_events`. Read state is the existing shared `Notification.read` flag
(not per user). No external delivery (LINE/Discord/e-mail) happens here.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from ..db import Camera, CameraHealthEvent, Incident, Notification, Session


class ReadIn(BaseModel):
    notification_ids: list[int] = Field(default_factory=list, max_length=200)
    all: bool = False


def build_router(deps) -> APIRouter:
    router = APIRouter(prefix="/api/alerts", tags=["alerts"])

    @router.get("/feed")
    def alert_feed(after_notification: int = Query(default=0, ge=0), after_health: int = Query(default=0, ge=0),
                   limit: int = Query(default=20, ge=1, le=100), user=Depends(deps.current_user)):
        with Session() as db:
            camera_names = {c.id: c.name for c in db.scalars(select(Camera))}
            notes = db.scalars(select(Notification).where(Notification.id > after_notification)
                               .order_by(Notification.id.desc()).limit(limit)).all()
            incidents = {i.id: i for i in db.scalars(select(Incident).where(Incident.id.in_([n.incident_id for n in notes])))} if notes else {}
            health = db.scalars(select(CameraHealthEvent).where(CameraHealthEvent.id > after_health)
                                .order_by(CameraHealthEvent.id.desc()).limit(limit)).all()
            notifications = []
            for n in notes:
                incident = incidents.get(n.incident_id)
                notifications.append({
                    "id": n.id, "kind": n.kind, "read": n.read, "created_at": deps.utc_iso(n.created_at), "incident_id": n.incident_id,
                    "incident": None if incident is None else {
                        "event_type": incident.event_type, "status": incident.status.value, "severity": incident.severity,
                        "simulated": incident.simulated, "camera_id": incident.camera_id,
                        "camera": camera_names.get(incident.camera_id, f"Camera {incident.camera_id}"),
                        "first_seen": deps.utc_iso(incident.first_seen)},
                })
            return {
                "notifications": notifications,
                "health": [{"id": e.id, "camera_id": e.camera_id, "camera": camera_names.get(e.camera_id, f"Camera {e.camera_id}"),
                            "from_status": e.from_status, "to_status": e.to_status, "error_category": e.error_category,
                            "at": deps.utc_iso(e.at)} for e in health],
                # Cursors are the newest ids overall so a client can start "from now" without replaying history
                "cursor": {"notification": db.scalar(select(func.max(Notification.id))) or 0,
                           "health": db.scalar(select(func.max(CameraHealthEvent.id))) or 0},
                "unread": db.scalar(select(func.count()).select_from(Notification).where(Notification.read.is_(False))) or 0,
            }

    @router.post("/read")
    def mark_alerts_read(data: ReadIn, user=Depends(deps.current_user)):
        with Session.begin() as db:
            if data.all:
                db.execute(update(Notification).where(Notification.read.is_(False)).values(read=True))
            elif data.notification_ids:
                db.execute(update(Notification).where(Notification.id.in_(data.notification_ids)).values(read=True))
        with Session() as db:
            return {"unread": db.scalar(select(func.count()).select_from(Notification).where(Notification.read.is_(False))) or 0}

    return router
