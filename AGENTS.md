# Vigilon contributor guide

## Product and scope

Vigilon adds event review, evidence snapshots, notifications, and operator actions to existing CCTV cameras and NVR channels that the user owns or administers. It supplements certified safety and fire systems; it is not a camera, replacement NVR, universal compatibility layer, or certified alarm. Use only explicitly configured and authorized sources. Never scan networks, guess credentials, bypass authentication, or claim compatibility that has not been verified.

The local CPU demo uses generated video and simulated events. Real detector plugins are currently unavailable. Do not imply that the simulated scenarios are real inference or report accuracy/safety claims. Do not add facial recognition, identity profiling, or criminal-intent inference without a separately approved product requirement.

## Before changing code

- Read applicable parent and nested `AGENTS.md` instructions, inspect `git status`, and preserve existing user/team work. `task.md` records the original implementation assignment; use it for context, not as a reason to recreate the project or expand the current task.
- Read `README.md` and `docs/IMPLEMENTATION_STATUS.md` when relevant. Treat the code and checks you can reproduce as evidence; status records can become stale.
- `docs/CODEX-NAVIGATION-GUIDE.md` is referenced by a supplied Codex supplement but is not present in this checkout. Do not assume its surface map or PR workflow exists; use the repository map below and actual runtime instructions.
- Respect active Codex model, sandbox, approval controls, settings, installed skills, MCP tools, and hooks. Tool availability claims in documents are not proof of runtime availability. Do not change global Codex/ECC configuration, credentials, machine-wide settings, or reinstall tools unless explicitly asked. Do not bypass a hook or approval. Inspect and verify any hook-generated changes.
- Use relevant installed skills where they improve the requested work. Use Context7 for unfamiliar/version-sensitive APIs when available, and verify against locked versions. Use Playwright for authorized local browser checks when available. GitHub integration does not itself authorize publishing, messaging, merging, or settings changes. Do not export private code, footage, credentials, or evidence to external services without authorization.
- Multi-agent execution is optional. Follow the active session’s delegation rules; team roles below do not by themselves authorize spawning agents.
- Make focused changes. Do not remove failing tests, erase data, reset Git, force-push, or deploy publicly as a routine repair. Do not add placeholder-only layers, speculative infrastructure, or unnecessary global tools.

## Repository map and current implementation

- `backend/app/main.py`: FastAPI routes, request validation, authentication/authorization, previews, evidence, and operator actions.
- `backend/app/db.py`, `backend/migrations/`: SQLAlchemy persistence and Alembic schema history. Use migrations for durable schema changes; do not replace them with `create_all`.
- `backend/app/worker.py`: separate ingestion process, lease, source lifecycle, frame publication, detector/rule orchestration.
- `backend/app/adapters.py`: typed synthetic and OpenCV local-file/RTSP source adapters.
- `backend/app/detection.py`, `backend/app/rules.py`: detector contract, unavailable real detector, simulated scenarios, and temporal rule evaluation.
- `backend/app/services/`: incident/evidence persistence and in-app notification behavior.
- `backend/app/retention.py`: explicit evidence-retention cleanup command; no periodic scheduler currently invokes it.
- `backend/tests/`: API, worker, persistence, evidence, permissions, geometry, and adapter checks.
- `frontend/`: dependency-free JavaScript single-page operator interface. It is not React/Vite and has no package-manager build step.
- `compose.yaml`, `infra/`: local container configuration and Docker/Nginx assets.
- `scripts/`: Windows/Linux environment setup and local API/worker smoke check.
- `sample_data/`: generated demo media; keep real footage and evidence out of Git.
- `docs/`: architecture, compatibility, security, detector contract, roadmap, and implementation evidence.

The implemented demo includes login/logout, overview, source management, scenario selection, authenticated JPEG preview/evidence, normalized rectangle/polygon zone editing, rule minimum-duration/cooldown/timezone configuration, incident actions/history, and simulated in-app notification behavior. The zone editor and timezone setting exist; monitoring schedules are not evaluated. Full source settings/connectivity check, real detector, user-management UI, external notification delivery, clips, scheduled retention, password reset, and session revocation are not implemented. Consult `docs/IMPLEMENTATION_STATUS.md` for current evidence and limitations.

