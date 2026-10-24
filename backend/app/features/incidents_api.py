"""Single incident read: `GET /api/incidents/{id}` in the same public shape as `GET /api/incidents`.

Used to open one incident from another page (alert popup, logs) even when it is outside the
Control Center's current list filter. Read-only; actions stay on `POST /api/incidents/{id}/action`.
"""
from fastapi import APIRouter, Depends, HTTPException

from ..db import Incident, Session


def build_router(deps) -> APIRouter:
    router = APIRouter(tags=["incidents"])

    @router.get("/api/incidents/{incident_id}")
    def incident_detail(incident_id: int, user=Depends(deps.current_user)):
        with Session() as db:
            incident = db.get(Incident, incident_id)
            if not incident:
                raise HTTPException(404, "Incident not found")
            return deps.incident_dict(db, incident)

    return router
