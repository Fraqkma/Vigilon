# Vigilon / Visor — Modular Control Center Foundation

## Mission

Implement the first feature-development milestone in the existing Vigilon repository: a polished, modular Visor Control Center inspired by the user's fire-alarm console reference. Build a working UI foundation, reuse existing backend capabilities, and add only the backend structure and persistence necessary for this milestone. Make it easy for teammates to implement separate features without repeatedly editing the same files.

This is an implementation task. Inspect, document the assessment, then implement and validate. Do not stop at a proposal, static mockup, or empty directory scaffold. Do not attempt to finish the entire product backlog in this task.

## 1. Respect the local environment and existing work

- Read applicable AGENTS.md files, README, architecture/status documents, and relevant source before editing. Inspect git status and preserve unrelated and pre-existing changes, including command.md and task.md.
- Respect the user's existing Codex settings, ECC workflows, and configured MCP servers. Discover what is actually available. Use relevant installed skills (including archify if present and appropriate), Context7 for version-specific documentation when needed, and Playwright for UI verification when available. Do not claim to have used a tool that is unavailable.
- Do not install, overwrite, or globally reconfigure ECC, MCP, Codex settings, or skills. Missing optional tools are not a reason to abandon otherwise feasible work; document the fallback.
- Prefer the repository's existing frontend stack and conventions. The last reported frontend is plain JavaScript, not React. Use native modules and scoped CSS if appropriate. Do not introduce a framework migration, build system, microservices, or a new state-management dependency merely for this task.
- Preserve current API contracts, session authentication, authorization, camera credentials encryption, worker separation, AI Hub integration, and supported routes. Do not downgrade the reported Ultralytics 8.4.0 pin or change model/tracking behavior.
- Do not print secrets or add .env, camera credentials, live evidence, databases, or model weights to Git. Locally configured credentials may be used for authorized local tests without echoing their values.
- Do not commit, push, publish, or modify camera/network configuration. Do not reset the existing database. Use an isolated test database for fixture-based QA.
- Proceed autonomously on reversible implementation choices. Ask only for a genuinely blocking ambiguity, unavailable required credential, or physical action. Do not require approval after the assessment unless a material destructive change is necessary.

## 2. Known context — verify against the checkout

Existing reported capabilities include FastAPI, SQLAlchemy/Alembic, SQLite locally, PostgreSQL via Compose, a separate ingestion worker, authenticated JPEG previews, encrypted RTSP credentials, camera CRUD/probe, normalized zones/lines, incident status/history/evidence, FILE analysis jobs, and AI package readiness.

Existing Visor navigation reportedly includes Overview, Live Monitoring, Video Analysis, Incidents, AI Modules, and Settings. Preserve those workflows and deep links. Add Control Center as the operational landing view or integrate it with Overview with backward-compatible routing.

Real camera validation has previously passed for one Hikvision camera/channel on one host, with unresolved PermissionError, HEVC warnings, and an older-tab resource issue. Physical reconnect, other channels, general compatibility, and real AI inference are not established by that result. Do not silently change these readiness claims or turn old reports into new test evidence.

The user's eventual feature backlog is: custom maps/plans, single/multi-camera monitoring, per-camera rules, notifications, incident acknowledgement/resolution, historical logs/search, recorded-video analysis, and camera health/management. This milestone provides the shared foundation and a working Control Center slice; reuse existing workflows for the rest.

## 3. Inspect first, then implement

Write a concise docs/CONTROL_CENTER_ASSESSMENT.md before substantial code changes. Record:

1. Actual UI entry points, routing, CSS, API client, polling/subscription ownership, and cleanup behavior.
2. Existing camera, preview, incident, evidence, audit, rule, and analysis APIs that will be reused.
3. Existing location/device/owner fields and migrations, if any.
4. The minimal extraction plan for large shared files; avoid a wholesale rewrite.
5. Proposed feature boundaries, new data/API needs, and implementation sequence.

Then continue implementation. Treat suggested paths below as a logical design; adapt them to the actual repository rather than creating a second competing architecture.

## 4. UI reference and visual direction

The reference is a desktop fire-alarm console with six simultaneous panels arranged as three columns and two rows:

| Position | Reference | Vigilon implementation |
| --- | --- | --- |
| Top left | Map | Custom floor plan and camera markers |
| Top center | Camera | Live camera view, single/grid switch |
| Top right | Browser | Location context, responsible contact, response guidance |
| Bottom left | Event List | Operational incident queue |
| Bottom center | Event Action | Selected event evidence, details, and actions |
| Bottom right | Device image | Optional camera/device model, image, specifications, health |

