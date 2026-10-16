# Vigilon — AI Hub ready for teammate model packages

## Mission

Implement this task end-to-end in the existing Vigilon repository. Deliver a working AI Hub, real Ultralytics inference adapters, deterministic integration tests, model-package templates, and operator integration so teammates can place supported weights and configuration into documented folders and run inference without modifying Hub internals.

This task supersedes the original jumpstart's implementation scope for this work session. Preserve existing architecture and functioning features. Do not regenerate the project. Read applicable AGENTS.md instructions, README, status documents, source code, and Git diff before editing. Respect the user's active Codex settings, installed skills, ECC/hooks, and available MCP tools. Do not change global settings, reinstall agent tooling, or bypass approvals. Use available documentation tools to verify APIs against versions actually selected and locked.

The deliverable is implementation, not a proposed architecture. Continue through code, migrations if needed, local execution, verification, documentation, and handoff. Do not commit or push unless separately instructed. Preserve unrelated work and local data.

## Agreed method and team ownership

- Python + PyTorch.
- Ultralytics YOLO pretrained object-detection models; fine-tune only where needed.
- CVAT labels exported in compatible YOLO detection format.
- Training on an NVIDIA machine or Colab using reproducible scripts/configuration.
- Dataset splits by recording/session/site, not adjacent random frames.
- ByteTrack for people/vehicle tracking.
- Python temporal/spatial rules for zone entry, directional line crossing, and dwell.
- AI 1 owns people/vehicle weights, tracking, and its scenario module.
- AI 2 owns fire/smoke weights, training data, and its scenario module.
- AI 3 owns Hub runtime, plugin interfaces, scheduling, registration, and common tooling.
- Compatibility owner owns source decoding, RTSP/file/synthetic adapters, timestamps, and preview handoff.
- PM owns Visor, application APIs/database, infrastructure, and final integration.

Build the agreed initial modules and reusable rule utilities now so teammates can subsequently improve their modules without redesigning the Hub. Do not leave the functional integration for the PM to finish.

Vigilon supports LIVE monitoring and FILE analysis through the same modules. It adapts to existing authorized CCTV/NVR streams. A weights file alone is not a universal executable plugin: support a clearly specified Ultralytics detection-checkpoint contract. Segmentation, pose, arbitrary PyTorch state dictionaries, and other architectures require explicit adapters and should return UNSUPPORTED_MODEL rather than being guessed.

## Inspect actual baseline

The supplied handoff previously reported FastAPI/SQLAlchemy/Alembic, SQLite local mode and PostgreSQL Compose, separate API/worker, worker lease, source adapters, shared JPEG preview, authenticated snapshots, incidents, and a plain JavaScript frontend. Treat these as historical claims. Inspect current code and reuse working components. Do not migrate the frontend framework as part of this task.

Produce a brief gap map and then implement. Keep docs/IMPLEMENTATION_STATUS.md accurate. Missing Docker or physical-camera access is not a reason to stop implementing and testing the independent Hub/file workflow.

## Canonical repository-relative model paths

Use these public handoff paths exactly. Internal Python module paths may adapt to the existing codebase.

```text
models/
  README.md
  people_vehicle/
    manifest.yaml
    inference.yaml
    classes.json
    tracker.yaml
    scenarios.yaml
    MODEL_CARD.md
    evaluation.json
    weights/
      .gitkeep
      best.pt                 # supplied by AI 1, ignored by Git
  fire_smoke/
    manifest.yaml
    inference.yaml
    classes.json
    scenarios.yaml
    MODEL_CARD.md
    evaluation.json
    weights/
      .gitkeep
      best.pt                 # supplied by AI 2, ignored by Git
```

Do not create fake/empty .pt files. Provide valid configuration templates with explicit not-provided evaluation/provenance fields. Do not invent hashes, training runs, metrics, or licenses. Metadata describing runtime capabilities and actual package defaults must be concrete even when weights are absent.

Root model directory is resolved relative to the repository, not the shell working directory, with optional VIGILON_MODEL_DIR override. Package-relative paths resolve relative to each manifest. Verify Windows, Linux, and Compose mapping semantics. Mount packages read-only in the worker container and keep writable caches/evidence elsewhere. Dependencies, optional CUDA setup, and cache location must be documented. Inserting model weights must not require rebuilding an image.

