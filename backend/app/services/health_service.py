"""Camera health history: recording state changes (worker side) and uptime summaries (API side).

Only these states are stored: ONLINE, OFFLINE, DISABLED and UNKNOWN (worker stopped cleanly).
CONNECTING is a short start-up state and is deliberately not stored, so a worker restart does not
create noise. Uptime is derived from these recorded changes; a crashed worker cannot record its own
downtime, so the time after its last heartbeat is reported as unknown, never as online.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..db import CameraHealthEvent, Lease, now

RECORDED_STATES = ("ONLINE", "OFFLINE", "DISABLED", "UNKNOWN")
LEASE_SECONDS = 15  # worker refreshes its lease for 15 s on every loop (see worker.py)


def aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC like the rest of the API."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def record_transition(db, camera_id: int, previous: str | None, current: str, category: str = "", at: datetime | None = None):
    """Store one state change if it is meaningful and differs from the last stored state.

    Called by the worker in the same transaction that writes the camera status.
    Returns the new event, or None when nothing was stored.
    """
    if current not in RECORDED_STATES or previous == current:
        return None
    last = db.scalar(select(CameraHealthEvent).where(CameraHealthEvent.camera_id == camera_id)
                     .order_by(CameraHealthEvent.id.desc()).limit(1))
    if last is not None and last.to_status == current:
        return None  # e.g. ONLINE -> CONNECTING -> ONLINE after a config reload: no real change
    event = CameraHealthEvent(camera_id=camera_id, at=at or now(), from_status=(last.to_status if last else (previous or ""))[:24],
                              to_status=current, error_category=(category or "")[:48] if current == "OFFLINE" else "")
    db.add(event)
    return event


def record_gap_after_crash(db, last_heartbeat: datetime | None) -> int:
    """Called once when a worker starts. If the previous worker stopped without recording (crash, kill,
    power loss), mark each camera UNKNOWN from that worker's last heartbeat so the gap is not counted
    as ONLINE. A clean stop already recorded UNKNOWN; DISABLED cameras stay DISABLED."""
    if not last_heartbeat:
        return 0
    added = 0
    for camera_id in db.scalars(select(CameraHealthEvent.camera_id).distinct()).all():
        last = db.scalar(select(CameraHealthEvent).where(CameraHealthEvent.camera_id == camera_id)
                         .order_by(CameraHealthEvent.id.desc()).limit(1))
        if last and last.to_status not in ("UNKNOWN", "DISABLED") and aware(last.at) < last_heartbeat:
            db.add(CameraHealthEvent(camera_id=camera_id, at=last_heartbeat, from_status=last.to_status, to_status="UNKNOWN"))
            added += 1
    return added


def worker_state(db, at: datetime | None = None) -> dict:
    """Worker heartbeat from the existing lease row: ONLINE while the lease is unexpired."""
    at = at or now()
    lease = db.get(Lease, 1)
    expires = aware(lease.expires) if lease else None
    if not expires:
        return {"status": "OFFLINE", "last_seen": None}
    last_seen = expires - timedelta(seconds=LEASE_SECONDS)
    return {"status": "ONLINE" if expires > at else "OFFLINE", "last_seen": min(last_seen, at)}


def summarize(db, camera_ids: list[int], hours: int = 24, at: datetime | None = None, worker: dict | None = None) -> dict[int, dict]:
    """Uptime and a status timeline per camera over the last `hours`.

    uptime_pct = ONLINE seconds / (ONLINE + OFFLINE seconds), i.e. the share of monitored time the
    camera delivered frames (None when no such time is recorded yet). Time before a camera's first
    recorded state, while the worker was stopped (UNKNOWN), after the last heartbeat of an offline
    worker, and while the camera was DISABLED is excluded from the percentage.
    """
    at = at or now()
    start = at - timedelta(hours=hours)
    worker = worker or worker_state(db, at)
    known_until = at if worker["status"] == "ONLINE" or not worker["last_seen"] else max(start, worker["last_seen"])
    result: dict[int, dict] = {}
    for camera_id in camera_ids:
        before = db.scalar(select(CameraHealthEvent).where(CameraHealthEvent.camera_id == camera_id, CameraHealthEvent.at < start)
                           .order_by(CameraHealthEvent.at.desc(), CameraHealthEvent.id.desc()).limit(1))
        events = db.scalars(select(CameraHealthEvent).where(CameraHealthEvent.camera_id == camera_id, CameraHealthEvent.at >= start)
                            .order_by(CameraHealthEvent.at, CameraHealthEvent.id)).all()
        # Build [segment_start, segment_end, state] covering the window
        cursor, state, segments = start, (before.to_status if before else None), []
        for event in events:
            event_at = min(aware(event.at), at)
            if event_at > cursor:
                segments.append((cursor, event_at, state))
            cursor, state = max(cursor, event_at), event.to_status
        if known_until > cursor:
            segments.append((cursor, known_until, state))
        if at > max(cursor, known_until):
            segments.append((max(cursor, known_until), at, None))  # worker offline: unknown
        # Uptime counts monitored time only: ONLINE vs OFFLINE. Worker-stopped (UNKNOWN/None) and
        # admin-disabled periods are shown on the timeline but neither help nor hurt the percentage.
        online = sum((b - a).total_seconds() for a, b, s in segments if s == "ONLINE")
        known = sum((b - a).total_seconds() for a, b, s in segments if s in ("ONLINE", "OFFLINE"))
        first_known = next((a for a, b, s in segments if s is not None and s != "UNKNOWN"), None)
        last_event = events[-1] if events else before
        result[camera_id] = {
            "uptime_pct": round(online / known * 100, 1) if known > 0 else None,
            "known_seconds": round(known),
            "offline_events": sum(1 for e in events if e.to_status == "OFFLINE"),
            "last_change": aware(last_event.at) if last_event else None,
            "history_since": first_known,   # None when nothing is recorded inside the window
            "timeline": [{"status": s or "UNKNOWN", "start": a, "end": b} for a, b, s in segments if b > a],
        }
    return result
