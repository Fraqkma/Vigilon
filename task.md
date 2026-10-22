# Vigilon / Visor: Real Camera Ingestion Validation

## Objective and execution policy

Inspect the existing repository first, then connect the existing camera through the existing API, worker, frame buffer and Visor. Complete a bounded real-camera validation and fix concrete integration defects only after the assessment is complete. Do not rebuild the architecture. This task authorizes local implementation fixes after assessment; it does not authorize changing camera/router configuration, installing global software, committing, pushing or deploying.

Before editing code, write a concise assessment and proposed execution sequence to docs/CAMERA_INTEGRATION_ASSESSMENT.md and summarize it to the user. Continue with compatible, local, reversible fixes without requesting another routine approval. If a substantial architecture/API change appears necessary, describe the evidence and stop that change for a decision. Preserve unrelated work.

## Current evidence supplied by the user (2026-10-22)

- Camera: Hikvision DS-2CD1143G2-LIU, powered by TP-Link ES206GP PoE switch port 4.
- Password recovered through Hikvision software recovery; not a confirmed hardware reset.
- Camera activated; browser login and real live view work.
- DHCP enabled; last camera IP 192.168.1.102, mask 255.255.255.0, gateway 192.168.1.1.
- Last PC IP 192.168.1.180 on Ethernet, Windows 11. The machine executing this task may be different: verify reachability from the actual worker host.
- HTTP port 80; RTSP port 554.
- User verified VLC playback of rtsp://192.168.1.102:554/Streaming/Channels/101 with admin credentials.
- Channel 102 is a candidate substream, NOT verified: rtsp://192.168.1.102:554/Streaming/Channels/102.
- ONVIF is disabled/not tested; not a prerequisite for this RTSP milestone.
- DHCP reservation, encoding details, time synchronization and long-run stability are not verified.
- No evidence yet of real frames reaching the Vigilon backend or Visor.
- The people/vehicle team reported improved fine-tuning metrics, but checkpoint availability, compatibility and runtime inference inside this repository remain unverified.

Treat these as user-reported external checks, not checks you ran. Never claim VLC success establishes backend success. Do not use the previous camera IP 172.16.26.33.

## Phase 1: Read-only repository assessment

1. Confirm repo root, branch and git status. Read applicable AGENTS.md, README, implementation-status documents, architecture, camera compatibility, security and AI Hub docs. Respect existing Codex/ECC settings and available tools; do not modify global settings, hooks or MCP configuration. Do not assume a named tool is available.
2. Inspect actual code and pinned dependencies, not only documentation. Locate:
   - Camera/source create/edit/probe APIs and credential encryption/redaction.
   - RTSP adapter, decoder backend, transport options, connection/read timeouts and process/thread cleanup.
   - Worker ownership/lease, per-source lifecycle, bounded buffers, timestamps and stale-frame handling.
   - Worker-to-API preview publication, shared storage and authenticated preview access.
   - Visor camera management and Live Monitoring, including loading/offline/stale states.
   - Model registry/validation/reload and scenario-to-incident integration.
   - Existing tests and documented Windows startup commands.
3. Identify which pieces already exist, which have mock-only evidence, and concrete gaps. Reference actual repository paths. Keep FastAPI, the existing database setup and frontend stack unless a real blocker proves a change necessary.
4. Establish acceptance checks before making fixes. Do not add new ONVIF, streaming servers, dashboards, adapters or database tables simply to run this task.

## Phase 2: Local setup and credentials

- Use the current virtual environment and dependency locks. Inspect running services before starting anything; avoid duplicate ingestion workers and do not kill unrelated processes.
- Prefer the currently functioning local database mode. Do not make Docker/PostgreSQL a prerequisite for a local SQLite camera test. Report environments not exercised.
- Use the existing authenticated camera form to enter the password. The user must enter secrets locally; never request passwords in chat, command arguments, task files or screenshots. If unattended tooling needs a credential, use an existing secure mechanism or an ignored local secret file entered by the user; do not print its content.
- Never log complete credential-bearing URLs. Redact credentials in errors, decoder stderr, reports and examples. Preserve encryption and existing password keep/clear semantics.
- Preserve existing camera records; reuse or create one clearly named test source without duplicating it on reruns. Inspect existing URL/credential fields rather than assuming their schema.
- If the host has no LAN access or credentials are missing, complete the assessment and useful local checks, then give the exact minimal user action required. Do not substitute a synthetic source and mark the physical camera passed.