Commit configuration, templates, docs, and .gitkeep. Ignore weights, training datasets, generated video, run outputs, and secrets. Preserve existing assets; do not delete them.

## Model-package schema and validation

Create a versioned schema and concrete examples. manifest.yaml includes:
- schema_version, module_id, package_version, adapter_id.
- task: detect, framework/runtime identifiers, tested/required runtime compatibility.
- weights relative path and optional expected SHA-256.
- paths to inference/class/scenario metadata and optional tracker configuration.
- supported events and model-card/evaluation references.

Initial registered adapter IDs should correspond to built-in reviewed people/vehicle and fire/smoke plugins. Manifest data must not specify arbitrary import paths, executable commands, or pip installs.

classes.json explicitly maps numeric checkpoint class IDs to canonical labels. On load, validate against checkpoint names. Preserve original names separately when aliases such as motorbike → motorcycle are deliberately configured. Never assume car has a fixed numeric index or fire is always class 0. Fail on mismatches/duplicates/unsupported scenario requirements with actionable errors.

inference.yaml supports validated input size, score threshold, NMS IoU, selected classes, device cpu/cuda/auto, and CPU fallback policy. Define configuration precedence; report effective settings and model version without sensitive source details. Reject unknown/invalid fields rather than silently ignoring them.

scenarios.yaml holds explicit event defaults: required class labels, zone/line references, minimum observation duration, disappearance grace, cooldown, hysteresis where needed. Per-camera/job settings override allowed defaults. Validate geometry and scenario/module compatibility before starting.

Two-stage validation:
1. Metadata validation without deserializing weights: file existence, containment, schema, metadata, optional checksum, and declared readiness.
2. Runtime validation of a trusted local checkpoint: load with the supported library, check task/class mapping, warm up on a controlled image, validate outputs, release resources.

Treat .pt files as executable/trusted artifacts: load only team-approved local packages. Do not auto-download weights or accept arbitrary public checkpoint uploads. Do not globally monkey-patch safe-loading behavior. Checksum verifies integrity, not trust. Report unsupported checkpoint errors clearly.

Status must distinguish MISSING_WEIGHTS, INVALID_CONFIG, UNSUPPORTED_MODEL, DEPENDENCY_MISSING, READY, LOADING, RUNNING, ERROR, DISABLED as appropriate. READY requires successful runtime load validation; metadata-only validation is not READY. Missing real weights never activates a dummy model silently.

## Hub contract and implementation

Reuse/evolve existing schemas rather than creating disconnected parallel ones. Include schema versions and representative fixtures.

FramePacket:
- source_id, session_id/job_id, frame_id/sequence.
- media timestamp for file playback; receive/capture timestamp for live with timestamp origin explicit.
- original width/height, image data/reference, colorspace and relevant transform metadata.
- stream discontinuity information when reconnect/seek/replay occurs.

Detection:
- canonical label, original class ID/name, score if provided.
- bounding geometry in one documented coordinate convention.
- optional track ID, model/package version, frame reference, simulation flag.

EventCandidate:
- stable event key, source/session/module/scenario identifiers.
- lifecycle START/UPDATE/END or equivalent explicit semantics.
- event type, start/last observed time, geometry, related track IDs, evidence-frame reference.
- structured facts, score semantics, simulation flag; no invented calibrated probabilities.

Define lifecycle methods equivalent to:
- load(package_config)
- create_session(session_id, source_context, scenario_config)
- process(frame_packet, session_context)
- reset/close_session(session_id)
- close()

Separate immutable weights/runtime from mutable per-source/per-job tracker and rule state. Model sharing requires safe serialized inference or explicit synchronization. Do not share one persistent tracker between cameras. Reset on new job/seek/replay/discontinuity according to documented policy.

Hub responsibilities:
- Built-in plugin registry and package catalog.
- Enable selected modules per source/job.
- Bounded scheduling and resource lifecycle.
- Isolate a module failure from unrelated modules/sources.
- Safe load/unload with explicit reload after replacing package files; no unsafe live hot swap.
- Record package version/config revision for each session/event.
- Handle cancellation and graceful shutdown without orphan workers or leaked GPU memory.
- Preserve the existing worker ownership mechanism; do not launch a competing ingestion worker.

