# Vigilon — executable infrastructure jumpstart for Codex

## Assignment

Work in this repository as the implementation engineer. Build the runnable foundation described below, create/update `AGENTS.md`, and verify the result. This is an implementation task, not a request for a proposal or documentation-only scaffold.

Inspect repository instructions and existing files first. Preserve unrelated changes and working functionality. Adapt an existing suitable stack rather than replacing it needlessly. Make routine decisions autonomously. Do not stop after planning; continue through implementation and verification. If a dependency or environment blocks one part, complete independent parts and report the exact blocker honestly.

## Product contract

**Vigilon is an adaptable software hub for existing, owner-authorized CCTV infrastructure.** It adds event detection, evidence, notifications, and incident response to compatible cameras/NVR channels. It is not a proprietary camera, a single-purpose hardware appliance, or a replacement NVR.

Deploy on a PC, local server, or edge computer. CPU-only demo operation is mandatory; GPU inference can be added later. Connect only through supported interfaces with explicitly supplied authorization. Do not scan networks, guess passwords, bypass camera authentication, or claim universal camera compatibility.

Initial users: administrators and operators of condos, dormitories, schools, and small commercial properties.

End-to-end workflow:
Register source → ingest frames → preview → configure zones/rules → evaluate detections over time → create incident/evidence → notify operator → acknowledge → resolve or mark false alarm.

Future detector targets:
- Person falling or remaining on the ground.
- Object/vehicle obstructing a configured emergency route.
- Visible smoke/flame.
- Later: prohibited-direction movement, restricted-zone entry, crowding, and water accumulation.

This task builds extensible infrastructure and explicitly simulated detector scenarios. It does not require training or integrating all real AI models. Do not manufacture inference results or accuracy claims. Do not add facial recognition, identity profiling, or claims of predicting criminal intent. The platform supplements, rather than replaces, certified fire/safety systems.

## Phase 0 — inspect, plan, and establish instructions

- Inspect Git status, existing instructions, dependencies, and available runtimes.
- Record a short plan and track progress in `docs/IMPLEMENTATION_STATUS.md`.
- Create or carefully update root `AGENTS.md` early; refine it after implementation so commands and paths reflect reality.
- Preserve this task's requirements. Do not rewrite acceptance criteria merely to mark work complete.
- Use existing Context7/documentation tools if available to verify unfamiliar APIs. Do not install global tooling or modify global agent configuration for this task.
- No public deployment, real-camera access, external notifications, or large model downloads are needed. Use generated local fixtures for verification.

## Architecture and stack

Default for an empty repository:
- Python FastAPI API and a separately runnable Python ingestion worker.
- PostgreSQL, SQLAlchemy, Alembic migrations.
- React, TypeScript, Vite frontend.
- Local evidence storage through a storage interface.
- Docker Compose for API, worker, database, and frontend.
- Python package management with a lockfile; npm with a lockfile for frontend.
- Structured logs, OpenAPI, environment-based configuration.

Keep a modular monolith with a separate worker process. Do not add Kubernetes or unrelated microservices. Use PostgreSQL for durable state; add Redis only if a concrete implemented requirement needs it.

Suggested layout (adjust to actual needs):

```text
backend/app/{api,core,db,models,schemas,services,adapters,detection,workers,storage}/
backend/migrations/
backend/tests/
frontend/
infra/
scripts/
sample_data/
docs/
AGENTS.md
task.md
compose.yaml
.env.example
README.md
```

Document the API-worker boundary explicitly. Frame buffers inside a worker are not magically accessible to API processes. Implement a concrete latest-frame handoff, such as atomically replaced JPEGs and metadata on a shared local volume. Keep video frames out of database rows. Persist incidents, configuration, and worker heartbeats in PostgreSQL.

## Phase 1 — repeatable infrastructure

- Dockerfiles and Compose with health checks, persistent database/evidence volumes, and appropriate dependency readiness.
- Bind user-facing development ports to localhost by default; database need not be exposed to the host.
- Explicit migration command/service. Do not have API and worker race to apply migrations.
- Idempotent administrator bootstrap and separate demo-seeding commands.
- `.env.example` with placeholders; no fixed default passwords or committed secrets.
- A setup script that generates required local secrets without printing them and does not overwrite existing configuration.
- PowerShell startup instructions for Windows/Docker Desktop and shell instructions for Linux.
- Dependencies locked to compatible versions; avoid floating `latest` images.
- Graceful shutdown and resource cleanup; bounded/rotated logs.
- Local data, evidence, credentials, downloaded models, and generated media excluded from Git.

## Phase 2 — source adapters and ingestion

Define a typed source adapter interface and implement:
1. Synthetic source with changing frames and controllable deterministic scenarios.
2. Local video file adapter, with clear EOF/replay behavior.
3. Real RTSP adapter, also usable with an NVR channel exposing RTSP.