## Phase 3: Real RTSP ingestion, without AI

Start with the user-verified channel 101 and the camera's CURRENT configuration. Do not change encoding just because H.264/1080p/15 FPS was previously suggested.

1. Verify the specific camera host/port from the worker host using bounded checks; do not scan the LAN. Distinguish unreachable host, refused port, authentication failure and decoding failure where supported. If DHCP changed the address, ask the user for the current address instead of guessing.
2. Use the existing connection-probe workflow and decoder to obtain real decoded frames. Observe codec, dimensions and stream metadata if exposed. Do not confuse configured stream FPS, decoded FPS and inference FPS.
3. Add/enable the source through the existing application flow with AI disabled. Verify worker health, frame delivery and preview updates through the API and Visor.
4. Run a bounded 10-minute ingestion test (configurable shorter diagnostic runs are allowed, but report actual duration). Monitor at short intervals without blocking communication. Record time to first frame, decoded/published frame counts where available, measured FPS, read failures, reconnect attempts, frame age, buffer occupancy/capacity and process resource usage at start/end. Do not invent measurements not exposed by the system.
5. Verify freshness using sequence numbers/timestamps and a physical scene change if possible. A static scene can produce identical image hashes, so hash equality alone is not a valid frozen-stream detector. Distinguish local receipt age from true camera-to-screen latency; do not claim end-to-end latency without synchronized capture timestamps.
6. Verify Visor shows current frames and honest online/stale/offline states. Prevent an old image being presented as current live footage after ingestion stops.
7. Check bounded buffers remain bounded and old frames do not accumulate into growing live latency. Verify source shutdown releases resources.
8. Optionally test channel 102 independently after 101 works. Record its actual resolution/codec and results. A successful low-resolution preview does not establish that small objects will be detectable; choose the AI stream later using real examples. Failure of unverified 102 must not invalidate working 101.

## Phase 4: Controlled reconnect test

- Use the existing source disable/enable operation to test application lifecycle separately from network loss.
- For a genuine disconnect, ask the user to unplug/reconnect only the test camera's Ethernet cable. Explain that PoE removal also reboots the camera and report this as a power/network interruption. Do not disable the PC NIC, alter firewall/router settings or interrupt other devices.
- Coordinate the physical action while observing the worker. Verify stale/offline indication, bounded reconnect backoff and automatic return to fresh frames without manually restarting the application.
- Record recovery time from the camera becoming reachable again where possible; separate camera boot time from worker reconnect delay.
- Verify there is no duplicate source reader/worker and no resource accumulation from repeated reconnects. Reset or invalidate downstream tracking state after a discontinuity using the existing contract.
- If no physical action is available, explicitly mark REAL_DISCONNECT_RECOVERY as NOT_TESTED. A simulated failure or manual disable/enable is useful but is not equivalent evidence.

## Phase 5: Minimal fixes, only where evidence warrants them

Make focused, backward-compatible fixes for defects discovered above, such as ineffective read timeouts, blocked shutdown, stale preview status, unsafe error logging or broken UI/API integration. Confirm decoder timeout/transport support in the actual installed versions using official docs or Context7 when available. Do not merely set an unsupported option and claim a timeout guarantee.

If a decoder can block despite configured timeouts, use the smallest architecture-compatible containment mechanism and demonstrate bounded failure behavior. Avoid broad rewrites. Add meaningful regression tests for repaired behavior; run existing relevant tests and syntax/diff checks. Keep mocked tests clearly distinguished from hardware tests.

## Phase 6: Optional real AI validation, separately gated

Proceed only after real ingestion succeeds AND a trusted team-supplied checkpoint and matching package configuration are available. Do not download random weights or retrain as part of this task.

