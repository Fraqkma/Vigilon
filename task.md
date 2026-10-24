# Vigilon / Visor — Live Monitoring Feature

## Mission

Complete Live Monitoring on a dedicated feature branch and integrate it with BOTH the existing Control Center camera panel and the existing Live Monitoring page. Build on the committed foundation and Map feature. This is an implementation task: inspect, implement missing behavior, test, and document. Do not deliver a disconnected replacement page or only a mockup.

The two UI surfaces must use the same monitoring implementation and preview lifecycle. Preserve the user's current visual design, map editor, incident workflows, authentication, and navigation.

## 1. Instructions, tooling, and branch safety

- Read applicable AGENTS.md, README, feature ownership/contracts, MAP_FEATURE.md, architecture/status documents, and relevant source first. Respect existing Codex settings, ECC workflows, and configured MCP tools. Discover actual capabilities; use relevant installed skills such as archify where appropriate, Context7 when version-specific documentation is needed, and Playwright for browser QA. Do not reinstall or change global tool settings. Report unavailable tools and use a reasonable fallback.
- Verify repository root, git status, branch, recent commits, and worktrees. The user reports Map is committed on feat/map; merging into the main integration branch has NOT been confirmed.
- Create/use `feat/live-monitoring` from a verified commit containing both the Control Center foundation and completed Map feature. If the current checkout is the committed feat/map tip, branching directly from it is allowed; document that this is a stacked branch depending on Map. Do not assume main contains Map, merge branches automatically, or include unrelated feature commits.
- If the desired branch already exists, inspect it before using it. If another task/worktree owns it or dirty unrelated work would be mixed in, use an isolated worktree with a descriptive unused branch name. Preserve all user changes, including task.md. Do not reset, discard, stash, or move unrelated changes automatically.
- Record branch, actual base SHA, worktree, and Map dependency. Do not commit, push, open a PR, merge, rebase, or delete branches.
- Use the project's existing frontend stack and backend conventions. No framework migration, new RTSP proxy stack, Redis, or microservices merely for this task.
- Do not print credentials, change encryption/signing keys, or commit .env, databases, captured frames, videos, or model weights. Existing local credentials may be used for authorized local testing without exposing their values.

## 2. Baseline and assessment

Reported baseline, to verify against code:

- FastAPI and SQLAlchemy/Alembic; API and ingestion worker run separately.
- RTSP/RTSPS, FILE, and synthetic sources; per-source bounded frame buffers and reconnect logic.
- Worker publishes JPEG/manifest data for authenticated preview; browsers do not receive camera credentials.
- Modular Control Center with shared plan/camera/incident selection; existing Live Monitoring and camera/rule management pages.
- Map supports plan management, pan/zoom, placement editing, save/cancel, revision conflicts, and cross-panel selection. Migration 0005_map_revision reportedly follows 0004_control_center.
- AI packages may still lack weights. Do not assume any real inference works.
- Earlier physical camera test: one Hikvision main stream decoded successfully and displayed a 1280x720 preview, around 1.98 decoded/queued FPS. There were PermissionError publishing errors, HEVC warnings, and an older browser tab resource issue. These are historical observations, not current validation or proof of their causes.

Start docs/LIVE_MONITORING_FEATURE.md with a short gap assessment:

1. Existing UI entry points, preview component, timers, subscriptions, API client, and cleanup.
2. Actual preview transport, headers/manifests, freshness metadata, camera/worker health semantics, auth, and relevant endpoints.
3. Existing frame identity and possible stale-frame/race behavior.
4. Minimal module extraction and shared-file changes needed.
5. Current branch/base and existing tests.

Then proceed with implementation; do not stop at the assessment.

## 3. User-facing behavior

### A. One monitoring module, two integrated surfaces

