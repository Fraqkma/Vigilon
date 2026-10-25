# Vigilon / Visor — Minimal UI and usability redesign

## User request and outcome
The current website feels sloppy, cluttered and extremely difficult to use. Redesign the actual existing Visor frontend into a coherent, minimal, polished product, inspired by the clarity of the user's previous KBTG / Flow Sync digital-banking UI work. Improve information architecture and workflows, not just colors or border radii. Implement and validate the redesign end to end in this repository. A mockup, separate demo site, proposal, or CSS-only patch is not the requested result.

Reference context: the recovered KBTG direction used white/charcoal neutrals, readable typography, strong hierarchy, restrained cards and a red accent. The exact foreign-bank reference and screenshot are not available here; do not pretend to have seen them or invent a bank name. Translate the simplicity and polish to camera operations. Use Vigilon/Visor identity, without bank branding or financial widgets. For Visor, reserve red/amber for danger and incident severity; use a restrained teal accent for normal primary actions. Default to a light interface; video itself can retain a dark canvas. If the user supplies an exact visual reference during work, incorporate it.

## 1. Inspect and establish scope
- Read applicable AGENTS.md, README, current architecture/status, module ownership and feature contracts. Respect actual Codex settings, installed skills, ECC workflows and available MCP tools. Do not change global tools/configuration.
- Inspect git status, branch, HEAD, recent commits and the actual frontend stack. Preserve teammate edits, task.md, existing data and API contracts. If clean, create/use `feat/visor-ui-refresh` from the current verified feature baseline; do not automatically merge missing branches or discard changes. If dirty, continue safely in the current checkout and record this.
- Run the existing app with isolated test data where possible. Inspect every reachable route, login, dialogs and representative workflows in the browser before editing. Read source as well as docs; do not assume all claimed features exist.
- Record the most important concrete usability problems and a concise implementation plan in `docs/VISOR_UI_REDESIGN.md`, then proceed without waiting for design approval. Make ordinary design decisions autonomously.
- Preserve the current implementation technology. Historical reports describe plain JavaScript feature modules: verify this. Do not introduce React, a new build pipeline, a new UI framework or a backend rewrite for a visual redesign.

## 2. Visual direction — deliberate, quiet and usable
Use these as initial tokens, then refine for actual contrast and screenshots:
- Page background #F6F7F9, surfaces #FFFFFF, primary text #17212B, secondary text #526170, subtle border #DDE3E8, primary action #0F766E with white text.
- Dark text, generous but purposeful whitespace, subtle dividers, minimal shadows, modest 8–12 px corner radii. No gradients, glass effects, neon, oversized welcome banners, decorative charts, unnecessary KPI tiles, or a card around every field.
- One clean sans-serif stack with Thai fallback, e.g. system-ui, Segoe UI, Noto Sans Thai, sans-serif. Use existing local assets if available; do not make rendering depend on external font CDNs. Fix broken character encoding, including page titles, as UTF-8 at the source rather than masking corrupted text with CSS.
- Consistent type scale: roughly 14–16 px body, 12–13 px secondary labels, 24–28 px page heading. Readable line heights and tabular numerals for time/counts where useful.
- Use a 4/8 px spacing rhythm, consistent field heights and alignment. Prefer 40–44 px main controls; touch targets at least 44 px on mobile. One icon family with visible labels for important actions; no emoji as product icons.
- Status indicators combine text with restrained color. Do not confuse camera health, incident severity and incident workflow status.
- One clear primary action per page or active workflow. Secondary controls are neutral; destructive actions are separated and explicit.
- Standardize buttons, fields, select menus, tabs, badges, tables/lists, menus, dialogs, drawers, toasts, empty states and loading states across all existing pages.
- No global CSS hacks that break maps, video or dialogs. Use shared tokens/primitives and scoped feature styles; remove superseded rules carefully.

