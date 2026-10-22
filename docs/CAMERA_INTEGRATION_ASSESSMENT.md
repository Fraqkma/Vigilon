# Camera integration assessment

Date: 2026-10-22  
Repository: `main`, HEAD `85a9e77`; working tree already contains user changes in `command.md` and `task.md`. These files will be preserved.  
Scope: bounded validation of the user-authorized Hikvision DS-2CD1143G2-LIU RTSP stream through existing Vigilon paths. No camera/router settings, architecture, global tools, or persistent API statuses are in scope.

## Existing implementation and evidence

- `backend/app/main.py`: admin-only `POST /api/cameras/test-connection`, max two concurrent probes, bounded probe thread, configured RTSP policy, redacted response; `POST /api/cameras` encrypts RTSP connection values, `PATCH /api/cameras/{id}` preserves an existing secret when the submitted connection is blank; authenticated preview serves worker handoff JPEGs. No camera-probe or preview endpoint has been run against this physical camera in this work session yet.
- `backend/app/adapters.py`: `OpenCVAdapter` uses pinned `opencv-python-headless==4.11.0.86`, FFmpeg backend, open/read timeout properties, URL/CIDR/service-port validation and decoder cleanup. Hardware timeout/codec compatibility is not established by the current generated AVI tests.
- `backend/app/worker.py`: separate singleton lease, per-source reader, one-slot replace-oldest frame queue, reconnect backoff, processed/dropped/reconnect counters, encrypted RTSP URL decryption, atomic JPEG/manifest handoff, and source `last_frame` timestamps. `camera_dict` computes `preview_stale` after eight seconds. Existing automated evidence covers synthetic/file fixtures and a mocked probe, not physical RTSP.
- `frontend/app.js`: existing authenticated camera configuration/test flow and Live Monitoring preview/status UI; no change is justified before observing real API/worker behavior.
- `docs/ARCHITECTURE.md`, `docs/CAMERA_COMPATIBILITY.md`, `docs/SECURITY.md`, and `docs/AI_HUB.md` document these contracts and explicitly state that a physical stream is unvalidated. No trained weights are recorded as available; real model validation is separately gated.
- User-reported only (not independently verified here): VLC played channel 101 at `192.168.1.102:554/Streaming/Channels/101`; candidate channel 102 is unverified; prior workstation address was `192.168.1.180`; no confirmed DHCP reservation. User must enter camera credentials only in the local authenticated form if needed.

The requested `docs/CODEX-NAVIGATION-GUIDE.md` is absent from this checkout. Root `AGENTS.md` is the only repository instruction file found. No other repository documentation or test evidence upgrades user-reported VLC playback to a backend/camera validation result.

## Acceptance checks and execution sequence

1. Inspect current local API/worker processes, configured local database mode, Python/OpenCV versions, and current worker-host reachability to the exact user-supplied camera address and RTSP port. Use bounded checks only; do not scan the LAN or reveal `.env` values.
2. Run focused existing repository checks for the connection probe, credential redaction, RTSP policy, bounded reader, and preview/status behavior. Label these as automated/mock or generated-media checks.
3. If the host can reach the supplied address and an existing local API/worker is safely available, ask the user to enter credentials through Visor's existing camera form (never chat/CLI); reuse a matching existing test source or create one named for this validation, with AI disabled. Probe channel 101 first.
4. Verify actual worker-published frame progression through the authenticated API/Visor. Record only observable counters/timestamps, elapsed duration, decoder metadata if exposed, and sanitized stream address. A short run may diagnose; only report the actual duration. Do not infer true camera-to-screen latency from local timestamps.
5. Do not perform a physical disconnect without the user's coordinated local action. Source disable/enable can test app lifecycle but cannot pass real-disconnect recovery. Test channel 102 only if channel 101 succeeds and then label it independently.
6. Fix only a reproducible, local, backward-compatible defect; add focused regression coverage and rerun relevant checks. If evidence requires a substantial API/architecture change, stop before that change.
7. Write actual outcomes and limitations to `docs/CAMERA_VALIDATION.md`, then update `docs/IMPLEMENTATION_STATUS.md` and README only where evidence changes the current record. Preserve existing user changes; do not commit or push.

## Result gates

- `EXTERNAL_RTSP_VALIDATED`: user-reported VLC channel 101 PASS only.
- `BACKEND_INGESTION_VALIDATED`: PASS only after real camera frames pass through the actual worker and API.
- `VISOR_LIVE_VALIDATED`: PASS only after authenticated real preview updates in Visor.
- `REAL_DISCONNECT_RECOVERY`: PASS only after a coordinated physical interruption and observed recovery; otherwise NOT_TESTED.
- `REAL_MODEL_VALIDATED`: requires available trusted weights and real runtime inference; not required for raw ingestion and not inferred from team metrics or mocks.
- `CAMERA_AI_E2E_VALIDATED`: requires a real camera observation through rule, persisted incident, matching evidence, and operator action. Do not silently redefine `CAMERA_VALIDATED`; report the documented gate and leave pending when evidence is insufficient.

No code changes have been made at this assessment stage.
