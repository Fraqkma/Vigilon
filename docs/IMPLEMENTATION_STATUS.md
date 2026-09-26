# Implementation status

## Progress

1. Inspected the repository and runtimes; preserved the user-supplied `task.md`. **Done.**
2. Created root repository guidance and this evidence ledger. **Done.**
3. Implemented infrastructure, source adapters, and a runnable local synthetic vertical slice. **Done.**
4. Ran checks supported by this environment and recorded unavailable checks below. **Done.**

## Implemented and verified

- Windows Python 3.10 local setup, `.env` placeholder filling without printing generated secrets, SQLite Alembic migration, idempotent admin bootstrap, and idempotent demo seed.
- FastAPI API, signed HTTP-only role-aware login, Argon2 password hashes, authenticated JPEG preview/evidence, administrator-only source/rule endpoints, and operator incident actions.
- Separate worker process with a singleton expiring lease, per-source reader threads, bounded one-frame queues, replace-oldest behavior, configuration polling, configurable timeout/reconnect backoff, health counters, stale preview reporting, and persisted redacted source errors.
- Synthetic source changes its rendered frame and supports `normal`, `obstruction`, `person_down`, and `smoke_fire`. The scenarios are simulated and visually marked.
- Typed detection contract; unavailable real detector reports no availability/results. Separate temporal rule, incident persistence/deduplication, and notification services exercise minimum duration, cooldown, active incident deduplication, snapshot evidence, and operator transition history.
- OpenCV local file adapter with generated MJPEG AVI fixture, observed EOF, and media-path escape rejection.
- Evidence retention removes aged snapshot files and preserves the incident record with an expired-evidence marker; covered by an automated test.
- Normalized polygon/rectangle zone validation and a browser editor that maps clicks over contain-letterboxed previews. Rule minimum duration/cooldown/timezone values can be saved. Schedule execution is not implemented.
- Docker Compose/YAML parses locally; Python modules compile; browser JavaScript syntax passes. Browser QA exercised login, navigation, camera preview, zone editor, logout, and 375/768/1440 px layouts with no horizontal overflow or console errors.
- End-to-end live API + worker smoke completed on SQLite: login, worker heartbeat, simulated JPEG preview, incident creation, JPEG evidence serving, acknowledge, resolve, and persisted history.

## Implemented, verification unavailable

- PostgreSQL-specific migration/runtime and full Docker Compose startup. Docker/Compose are not installed in this environment.
- RTSP/RTSPS OpenCV FFmpeg adapter, destination allowlist, actual open/read timeout behavior against a publisher or hardware, NVR stream compatibility, and local video codecs beyond the generated MJPEG test fixture.
- Docker image builds, Nginx frontend proxy, CI execution on GitHub, production-sized retention load, and shutdown under a truly wedged decoder.

## Simulated

- Only the generated source produces obstruction, person-down, or smoke/fire events. Its fixture draws visible event evidence into the same frame referenced by the incident snapshot, and incidents/UI include a `SIMULATED` badge.
- No real AI inference, accuracy, safety certification, identity, or intent inference is claimed. Real detector plugins are unavailable.

## Verification record

- `pip install -r requirements.lock` and `pip install -r requirements-dev.lock`: passed in the project-local `.venv`; `pip check`: no broken requirements.
- `python -m app.commands migrate` on a fresh SQLite file: all three Alembic revisions applied and the source configuration columns/tables were present. Upgrade was also applied to the persistent local demo database.
- `python -m compileall -q backend/app backend/migrations`: passed.
- `python -m pytest -q backend/tests`: **7 passed**, with one upstream Starlette/AnyIO deprecation warning.
- `node --check frontend/app.js`: passed. Compose YAML parsed with PyYAML.
- `python scripts/smoke_demo.py` against the running local API and worker: passed login, ONLINE worker, changing SIMULATED JPEG preview, OBSTRUCTION incident, JPEG evidence, RESOLVED status, and two history entries.
- Playwright browser QA: login/logout and zone editor opened; visible API requests returned 200 after authentication; 375, 768, and 1440 px layouts had no horizontal overflow; zero browser console errors. No committed visual baseline exists, so no pixel comparison was made.
- Docker/Compose executable is absent. Docker image builds, Compose runtime, PostgreSQL runtime, and CI job were not run. No physical camera or RTSP publisher was available.

## Planned or incomplete

- Real detector evaluation data and a temporally validated person-down or obstruction plugin.
- Monitoring schedule execution and full source settings/connectivity check workflow.
- External notification delivery, clips, user-management UI, automated retention schedule, and production deployment hardening.
- Frontend is dependency-free JavaScript rather than the suggested React/TypeScript/Vite stack; there is no frontend package build/typecheck.
- Password reset/session revocation and full administrative account lifecycle.