If the screenshot is available in the user's attachments or repository, inspect it. If unavailable, use this description and state the limitation; do not block implementation or invent an accessible file path.

Use the reference's operational information hierarchy, with a modern visual treatment. Do not copy its old desktop chrome. Do not claim compliance with a fire-alarm standard or imply that Vigilon controls certified alarm equipment.

Visual requirements:

- Desktop-first, dense but readable. Use a restrained charcoal/navy surface, clear typography, consistent spacing, subtle borders, and visible focus states. Prefer existing local fonts/assets; do not require remote assets.
- Make map and live video the dominant work areas. Keep the context/device column narrower and collapsible; reclaim its space when hidden. Do not force six equally sized cards.
- Compact header: site/plan selector where applicable, camera/worker connectivity summary, active incident count, user/session controls.
- Reserve red/amber for severity or warnings. Status must also have text/icons, not color alone. Keep incident severity separate from lifecycle status and camera health.
- Provide panel expand/restore. Start with a stable responsive grid, not a draggable/dockable window framework.
- At smaller widths, stack or tab panels while retaining access to event actions. No page-level horizontal overflow. Allow deliberate local table scrolling where needed.
- Show explicit loading, empty, error, unavailable, stale, offline, and permission-denied states. Avoid placeholder buttons that appear functional.
- Optional device information must not leave a large empty panel when absent.

## 5. Required working behavior

### A. Custom floor plan

- Support named plans with an optional location label, an uploaded PNG/JPEG image, and camera placements referencing existing camera/source IDs.
- Reuse an existing site/building/floor model if present. Otherwise keep the initial location structure minimal; do not build a complex GIS or facility hierarchy merely to render a selector.
- Implement plan create/update/list, validated image upload, and persistent placement editing. Provide a clear view/edit mode and an unplaced-camera list.
- Store marker coordinates normalized to the image bounds, not screen pixels. Correctly handle letterboxing, resizing, zoom/pan, and any image replacement. A simple fit-to-view baseline is sufficient if zoom/pan would overcomplicate this milestone.
- Allow markers to be placed, moved, and removed without deleting the underlying camera. Do not silently lose placements when changing plans/images.
- Markers show camera health and indicate active incidents without inventing AI-confirmed positions. A camera marker indicates the camera's configured location, not the exact location of a detected person/fire.
- Clicking a marker selects that camera and updates relevant panels. A camera without a placement remains usable everywhere else.
- Protect image access with the existing auth model. Validate decoded image format, byte/pixel limits, and storage paths. Use generated storage names and the existing media/file patterns. Avoid arbitrary SVG/HTML uploads or remote image fetching in this milestone.

### B. Live monitoring panel

- Reuse the existing preview transport. Do not open an additional RTSP connection for each UI panel or expose camera credentials in the browser.
- Implement a selected-camera view and a bounded 2x2 grid using the existing preview capability. Limit concurrent subscriptions and make selection explicit.
- Display camera name, connection state, frame timestamp/freshness, and REAL/SIMULATED state derived from actual data.
- Stale or offline images must be visibly marked; never present the last frame as current video.
- Share preview subscriptions where possible. Stop polling on unmount, logout, and hidden views; resume safely. Cancel stale requests and release object URLs/listeners. Avoid accumulating requests on repeated navigation.
- Clearly distinguish live preview from the selected incident's historical snapshot.

### C. Event list

- Reuse existing incident persistence; do not create a second event table for the same incidents.
- Provide bounded/paginated fetching, status filters (new/acknowledged/all), and camera filtering. Add severity/type filters only when supported or coherently implemented.
- Show timestamp, type, camera, severity if available, and lifecycle status. Do not fabricate severity values for historical records.
- Clicking an event selects it, selects its camera, highlights a known placement, and updates details/context. If no placement/evidence exists, show that honestly.
- Incoming events update the queue/count without stealing the operator's current selection or resetting scroll unnecessarily.

### D. Event detail and actions

- Display incident identity, type, time, camera, existing rule/zone context where available, evidence, and history/notes.
- Wire Acknowledge, Resolve, and False Alarm to existing authorized backend actions. Preserve existing status-transition rules and audit identity/time.
- Acknowledge means a person has seen/taken responsibility for handling the event; it does not mean resolved.
- Pending/error feedback must be clear; prevent accidental duplicate submissions. Update all affected panels after a successful action and handle stale state/API rejection without pretending success.
- Use existing authenticated evidence routes. Handle missing/expired evidence separately from camera offline status.
- Do not add controls to trigger/reset physical alarm hardware.

