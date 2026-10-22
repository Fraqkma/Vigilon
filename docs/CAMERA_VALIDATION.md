# Camera validation record

Date: 2026-10-22. Repository branch `main`, validation base HEAD `85a9e77`; workspace remains dirty with pre-existing `command.md` and `task.md` edits plus the local setup/provisioning work below. No commit or push was made.

Execution host: Windows 11 / PowerShell; `.venv` Python 3.13.0, OpenCV 4.11.0 with FFmpeg enabled, FastAPI 0.115.12. SQLite database `.data/vigilon.db`; API bound to `127.0.0.1:8000`. `.env` is ignored and untracked. Its malformed Fernet key was replaced only after verifying the local database had zero camera rows; other configured secrets were preserved. Admin and camera credentials were read locally and were not emitted.

## Actual camera results

Configured only the user-authorized Hikvision channel 101 source: source id `1`, sanitized URI `rtsp://192.168.1.102:554/Streaming/Channels/101`. The app stored its credential-bearing source encrypted. `simulated=false`, source enabled, assigned AI modules empty. Exactly one API process and one leased worker were used.

| Gate/check | Result | Evidence and boundary |
| --- | --- | --- |
| `EXTERNAL_RTSP_VALIDATED` | User-reported PASS | User reports VLC playback of channel 101. Independent app validation follows below. |
| Authenticated existing connection probe | PASS with decoder warnings | `POST /api/cameras/test-connection`, timeout 10s: `Connected and decoded a frame.` FFmpeg emitted HEVC `Could not find ref with POC` warnings while decoding; decoded frames and previews still arrived. Request used local credentials and did not expose them in logs/output. No camera encoding settings were changed. |
| `BACKEND_INGESTION_VALIDATED` | PASS | Real RTSP worker frames were published to the app's latest-frame handoff and retrieved by the authenticated preview route. API reported `ONLINE`, `simulated=false`, fresh frame. |
| `VISOR_LIVE_VALIDATED` | PASS, scoped to this run | Playwright authenticated to local Visor; live view showed the actual camera image at 1280x720 and `/api/cameras/1/preview`. A final fresh tab had zero console errors and the preview route returned 200, `REAL SOURCE`, a new captured-at timestamp and a 1280x720 JPEG. API and card counter advanced together after a stale-list UI fix. An earlier tab accumulated 198 browser-side `ERR_INSUFFICIENT_RESOURCES` messages over the prolonged tool session; cause was not isolated, and the final fresh-tab check passed. |
| Ten-minute stability | QUALIFIED, not clean | 600.6s, 121 samples, API status remained `ONLINE`; decoded/queued counter 309 to 1497 (+1,188; 1.978 frames/s), first counter increment within 5s, max sampled source-frame age 0.67s / mean 0.38s, dropped +0 and reconnects +0. Worker stdout also recorded `processing_error category=PermissionError` during the run. That counter is updated by the reader before preview publication, so it does not prove every frame was published; error count and exact failed filesystem operation were not captured. A later manifest and authenticated preview check succeeded (see below).
| Worker/API process resources | Measured | Worker: CPU 66.75 to 311.27s (+244.52s, ~40.7% of one logical core during the interval); working set 217.8 to 295.4 MiB (+77.6 MiB). API: CPU 3.11 to 7.34s; working set 94.5 to 94.9 MiB. A ten-minute increase is recorded, not interpreted as a long-run leak trend. |
| App disable/enable | PASS | Visor showed `DISABLED` after saving the source disabled. Re-enabled through Visor; worker returned it to `ONLINE`, preview fresh, with frame counter progressing. One reader-queue drop was observed after the timed window during follow-up UI actions; reconnects remained 0. This does not simulate a physical network interruption. |
| `CAMERA_VALIDATED` | PASS, scoped | The documented gate in `docs/AI_HUB.md` is separately authorized physical stream testing; channel 101 passed authenticated probe, worker ingestion and Visor preview on this host. This is not a universal compatibility or safety certification. |
| `REAL_DISCONNECT_RECOVERY` | NOT TESTED | No physical unplug / PoE cycle was requested or performed. Coordinate with the user; never disable the PC network adapter. |
| Channel 102 | NOT TESTED | Candidate substream was not attempted. |
| `REAL_MODEL_VALIDATED` | NO | Both model packages report `MISSING_WEIGHTS`; no model was assigned to the camera. |
| `CAMERA_AI_E2E_VALIDATED` | NOT TESTED | No real inference, incident/evidence or operator event workflow was exercised. |