- Extend the actual existing monitoring feature directory, or create a narrowly scoped one if missing. Both Control Center and Live Monitoring page must compose its public interfaces.
- Control Center: compact selected-camera view plus a 2x2 grid option, using existing panel chrome and expand/restore behavior.
- Dedicated Live Monitoring page: single-camera and 2x2 grid views, camera search/filter, slot selection, and a clear return/open-in-Control-Center action. Four simultaneous visible previews are sufficient for this milestone; do not advertise untested larger grids.
- Preserve existing route URLs/deep links where possible. Selecting a camera then opening the other surface must retain the intended selection through the existing coordinator/router.
- Retain existing rule/settings/AI module actions via real links or existing controls. Do not rebuild those features inside monitoring.
- Use existing theme tokens, spacing, icons, and typography. Keep video dominant, actions compact, labels readable, and responsive layouts usable at 375/768/1440 pixels. No page-level horizontal overflow.

### B. Camera selection and grids

- List existing cameras with name and real health state. Search by existing name/location fields and filter by health where supported. Do not expose RTSP URLs or credentials.
- Single mode displays the selected camera. Grid mode supports explicit camera assignment/replacement/removal per slot and clear empty-slot states.
- Avoid duplicate camera assignments within one grid; explain or focus the existing slot instead of silently creating duplicates.
- Selecting a tile updates selectedCameraId and existing map/device context without forcing the entire grid to single mode.
- External map/event selection focuses the existing tile if already present. If absent, use a documented deterministic policy such as replacing the active slot, while preserving other slots. When no active slot exists, use the first empty slot, otherwise the first slot. Do not unexpectedly repopulate the whole grid.
- Preserve Map's unsaved-edit guard: monitoring selection must not force map navigation or discard placement edits. Use public selection actions; let Map apply its own guard.
- New incidents may update badges but must not steal selected camera, change grid assignments, or interrupt operator viewing.
- Preferences may be persisted locally if useful, scoped by user and validated against available cameras. Do not store credentials or images in browser persistence.

### C. Preview controls and truthful states

- Show camera name, connection state, frame capture timestamp where available, preview freshness, and actual REAL/SIMULATED source designation.
- Separate source connectivity, worker availability, and displayed-frame freshness. An ONLINE reader does not prove the displayed JPEG is fresh.
- Cover no selection, initial loading, source disabled, connecting/reconnecting, offline, stale frame, worker unavailable, access denied, session expired, and preview error. Use actual available signals; show unknown when evidence is absent.
- Retain the last good image only with an explicit stale/offline/paused overlay and last-frame time. Never relabel a cached frame as live because its HTTP request succeeded.
- Provide Retry preview, expand/restore, and optional browser fullscreen with graceful unsupported behavior. Retry should retry the UI/API operation, not reboot the camera or start an extra reader.
- Provide Pause/Resume preview if useful. Label it as a display-only action: it must not disable the source, ingestion, or AI monitoring. Do not add a global stop-monitoring switch disguised as pause.
- Camera enable/disable remains an explicit existing administrative action, subject to server permissions; preserve existing access without duplicating the management UI.
- Keep incident snapshots separate from live images. Selecting a historical incident must not overwrite the live panel with evidence labeled LIVE.
- Never render invented bounding boxes, tracking IDs, counts, or AI statuses. Reuse existing real overlay data only if it includes a reliable matching frame identity/dimensions; otherwise leave overlays out and document the reason. Do not overlay old detections on a newer frame.
- No audio, recording, PTZ, or camera controls unless already implemented and safely reusable; do not add fake action buttons.

## 4. Preview lifecycle and resource limits

Reuse the current authenticated JPEG/manifest transport unless a verified blocking defect requires a narrow fix. This milestone does not require WebRTC/HLS/MJPEG migration or browser-direct RTSP.

