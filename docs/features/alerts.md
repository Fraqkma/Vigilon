# In-app alerts

Branch: `feature/alerts` (needs `feature/camera-health`). MVP item: event alerts.

## What it adds

- A bell in the topbar with the unread incident count and a panel of recent alerts.
- A popup toast for every new incident, and for a camera going OFFLINE or recovering. The first poll after
  sign-in only remembers the newest ids, so old events never replay as a flood of popups.
- "View event" opens the incident in Control Center (selected and enlarged for action). "Camera health"
  opens the Camera Health page.
- Optional sound (starts after the first click, browser rule) and opt-in desktop notifications while
  the tab is in the background. These preferences are stored per browser in `localStorage`
  (`visor.alerts.prefs`).

## API

Both routes need the existing session cookie. The POST also keeps the existing same-origin check.

- `GET /api/alerts/feed?after_notification=0&after_health=0&limit=20` returns
  `{notifications:[{id, kind, read, created_at, incident_id, incident:{event_type,status,severity,simulated,camera_id,camera,first_seen}}], health:[{id,camera_id,camera,from_status,to_status,error_category,at}], cursor:{notification,health}, unread}`.
  Rows are newest first and strictly newer than the given ids. `cursor` holds the newest ids overall.
- `POST /api/alerts/read` with `{"notification_ids":[1,2]}` or `{"all":true}` returns `{unread}`.

Data sources:

- Incident alerts read the existing `notifications` rows, one per created incident.
- Camera alerts read `camera_health_events`, from the camera health feature.
- No new tables.

## Frontend

`frontend/features/alerts.js` registers through `window.VisorServices`. The shell starts it after
sign-in and stops it on logout or session expiry. It appends its own bell element into `#topbarSlot`
and never replaces the slot's content, so other services can share the slot. It polls every 4 s
while the tab is visible (also while hidden if desktop alerts are on). It loads `features/alerts.css`
itself.

## Limits

- No external delivery (LINE, Discord, e-mail, SMS). A notifier with durable delivery state is the next step.
- Read state is the existing shared `Notification.read` flag, not per user.
- Browsers throttle background-tab timers, so hidden-tab desktop alerts can be delayed up to about a minute.

## Tests

`backend/tests/test_alerts.py`:

- cursors return only newer rows
- incident details and SIMULATED label
- mark one or all read
- camera OFFLINE/recovery rows, newest first
- authentication and limit validation