After the 10-minute window, a new authenticated `GET /api/cameras/1/preview` returned HTTP 200, `X-Simulation: REAL SOURCE`, JPEG 57,006 bytes, 1280x720 and captured-at `2026-10-22T12:41:00.294471Z`; the on-disk manifest also advanced afterwards. The app exposes published preview dimensions, but not upstream codec, native camera resolution, configured source FPS, bitrate, I-frame interval, or camera/NTP timezone. The preview was 1280x720; upstream/native metadata remains unknown. Worker buffer occupancy is not exposed; code inspection confirms one bounded replace-oldest frame slot per source. No human-performed scene change was coordinated, so visual motion itself was not a separate freshness test; freshness was established from advancing worker timestamps/counters and frame-age samples.

## Automated / simulated checks (separate from the camera results)

Focused command (isolated test DB, not the live camera DB):

```powershell
$env:PYTHONPATH='backend'
$env:DATABASE_URL='sqlite:///./.data/camera-validation-tests.db'
$env:VIGILON_SECRET_KEY='test-signing-key-that-is-local-only'
$env:VIGILON_ENCRYPTION_KEY='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -p no:tmpdir --tb=short backend/tests/test_camera_setup.py backend/tests/test_vertical_slice.py::test_camera_connectivity_probe_is_admin_only_and_redacts_source_url backend/tests/test_vertical_slice.py::test_rtsp_policy_rejects_loopback_and_service_ports backend/tests/test_vertical_slice.py::test_source_reader_buffer_is_bounded_and_retention_keeps_reference backend/tests/test_vertical_slice.py::test_worker_lease_rejects_second_owner
```

Result: **10 passed**, one Starlette/AnyIO deprecation warning. These are automated unit/integration fixtures; they are not the physical-camera evidence above. `node --check frontend/app.js` also passed after the live-card refresh fix.

The previously attempted `test_bounded_video_import_preview_authorization_and_job_path` separately failed because `cv2.VideoWriter.isOpened()` was false, followed by Windows access denied while cleaning a temporary directory under `sample_data`. This is an existing generated-video/Windows cleanup issue, not a camera-path failure; it was not changed because it did not block this workflow. No claim is made that the full suite passes.

## Focused implementation fixes and setup

- Added explicit, opt-in `python -m app.commands provision-camera`. It validates through the existing RTSP destination policy and Camera model, encrypts credentials with the existing Fernet service, is idempotent, refuses conflicting or blank-password replacement, and never provisions automatically at startup.
- Preserved literal dotenv values by loading with interpolation disabled. `.env.example` contains only blank password fields.
- Fixed the Live Monitoring refresh closure to render the latest `cams` list, and versioned the app asset in `frontend/index.html` so cached browsers load the fix.
- The existing decoder, single worker, frame handoff, and preview routes needed no architectural changes. The PermissionError did not reproduce in the later authenticated preview check, but its exact filesystem operation was not established; do not treat the 10-minute interval as error-free.

Commands used for local bootstrap and operation (password values intentionally omitted):

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m app.commands bootstrap-admin
.\.venv\Scripts\python.exe -m app.commands provision-camera
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m app.worker
```

The API and worker are currently running in their original local sessions. AI remains disabled. For physical interruption recovery, ask the user to disconnect/reconnect only the test camera Ethernet/PoE and observe camera boot separately from worker reconnect delay.