- Build/reuse one per-tab preview subscription manager keyed by source ID. Multiple consumers of one camera share its fetch lifecycle; use reference counting or an equivalent explicit ownership model.
- Only visible, active consumers request frames. Release subscriptions when slots change, pages/panels unmount, or the user logs out. Pause or stop requests when the document is hidden; resume promptly without a request burst. Do not unexpectedly unpause a user-paused preview.
- At most one in-flight preview fetch per source, plus a bounded global concurrency cap suitable for four visible cameras. Schedule the next fetch after completion, not overlapping setInterval calls.
- Apply reasonable timeouts and bounded retry backoff for network/5xx failures. Distinguish auth failures from transient failures; do not retry forever after logout or forbidden responses.
- Abort obsolete requests. Use generation/frame identity checks so a late response cannot paint a different slot, camera, or logged-out screen.
- Revoke replaced object URLs and release listeners, observers, timers, and image resources. Repeated navigation must not create accumulating polling loops or detached live consumers.
- Reuse shared health refresh data or one bounded batch request; do not add one independent health poll per component/marker. Do not introduce extra camera connections to display four tiles.
- Respect server freshness/cache contracts. Use cache behavior that avoids stale authenticated previews without generating unbounded unique DOM/images. Compare actual frame identity/timestamp; repeated bytes or repeated frame IDs are not newly captured frames.
- If metadata and JPEG can refer to different frames, inspect the handoff contract and add the minimal compatible mechanism (for example frame ID/timestamp returned with the actual preview response). Do not treat an unrelated current manifest timestamp as proof of an old image's freshness.
- Handle timestamp clock differences sensibly. Prefer server-reported age/health plus monotonic elapsed time since receipt where feasible; do not claim precise latency from unsynchronized browser/camera clocks. Document timestamp meanings and configurable stale thresholds.
- Separate source FPS, configured sampling FPS, actual preview refresh rate, and inference FPS. Do not promise or force 25/30 FPS. The objective is current, stable, bounded monitoring with measured refresh behavior.

## 5. Backend boundaries and compatibility

- Reuse existing camera, health, worker, preview, and auth APIs. Add only small backward-compatible metadata/errors or aggregation needed by this feature, with documented contracts and tests.
- Use existing API client/session handling and server-side permissions. Expired sessions must stop preview delivery; preview routes must remain authenticated. Do not expose source secrets in response metadata, URLs, logs, or errors.
- Never run RTSP decode or AI inference inside an HTTP request just to serve a tile. Preserve the worker lease and ingestion process boundaries.
- Do not introduce new schema/migrations unless a specific persistent requirement cannot be met otherwise. Viewing preferences do not automatically need a database table.
- Investigate the old PermissionError/resource issue only if it reproduces or blocks this work. If preview publication needs a fix, preserve atomic publication, bounded retry behavior, and cleanup. Do not swallow arbitrary filesystem errors or declare historical HEVC warnings solved by a UI change.
- No camera codec/FPS/IP/ONVIF configuration changes or physical unplug tests. Report a required physical/network action as a separate limitation.

## 6. File ownership and conflict avoidance

Primary owned areas: monitoring feature code/styles/tests, preview lifecycle service, narrowly scoped backend preview/health changes, and docs/LIVE_MONITORING_FEATURE.md. Adapt paths to the existing project.

- Do not put the full feature in frontend/app.js or frontend/features/control-center.js. Those should import/compose monitoring and forward shared actions.
- Keep any necessary extraction behavior-preserving and limited to monitoring code. Do not refactor Map or incident internals, change placement cardinality, or modify migration 0005_map_revision.
- main.py may register routes or delegate to existing services; avoid growing it with a new monolithic preview subsystem. Follow the actual backend structure.
- Preserve shared selection and API contracts. No private cross-feature DOM access or direct imports of another feature's implementation.
- List every shared file changed and explain why. Avoid unrelated formatting, dependency upgrades, root instruction rewrites, or global CSS changes.
- Document mount/update/dispose or equivalent interface, selection callbacks, subscription ownership, error/freshness states, and how another page embeds the same viewer.

## 7. Verification

