# Live Monitoring

## Gap assessment

| Area | Existing behavior on `feat/map` | Gap for this feature |
| --- | --- | --- |
| UI entry points | Control Center had a compact preview renderer; Live Monitoring had separate camera cards and a camera-detail click action. | The surfaces did not share selection, tile controls, or preview ownership. |
| Preview transport and lifecycle | Both used authenticated `GET /api/cameras/{id}/preview` JPEG responses. The standalone page refreshed `<img>` URLs with an interval; Control Center relied on image loads. | Requests could overlap or paint late; each UI owned image refresh independently; object URLs and source sharing were absent. |
| API headers and freshness | Worker writes a JPEG and atomic JSON manifest containing capture time, dimensions, sequence, simulation flag and file name. API sends `X-Captured-At`, dimensions and source designation with `Cache-Control: no-store`. | The response did not expose frame identity or server-computed frame age, so the browser could not distinguish new bytes from a repeated/stale frame. |
| Health and authentication | `/api/cameras` provides enabled/status/last-frame/preview-stale; `/api/overview` includes worker lease state. Preview requires the authenticated session and returns 401/503 as appropriate. | Source, worker and displayed-image states were conflated in some UI overlays. Preview 401s needed to stop retries and use the shell's session flow. |
| Frame identity and races | Worker stores sequence-based JPEGs and retains a short handoff window; the route resolves one manifest to one JPEG. | No frame identity was sent to consumers, and interval-based refresh had no late-response generation check or bounded global scheduling. |
| Modules and ownership | `frontend/features/monitoring.js` only generated Control Center preview markup. `frontend/app.js` owned the separate live grid, intervals and camera selection. | Extract a shared preview manager and embeddable viewer inside monitoring.js; keep shell routing/auth transport and coordinator selection authoritative. |
| Branch and tests | Worktree `D:\GitHub\Vigilon`; branch `feat/live-monitoring`, based at `4d7cea530192b08dba51ec1bd364a4c8e79b280c` (committed Map feature). It is stacked on Map, which is not merged into `main`. Existing tests cover authenticated preview and Map; no monitoring lifecycle tests existed. | Add deterministic manager/grid tests, focused preview-header API assertions, integration documentation and browser QA. |

## Implemented scope

### Shared preview lifecycle

`frontend/features/monitoring.js` now owns preview subscriptions and UI presentation for Control Center, the Live Monitoring route, and camera detail. Requests use the authenticated `GET /api/cameras/{id}/preview` route and worker-published JPEGs; the browser never opens a camera/NVR session. Same-camera consumers share one request stream. The manager caps global in-flight requests at four, times out and aborts work, bounds transient retry backoff, stops on 401/403/404, suspends requests while the tab is hidden, ignores late responses after release, and revokes blob URLs after replacement/release/session end. Only visible tiles subscribe. Pause stops this display's requests while worker ingestion and AI processing continue.

The existing preview response is backward compatible and now includes `X-Frame-ID` and `X-Frame-Age-Ms` in addition to capture time, dimensions, simulation label, and `Cache-Control: no-store`. Frame identity combines the worker sequence and capture timestamp. Repeated identity does not change the displayed frame receipt time or measured new-frame rate. UI distinguishes camera health, worker lease, frame freshness/age, simulated source, and browser-displayed new-frame refresh rate. The latter is not source processing FPS or inference FPS. No database migration or detector change was needed.

### User interface and shared selection

The embedded viewer supports single view and up to four unique assigned cameras. Live Monitoring adds camera search and health filtering, per-slot assignment and focus, display pause, expand/fullscreen, and session-local preferences scoped to the current user. Cross-panel selection from a camera, floor-plan marker, or incident moves focus to its existing grid slot while preserving the other assignments. The Control Center's unsaved placement guard remains in charge of leaving the page. Ineligible/disabled cameras show explicit unavailable status; no simulated fallback image is created.

`frontend/app.js` owns route/auth/session transitions and the authenticated API transport. It mounts and disposes the shared module and handles an expired preview session through the normal login flow. `frontend/features/control-center.js` retains map and cross-panel behavior while composing the shared viewer. CSS is scoped under `.lm-`; no frontend build pipeline or new dependency was added.

### Contracts and tests

- `frontend/features/monitoring.test.js`: **10 passed**, covering shared source subscriptions, four-request concurrency cap, measured distinct frame updates, repeated identity, auth and transient failure behavior, timeout/backoff/recovery, hidden-tab suspension, late-response rejection, and unique grid/focus behavior.
- `backend/tests/test_vertical_slice.py`: authenticated preview test now asserts no-store, frame ID, age, capture/dimension headers, and simulation designation.
- `docs/FEATURE_MODULES.md` describes public module/lifecycle boundaries. `README.md` and `docs/IMPLEMENTATION_STATUS.md` link the feature and record tested limits.

### Verification record

Worktree is `D:\GitHub\Vigilon`, branch `feat/live-monitoring`, based on committed Map feature `4d7cea530192b08dba51ec1bd364a4c8e79b280c`; it is stacked on `feat/map`, which is not merged to `main`. No commit or push was made. The pre-existing user edit to `task.md` was preserved.

Automated checks: monitoring tests **10 passed**; Map geometry tests **5 passed**; full backend suite **29 passed** (one existing Starlette/AnyIO deprecation warning); focused preview API test **1 passed**; frontend JavaScript syntax checks, Python compileall, and `git diff --check` passed. Browser QA used a separate local SQLite database, local API/worker, generated plan image, and explicitly synthetic camera fixtures. It confirmed both UIs use the shared viewer, fresh authenticated frames and metadata, four unique tiles, cross-panel selection, duplicate-assignment focus, disabled-source error, pause without stopping worker processing, fullscreen and expand, ten route round trips, and viewport widths 1440x900, 768x1024, and 375x812 without horizontal overflow. A five-minute UI observation kept the worker lease ONLINE and all four tiles fresh with distinct frame IDs and hidden overlays; displayed new-frame rate was about 0.7/s while source target remained 2 fps. During this Windows-local synthetic run, the worker log also showed intermittent `PermissionError` while atomically replacing preview manifest files; frames continued to advance, but this means the run does not establish a clean worker-write stress result. After logout, the shell showed the login form, preview API returned 401, and no viewer tiles remained mounted.

No physical camera/NVR, real inference model, PostgreSQL, or Compose runtime was tested. Browser fixtures and worker events are simulated; no camera access or safety/accuracy claim follows from these checks.
