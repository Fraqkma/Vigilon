# AGENTS.md — Vigilon shared engineering instructions

## 1. Purpose and authority

This file aligns coding agents and the five-person Vigilon team. It defines project conventions, architecture boundaries, and verification expectations. It does not replace the user's current request, higher-priority platform instructions, active Codex settings, permission controls, or applicable parent instructions.

Before adopting this file in an existing checkout, compare it with the existing AGENTS.md and merge valid repository-specific instructions. Do not blindly overwrite instructions or verified commands contributed by teammates. This document was prepared from a reported implementation handoff, not an independent inspection of the repository.

For every task:
1. Read applicable parent/root instructions and any nested AGENTS.md covering files you will edit.
2. Inspect Git status and the relevant implementation.
3. Read README.md and docs/IMPLEMENTATION_STATUS.md as needed; consult task.md for the original jumpstart scope and the current user request for active priorities.
4. Treat code and reproducible execution as evidence of current behavior. Treat old summaries and checkboxes as claims to verify when relevant.
5. Make focused changes, verify material behavior, and update affected documentation.

Do not repeatedly rerun the original jumpstart or regenerate the repository merely because task.md describes initial scaffolding. Do not change requirements or remove failing tests simply to report completion.

## 2. Product definition

Vigilon is an adaptable software hub for existing, owner-authorized CCTV cameras and NVR channels. It adds configurable event detection, evidence, notification, and incident response.

Core workflow:
source → ingestion → frame context → inference → temporal/zone rules → incident → evidence/notification → operator review → resolution/history.

Deployment may use an existing PC, on-premises server, or edge computer. It is not tied to one camera vendor, a proprietary appliance, or one GPU. CPU-only demonstration must remain available.

Initial users are operators and administrators of dormitories, condos, schools, and small commercial properties. The product combines smart-city safety with community resilience.

Initial detector targets:
- Person falling or remaining on the ground.
- Obstruction of a configured route by supported objects/vehicles.
- Visible smoke/flame.

These are targets, not a statement that real detection currently exists. Add one real detection workflow end-to-end before expanding the model catalog. A person/vehicle dwelling in a zone is narrower than detecting every kind of obstruction; label it accurately.

Non-goals without a new explicit requirement:
- Replacing the NVR or recording all video indefinitely.
- Universal camera compatibility claims.
- Network intrusion, password guessing, or authentication bypass.
- Facial recognition, identity profiling, or inferring criminal intent.
- Certified fire alarm/medical diagnosis functionality.
- Kubernetes, billing, or a speculative fleet of microservices.

## 3. Existing Codex environment, settings, skills, MCP, and hooks

The developer has reported using Codex with Context7, Playwright, and GitHub MCP integrations and an Everything Claude Code (ECC) installation/configuration history. These are context, not proof that a particular tool or hook is currently available or enabled.

- Respect the actual active model settings, sandbox, approvals, hooks, skills, and tool availability supplied by the runtime.
- Do not install/reinstall Codex, ECC, MCP servers, or global dependencies as routine project work.
- Do not modify global Codex configuration, user-level instructions, credentials, hook configuration, or machine-wide environment variables unless the user explicitly requests that work.
- Do not assume ECC hooks are enabled, disabled, or safe to toggle. Do not bypass an approval/control by changing its configuration.
- If a hook modifies files, inspect its changes and include relevant changes in verification. Do not fight a formatter by repeatedly rewriting its output.
- Use applicable installed skills when required. Avoid duplicate global tooling when an existing tool is sufficient.
- Context7: use for unfamiliar or version-sensitive library APIs when available. Verify against the actual locked dependency version; do not upgrade just to match an example.
- Playwright: use for focused browser checks against the authorized local application when available. Use test accounts and controlled data; do not expose credentials in screenshots or logs.
- GitHub MCP: use for requested repository/issue/PR work within session authorization. Its presence alone does not authorize publishing, messaging, merging, or changing repository settings.
- If a tool is unavailable, use a suitable available local alternative and report the limitation. Do not silently reconfigure the user's setup.
- Never print full environment/configuration/authentication files to diagnose tool availability. Inspect only the non-secret fields needed for the task.
- Avoid enabling workflows that export video, private code, transcripts, or evidence to external services without authorization.
- Multi-agent execution is optional, not a requirement of this document. Follow the active session's delegation rules. Human ownership below does not imply permission to spawn agents.

## 4. Team ownership and integration boundaries