ONVIF discovery is not required. Document an extension point for authorized capability/stream lookup. Explain analog-camera-through-recorder compatibility and vendor-cloud-only limitations honestly.

Source configuration includes name, location, source type, enabled state, credentials/connection configuration, processing FPS, resize limit, timeout, and bounded reconnect backoff.

Requirements:
- Actual connect/read timeouts; prevent a blocked decoder from hanging worker shutdown indefinitely. Use a suitable decoding library or supervised subprocess and document the choice.
- Bounded buffers; discard stale frames under load.
- One source failing must not stop the others.
- Maintain last successful frame time, connection state, reconnect count, processed/dropped frame counts, and useful redacted error categories.
- Distinguish source connectivity from worker heartbeat and preview staleness.
- Reload enabled/configuration changes through a documented mechanism without restarting the entire stack.
- Initial single-worker operation is acceptable, but enforce ownership through a database lease/lock or equivalent so an accidental second worker cannot duplicate ingestion/incidents.
- Release/recover source ownership on shutdown or worker death.
- Do not infer a frozen feed merely from a visually static scene.

RTSP inputs are administrator-only. Intentionally support authorized private LAN destinations through configurable policy. Validate allowed protocols/destinations, deny inappropriate metadata/service endpoints, and avoid shell interpolation. Local video paths must remain within an allowed media directory. Do not expose a generic arbitrary-URL proxy or unrestricted filesystem reader.

## Phase 3 — preview, zones, and rules

Implement authenticated latest-JPEG preview with timestamps. Reuse ingestion frames, not a new upstream connection per viewer. Browser RTSP playback is not assumed. Display offline/stale/disabled states accurately.

Zone editor:
- Draw a rectangle or polygon on the preview.
- Save normalized coordinates and validate geometry.
- Render correctly when the preview is resized/letterboxed.
- Link zones to supported rule types.

Rule configuration:
- Enabled state, event type, zone, confidence threshold where applicable.
- Minimum duration, cooldown, monitoring schedule and explicit schedule timezone.
- Validate incompatible settings rather than silently ignoring them.

## Phase 4 — detection interfaces and deterministic demo

Separate four responsibilities:
1. Inference plugins.
2. Temporal/rule evaluation.
3. Incident deduplication/persistence.
4. Notification delivery.

Define typed frame context and detection results containing camera ID, capture timestamp, frame dimensions, geometry, optional track ID, detector ID/version, optional confidence, and structured metadata.

Plugins must advertise availability and supported event types. An absent real detector must appear unavailable, not enabled with fake results. Real fall detection and obstruction detection require temporal reasoning, not just single-frame labels.

Provide explicitly named simulated plugins and reproducible scenarios for obstruction, person-down, and smoke/fire. Demo scenarios should generate visible synthetic evidence aligned with event metadata. Mark every resulting incident and relevant UI as SIMULATED. Never apply simulated detectors silently to real RTSP sources.

Deliver one complete vertical slice early: synthetic source → preview → rule → incident → snapshot → operator action → persistent history. Then finish the remaining interfaces.

## Phase 5 — incidents, evidence, and notifications

Statuses: NEW, ACKNOWLEDGED, RESOLVED, FALSE_ALARM. Severity is independent of status.

Persist:
- Camera/location, type, first/last observed time.
- Status/severity and simulation flag.
- Detector/rule version or configuration snapshot sufficient to interpret the event.
- Snapshot reference and structured evidence metadata.
- Actor, timestamp, notes, and append-only transition history.

Implement server-side transition validation and concurrency-safe updates. Define deduplication by source/rule/event/track or zone as appropriate. A continuing event should update one incident. Explicitly define what happens when a resolved event persists or recurs; do not reopen on every frame. Manual resolution and scene-clear evidence are distinct concepts.

Evidence:
- Capture a snapshot corresponding to the triggering observation, not an unrelated later frame.
- Authenticated serving through the API; no public static evidence directory.
- Safe generated filenames and path traversal protection.
- Configurable retention cleanup for files and references; keep audit history indicating expired evidence.
- Extension interface for clips, but snapshot-only is acceptable and must be documented as such.

Notifications:
- Implement durable in-app notifications linked to incidents.
- Deduplicate updates to avoid notification floods.
- Provide interfaces for later external channels; unimplemented channels must not report delivery success.
- Optional escalation can remain on the roadmap unless implemented end-to-end.

## Phase 6 — authentication and frontend

Implement real authentication with established password hashing/auth libraries. Prefer a simple same-origin session arrangement; if using cookies, handle CSRF and appropriate cookie attributes. Do not put camera credentials into frontend state, responses, logs, or error traces.

Roles:
- ADMIN: users, sources, rules, settings, and incident management.
- OPERATOR: preview, evidence, incident review/actions; cannot retrieve source credentials or change administration settings.