LIVE policy: bounded queues, prefer latest frames, count dropped frames, measure backlog. FILE policy: ordered processing with backpressure; no silent live-style dropping. Explicit sampling is allowed but must report coverage/FPS and use media timestamps. A cancelled/failed/partially processed file must not be reported complete or event-free.

Use monotonic elapsed-time handling for live durations with UTC display timestamps; use media time for file durations. Handle missing observations/disconnects without accumulating fictitious continuous presence. Keep preview independent of slow inference.

## Implement initial real plugins and scenarios

### People/vehicle

Implement a real Ultralytics detector adapter plus ByteTrack integration using the pinned library's supported APIs. Coordinate preprocessing and RGB/BGR conversion once. Verify output mapping through resize/letterbox to original geometry.

Implement:
- Zone entry with explicit outside→inside transition policy, including behavior when an object first appears already inside.
- Directional line crossing using trajectory history and hysteresis/debounce, not frame jitter.
- Dwell duration in a zone with short-gap grace and reset rules.

Use configurable anchor geometry such as bottom-center, documented for the camera view. Dwell is not stationary-parking detection unless movement criteria are separately implemented. No cross-camera identity matching.

### Fire/smoke

Implement a real compatible detection-checkpoint adapter for canonical smoke/fire labels. Add temporal confirmation, short-gap tolerance, incident episode lifecycle, and cooldown. Define whether one active episode is aggregated per class/zone or another explicit key. Do not imply static single-frame boxes prove an emergency. No requirement to train a new model within this task.

### Deterministic demo

Provide a separate explicit dummy plugin with controllable observations to exercise every scenario, including negatives. Every synthetic result must be labelled SIMULATED in API/UI/evidence metadata. Dummy mode must be opt-in and may not be the fallback for missing real checkpoints.

## Application, evidence, API, and Visor integration

Wire Hub into existing application flows; do not leave it as an isolated CLI library.

Backend owns persistent incidents, audit, notifications, users, and files. Plugins produce typed events and do not write application tables. Provide a single event sink mapping stable START/UPDATE/END events into existing deduplication and incident workflow. Scene clearance and operator resolution remain distinct. Repeated updates must not create rows/notifications per frame. Define operator-resolved-but-still-observed and recurrence behavior.

Evidence must match the triggering frame. An event cannot simply refer to the latest JPEG after it has been overwritten. Implement bounded pinned/copy-on-event evidence handoff or equivalent. Protect evidence access and preserve existing retention semantics.

Add/integrate APIs for:
- Module catalog, metadata/status/errors, validation and reload (admin-only mutations).
- Assigning modules/scenarios and zones/lines to sources/jobs.
- File job creation, progress, cancellation, results, and failure details.
- Hub status: processing rate, drops, queue depth, inference latency, active sessions and failures.

Do not invent endpoint paths without checking existing routes. Record implemented endpoints in docs/OpenAPI. Long analysis runs in workers, not request handlers. Prevent duplicate file-job execution and define interrupted-job recovery/failure behavior.

Visor minimum:
- Show available/unavailable modules and actionable missing-file paths.
- Let users select compatible modules and configure scenarios with source/job zones and directional lines.
- Live: real preview, module health, event list and evidence.
- File: authorized upload/import, progress, cancel, event timeline and seek to event time in browser-playable input.
- Authenticate source/video/evidence routes; bounded file uploads/import roots.
- Distinguish decode support from browser playback support. Report unsupported browser codecs or provide a documented controlled preview conversion; never claim arbitrary codecs play in browsers.
- Show missing weights as unavailable, not zero detections or success.
- Preserve existing plain JavaScript UI unless the repository has already changed. No unrelated visual rewrite.

## Developer CLI and templates

Implement commands under the existing app.commands CLI or a compatible subcommand structure. Document exact commands that actually exist for:
- list-models
- validate-model <module_id> (metadata and runtime modes)
- reload-model <module_id> safely in the relevant runtime
- analyze-video with input, selected modules, scenario configuration, and output directory
- hub-self-test using explicitly simulated fixtures

These are required capabilities; adapt flag syntax to the current CLI consistently. No undocumented pretend commands. Analyze-video must exercise the same Hub/plugins as the application, not a separate throwaway implementation.