## 3. App shell and navigation
- A compact left sidebar, approximately 220 px on desktop, a quiet top bar and a clear content area. Consistent page title, short contextual subtitle only when useful, and relevant actions.
- Organize existing destinations into a small, understandable hierarchy. Suggested mapping: Operations (Control Center, Live Monitoring, Incidents); Analysis (Video Analysis, AI Modules/Hub); Configuration (Cameras, Maps, Settings). Adapt to actual routes and permissions: do not create duplicate pages merely to match these labels. Preserve useful Overview content if present and avoid two competing home dashboards.
- Keep important destinations directly discoverable; secondary administration can be grouped. Keep existing deep links working or provide explicit compatible routing.
- No confusing duplicate camera settings or competing notification controls. One canonical editing flow per entity, linked from other surfaces.
- Put user/account/logout in a predictable location. Keep meaningful alerts visible without an always-expanded diagnostics wall.
- Improve login using the same design language, proper labels/autocomplete, accessible password visibility control and clear error/loading states. Preserve authentication, CSRF/session handling and account semantics.

## 4. Control Center — simplify the original six-panel layout
The earlier fire-alarm-console layout is context, not an immutable requirement. Preserve its capabilities while removing the visual overload.

Desktop starting layout:
- A compact context toolbar: existing site/plan selector, relevant health/incident summary and only the necessary actions. Do not invent site selectors unsupported by the data model.
- Main workspace: Map about 55–60% width, live Camera about 40–45%. Both have aligned headers, useful canvas sizes and expand/restore controls. Avoid fixed heights that crop content on common laptops.
- Below: a readable incident list/table with concise filters, clear selected state and the most useful columns (time, event, location/camera, severity, status). No duplicate event feeds.
- Context/device/specification information becomes a secondary drawer, details tab or disclosure. Keep it one obvious action away, not permanently occupying a third of the screen.
- Selecting an incident opens a usable detail/action area (drawer or adjacent pane at wide widths). Show incident-time evidence, source, time, status and actions clearly. Live footage must be separately labelled.
- Acknowledge, Resolve and False Alarm remain accessible with correct permissions and transitions; Acknowledge must not imply resolved. Prevent accidental duplicate submissions and show persistence errors.
- New events update counters/list without stealing selection, changing the selected camera or closing ongoing work.
- Preserve selection synchronization: map marker -> correct camera/context; incident -> correct plan/source/details. Handle cross-plan sources and cameras not yet placed with explicit useful states.
- No freely draggable desktop-window system. Avoid multiple nested scroll areas; one main page scroll, with deliberate bounded scrolling only where needed.

## 5. Refine existing feature workflows, not just the dashboard
### Maps
- Separate view/edit modes clearly. Keep Add plan / Edit map discoverable, and show concise placement instructions only while editing.
- Present unplaced cameras in a searchable picker. Preserve normalized coordinates, pan/zoom/fit, placement persistence, revision conflicts, replacement keep/clear choices and Save/Cancel semantics.
- Do not lose unsaved edits through a drawer, route change, plan switch or responsive layout change. Keep marker targets usable, even on small screens.

### Live Monitoring and Cameras
- Preserve the shared viewer across Control Center, Live Monitoring and camera details; no duplicate preview loops.
- Clean search/status filter, obvious single/2x2 toggle and slot assignment. Avoid action buttons floating over important video content; keep video aspect ratio intact and use object-fit contain where appropriate.
- Make no-camera, connecting, disabled, offline, stale frame, missing worker and permission-denied states distinct, with a relevant next action. Do not offer a reconnect button unless it actually works.
- Camera forms group connection essentials first and optional device/context details under a disclosure. Preserve password retention/explicit clearing and connection-test behavior. Do not expose stored credentials.

### Incidents and notifications
- Use a clear list/detail workflow with consistent severity/status labels, readable timestamps, searchable/filterable history and existing export capabilities.
- Evidence and action hierarchy should let an operator understand the incident before choosing an action. Retain audit notes/history and missing/expired evidence states.
- Keep counters, toast and sound preferences consistent. Do not duplicate notification subscriptions or send external notifications during QA.

### Video Analysis, AI and rules
- Video Analysis presents upload -> module selection -> progress -> results as a clear sequence, reusing the existing FILE pipeline. Preserve cancel, validation, timeline and job/source isolation.
- AI Hub distinguishes available, missing weights, validation failure, loading and disabled states truthfully. Basic users see concise status/action; detailed metadata goes in a disclosure. Do not display fake model readiness.
- Rules/forms group source, detection scenario, geometry and timing logically with units and meaningful inline errors. Preserve supported schedules, zones/lines and permissions. Unsupported capabilities must not appear as working toggles.