Encrypt persisted source secrets with a maintained library and an externally supplied key. Fail clearly if the key is missing. Document backup implications. Authenticate previews, evidence, and any event streaming as well as REST endpoints.

Build a usable frontend connected to real APIs:
- Login/logout.
- Overview: source/worker health and active incidents.
- Cameras: create/edit/disable, connectivity check with a timeout, preview, zone/rule configuration.
- Incidents: filter, pagination, evidence, acknowledge/resolve/false alarm, notes/history.
- Clear source mode and simulation badges.
- Empty/loading/error/stale states; no fabricated dashboard metrics.
- Readable desktop-first responsive layout with straightforward navigation.

Use UTC internally and timezone-aware datetimes. Default display timezone may be Asia/Bangkok and must be configurable. Monitoring schedules require explicit timezone conversion.

## Phase 7 — verification and documentation

Meaningful automated checks:
- Temporal duration/cooldown and incident deduplication, including recurrence.
- Status transitions, history, and role restrictions.
- Credential redaction and unauthorized preview/evidence access.
- Adapter failures, timeout/reconnect, EOF, and bounded frame behavior.
- Zone validation and coordinate mapping.
- Evidence retention and safe file access.
- Demo happy-path integration with persisted state.

Use deterministic fixtures; real hardware is not required. If practical, run a local test RTSP publisher with generated media to exercise the RTSP adapter. Clearly distinguish a local protocol test from testing an actual camera.

Run backend checks, frontend typecheck/build, migrations on a clean database, and the full Compose demo when the environment supports them. Add CI for the reproducible checks. Do not broaden testing endlessly once the specified behavior is sufficiently verified.

Required documentation:
- README.md: exact commands from a fresh clone to a working demo, camera connection steps, troubleshooting.
- docs/ARCHITECTURE.md: data flow, process boundaries, source ownership, failure behavior.
- docs/CAMERA_COMPATIBILITY.md: interfaces/codecs actually supported or tested, RTSP/NVR prerequisites, Docker host/LAN networking limitations.
- docs/DETECTION_PLUGINS.md: contract, example integration, testing, model/license provenance requirements.
- docs/SECURITY.md: secrets, permissions, evidence retention, local deployment boundary.
- docs/IMPLEMENTATION_STATUS.md: implemented+verified / implemented+unverified / simulated / planned.
- docs/ROADMAP.md: next real detector, evaluation data, notification integration, clip support, deployment hardening.

## AGENTS.md requirements

Write concise repository-specific instructions for future Codex sessions. Include:
- Vigilon's product purpose and the existing-CCTV compatibility principle.
- Actual folder map and component responsibilities.
- Exact verified install, startup, migration, bootstrap, test, lint, and build commands.
- Coding conventions and API/schema/migration rules.
- Detector/source adapter contracts and temporal-processing boundaries.
- Demo-versus-real separation and honest capability reporting.
- Credential, evidence, authentication, and data-handling conventions.
- Requirement to update relevant docs when implementation changes.
- Preserve user changes; never erase data, reset Git, or deploy publicly as a routine step.
- Avoid speculative abstractions, placeholder-only implementations, and unnecessary global tooling.
- How to update implementation status and provide a useful handoff.

Do not copy this entire task into AGENTS.md. Do not invent commands or claim infrastructure exists before implementing it. Preserve applicable existing instructions when updating the file.

## Acceptance checklist

- [ ] Root AGENTS.md accurately describes the implemented repository.
- [ ] Compose/configuration/migrations/bootstrap are present and coherent.
- [ ] Demo runs without a physical camera, external AI API, or downloaded model.
- [ ] Live-changing demo preview comes from the worker ingestion path.
- [ ] Real RTSP and file adapters exist with bounded failure/reconnect behavior.
- [ ] Camera settings and zone/rule changes reach the worker.
- [ ] Simulated incidents include matching snapshots and persist across restart.
- [ ] Operator can acknowledge, resolve, and mark false alarms with history.
- [ ] Repeated observations do not create notification/incident floods.
- [ ] Auth and roles protect administration, preview, and evidence.
- [ ] Worker/source health and stale preview are distinguishable.
- [ ] Retention cleanup is implemented and documented.
- [ ] Dependency locks, relevant tests, and CI exist.
- [ ] README includes Windows/Docker Desktop and Linux instructions.
- [ ] Documentation distinguishes verified, unverified, simulated, and planned work.

Only check an item when supported by implementation and appropriate evidence. If execution is blocked, leave runtime verification unchecked and state the blocker; do not pretend it passed.

## Final handoff

Report concisely:
1. Implemented components and important architecture decisions.
2. Exact startup commands and local URL.
3. Checks run with actual outcomes, including unavailable checks.
4. Remaining limitations and any blockers.
5. Next three concrete tasks toward real-camera inference.

Proceed now: inspect, create/update AGENTS.md, implement the infrastructure and working demo, verify, and hand off. Do not stop at a plan.