## Team ownership and integration

| Responsibility | Primary area | Integration deliverable |
| --- | --- | --- |
| PM / integration | Scope, infrastructure, CI, contracts, integrated demo | Reproducible startup and compatible interfaces |
| Compatibility | RTSP/NVR/file/synthetic adapters, decoding, source health | Timestamped frames and truthful source status |
| AI data/model | Dataset rights, annotation, splits, baseline/evaluation | Versioned model, provenance, evaluation report |
| AI inference/rules | Runtime, tracking, temporal/zone rules | Typed observations and event candidates |
| Full stack | API, DB, authentication, incidents, notifications, UI | Authorized operator workflow and persistent history |

Coordinate shared schemas, migrations, lockfiles, and Compose changes. Document contract changes and keep fixtures/examples aligned with API schemas. Additive changes are preferred; breaking changes need a coordinated migration plan. Ownership does not justify leaving integration defects unexplained.

## Architecture and source handling

- Keep API and ingestion worker separately runnable in the shared backend. Do not decode continuous streams inside HTTP request handlers.
- PostgreSQL is the intended Compose deployment database; SQLite is the local convenience/demo mode and does not prove PostgreSQL behavior. Exercise PostgreSQL-specific migrations, locking, timestamps, and concurrent updates on PostgreSQL when available.
- Frames are transient binary data and must not be stored in database rows. Preserve the implemented bounded shared-volume latest-frame handoff and its atomic publication/metadata consistency. Persist configuration, incidents, audit history, evidence references, and worker/source health metadata.
- Use the existing typed `SourceAdapter`, `Frame`, detector, and rule contracts. Evolve them explicitly rather than introducing incompatible duplicate payloads.
- Source adapters must have bounded connect/read/reconnect behavior, cleanup, and bounded buffers. Drop stale frames under load and track drops. A failing source must not stall other sources or indefinitely block shutdown. Keep worker lease ownership recoverable after failure and configuration reload behavior documented.
- Distinguish worker offline, disabled source, disconnected camera, stale frame, file EOF, and unavailable detector. A visually static scene alone does not prove a frozen feed.
- RTSP/RTSPS is administrator-configured and must validate protocol and destination against the configured private CIDR allowlist; reject inappropriate service ports and redact credentials. Only connect to the exact authorized stream supplied. No arbitrary URL proxy, network discovery, credential guessing, or shell-interpolated source command.
- Local media paths must resolve beneath `VIGILON_MEDIA_DIR`; prevent traversal. Real RTSP/hardware/codec compatibility remains unverified unless a specific test matrix says otherwise. ONVIF capability must not be inferred from RTSP support.
- Reuse ingestion frames for previews; never open an upstream session per viewer. Browser RTSP playback is not assumed.

## Detection, zones, rules, and demo boundaries

- Keep inference, temporal/zone evaluation, incident persistence/deduplication, and notification delivery separate.
- Detector plugins advertise availability and event types. An unavailable real detector must produce no detections. Simulated scenarios run only on synthetic sources and must be reproducible, visibly marked `SIMULATED`, and clearly described in API/UI/evidence.
- Preserve the distinction between raw model observation, temporal/rule evaluation, candidate incident/deduplication, and operator-confirmed interpretation. A confidence score is not automatically a calibrated probability.
- Use UTC-aware timestamps internally. Zone geometry uses validated normalized coordinates mapped consistently through preview resizing/letterboxing. Validate dimensions, points, and nonzero area.
- Rule duration/cooldown and timezone configuration are supported. Schedule execution is not implemented: never imply saved timezone/schedule data means a monitoring schedule is being enforced. Do not count a long source outage as continuous event duration.
- Do not accumulate detections across gaps as if continuously observed. Define recurrence and cooldown behavior explicitly; continuing observations update an existing logical incident rather than creating a flood or reopening a resolved incident on every frame.
- Future real detector work should begin with one scoped event, a consented/licensed evaluation set, temporal reasoning, provenance, event-level precision/recall, false alerts per camera-hour, detection delay, missed events, throughput, and stated hardware/test conditions. Do not download large models or send footage to hosted AI without authorization.

## Incidents, evidence, authentication, and privacy

