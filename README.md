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

Use the repository `.venv` Python instead of system Python. Configure retention days in `.env`; the cleanup command removes expired snapshots and flags their database references while preserving incident history. No periodic scheduler currently invokes it automatically.

## Troubleshooting

- Missing secrets: rerun `scripts/setup.ps1` or `scripts/setup.sh`; existing non-placeholder `.env` values are left unchanged. Keep the encryption key backed up separately: losing it makes stored camera URLs unrecoverable.
- Login fails: use the administrator password chosen during setup. It is stored only in ignored `.env`; bootstrap does not reset an existing account.
- Preview is offline: check worker process health, source enabled state, and the camera status. Distinguish worker heartbeat from source connectivity and stale preview in Overview/Cameras.
- RTSP remains offline: check the exact authorized stream URL, protocol, reachable private address, port, codec support, firewall, and configured allowlist. Error logs expose a category, not credentials.
- Compose database errors: check `.env` has a generated `POSTGRES_PASSWORD`, then inspect `docker compose logs db migrate api worker`.
- SQLite is the no-Docker development option; Compose uses PostgreSQL for durable deployment state.

## Scope and limitations

The browser client is a dependency-free JavaScript single page app, not React/Vite. The verified vertical slice covers generated synthetic sources, private authenticated JPEG previews, simulated obstruction incidents, evidence snapshots, in-app notifications, operator history, and a normalized rectangle/polygon zone editor. Real RTSP/file adapters are implemented but were not hardware/protocol-tested. Real AI detector plugins are unavailable. Monitoring schedules, a real connectivity-check endpoint, clips, external notifications, and user-management UI are not implemented. See [implementation status](docs/IMPLEMENTATION_STATUS.md) for evidence and the exact boundary.
