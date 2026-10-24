# Control Center assessment

## Current surfaces and evidence

- UI entry: `frontend/index.html` serves the dependency-free SPA; `frontend/app.js` owns login, route selection, feature rendering, and a shared same-origin `api()` helper. `frontend/analysis.js` adds analysis helpers. `frontend/style.css` contains global dark-theme and responsive rules.
- Routing is in-memory (`page`) via sidebar buttons. There are six destinations: Overview, Live Monitoring, Video Analysis, Incidents, AI Modules, and Settings. There is no deep-link router.
- Polling is page-specific but timer ownership is shared (`pageTimer`, `previewTimer`) and `render()` clears both before replacing the view. Live preview uses authenticated `/api/cameras/{id}/preview` refreshes. No abort controller/request generation guard exists.
- Existing API capabilities: `/api/overview`; camera list/create/patch/preview/rules; incident list/action/evidence; notifications; AI modules and jobs/imports. Camera, incident, transition, rule and notification persistence is in SQLAlchemy models and Alembic migrations.
- `Camera.location` is the only location metadata. No site/plan/device contact/specification model exists. Current migrations end at `0003_source_timeouts`.
- Backend is a single FastAPI `main.py`; frontend is a large classic-script `app.js`. Preserve existing entry points and extract the new Control Center as a scoped feature module injected with the existing API transport and session context.

## Minimal implementation plan

1. Add a standalone assessment (this document), then a Control Center module and scoped CSS, mounted from the existing shell with Overview remaining available as a separate destination.
2. Add minimal `FloorPlan` and `CameraPlacement` persistence plus nullable camera manufacturer/model/specification/contact/response-note fields. Keep plan image bytes in a private generated-name directory; serve only through authenticated API routes. Removing a placement or plan never deletes a camera or incident.
3. Add a portable Alembic migration, bounded CRUD/upload endpoints, normalized placement validation, and admin-only edits. Reuse existing camera and incident APIs for live state/actions/evidence.
4. Add focused backend tests and module contract docs; validate with existing test/syntax/migration/browser tooling where available.

## Proposed feature boundaries

- `frontend/features/control-center/`: composition and selection coordination; `maps/`, `monitoring/`, `incidents/`, and `devices/` modules expose mount/update/dispose functions and receive API/state callbacks. Existing `app.js` remains the shell and owns authentication.
- `backend/app` remains the FastAPI boundary for this increment; keep new persistence and request schemas cohesive and do not duplicate incidents or source ingestion.
- New API data is limited to floor plans, placements, and nullable camera context metadata. All camera/incident facts remain authoritative in existing records/endpoints.
- Sequence: implement backend contracts/migration and tests, then feature module/layout, then docs and validation. Do not modify `.env`, configured sources, or the local database.

## Baseline and limitations

- The repository reports existing six-screen Visor browser QA and 20 passing tests in `docs/VISOR_IMPLEMENTATION.md`; those are historical baseline evidence, not rerun results.
- Current `git status` showed a pre-existing modification to `task.md`; it is user work and must be preserved. `docs/CODEX-NAVIGATION-GUIDE.md` is absent as the repository instructions already note.
- No model weights or new camera/AI claims are part of this milestone. Database work must use a disposable temporary SQLite DB; PostgreSQL requires Docker availability.
