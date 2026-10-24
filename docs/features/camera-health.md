# Camera health and uptime history

Branch: `feature/camera-health` (needs `feature/registry-navigation`). MVP item: camera management and health.

## What it adds

- Sidebar page **Camera Health** (after Event List): every source with its state, frame age, measured
  processed FPS, uptime percentage, a 24 h / 7 day timeline, offline and reconnect counts, and a
  per-camera state history.
- The ingestion worker records camera state changes, so uptime is based on recorded history, not a guess.
- Admins can enable or disable a camera from the page (with a confirmation). Anyone signed in can open
  that camera's settings, rules and zones.

## Data

Alembic `0006_camera_health_events` (after `0005_map_revision`) adds
`camera_health_events(id, camera_id → cameras ON DELETE CASCADE, at, from_status, to_status, error_category)`.

The worker writes a row when a camera moves between ONLINE, OFFLINE, DISABLED and UNKNOWN:

- CONNECTING is a short start-up state and is not stored.
- The first state seen in each worker run is stored once, deduplicated against the last stored state.
- A clean worker stop records UNKNOWN, so stopped time is not counted as online.
- When a worker starts after its predecessor died without recording (crash or kill), it marks each camera
  UNKNOWN from the predecessor's last heartbeat. A crash is never counted as online time.

## API

Both routes need the existing session cookie (operator or admin).

- `GET /api/camera-health?hours=24` (1–168) → `{generated_at, window_hours, worker:{status,last_seen}, cameras:[...camera fields, derived_state, frame_age_seconds, uptime_pct, known_seconds, offline_events, last_change, history_since, timeline:[{status,start,end}]]}`
  - `derived_state` is one of:
    - DISABLED
    - UNKNOWN: the worker is not running, so the stored status is only the last known value
    - ONLINE
    - STALE: online, but no fresh frame for 8 s
    - CONNECTING
    - OFFLINE
  - `uptime_pct` = ONLINE ÷ (ONLINE + OFFLINE) recorded time. UNKNOWN, DISABLED and unrecorded time are
    excluded. It is `null` until some monitored time exists.
  - `history_since` is when the first recorded state in the window begins. The page shows "Recording since …"
    so a short history does not look like an outage.
- `GET /api/camera-health/{camera_id}/events?limit=50` → newest-first state changes. Returns 404 for an
  unknown camera.

## Frontend

`frontend/features/health.js` registers through `window.VisorPages` and loads `features/health.css`
itself. It polls every 5 s while the tab is visible. Processed FPS is the change in the worker's
processed-frame counter between two polls, so it appears after the second poll. Enable and disable reuse
`PATCH /api/cameras/{id}`.

Other features can build on `backend/app/services/health_service.py`. For example, alerts read
`camera_health_events` for "camera offline / recovered" toasts.

## Limits

- History starts when this version first runs. A camera disabled before the worker starts has no
  DISABLED row until it changes state.
- Uptime is shown for the selected window only. Older rows are kept; there is no retention job yet.

## Tests

`backend/tests/test_camera_health.py`:

- transitions are stored without CONNECTING noise or duplicates
- uptime counts only known time, and time after the worker stops counts as unknown
- worker-stopped and disabled periods are excluded from uptime
- the crash gap is marked once
- API shape, authentication and 404
- the migration chain stays linear (`0006` follows `0005_map_revision`)