Use isolated test database/media/handoff directories and synthetic fixtures for deterministic testing. Fixtures must be explicitly labeled. A mocked transport test is not a physical camera validation.

Automated tests should cover:

1. Per-source deduplication/reference counting, in-flight limits, timeout/backoff, and cancellation.
2. Unmount/logout/hidden-tab cleanup and safe resumption; no stale response updates after camera switch.
3. Repeated frame ID, stale image with ONLINE source, worker unavailable, disabled source, and recovery to a genuinely fresh image.
4. Auth expiry/forbidden behavior without infinite retry or credential leakage.
5. Grid assignment and shared selection behavior, including deleted/missing cameras.
6. Actual preview frame identity/timestamp and authorization if backend contracts change.

Use existing test tooling. Avoid large new frameworks merely for small lifecycle tests.

Playwright/browser QA:

- Login -> Control Center -> select a map marker -> matching live camera and context.
- Select an incident -> matching camera without confusing evidence and live preview; preserve Map dirty edits.
- Open the dedicated Live Monitoring page with the selected camera, switch single/grid, assign/remove/focus slots, and return to Control Center.
- Verify four distinct synthetic/test camera slots, empty slots, unavailable source, stale image, request errors, and recovery. Real/simulated labels must match actual sources.
- Verify Pause affects display only, and expand/fullscreen restores layout and selection.
- Rapidly switch cameras/pages and repeat navigation at least ten times. Inspect subscriptions, network request counts, and console errors for accumulation; do not claim absence of a memory leak solely from one screenshot.
- Hide/resume the page using browser lifecycle tooling where available; otherwise document what was actually tested.
- Logout during active preview: abort work, clear displayed private images, and reject further authenticated access.
- Check 1440x900, 768px, and 375px layouts, keyboard focus, accessible button labels, and no horizontal page overflow.
- Run a bounded stability observation (around five minutes) with synthetic sources, capturing refresh/freshness behavior and resource/request counts at start/end. Keep progress updates during the observation rather than blocking silently.

Optional physical camera validation:

- If the previously configured Hikvision source is reachable and credentials already exist locally, reuse it for a non-disruptive preview smoke/stability check. Do not request credentials in chat or change source configuration.
- Do not open an extra competing worker or stop a user-owned process; inspect existing processes/lease first. Start only necessary services and record ownership. Stop your temporary services after QA; leave pre-existing services untouched.
- Report REAL results separately, including duration, observed image updates/freshness, and errors. No camera available is not a blocker for completing the feature, but must remain unverified.
- Physical reconnect, multi-camera hardware throughput, and real AI inference remain separate validations.

Run relevant existing backend/frontend checks, syntax/compile checks, and git diff --check. Run a practical regression suite once after focused checks pass. Preserve pre-existing failure records. Do not claim PostgreSQL/Compose tested unless actually executed.

## 8. Acceptance and delivery

Done means:

- Both existing UI surfaces use the shared monitoring module and remain visually integrated.
- Single and 2x2 views work with shared camera/event/map selection.
- Preview lifecycle is bounded, cancellable, and cleaned up on navigation/logout.
- Displayed freshness and source/worker status are honest; cached images and simulated sources cannot masquerade as live real footage.
- Existing Map editing, incident actions, rules, settings, AI Hub, and video analysis remain accessible and intact.
- Required tests and browser QA are completed or specific environment blockers are documented without inflated claims.

Finish docs/LIVE_MONITORING_FEATURE.md with implemented/deferred scope, module interfaces, refresh/freshness semantics, API changes, test evidence, limitations, and merge notes. Make only minimal links/entries in shared docs as needed.

Final report must give branch/base/worktree and whether it depends on an unmerged Map commit; working user flows; main owned/shared files; actual tests and real vs synthetic observations; local run commands; known limitations; and a proposed commit message:

`feat(monitoring): integrate shared live views across Visor`

Do not commit or push. Leave reviewable changes ready for the user.