- Expected existing package paths, relative to repository root:
  - models/people_vehicle/weights/best.pt
  - models/fire_smoke/weights/best.pt
- Read the actual manifest/config contract. Check architecture, task type, classes/IDs, checksum, provenance and compatibility with the pinned runtime. Do not assume that renaming an arbitrary checkpoint best.pt makes it compatible.
- Run existing metadata/runtime validation and explicit reload. Verify the worker actually loaded the requested version; an accepted reload request alone is insufficient.
- Missing weights must stay MISSING_WEIGHTS, with ingestion and raw preview working independently. Never fall back silently to SIMULATED detections.
- Start with people_vehicle. Verify real observations, frame association, tracking IDs and processing speed. An empty scene with zero detections is not sufficient proof of successful person detection.
- Let the user draw a zone/line through Visor and perform a safe walk-through. Test one selected rule end to end: actual detection -> tracking/rule -> event candidate -> persisted incident -> matching evidence -> acknowledgment/resolution and audit history.
- Check an ordinary negative case and repeat an event to inspect deduplication. Confirm observations/evidence belong to the correct source/frame; ensure reconnect does not generate spurious crossing events from stale tracks.
- Do not stage actual fire or dangerous falls. Fire/smoke model testing, if needed, uses authorized recorded footage in a separate FILE test and must not be represented as a physical-camera fire test.
- These are integration checks, not a general accuracy certification. Report the team's training metrics separately from runtime checks.

## Camera settings to report, not change silently

Create a short checklist of actual and pending values: codec, resolution, FPS, bitrate/mode, I-frame interval, substream, camera time/timezone/NTP. Record unknown values as unknown. If decoding is blocked by an encoding setting, explain the observed error and propose the smallest manual change, recording old/new values if the user performs it.

Recommend reserving the current camera address via router DHCP reservation as a follow-up, subject to the router supporting it. Do not set an arbitrary static IP that could conflict with the DHCP pool. ONVIF setup is deferred unless a specific existing integration requirement makes it necessary. No firmware upgrade is required by this task.

## Evidence and delivery

Create/update docs/CAMERA_VALIDATION.md with:
- Date, tested repo commit plus dirty-work note, actual execution environment and relevant versions.
- Source ID and sanitized stream address, stream metadata, commands actually executed with no secrets.
- Results for direct decode, existing probe API, worker ingestion, Visor preview, freshness, bounded-duration stability and reconnect, including durations/measurements.
- Exact defects, fixes and regression checks.
- Human-performed observations clearly attributed to the user.
- Unverified items and reproducible next steps.

Preserve the repository's current readiness semantics. Distinguish in the report:
- EXTERNAL_RTSP_VALIDATED: user-reported PASS for VLC channel 101.
- BACKEND_INGESTION_VALIDATED: PASS only with real decoded frames through the actual worker and API.
- VISOR_LIVE_VALIDATED: PASS only with real updating authenticated preview.
- REAL_DISCONNECT_RECOVERY: PASS only after an observed real interruption and recovery.
- REAL_MODEL_VALIDATED: only if real runtime/model checks pass; not inferred from metrics or mocks.
- CAMERA_AI_E2E_VALIDATED: only if the actual camera event/evidence/operator workflow succeeds.

Do not silently redefine CAMERA_VALIDATED. Inspect its documented meaning, state which checks it requires and set it only when those checks have evidence. If no definition exists, keep it pending and propose the precise gate in the report rather than fabricating one. New report labels do not require new persistent API statuses or migrations.

Keep private footage/evidence, credentials, local databases, model binaries and machine-specific secrets out of Git. Store test artifacts in existing ignored local storage and reference sanitized evidence in documentation. Do not erase pre-existing recordings or data.

Update IMPLEMENTATION_STATUS.md and relevant README instructions with actual results. Update AGENTS.md only if a concrete repo-specific workflow needs documenting; preserve current instructions and global settings.

Final response in Thai: what was inspected, what changed, what passed with real hardware versus mocks, what remains blocked, and exact Windows next steps. Include a suggested commit message reflecting actual changes. Do not commit or push.
