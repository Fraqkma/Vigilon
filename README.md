# Vigilon

Vigilon adds incident review, evidence snapshots, and operator actions to compatible cameras and NVR channels that you own or administer. It supplements certified safety and fire systems; it is not a camera or replacement NVR. The working demo runs entirely on CPU and uses generated frames and clearly marked simulated detections.

## Local demo on Windows

Requirements: Python 3.10 or newer. Node and Docker are not needed for the local demo.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\scripts\setup.ps1
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.commands migrate
.\.venv\Scripts\python.exe -m app.commands bootstrap-admin
.\.venv\Scripts\python.exe -m app.commands seed-demo --scenario obstruction
```

Setup creates ignored `.env` values only where placeholders remain, prompts for an administrator password without echoing it, and leaves configured values alone. Start the API and worker in two PowerShell windows from the repository root:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.worker
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) and sign in as the admin user configured in `.env`. OpenAPI is at `/docs`. To run the automated checks and live smoke command, install the test tools with `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock`; then run `.\.venv\Scripts\python.exe scripts\smoke_demo.py` in a third window with `PYTHONPATH=backend`.

Choose `normal`, `obstruction`, `person_down`, or `smoke_fire` on the Cameras page. A simulated incident appears after the configured minimum duration. Its synthetic snapshot, `SIMULATED` badge, acknowledgement, resolution, and actor history are stored locally. Operator actions are also available from Incidents.

## Docker Desktop / Linux Compose

Install Docker Desktop with the Compose plugin on Windows, or Docker Engine and the Compose plugin on Linux. Generate `.env` with `scripts/setup.ps1` on Windows or `bash scripts/setup.sh` on Linux; setup generates local secrets without requiring Python packages and leaves already configured values unchanged. Then:

```sh
docker compose build
docker compose up -d db
docker compose run --rm migrate
docker compose run --rm bootstrap
docker compose run --rm seed-demo
docker compose up -d api worker web
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The frontend is bound to localhost, PostgreSQL has no host port, and Compose persists PostgreSQL and evidence/frame handoff volumes. To stop services use `docker compose down`; local database/evidence volumes remain. `docker compose down -v` deletes those volumes and their data.

On Linux without Compose, the equivalent local setup is:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
bash scripts/setup.sh
export PYTHONPATH=backend
.venv/bin/python -m app.commands migrate
.venv/bin/python -m app.commands bootstrap-admin
.venv/bin/python -m app.commands seed-demo --scenario obstruction
```

Run `.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000` and `.venv/bin/python -m app.worker` in separate shells, then browse to `http://127.0.0.1:8000`.

The migration is an explicit one-shot service. It runs before API and worker startup; neither process races to migrate. Bootstrap is idempotent. Demo seeding can be repeated to change the synthetic scenario.

## Add an authorized camera or NVR stream

An administrator can create a source through `POST /api/cameras` or the authenticated API. Supported source types are `rtsp`, `file`, and `synthetic`. For RTSP, supply the exact `rtsp://` or `rtsps://` channel URL and credentials only for a camera/NVR you administer. The API encrypts that URL with `VIGILON_ENCRYPTION_KEY`; it never returns it. Set `VIGILON_ALLOWED_RTSP_CIDRS` to the specific private ranges in your deployment. The adapter rejects other protocols and destinations, common non-stream service ports, and unresolved hosts. The worker status and latest frame show whether the configured stream connected.

For a recorder-managed analog camera, compatibility depends on the recorder exposing an authorized RTSP stream for that channel. A vendor-cloud-only camera is unsupported unless it exposes one of the implemented local interfaces. Docker Desktop may not route a container to every host LAN; check host firewall, VLAN routing, DNS, and camera/NVR stream permissions. Avoid publishing RTSP or Vigilon ports to the internet.

Local video paths are resolved beneath `VIGILON_MEDIA_DIR` (default `sample_data`). OpenCV/FFmpeg decodes the selected local file. At EOF the worker reconnects with bounded exponential backoff and replays the file from its beginning. RTSP/file decoding and codec combinations have not been verified against hardware here.

## Commands

From the repository root on Windows, set `$env:PYTHONPATH='backend'`; on Linux/macOS prefix Python commands with `PYTHONPATH=backend`. Then use:

```text
python -m app.commands migrate
python -m app.commands bootstrap-admin
python -m app.commands seed-demo --scenario obstruction
python -m app.retention
python -m pytest -q backend/tests
node --check frontend/app.js
```

## Model-ready AI Hub