| Owner | Primary responsibility | Integration deliverable |
| --- | --- | --- |
| PM / integration | Scope, infra, CI, contracts, integration, demo/pitch | Reproducible startup, accepted contracts, integrated release |
| Compatibility engineer | RTSP/NVR/file/synthetic adapters, decoding, source health, reconnect | Timestamped frame stream and source status |
| AI data/model engineer | Dataset rights, annotation, splits, baseline selection, training/evaluation | Versioned model, provenance, evaluation report |
| AI inference/rules engineer | Model runtime, tracking, temporal/zone rules, inference performance | Typed observations and event candidates |
| Full-stack engineer | API, DB, authentication, incidents, notifications, frontend | Authorized operator workflow and persistent history |

Agents should work within the requested responsibility. Cross-boundary fixes are allowed when necessary, but document contract changes and coordinate shared-file changes. Ownership is not a reason to leave a necessary integration bug unexplained.

Agree on shared contracts before parallel work. Keep examples/fixtures consistent with API schemas. Prefer additive compatible changes; document coordinated migrations for breaking changes.

## 5. Reported baseline — verify before relying on it

The latest supplied handoff reported:
- FastAPI, SQLAlchemy, Alembic; PostgreSQL in Compose, SQLite for local demo.
- Separate API and worker processes, worker lease, per-source threads and bounded frame handling.
- Synthetic, local-file, and RTSP/RTSPS adapters.
- Latest JPEG and manifest shared between worker and API.
- Argon2 authentication, ADMIN/OPERATOR, session cookies, encrypted source configuration.
- Normalized zones, detector contracts, simulated scenarios, temporal rules and deduplication.
- Incidents and authenticated snapshot evidence, audit history, explicit retention command.
- A plain JavaScript frontend, not React/TypeScript/Vite.
- Compose, environment setup, lockfiles, CI definitions, and documentation.

Reported checks were seven passing tests, SQLite migrations, Python compilation, JavaScript syntax, YAML parsing, an API/worker demo smoke test, and selected browser checks. These are historical reports; do not present them as checks run in your session.

Reported gaps:
- Docker builds/Compose and PostgreSQL runtime not verified.
- RTSP publisher/physical camera/NVR compatibility not verified.
- No real AI detector; demonstrated incidents were simulated.
- Monitoring schedule not actually evaluated.
- No external notification, evidence clips, automatic retention scheduling, password reset/session revocation, or user-management page.
- CI configuration existed but GitHub execution was not verified.

Read current status/code before treating a gap as still open. Update this baseline when substantive changes are verified.

## 6. Architecture conventions

Keep the API and worker separately runnable with a shared, maintainable backend codebase. Do not decode continuous video inside API request handlers.

PostgreSQL is the intended integrated deployment database. SQLite is a convenience mode, not proof of PostgreSQL correctness. Test database-specific behavior, especially migrations, locking/leases, timestamps, and concurrent incident updates, on the intended backend.

Use explicit Alembic migrations for schema changes. Never delete/reset a database or Docker volume as an automatic migration fix. Never edit an already-shared migration to rewrite deployed history; add a migration and document any required data handling.

Frames are transient binary data, not database row payloads. Use the implemented shared-frame mechanism with atomic publication and consistency checks so metadata and images correspond. Persist configuration, incidents, audit records, evidence references, and health/heartbeat metadata appropriately.

Preserve the existing frontend unless migration is an active team decision. Do not introduce React/TypeScript merely to match the original proposal. If migration is requested, plan a coherent cutover and preserve working operator flows.

Keep abstractions purposeful: source adapters, detector plugins, evidence storage, and notification channels are appropriate extension points. Avoid unused frameworks and placeholder-only service layers.

## 7. Source adapters and compatibility

- Use authenticated, explicitly configured sources only.
- Support RTSP/NVR channels only when the device actually exposes a compatible stream.
- Do not equate ONVIF support with support for every codec or camera feature.
- Record tested device/recorder, firmware if known, codec, transport, resolution, and environment without credentials.
- Restrict protocols and allowed source destinations while intentionally accommodating authorized private CCTV networks.
- Restrict local-video inputs to the configured media root; prevent path traversal.
- Use argument arrays rather than shell-interpolated source strings for subprocesses.
- Enforce connect/read timeouts, bounded retries/backoff, and interruptible cleanup.
- One failing source must not hang other sources or indefinitely block worker shutdown.
- Bound queues; discard stale frames under load and count drops.
- Reuse ingestion frames for preview; never create an upstream session for every viewer.
- Implement or document configuration reload behavior.
- Preserve exclusive worker/source ownership with expiration/recovery after worker failure.
- Separate worker offline, camera disconnected, disabled source, stale frame, EOF, and unavailable detector states.
- A static scene is not proof of a frozen camera feed.