### E. Context and optional device details

- Context includes configured location, optional responsible contact, and optional response notes. These are metadata, not AI-generated emergency instructions.
- Keep the location's responsible contact concept distinct from an incident assignee. Do not imply assignment functionality if not implemented.
- Optional device details: manufacturer/model, installed device image if supported, concise specifications, and existing health data. Missing values display as absent/unknown, never guessed from RTSP URLs.
- Prefer existing fields. Where absent, add minimal nullable metadata and a small authorized edit form, without requiring extra fields to register a camera.
- Provide links to existing camera settings, rules, incident history, and analysis pages. Those workflows must remain usable after the UI refactor.

## 6. Modular frontend contracts

Use feature modules with explicit public interfaces. Suggested logical ownership:

| Module | Owns |
| --- | --- |
| control-center | Layout, composition, selection coordination |
| maps | Plans, editor, markers, placements |
| monitoring | Preview lifecycle, single/grid views |
| incidents | Event list, detail, actions, history |
| devices | Device metadata, health, context integration |
| rules | Existing rule editor integration |
| notifications | Existing in-app notifications and future integration boundary |
| video-analysis | Existing recorded-video workflow |
| shared | API transport, small UI primitives, theme tokens, formatting |

- Keep feature-specific JS/CSS/tests inside their feature area. Scope styles; avoid broad selectors that alter other panels.
- The application bootstrap should compose features rather than contain their implementation. Extract only the existing code necessary for this work.
- Define a small coordinator/store for selectedPlanId, selectedCameraId, selectedIncidentId, and view mode. Define clear actions and immutable/read-only snapshots where practical. Keep server entities authoritative; selection state must not become a duplicate database.
- Modules must not reach into each other's DOM or import private internals. Communicate through documented callbacks/actions/subscriptions.
- Provide a lifecycle contract such as mount/update/dispose, adapted to the stack. Disposal must release requests, timers, listeners, and preview resources.
- Prevent stale async responses from overwriting a newer selection. On plan switches, filters, deleted cameras, and unavailable incidents, apply documented deterministic behavior rather than creating selection loops.
- Use one authenticated API transport that handles cancellation, errors, and session expiry. Do not introduce a separate login/token scheme.
- Provide explicit fixture/demo providers for isolated development. Fixtures must be opt-in, clearly labeled DEMO/SIMULATED, and never a silent fallback when a real API fails. Do not contaminate the user's real camera database.
- Avoid generic plugin frameworks or broad abstraction layers that do not solve a current dependency.

## 7. Backend structure and contracts

- Keep the existing FastAPI application and worker architecture. Reuse routers/services/models before introducing new ones.
- Add cohesive router/schema/service boundaries for plans/placements and needed metadata, following existing naming conventions. Do not duplicate camera ingest, incidents, evidence, rules, or AI inference.
- Preserve existing response contracts. Add endpoints/fields compatibly; document exact request/response examples from the implemented code, including errors and permission requirements.
- Reuse existing camera identifiers and authorization. Enforce access server-side. Plan/placement/device edits should use existing administrative permissions; event handling should follow existing operator permissions.
- Validate finite normalized coordinates within [0,1], references, names, file inputs, and optional metadata. Define uniqueness and deletion behavior explicitly; removing a plan/placement must not delete cameras or incident history.
- For any new data, add reviewed Alembic migration(s), portable between SQLite and PostgreSQL. Do not generate migrations that drop/recreate populated tables for convenience.
- Keep timestamps/timezone handling consistent with the current API. Store canonical times and format for display, not ambiguous local strings.
- Use existing polling/event delivery if adequate. Do not require WebSockets, Redis, or a message broker just for this milestone. Bound query sizes and avoid per-marker request storms.
- If implementing an aggregated read endpoint helps, make it a composition of existing services and document freshness; do not make it a second event authority.

## 8. Team handoff and conflict reduction

Create docs/FEATURE_MODULES.md and docs/CONTROL_CENTER_CONTRACTS.md describing actual implemented paths, public module interfaces, dependencies, API schemas, and extension examples.

Create docs/FEATURE_OWNERSHIP.md with work packages and file boundaries rather than invented teammate names:

1. Integration owner: shell, routing, shared state/API/theme, migration coordination.
2. Map contributor: plans, marker editor, placements API/tests.
3. Monitoring/device contributor: previews, camera context/health and metadata.
4. Incident contributor: queue, details/actions, notification integration.
5. Subsequent contributors: rules and recorded-video workflows through documented integration points.

