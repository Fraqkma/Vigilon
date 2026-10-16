# Implementation status

## AI Hub readiness

**HUB_INFRA_READY: yes.** The repository now contains two canonical package templates, strict metadata/path/class/scenario validation, optional SHA-256 verification, optional Ultralytics runtime loading and warmup, CPU/CUDA policy, detection-only task enforcement, BGR/RGB handling, original-pixel boxes, ByteTrack instances per source/job, serialized shared model calls, worker reload control, source module assignment, incident/evidence mapping, authenticated Hub APIs, and an AI Hub view in the existing JavaScript Visor. Ordered FILE analysis uses the same Hub and source adapter through `analyze-video`; it reports progress as frame counts in a final result document and does not silently call a partial run complete.

`REAL_MODEL_VALIDATED: no.` Neither canonical `best.pt` exists. Runtime-adapter control behavior was tested with a mocked loader; no Ultralytics or PyTorch model was installed or loaded, and no trained/untrained checkpoint inference was run. `CAMERA_VALIDATED: no.` There was no explicitly authorized physical camera or NVR session during this work. Synthetic tests below validate only simulated paths.

The live worker can run explicitly assigned modules and persist scenario events to existing incidents/evidence. Module selection is kept in existing rule configuration, without a schema migration. The authenticated API supports module catalog, metadata/runtime validation, worker reload requests, and per-camera module assignment. The Visor exposes readiness, validation/reload, live selection for configured RTSP/RTSPS sources, and FILE job creation/progress/cancel/results with an authenticated media route and event timeline seeking.

FILE jobs are stored as atomic JSON state/results in the existing shared handoff directory (no database migration). The worker runs one job at a time alongside LIVE ingestion, reports progress every ten frames, checks cancellation between frames, marks interrupted jobs failed on restart, caps event output at 10,000 and job history at 100, and exposes explicit deletion of terminal results. The Visor timeline seeks the authenticated original media route; browser playback still depends on codec support. No upload exists; inputs must be imported beneath `VIGILON_MEDIA_DIR`. The shared scenario utility is wired into live zone-entry/line-crossing/dwell processing and FILE jobs; detailed fire/smoke event confirmation still requires real temporal evaluation data and owner review.

## Simulated and metadata validation

- `hub-self-test` reports only `SIMULATED_SELF_TEST_PASSED`; normal/obstruction/person-down/smoke-fire use the existing generated synthetic plugin. These observations are marked simulated and do not prove detector performance.
- Metadata validation passed for both packages with `MISSING_WEIGHTS`; package schema, path escape, malformed YAML/config, duplicate labels, checksum mismatch, missing weights, and status distinctions are covered in tests.
- Adapter behavior tests use a stub YOLO loader to verify CPU warmup path, explicit CUDA-unavailable failure, unsupported task, and class-name mismatch. They are mocks, not model-library inference.
- No package weight file, production model, or false performance metric was created.

## Existing Vigilon behavior preserved

The API and worker remain separate and share the existing worker lease. Synthetic source, bounded latest-frame handoff, authenticated previews/evidence, incident deduplication/operator history, retention command, and existing camera/rule workflows remain in place. Real source module execution does not replace or weaken RTSP destination allowlisting or local media-root containment. Compose mounts `./models` read-only at `/models`; packages are not baked into images.

## Verification performed for this change

- `.venv` was created with Python 3.13 and project `requirements-dev.lock` installed. `pip check`: passed.
- `python -m pytest -q -p no:cacheprovider --basetemp=.data/pytest-last backend/tests`: **17 passed**, one existing Starlette/AnyIO deprecation warning.
- `python -m compileall -q backend/app backend/tests`: passed.
- `node --check frontend/app.js`: passed.
- `python -m app.commands list-models`: passed; both modules correctly report `MISSING_WEIGHTS` with absolute paths.
- `python -m app.commands validate-model people_vehicle --mode metadata`: passed metadata, reported missing weights.
- `python -m app.commands hub-self-test`: passed with three explicitly simulated scenarios; did not validate real inference.
- FILE job worker/API test: a generated three-frame AVI, mocked detection runtime, ordered frame count, scenario event, cancellation, result retrieval, deletion, and media-root escape rejection passed. This is a FILE pipeline test with mocked observations, not model inference.
- Docker Compose runtime was not available because the Docker executable is absent; Compose YAML parsed. PostgreSQL, actual Ultralytics/PyTorch inference, physical camera/NVR, live model reload with a running worker, and browser-level AI Hub workflows were not run.

## Remaining work / owners

- **AI 1:** supply trusted people/vehicle detection checkpoint and exact class map, model card/provenance/license, training/evaluation evidence and runtime versions; verify entry/crossing/dwell and cross-source tracker isolation.
- **AI 2:** supply trusted fire/smoke checkpoint and exact class map, provenance/license and temporally evaluated episode behavior.
- **AI 3 / integration:** run browser QA for the AI Hub/file timeline and test FILE cancellation while LIVE sources are active; confirm runtime and codec behavior on a target machine.
- **Compatibility / PM:** test supported codecs and authorized RTSP/NVR on a stated hardware matrix; record `CAMERA_VALIDATED` only after that test.

Startup, validation and activation commands are in `models/README.md` and the AI Hub section of `README.md`.