## 8. Frame, detector, and event contracts

Use the existing typed schemas rather than inventing a second incompatible payload. Evolve them explicitly if required.

Frame context needs source ID, capture/receive timing as applicable, sequence/reference, image dimensions, frame access, and relevant configuration revision. Document timestamp origin and do not equate processing time with capture time.

Detection observations should identify detector/model version, object/event type, geometry, optional track ID, optional model score, and structured metadata. Do not present uncalibrated model scores as a probability that an incident is real.

Distinguish:
1. Raw model observation.
2. Temporal/zone rule evaluation.
3. Candidate incident and deduplication.
4. Operator-confirmed interpretation.

Use normalized zone coordinates with documented mapping through resizing, letterboxing, and model preprocessing. Validate shapes and coordinate limits.

Rules must account for duration, sampling intervals, gaps, cooldown, schedules, and timezone. Do not accumulate event duration across long disconnections as though the event was continuously observed.

An unavailable real detector must be visibly unavailable. Synthetic detections may not silently run on real camera feeds. All simulated incidents, snapshots, and demo flows must remain explicitly identifiable.

Monitoring schedules must either be enforced or disabled/labelled unsupported. Saving a schedule while ignoring it is unacceptable product behavior.

## 9. AI data and model development

- Start by evaluating a suitable existing model; train/fine-tune only when a concrete gap warrants it.
- Record dataset source, license/consent, allowed use, labeling policy, model license, version/hash, preprocessing, and inference requirements.
- Keep real video, identifiable images, large datasets, and weights out of Git. Store authorized data separately with documented references.
- Split by original recording/session and, where appropriate, location/camera. Near-identical neighboring frames must not leak across train/validation/test.
- Keep the final test set out of threshold tuning and training decisions.
- Include negative examples, difficult lighting, occlusion, ordinary sitting/lying activities, and relevant camera perspectives.
- Evaluate event-level precision/recall, false alerts per camera-hour, detection delay, missed events, throughput, and hardware utilization where data supports them.
- Report sample sizes and test conditions; do not promise general deployment performance from a small demo set.
- Define person-down versus fall detection precisely. Likewise define supported obstruction classes, zones, and dwell thresholds.
- Keep model-dependent work in plugins, not scattered across API/UI code.
- Document CPU baseline and optional GPU paths; avoid mandatory GPU dependencies in the base demo.
- Do not automatically download large models or send frames to hosted AI services without authorization.

## 10. Incidents and evidence

Statuses: NEW, ACKNOWLEDGED, RESOLVED, FALSE_ALARM. Severity is independent. Validate transitions on the server and retain actor/time/notes in audit history.

Continuing observations update one logical incident according to explicit deduplication rules. Define recurrence after resolution and respect concurrent operator changes. Do not reopen an incident on every frame.

Manual resolution, a cleared scene, and a false alarm are different facts. Preserve those distinctions.

Capture evidence from the observation that triggered the event; do not attach a random later frame. Use safe generated filenames and authenticated evidence access. Retention must keep metadata honest about expired/missing files while preserving relevant audit history.

Snapshots do not imply video clips are supported. In-app notifications do not imply external delivery. Persist delivery status accurately for any later integration, with deduplication/retry behavior that does not flood recipients.

## 11. Security and operational data

- Keep credentials, encryption keys, sessions, and raw authenticated source URLs out of Git, logs, API responses, screenshots, and handoff text.
- Never dump .env or global auth files. Diagnose only necessary non-secret fields.
- Camera credential encryption keys remain outside the database. Document restoration/key loss implications.
- ADMIN manages users/sources/rules/settings. OPERATOR accesses allowed previews/evidence and incident actions without retrieving source secrets.
- Protect preview/evidence endpoints and streaming paths, not just JSON APIs.
- Preserve established password hashing, session protections, CSRF handling for cookie-authenticated mutations, and appropriate deployment cookie attributes.
- Do not claim session revocation/password reset exists until implemented and tested.
- Bind local development services appropriately; do not expose PostgreSQL or evidence publicly by default.
- No automatic public deployment, external notifications, or changes to real cameras as part of a local test.
- Do not add new third-party telemetry or export real footage as an incidental dependency change.

