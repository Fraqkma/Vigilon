# Visor implementation

## Checklist

- [x] Inspect existing routes, UI, persistence, Hub, jobs, and source contracts before edits.
- [x] Build Overview, Live Monitoring, Video Analysis, Incidents, AI Modules, and Settings destinations.
- [x] Connect camera edit/create/probe, worker preview, module/scenario/rule configuration, incident filters/actions, video import and FILE jobs to the application APIs.
- [x] Keep source credentials private, module readiness distinct from camera connectivity, and monitoring schedules unavailable where not enforced.
- [x] Add authenticated bounded imports, real progress/result state, timeline evidence/media and JSON/CSV exports without schema duplication.
- [x] Add an explicit generated SIMULATED file-job path for QA; uploaded footage is never processed with simulated detections.
- [x] Add focused API contract tests and run browser checks at 1440, 768, and 375 CSS pixels.
- [x] Update operational docs with observed outcomes and explicit real-model/camera/deployment limits.

## Existing application map

- `frontend/app.js`, `frontend/analysis.js`, `frontend/index.html`, and `frontend/style.css`: dependency-free responsive SPA, camera forms, normalized geometry editor, live grid, file workflow, timeline and operator UI.
- `backend/app/main.py`: cookie auth/CSRF, camera/rule APIs, test connection probe, authenticated import/media/frame, FILE jobs, overview, incidents/actions and Hub administration.
- `backend/app/db.py`: existing camera, rule, incident, evidence, transitions, notification, user, and worker lease persistence. This work required no schema migration.
- `backend/app/worker.py`, `backend/app/adapters.py`, `backend/app/file_jobs.py`: separate live ingestion, source adapters, reload handling, and persistent bounded FILE worker.
- `backend/app/ai_hub.py`: package validation/runtime/reload state; model templates remain `people_vehicle` and `fire_smoke`.

## API additions and extensions

- `POST /api/cameras/test-connection`: admin-only, bounded, redacted probe through the existing adapter policy.
- `POST /api/ai/imports`, `GET /api/ai/imports/{id}/frame`, `GET /api/ai/imports/{id}/media`, `DELETE /api/ai/imports/{id}`: admin import/delete and authenticated media/frame access. Generated IDs; files stay in `VIGILON_IMPORT_DIR`; 512 MiB per file and 100-file/5 GiB aggregate limits.
- `POST /api/ai/demo-jobs`: admin-only explicit generated fixture. It writes a short synthetic AVI then queues the normal persistent FILE job worker; there is no simulated mode for uploaded inputs.
- `GET /api/incidents`: bounded filter/search/pagination over current incident model fields.
- Existing camera/module/rule/job/result/evidence APIs remain authoritative. The frontend consumes current OpenAPI shapes rather than a parallel API.

## Verification evidence

- Backend: `PYTHONPATH=backend .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=.data/visor-pytest-final-pass --tb=short backend/tests`: 20 passed, one Starlette/AnyIO deprecation warning. Run outside the Windows sandbox because OpenCV video fixtures and pytest cleanup were blocked inside it.
- Static checks: Python `compileall`, `node --check frontend/app.js`, and `node --check frontend/analysis.js` passed.
- Browser, isolated SQLite demo on `127.0.0.1:8765`: login and six screens; worker-published synthetic preview/freshness; normalized rectangle save and reload; import/decode with duration and representative frame; honest missing-runtime-weight message; generated SIMULATED job through FILE worker to completed result/timeline; incident acknowledgement reflected by server; responsive widths 1440/768/375 without page overflow after a mobile-nav correction.
- Browser codec check: OpenCV decoded generated AVI, but Chromium did not play that codec. Result events and media-relative timestamp remained accessible; no conversion was attempted.
- Existing browser console log contains earlier deliberate invalid geometry responses (422), unauthenticated requests while checking protection (401), connection refusals during server restart, and missing evidence on the isolated seed record (404). Valid save, preview, job, import, and acknowledgement flows completed.

## Boundaries

`HUB_INFRA_READY` is distinct from `REAL_MODEL_VALIDATED` and `CAMERA_VALIDATED`. The two catalog packages are missing weights. The generated fixture is explicitly simulated and tests UI/job integration only. PyTorch/Ultralytics inference, physical camera/NVR compatibility, PostgreSQL/Compose runtime, and browser playback of a supported real-media codec were not verified.