These are ownership packages, not a reassignment of the user's existing five-person AI/camera/PM team. Show which packages can be worked on independently and which require the integration owner's review.

Give each package: owned files, public interface, prerequisites, acceptance checks, and shared files to avoid editing. Centralize shared contract changes and dependency-lock changes through the integration owner. Explain migration coordination to avoid duplicate Alembic heads. Do not create branches or CODEOWNERS entries with guessed identities.

Update AGENTS.md carefully if needed with feature boundaries and development rules; preserve existing instructions. Do not turn the completed task into a permanently applicable instruction to rebuild the product.

## 9. Implementation sequence

1. Baseline assessment and relevant existing checks.
2. Agree with the repository through code: define small module/state/API interfaces and record them in docs.
3. Build shell/theme/layout and feature modules; preserve existing routes.
4. Implement minimal persistent plans/placements/metadata and migrations.
5. Connect actual camera, incident, evidence, and action APIs.
6. Complete cross-panel selection, async cleanup, and explicit fixture mode.
7. Run focused backend/frontend tests and browser QA; fix regressions caused by this change.
8. Finish ownership/contract/runbook/status documents and a concise delivery report.

## 10. Verification and acceptance gates

Write meaningful tests for normalized placement validation and persistence, permissions, missing references, migration behavior, shared selection/stale responses, action failures, and subscription cleanup. Reuse existing test tools; do not add a large test framework merely to mirror implementation details.

Browser QA using available Playwright tooling must cover:

- Desktop 1440x900 (and larger if available), tablet 768px, and mobile 375px; no page overflow or obscured actions.
- Login, Control Center entry, navigation to existing pages, and logout.
- Empty site, missing plan, missing optional metadata, absent evidence, and unavailable camera.
- Upload plan, place/move a camera, reload, and verify persistence and coordinate alignment.
- Select marker -> correct camera/context. Select event -> correct camera/plan/details/evidence.
- New event does not steal selection; quickly changing selections does not render stale details.
- Single/grid switching, expand/restore, repeated page navigation, and resource cleanup with bounded network activity.
- Acknowledge/resolve/false alarm success and API rejection; server-side authorization tests for mutation permissions.
- Real API errors remain errors; demo mode remains visibly separate.

Test fixture-based browser scenarios against an isolated environment. If the existing local camera is reachable and authorized credentials are already configured, perform a non-disruptive real preview smoke test, but do not require hardware availability to complete the UI foundation. Do not mutate the real incident history merely to demonstrate QA.

Run applicable existing tests, syntax/type checks, migrations on a fresh temporary database and an upgrade path, and git diff --check. Test PostgreSQL/Compose only if available; report untested environments accurately. Preserve pre-existing failure records and distinguish new regressions from known failures.

Definition of done:

- A polished six-panel operational UI exists, with responsive/collapsible behavior.
- Plans and camera placements persist and are usable after reload.
- Existing camera previews and incident APIs drive the live UI.
- Selection synchronization and incident actions work end to end with real backend responses (fixture data may be used in an isolated test database).
- Modules have clean lifecycle/ownership boundaries; the new implementation is not another monolithic app.js.
- Existing login, camera management, rules, AI Hub, and video analysis workflows remain accessible.
- Relevant checks pass or specific blockers are documented with evidence; simulated tests are never described as hardware/AI validation.
- A teammate can implement or modify one feature using the documented contracts without changing the shell or another feature's private files for routine work.

## 11. Scope exclusions

Do not add model training, new detection scenarios, ONVIF discovery, RTSP transport rewrites, physical alarm actuation, external notification services, full GIS, an NVR/video archive, a drag-and-dock framework, or a complete frontend framework migration. Do not fix unrelated historical issues unless they block this milestone; record them separately.

## 12. Deliverables and final report

Deliver implemented code, required migrations, focused tests, module/contract/ownership docs, a brief usage guide, and updated implementation status. Use docs/CONTROL_CENTER_IMPLEMENTATION.md or a consistent existing status document to record implemented vs deferred behavior.

In the final response, report:

1. Concrete working behavior and how to open/use the Control Center.
2. Main feature directories and who can work on them independently.
3. New endpoints/migrations and any required local setup commands.
4. Tests and browser QA actually run, with outcomes.
5. Known limitations, existing issues, and unverified hardware/runtime conditions.
6. Suggested commit message: feat(visor): add modular control center foundation

Do not claim all MVP features are finished. Do not commit or push.
