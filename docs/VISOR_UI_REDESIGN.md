# Visor UI redesign

## Baseline and implementation plan

Work began on `main` at `ee04dd9` with an existing user edit to `task.md`. That edit is preserved; no branch reset, merge, commit or push is part of this work.

The actual application is a plain JavaScript SPA with feature registration, a shared preview manager, and a FastAPI backend. The navigation guide referenced by the supplement is absent. Browser baseline captures are in ignored `.data/visor-redesign-qa/`, using a separate SQLite database, generated media, test accounts, and API/worker on port 8016.

Observed problems: six competing Control Center panels; map configuration fields always visible; tiny labels and preview controls; duplicated expansion controls; dense technical copy; horizontal mobile navigation; missing password visibility/loading feedback; polling replacing form inputs; incident actions separated from review; a prominent simulated demo competing with the real upload workflow. Overview repeatedly creates timers. Camera/rule dialogs need close protection and cleanup.

Implementation sequence:

1. Shared light tokens, typography, controls and grouped navigation, accessible mobile drawer and login.
2. Map and live workspace above a single incident queue; secondary context disclosure; deliberate map edit mode and retained drafts.
3. Consistent camera, incident, analysis, module and settings workflows without changing API schemas or preview scheduling contracts.
4. Browser checks at 1440, 1280, 768 and 375 pixels, focused behavioral tests, and final evidence/limitations below.

## Design and navigation

White surfaces on `#F6F7F9`, text `#17212B`, secondary `#526170`, borders `#DDE3E8`, primary teal `#0F766E`. Red and amber indicate danger/severity. Video remains dark. System fonts with Thai fallbacks, 4/8 pixel spacing, 40–44 pixel controls, visible keyboard focus and reduced motion.

Operations: Control Center, Live Monitoring, Incidents. Analysis: Video Analysis, AI Modules. Configuration: Overview (system health), Settings. Camera configuration remains in Live Monitoring → camera settings; map configuration remains in Control Center → Edit map. Existing route identifiers and feature registry extension points remain compatible.

## Implemented workflows and files

- `frontend/style.css` and the feature styles establish the light interface and consistent controls; video frames remain on dark canvases.
- `frontend/app.js` and `frontend/ui.js` provide grouped navigation, the mobile drawer, saved route identifiers, account controls, accessible native dialog handling, and normalized keyboard geometry input. Camera, rule, and incident actions keep their existing API payloads.
- `frontend/features/control-center.js` and its styles lead with the floor plan and shared live viewer, put the incident queue below them, and tuck optional camera and location information into one disclosure. Map metadata, normalized marker drafts, context edits, and incident notes survive re-render and request failures; navigation and plan switches guard unsaved work.
- `frontend/features/monitoring.js` and its styles keep the existing four-camera scheduler and shared preview owner while reducing repeated diagnostic text. Disabled cameras do not start preview requests. `frontend/analysis.js` releases its frame geometry observer when a later import replaces a drawing.
- Incidents use a searchable, filterable review list and evidence-first detail dialog. Camera source, zone, and context workflows remain attached to their existing screens. Generated demo analysis is secondary and visibly simulated; package metadata stays collapsed until requested. Unsupported schedules remain explanatory text, not a pretend toggle.
- `backend/app/main.py` decodes the UTF-8 HTML shell explicitly so its real title and branding render correctly on Windows locales that otherwise default to CP874.

## Verification evidence

Browser QA used an isolated SQLite database, two disposable accounts, three generated synthetic camera sources, a disabled source, a generated floor plan and clip, and API/worker on port 8016. Nothing used configured CCTV. Baseline and final screenshots are held in ignored `.data/visor-redesign-qa/`.

Playwright traversed all seven destinations at 1440, 1280, 768, and 375 pixels: **28 page/viewport checks passed**, with no document-width overflow or page JavaScript exceptions. The script is [check_visor_ui.js](../scripts/check_visor_ui.js); run it using Playwright's browser code runner in an authenticated local test session.

Additional browser/API journeys confirmed admin plan creation and PNG upload, placement save/reload, coordinate edit and cancel, keep-placement image replacement, map metadata save, searchable camera selection, disabled camera state and 2×2 slots, camera create/edit with long Thai text, rule geometry/timing save, incident acknowledgement/resolution/false-alarm audit history, a failed action that preserved its note, authenticated video import, simulated job completion, timeline and CSV export, job cancellation, truthful missing-weight package state, and keyboard/escape focus restoration for dialogs and the mobile navigation. An operator could acknowledge an incident but did not see admin controls; server attempts to create a plan or change a camera returned 403. An expired session returned to login and cleared preview tiles.

Automated checks: **24 frontend tests passed** (existing feature tests plus geometry and dialog lifecycle regressions); focused API, authorization, feature registry and incident checks: **19 passed**, with one existing Starlette/AnyIO deprecation warning. JavaScript syntax checks and `git diff --check` passed.

The evidence verifies the local interface and existing API paths. It does not validate PostgreSQL, deployment, camera/NVR interoperability, the loaded checkpoint, or real-model inference. Real footage was not used. No Git commit or push was made; the pre-existing `task.md` edit remains intact.