- Incident statuses are `NEW`, `ACKNOWLEDGED`, `RESOLVED`, and `FALSE_ALARM`; severity is separate. Validate transitions server-side and retain actor, timestamp, and note history. Manual resolution does not prove the scene cleared.
- Capture a snapshot corresponding to the triggering frame, not an unrelated later image. Serve preview/evidence only through authenticated routes with safe generated names and path checks. Snapshots do not imply clips. In-app notifications do not imply external delivery.
- Retention cleanup is explicitly run with `python -m app.retention`; no automatic schedule currently invokes it. Expired files should be reflected in metadata while preserving incident/audit history.
- Keep passwords, keys, sessions, authenticated source URLs, real footage, and evidence out of Git, logs, API responses, screenshots, and handoff text. Never print `.env` or global auth/config files for diagnosis.
- Preserve Argon2 password hashing, encrypted source credentials with an externally supplied key, role checks, authenticated evidence/preview, cookie protections, and CSRF checks for cookie-authenticated mutations. Do not claim password reset, session revocation, or a complete account lifecycle until implemented and verified.
- Losing the encryption key can make stored camera URLs unrecoverable; preserve/document backup implications. Bind local services safely; do not expose the database/evidence publicly by default.

## Environment and verified commands

Discover current commands from README, scripts, lockfiles, and entry points before execution; commands below reflect this checkout’s documented local flow. Use `.venv` rather than global Python. Setup scripts fill only recognized placeholders and leave configured `.env` values unchanged; inspect bootstrap/seed effects before using against existing data. Bootstrap preserves an existing administrator. Demo seeding changes the synthetic scenario.

Windows PowerShell, from repository root (API and worker run in separate terminals):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\scripts\setup.ps1
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.commands migrate
.\.venv\Scripts\python.exe -m app.commands bootstrap-admin
.\.venv\Scripts\python.exe -m app.commands seed-demo --scenario obstruction
```

API terminal:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Worker terminal:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.worker
```

Local application URL: `http://127.0.0.1:8000`. For tests and smoke check, install `requirements-dev.lock`; run smoke while API and worker are running:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pytest -q backend/tests
node --check frontend/app.js
.\.venv\Scripts\python.exe scripts\smoke_demo.py
```

The `smoke_demo.py` command exercises a running local API and worker; it does not test a physical camera. There is no separate frontend lint/typecheck/build command. On Linux, use `bash scripts/setup.sh`, `.venv/bin/python`, and `PYTHONPATH=backend`; full commands are documented in `README.md`. The documented Compose path is `docker compose build`, start `db`, run the one-shot `migrate`, `bootstrap`, and `seed-demo` services, then start `api worker web`. Do not call Compose parsing or config validation a runtime test. PostgreSQL/Compose verification is unverified unless status records new evidence.

Do not kill unrelated local processes; track only processes started for the task and stop them cleanly. Do not change machine-wide execution policy to run scripts. Never run destructive database/volume operations as an automatic repair.

## Verification and status reporting

Select focused tests for changed behavior. Important boundaries include migrations on clean and intended databases; lease recovery; independent source failure, timeout/reconnect/EOF; bounded frames and snapshot correspondence; temporal thresholds/cooldown/recurrence; zone mapping; roles/CSRF/secrets; preview/evidence access; retention metadata; and simulation labels. For UI changes verify relevant API-backed actions and loading/empty/error states at applicable viewport sizes. A browser screen opening is not proof a save/action works.

Use generated fixtures and authorized local RTSP publishers where practical. Clearly distinguish adapter/protocol testing from testing a physical camera/NVR. If Docker/PostgreSQL is unavailable, run independent checks and report that limitation; SQLite is not equivalent verification.

Update relevant docs when behavior changes: README startup and operation; `docs/IMPLEMENTATION_STATUS.md` evidence and implementation boundary; architecture, camera compatibility, detector, security, or roadmap docs when their subject changes. Status must separate implemented and verified, implemented but unverified, simulated, and planned. Never claim a test, camera access, or deployment that did not happen. Keep code identifiers and shared technical docs in English; communicate with users in Thai unless they request otherwise.

Final handoff should state what changed and why, key files/contracts, checks actually run and outcomes, untested paths/blockers, exact relevant commands, and concrete next work/owner. Keep the handoff concise and evidence-based.
