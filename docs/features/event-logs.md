# Event logs: historical search and CSV export

Branch: `feature/event-logs` (needs `feature/camera-health`). MVP item: historical log search.

## What it adds

- Sidebar page **Event Logs** (after Event List): incidents, operator actions (acknowledge / resolve /
  false alarm with actor and note) and camera health changes in one list, newest first.
- Filters:
  - Quick ranges: hour, 24 h, 7 days, 30 days, all.
  - A custom from/to range.
  - Record type.
  - Camera.
  - Event type.
  - Incident status.
  - Severity.
  - Live or simulated.
  - Camera state.
  - Free-text search: camera, location, event, person or note.
- Paging with Newer and Older.
- **Export CSV** with the same filters.
- A read-only detail panel with evidence and operator history. **Open in Control Center** takes the incident
  there to act on it.

## API

Both routes need the existing session cookie (operator or admin).

- `GET /api/logs?kinds=INCIDENT,ACTION,HEALTH&camera_id=&event_type=&status=&severity=&source_mode=LIVE|SIMULATED&health_status=&start=&end=&search=&limit=50&offset=0`
  returns `{items:[{kind,id,at,camera_id,camera,location,event_type,status,severity,simulated,incident_id,actor,note,from_status,to_status,error_category,summary}], offset, limit, has_more}`.
  Rules:
  - `start` and `end` must be ISO timestamps with a timezone.
  - Incident filters (`event_type`, `status`, `severity`, `source_mode`) exclude HEALTH rows.
  - `health_status` excludes INCIDENT and ACTION rows.
  - `limit` is at most 200 and `offset` at most 5000.
  - Invalid values return 422.
- `GET /api/logs/export.csv` takes the same filters and returns at most 5,000 rows as CSV. Cells that begin
  with `= + - @` are prefixed with `'` to block spreadsheet formula injection.
- The detail panel uses `GET /api/incidents/{id}` from the registry branch.

No new tables. The log merges the existing `incidents` and `transitions` tables with `camera_health_events`.

## Frontend

`frontend/features/logs.js` registers through `window.VisorPages` and loads `features/logs.css` itself.
It does not poll. Stale responses are dropped by a request counter. When the event-action evidence
feature is merged, the detail panel uses its boxed evidence view; otherwise it shows the plain
snapshot.

## Limits

- The date inputs use the browser's local time. Timestamps are shown in the configured application timezone.
- Search is a simple substring match, which is fine for MVP volumes.

## Tests

`backend/tests/test_event_logs.py` covers:

- merging the three sources, newest first
- filters, kind exclusion, time range and paging
- validation: 422 on bad input
- CSV export with formula neutralisation
- search
- authentication