The AI Hub accepts only reviewed Ultralytics detection checkpoints through the built-in `people_vehicle` and `fire_smoke` adapters. Place the owner-approved file at `models/people_vehicle/weights/best.pt` or `models/fire_smoke/weights/best.pt`, and update `classes.json`, scenarios, model card, evaluation, and optional checksum to match the checkpoint. The directories are mounted read-only in Compose and are not copied into the image, so adding/replacing weights does not require an image rebuild. The optional AI runtime is intentionally separate from the small CPU demo install. Install the matching CPU or CUDA PyTorch build for the target machine first, then `python -m pip install -r requirements-ai.lock`.

Windows activation/validation commands (run from repository root):

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.commands list-models
.\.venv\Scripts\python.exe -m app.commands validate-model people_vehicle --mode metadata
.\.venv\Scripts\python.exe -m app.commands validate-model people_vehicle --mode runtime
.\.venv\Scripts\python.exe -m app.commands reload-model people_vehicle
```

Repeat with `fire_smoke`. `reload-model` queues worker reload in the shared handoff directory. A running worker handles it at its next loop boundary. In Visor, open **AI Hub**, select an authorized file/RTSP source, choose modules, and save. Modules assigned without weights remain unavailable and produce no detections. Runtime validation is not an accuracy test.

For ordered file analysis in Visor, go to **AI Hub → FILE analysis**, choose an input beneath `VIGILON_MEDIA_DIR`, choose ready modules, and monitor/cancel the job. Results include a media-time event timeline that seeks the authenticated original video; browser playback depends on codec support. Compose mounts the host `sample_data` read-only at `/app/sample_data`, so copy/import files there before creating a job. The API keeps at most 100 job records and 10,000 events per result; terminal jobs can be deleted in Visor. There is no browser upload.

The CLI is also available: `python -m app.commands analyze-video --input <path-under-media-root> --modules people_vehicle,fire_smoke --scenario-config <json-file> --output <directory>`. Omit a module if its trusted weights are not installed. Result JSON is only marked `COMPLETED` after ordered EOF; decode/inference errors and cancellation produce `FAILED`/`CANCELLED` results. `python -m app.commands hub-self-test` exercises the explicit simulated fixture only.

The Hub catalog and templates establish `HUB_INFRA_READY`. No trained checkpoint is included, so this checkout does not claim `REAL_MODEL_VALIDATED` or `CAMERA_VALIDATED`. See [AI Hub](docs/AI_HUB.md), [package spec](docs/MODEL_PACKAGE_SPEC.md), and [model placement and handoff](models/README.md).

Use the repository `.venv` Python instead of system Python. Configure retention days in `.env`; the cleanup command removes expired snapshots and flags their database references while preserving incident history. No periodic scheduler currently invokes it automatically.

## Troubleshooting

- Missing secrets: rerun `scripts/setup.ps1` or `scripts/setup.sh`; existing non-placeholder `.env` values are left unchanged. Keep the encryption key backed up separately: losing it makes stored camera URLs unrecoverable.
- Login fails: use the administrator password chosen during setup. It is stored only in ignored `.env`; bootstrap does not reset an existing account.
- Preview is offline: check worker process health, source enabled state, and the camera status. Distinguish worker heartbeat from source connectivity and stale preview in Overview/Cameras.
- RTSP remains offline: check the exact authorized stream URL, protocol, reachable private address, port, codec support, firewall, and configured allowlist. Error logs expose a category, not credentials.
- Compose database errors: check `.env` has a generated `POSTGRES_PASSWORD`, then inspect `docker compose logs db migrate api worker`.
- SQLite is the no-Docker development option; Compose uses PostgreSQL for durable deployment state.

## Scope and limitations

The browser client is a dependency-free JavaScript single page app, not React/Vite. The verified vertical slice covers generated synthetic sources, private authenticated JPEG previews, simulated obstruction incidents, evidence snapshots, in-app notifications, operator history, and a normalized rectangle/polygon zone editor. Real RTSP/file adapters are implemented but were not hardware/protocol-tested. The model-ready AI Hub and Ultralytics adapters are implemented, but this checkout has no weights; runtime model and physical-camera validation remain pending. FILE job APIs, bounded worker processing, progress/cancel/results and browser event timeline are implemented; browser codec coverage was not tested. Monitoring schedules, a real connectivity-check endpoint, clips, external notifications, and user-management UI are not implemented. See [implementation status](docs/IMPLEMENTATION_STATUS.md) for evidence and the exact boundary.