Provide a delivery checklist and generation/validation helper for model packages. Creating templates must never overwrite teammates' weights or existing populated configuration. Package reload should require deliberate action, reject mixed/incomplete file updates, and preserve the last valid version or leave an explicit failure state.

## Verification

Run focused tests for:
- Missing weights, malformed manifest, wrong class map/task, path escape and checksum mismatch.
- CPU operation and explicit CUDA-unavailable behavior without pretending GPU tests passed.
- Model-load reuse and isolation of tracker/rule state across two sources/jobs.
- Module failure isolation and cancellation/shutdown.
- Coordinate transforms and zones/lines.
- Entry/crossing/dwell/fire episode timing, jitter, gaps, cooldown and recurrence.
- Evidence correspondence and incident deduplication.
- Ordered file processing and timestamp-based results independent of execution speed.
- Access restrictions on catalog mutations, video and evidence.
- Complete synthetic pipeline through actual API/worker/database and Visor where supported.

Real inference tests: use a trusted compatible checkpoint already available. If none exists, implement the real adapter fully and test a small locally generated untrained model checkpoint through the actual installed model library where practical. Label this an integration smoke test, not a trained detector or accuracy test. Do not download production weights automatically or create fake performance metrics. Record which tests use mocks/synthetic observations versus actual model loading/inference.

Docker/PostgreSQL tests should run if available; otherwise record the gap and verify independent local paths. Physical camera tests require explicit configured authorization; lack of camera access does not block file-mode completion.

No training of large models is required. No external notifications, public deployment, facial identification, or large dataset acquisition in this task.

## Documentation and team handoff

Create/update:
- models/README.md: exact placement and activation steps for AI 1 and AI 2.
- docs/MODEL_PACKAGE_SPEC.md: complete validated schema and examples.
- docs/AI_HUB.md: lifecycle, scheduling, isolation, runtime choices and failures.
- docs/AI_INTEGRATION_CONTRACT.md: typed frame/detection/event contracts with fixtures.
- docs/SCENARIO_RULES.md: precise temporal/spatial semantics.
- docs/MODEL_HANDOFF.md: owner checklist, validation and integration steps.
- README.md, AGENTS.md, docs/IMPLEMENTATION_STATUS.md: actual commands and verified scope.

Document that AI owners submit best.pt PLUS accurate class mapping/config, model card/provenance, training/evaluation details and tested package/runtime versions. Once the package passes validation, the operator explicitly reloads/selects it. Only checkpoints compatible with the installed adapter are drop-in; another architecture needs a new reviewed plugin.

## Acceptance checklist

- [ ] Existing repo preserved; no duplicate competing Hub or ingestion implementation.
- [ ] Canonical model directories and valid templates created, with no fake weights.
- [ ] One documented plugin contract and package validator.
- [ ] Real Ultralytics detection adapters and ByteTrack integration implemented.
- [ ] Entry, directional crossing, dwell and smoke/fire temporal rules implemented.
- [ ] Per-camera/per-job state isolation and bounded scheduling.
- [ ] Hub connects to existing ingestion, incident persistence and evidence paths.
- [ ] LIVE and FILE mode use the same modules with correct time semantics.
- [ ] Visor can inspect module readiness and select/configure supported modules.
- [ ] File job progress/cancel/results and event navigation work for supported input.
- [ ] Safe explicit package reload without rebuilding the application.
- [ ] Demo works without real weights and is unmistakably simulated.
- [ ] Missing real weights remain explicitly unavailable; no invented detections.
- [ ] CLI, tests, model placement guide, and AGENTS documentation align with code.

Do not mark runtime acceptance passed based on file existence, syntax checks, or mocked calls alone. Report HUB_INFRA_READY separately from REAL_MODEL_VALIDATED and CAMERA_VALIDATED. Infrastructure can be complete while specific real-model/device validation remains pending.

## Final response

Report what was implemented, checks and actual outcomes, remaining blockers, exact commands to run self-test and import/activate each package, and the absolute model paths resolved from this checkout. Show both canonical relative paths:
- models/people_vehicle/weights/best.pt
- models/fire_smoke/weights/best.pt

Explicitly state whether a trained model was used and which scenarios were validated with real inference. Do not stop at scaffolding or documentation; finish the working model-ready Hub and application integration within this scope.