## 6. Behavior, accessibility and responsiveness
- Use real API data and persistent saves. No production mock fallbacks, fabricated cameras, fake charts, fake success toasts or inert controls. Synthetic demo states stay explicitly labelled.
- Preserve API response/error contracts and backend role enforcement. Do not alter database schema or operational settings unless a confirmed UI integration blocker requires a minimal documented change.
- Do not clear operator input on request errors. Use inline validation and clear recovery actions; prevent duplicate mutation requests.
- Implement loading, empty, error, offline, stale, permission-denied and session-expired states as appropriate. Do not use endless skeletons when an error has occurred.
- Keyboard access, visible focus, associated field labels, semantic buttons, accessible names, focus trapping/return for dialogs and drawers, Escape handling with unsaved-change protection, adequate contrast and reduced-motion support.
- Desktop at 1440 px and laptop at 1280 px: map/video remain useful and actions do not collide. Tablet at 768 px: simplify columns and move secondary information into drawers. Mobile at 375 px: use an accessible navigation drawer and clear Map / Camera / Events views or stacking, preserving selection across views. Do not shrink six panels into unreadable boxes.
- Long camera names, many cameras, long incident notes and Thai text must not break layout. No horizontal page overflow; intentional table scrolling must be contained and usable.
- Changing viewport, tabs or routes must not duplicate requests, reset saved map coordinates or leak listeners/object URLs. Retain bounded preview concurrency, frame freshness, cancellation/retry and logout cleanup from the existing monitoring implementation.

## 7. Implementation sequence
1. Audit the live UI and current feature/route contracts; note baseline screenshots internally without credentials or private camera imagery.
2. Implement shared tokens/components and app shell; create a coherent first working Control Center and login.
3. Apply the same system to every existing operator-facing route, modal and form. Finish the main workflows before decorative polish. Do not leave half the application in the old style.
4. Validate with the real local API and controlled fixtures. Iterate after viewing actual screenshots, including all requested widths.
5. Remove obsolete UI/styles only after checking references; update relevant docs and provide the final handoff.

## 8. Verification and definition of done
Use the existing tests and focused regressions where behavior changed; do not add tests that merely assert chosen colors/classes. Run applicable frontend/backend tests, syntax checks and git diff --check. No need to repeat unrelated model training or hardware qualification for a UI redesign.

Browser QA is required for claiming visual completion. Prefer the available Playwright tooling. If its regular Chrome profile is occupied, use an isolated temporary browser profile/context or an available local runner. Do not kill the user's browser, bypass tool restrictions or silently mark browser checks as passed. If genuinely unavailable, finish independent work and clearly mark visual acceptance NOT VERIFIED.

Exercise with an isolated test database/account and synthetic media:
- Login -> Control Center -> every existing navigation destination -> logout.
- Plan create/select/edit/place camera/save/reload/cancel, including zoom and responsive changes.
- Marker/incident selection -> correct preview/context/evidence, with no selection stealing when events arrive.
- Single/2x2 live monitoring, camera picker, offline/stale/worker-down states and repeated navigation cleanup.
- Incident acknowledge/resolve/false-alarm and persisted history using the allowed transitions.
- Existing camera edit/test, video upload/progress/cancel/results and AI/rules forms.
- ADMIN/OPERATOR UI permissions and direct API restrictions remain intact.
- 1440, 1280, 768 and 375 px; keyboard/dialog focus; long text; empty/loading/error states; console and failed network requests.

Inspect before/after screenshots locally for spacing, hierarchy, alignment and readability. Keep QA outputs free of secrets and private footage, and out of Git unless an existing test convention calls for sanitized fixtures. Stop only temporary services created for this task.

Deliver:
- The redesigned working existing Visor application, not a parallel prototype.
- `docs/VISOR_UI_REDESIGN.md` with the usability problems addressed, final navigation mapping, design tokens, modified modules, workflow changes, browser evidence/results and limitations.
- Relevant status/docs updates and a short Thai handoff: what changed, how to start/view it, actual checks, unresolved issues and suggested commit message.
- No commit, push, merge or deployment. Preserve task.md edits and teammate work. Do not claim camera connectivity, real model inference or production readiness from a UI test.

Begin assessment now and continue through implementation and visual verification. Make the interface substantially easier to use, not merely more decorative.