## 12. Development environment and commands

Discover actual commands from the current README, scripts, lockfiles, and entry points before executing. Use the repository virtual environment instead of installing Python packages globally. Preserve compatible dependency locks and explain upgrades.

The following were reported to work on Windows; validate that files/options still exist. These commands are not evidence that they have run in the current session.

Initial setup from repository root (do not recreate/overwrite an existing environment unnecessarily):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\scripts\setup.ps1
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.commands migrate
.\.venv\Scripts\python.exe -m app.commands bootstrap-admin
.\.venv\Scripts\python.exe -m app.commands seed-demo --scenario obstruction
```

Inspect setup/bootstrap behavior first when configuration or users already exist. Never reset an existing administrator or seed demo records into an operational database accidentally.

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

Reported local URL: http://127.0.0.1:8000

Reported frontend syntax check:

```powershell
node --check frontend/app.js
```

Find the actual test/lint/retention/Compose commands in repository configuration and document verified invocations. Do not fabricate script names, service names, or a frontend build step for the current plain-JavaScript frontend. YAML parsing and `docker compose config` alone are not runtime verification.

On Windows, respect PowerShell quoting and existing process ownership. Do not kill unrelated Python/Node/Docker processes. Track only processes started for this task and stop them cleanly. Do not change machine-wide execution policy to run a script.

## 13. Testing expectations

Choose focused tests based on the behavior changed. Do not pursue test counts or broad rewrites unrelated to the task.

Important integration risks:
- Clean PostgreSQL migrations and supported upgrades, not SQLite alone.
- Worker lease concurrency, expiry, and recovery.
- RTSP timeout/reconnect and independent source failures.
- Correct frame/snapshot correspondence and bounded memory.
- Temporal thresholds, schedules/timezones, deduplication, and recurrence.
- Zone mapping at different image/viewport sizes.
- Authentication, CSRF where applicable, ADMIN/OPERATOR boundaries, credential redaction, preview/evidence authorization.
- Evidence cleanup with consistent metadata.
- Demo flags that cannot be confused with actual inference.

Use generated fixtures and an authorized local RTSP publisher where useful. Label protocol tests separately from physical device compatibility tests.

For UI changes, verify relevant actions with actual API behavior, loading/empty/error states, and applicable viewport sizes. Opening a screen is not proof that saving a zone or resolving an incident works.

Test the changed workflow through persistence when practical. No Docker available means Compose/PostgreSQL execution remains unverified; complete independent checks without claiming equivalence.

## 14. Git, collaboration, and progress

- Inspect status/diff first. Preserve teammates' uncommitted work.
- Use focused changes; avoid mass formatting outside scope.
- Do not force-push, hard-reset, delete branches/data, or rewrite history as a routine repair.
- Commit/push/PR/merge according to the current user's authorization and workflow. Do not publish merely because GitHub MCP is installed.
- Coordinate edits to migrations, shared schemas, dependency locks, Compose, and root instructions.
- Document contract changes before another team member relies on them.
- Report concrete findings and blockers during longer tasks. Avoid repeatedly requesting permission for already-authorized reversible implementation steps.
- Do not disable security controls or alter global settings to work around a failure.

## 15. Documentation and definition of done

Update documentation when behavior changes:
- README.md: real startup/operation commands.
- docs/IMPLEMENTATION_STATUS.md: verified, unverified, simulated, planned, and blockers.
- docs/ARCHITECTURE.md: process/data boundaries and source ownership.
- docs/CAMERA_COMPATIBILITY.md: interfaces and actual test matrix.
- docs/DETECTION_PLUGINS.md: schemas, availability, model integration.
- docs/SECURITY.md: permissions, secrets, retention, deployment boundaries.
- docs/ROADMAP.md: outstanding work and priorities.

A task is done when the requested behavior is implemented, relevant verification supports it, interfaces/docs are aligned, and limitations are explicit. A scaffold, mocked UI, or simulated result must not be reported as a working real detector.

Final handoff should state:
1. What changed and why.
2. Important files/components and contract changes.
3. Checks actually executed and results.
4. Untested paths and blockers.
5. Exact relevant startup/verification commands.
6. Next concrete task and team owner.

Communicate with the user in Thai unless requested otherwise. Keep code identifiers and shared technical documentation in consistent English. Never claim to have inspected a file, run a test, accessed a camera, or deployed a service when you have not.
