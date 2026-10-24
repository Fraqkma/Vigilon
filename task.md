# Vigilon / Visor — Complete the Map Feature on Its Own Branch

## Objective

Finish the custom floor-plan Map feature on top of the committed modular Control Center foundation. Deliver a usable, persistent map viewer/editor integrated with existing camera and incident selection. This is implementation work: inspect the current code, identify gaps, implement them, test, and document the result. Do not rebuild features that already work.

The user is separating product features into individual branches. This task owns Map only. Preserve clear boundaries so monitoring, incident handling, rules, notifications, and video analysis can evolve independently.

## 1. Environment, instructions, and branch

- Read applicable AGENTS.md files, README, CONTROL_CENTER_ASSESSMENT.md, CONTROL_CENTER_CONTRACTS.md, FEATURE_MODULES.md, FEATURE_OWNERSHIP.md, and relevant implementation status/source. Missing documents should be reported, not invented.
- Respect existing Codex settings, ECC workflows, and configured MCP tools. Discover actual availability. Use relevant installed skills, including archify when appropriate, Context7 for documentation when needed, and Playwright for browser verification. Do not reconfigure or reinstall global settings/tools, or claim unavailable tools were used.
- Inspect repository root, current branch, git status, recent commits, and worktrees before changing anything. The user reports the Control Center foundation is committed; verify the current checkout contains it.
- Use branch `feat/map`. If already on that branch, continue. If it does not exist and the current HEAD contains the intended committed foundation, create it from that HEAD. Record the actual base commit. Do not assume the base branch is named main or that a remote branch is newer.
- If `feat/map` already exists elsewhere or switching would mix another feature's changes, use an isolated worktree based on the verified foundation with a descriptive unused map branch name. Do not reset, discard, stash, or move another contributor's changes automatically. A pre-existing task.md edit is user input, not permission to rewrite it.
- Do not fetch/merge/rebase other feature branches, commit, push, open a PR, or delete branches in this task. Report the resulting branch and worktree path.
- Keep secrets, local databases, uploaded plans, evidence, and model weights out of Git. Do not alter camera/network configuration or production data for tests.

## 2. Existing baseline to verify

The latest user report says:

- Control Center is the default page and uses modules under frontend/features.
- Plan creation/editing/image upload and normalized camera placement already exist.
- Camera/event selection synchronizes panels; context and device metadata exist.
- Migration `0004_control_center` adds relevant persistence.
- Backend suite passed 29 tests; SQLite fresh and upgrade migrations passed.
- Browser checks covered plan upload/placement, selection, context, incident actions, polling cleanup, and mobile logout.
- PostgreSQL/Compose, real camera/model integration, and camera codec behavior were not validated during that change.

These are reported results, not tests run by you. Do not recreate tables or rewrite migration 0004. Inspect actual implementations and preserve working behavior.

## 3. Map scope and gap assessment

Write `docs/MAP_FEATURE.md` with a concise assessment table: requirement, existing implementation, gap, intended change, actual owned paths. Then continue coding without waiting for approval on routine reversible decisions.

Map means uploaded custom floor plans/site diagrams, not a geographic map service. Support multiple independent plans with simple names/location labels. Reuse any existing hierarchy, but do not add a large building/floor/site administration system just for this feature.

Deliver the following behaviors end to end, reusing existing ones where complete.

### A. Plan management

- List/select plans; create and rename plans; edit existing supported location labels.
- Upload PNG/JPEG with a clear preview and validation feedback. Fit the image without distortion.
- Replace the background image safely using the workflow below.
- Delete a plan with a normal confirmation that explains which placements are removed. Never delete its cameras, incidents, rules, or evidence. Handle selection of a deleted plan deterministically.
- Clear empty states: no plans, plan without image, no cameras, no placements, and no permission to edit. Do not automatically create demo records in a real database.
- Persist data on the backend and verify reload behavior. Remembering the selected plan locally is optional; validate it still exists and scope any preference to the authenticated user. Clear incompatible state on logout.

### B. View mode

- Display the plan with pan, bounded zoom in/out, and Fit/Reset controls. Wheel zoom should anchor at the pointer where practical and must not hijack scrolling outside the map. Provide buttons for touch/keyboard users.
- Resizing, panel expansion, and device rotation must preserve correct marker alignment. Rendering and hit testing must use the same image-to-screen transform.
- Show readable camera markers with short labels/tooltips, selected state, actual health, and a badge/count for relevant active incidents when available through the existing incident contract.
- Keep health, selection, and incident severity distinguishable. Include a compact legend and text equivalents; avoid color-only meaning or continuous flashing.
- Clicking a marker selects that existing camera through the shared coordinator. Keep monitoring/context integration working without private DOM access.
- Provide an accessible camera list/search alongside or inside the map panel, including unplaced cameras, so small or overlapping markers are still usable.
- Show loading, request error, unavailable image, stale/unknown health, and retry states honestly. Cached last-known health must not silently remain ONLINE after refresh failure.

### C. Edit mode and placements

- Clearly separate view and edit mode. Gate mutations by existing backend authorization; hiding buttons alone is insufficient.
- Allow selecting an existing camera from an unplaced list and clicking the image to place it. Support repositioning by dragging and a non-drag alternative such as selecting a marker and choosing a new point or editing normalized coordinates.
- Allow removing a placement without deleting the camera. Include explicit Save and Cancel controls for draft edits, saving/error states, and an unsaved-changes guard when switching plans, leaving the editor/page, or replacing the image.
- Cancel must restore the last persisted state. Failed saves must retain recoverable edits and show the actual failure rather than falsely displaying success.
- Document camera-placement cardinality from the existing schema. Preserve it unless a necessary change is justified. A suitable default when unspecified is one placement per camera per plan; never silently relocate a camera on another plan or introduce duplicate markers contrary to the existing contract.
- Prefer an atomic save for a set of placement changes. Reuse existing transaction/bulk behavior if present; if missing, add a minimal compatible map-specific operation. Do not allow partially saved edits to appear as a successful complete save.
- Prevent lost updates between tabs/operators: reuse revision/ETag support if available, otherwise add a small map revision/optimistic concurrency check. Reject a stale save with a clear conflict response and reload/reapply workflow; do not overwrite another operator's placements silently.

### D. Coordinate correctness

- Store finite normalized coordinates within [0,1] relative to the decoded image, independent of viewport pixels. Preserve the existing coordinate convention and document the origin/axes.
- Use one tested transform/inverse-transform implementation for placement, dragging, zoom, pan, and hit testing. Account for the image's actual bounds, letterboxing, scroll/container offset, and the chosen transform order. Handle pixel ratio if using canvas.
- Clicks in margins outside the image must not create a placement. Dragging beyond bounds must clamp consistently or reject with clear feedback.
- Pointer cancellation/lost capture must not leave dragging active. Disallow accidental placement during pan gestures.
- Image replacement must never imply automatically calibrated placement. Offer explicit choices: keep normalized placements and review against the new image, or clear placements. Warn that even an identical aspect ratio does not imply identical floor-plan geometry.
- Make replacement image plus the chosen placement policy consistent as one logical operation. If upload/validation/save fails, retain the previous usable image and placements. Do not delete the old asset before the new state commits.

### E. Camera/event integration

- Use existing selectedCameraId/selectedIncidentId/selectedPlanId interfaces or their actual equivalents. Do not add a competing global store.
- When an event/camera is selected outside the map, highlight its placement if present. If the current plan contains it, keep that plan. If only one other plan contains it, reveal that plan when no unsaved edit blocks switching. If several plans contain it, prefer the current matching plan or offer a deterministic chooser; do not jump arbitrarily.
- If no placement exists, show an explicit unplaced/not-on-this-plan state while preserving event/camera selection and keeping the rest of Control Center usable.
- Never discard unsaved edits due to external selection. Keep the current editing plan and offer a deliberate navigation action if needed.
- Incoming incidents may update markers/counts but must not steal selection, pan/zoom, or reset edits. Reuse existing lifecycle semantics for active incidents rather than inventing new status rules.
- A marker represents the configured camera location. Do not claim it locates a detected person, vehicle, or fire within the plan. Do not project camera-space AI zones/boxes onto floor-plan coordinates without calibration.
- Handle deleted/unavailable cameras and stale references gracefully. Retain backend referential integrity according to the documented deletion policy.

## 4. Module and branch boundaries

Primary ownership: existing map feature directory, map-specific CSS, map API/schema/service code, focused tests, map migrations if required, and docs/MAP_FEATURE.md. Use actual existing names; do not create a parallel maps subsystem.

- Preserve current framework and styling system. Do not migrate to React or introduce a GIS/canvas framework unnecessarily.
- Keep existing Control Center visual language. Make the map toolbar/editor compact; prioritize map space over permanently open forms. Support desktop, expanded panel, tablet, and mobile without page overflow.
- Use existing shared API/auth/error utilities and mount/update/dispose lifecycle. Cancel obsolete requests, release image object URLs, remove document/pointer/resize listeners, and avoid duplicate subscriptions after remount.
- A delayed response from a previous plan must never replace the currently selected plan or its draft. A health refresh must not overwrite locally edited placements.
- Do not refactor monitoring, incidents, devices, AI Hub, camera readers, rules, video analysis, or the application shell. Minimal additive shared changes are allowed only when essential for map integration; list their reason and contract impact in the handoff.
- Avoid broad formatting, mass renames, new dependencies, root AGENTS.md rewrites, and lockfile changes unrelated to Map.
- Keep map documentation mainly in docs/MAP_FEATURE.md to reduce conflicts. Update shared contract/status docs only with small necessary entries or links. Do not edit another feature's ownership assignment.

## 5. Backend and storage requirements

- Reuse existing plan/placement endpoints and models; extend compatibly only where the acceptance criteria need it. Do not invent endpoint paths before inspecting the current contracts.
- Enforce auth and edit roles on every mutation and protected image route. Return no RTSP credentials. Validate referenced cameras and plans server-side.
- Validate names, metadata, finite normalized coordinates, duplicates, and revision values. Define meaningful HTTP errors for invalid input, missing references, conflicts, forbidden access, and unsupported/oversized images using existing conventions.
- Enforce upload byte and decoded pixel limits. Validate actual decoded PNG/JPEG content; do not rely on extension/MIME alone. Use safe generated storage names, prevent path traversal, and reject SVG/HTML or arbitrary remote image fetching.
- Account for image orientation consistently: normalized marker coordinates must refer to the same orientation users see. Reuse existing image processing support; do not add dependencies without a demonstrated need.
- Use transactional placement updates and concurrency checks. Keep file replacement/deletion consistent with database state; clean up newly created files after failed writes and avoid removing a still-referenced image.
- Preserve SQLite/PostgreSQL portability. Add a new uniquely identified Alembic revision only if schema changes are needed, based on the actual current head. Do not edit already committed migrations or resolve unrelated parallel migration heads by guessing. Document merge-time migration coordination.
- Avoid N+1 requests for markers/health/incident counts. Reuse shared refresh data or bounded/batched requests. Do not fetch every historical incident just to count active ones.
- Use local storage paths already supported by configuration. Do not introduce a new external storage service.

## 6. Out of scope

No geocoding, Google Maps/OSM, GPS tracking, 3D plans, CAD/PDF import, multi-floor route planning, image calibration, AI model changes, camera discovery, RTSP changes, alarm hardware controls, historical heatmaps, new notification channels, or full rule editor work. Do not implement decorative fields of view unless real orientation/calibration data and a specific need already exist.

## 7. Tests and browser acceptance

Use isolated databases/media directories. Do not point automated destructive tests at the user's real camera records or uploaded plans. Preserve pre-existing known failures separately from new regressions.

Focused automated tests must verify meaningful behavior:

1. Normalized coordinates and transform/inverse-transform round trips with portrait/landscape images, letterboxing, pan, zoom, and resize.
2. Out-of-bounds/margin input, NaN/infinite values, duplicate placement, missing camera/plan references, and authorization.
3. Persistence, Cancel behavior, atomic multi-placement save, stale revision conflict, and error recovery.
4. Image upload validation, replacement keep/clear policies, rollback after failure, and plan deletion without deleting cameras/incidents.
5. External selection without a placement, selection across plans, stale async responses, and preservation of dirty edits.
6. Listener/subscription/request cleanup through repeated mount/dispose where test tooling supports it.

Run browser QA with the configured Playwright tooling or a documented equivalent:

- Create two plans and several test cameras in an isolated environment; use generated/local non-sensitive plan images.
- Upload, place, move, save, reload, and verify each marker remains correctly positioned.
- Pan/zoom/fit, expand/restore, and resize without coordinate drift; test placing near image edges and rejecting margin clicks.
- Use keyboard/non-drag controls and a touch-sized viewport; inspect 1440x900, 768px, and 375px layouts for overflow, legibility, and accessible controls.
- Cancel edits; switch plans with unsaved changes; simulate failed save and stale concurrent save in a second tab.
- Replace the image with a different aspect ratio using both keep and clear choices; verify the warning, saved result, and recovery from a failed replacement.
- Select marker -> existing camera/context selection; select event -> appropriate marker/plan without losing dirty edits.
- Remove placement and delete a plan; confirm cameras/incidents remain and UI selection stays valid.
- Verify read-only/edit role behavior and authenticated images.
- Repeatedly navigate away/back and log out. Check for console errors, duplicate requests, and retained resources. Restore test service/environment state after QA.

Real camera streaming and real model weights are not prerequisites for validating the Map feature. If available, do a non-disruptive optional smoke check with existing local credentials, but distinguish it clearly from fixture-based tests. Never mark camera/AI readiness as newly validated by a map test.

Run relevant existing backend/frontend checks and git diff --check. Test SQLite migration fresh/upgrade behavior if schema changes. Test PostgreSQL/Compose if available; otherwise state it remains unverified. Once focused checks pass, run the existing practical regression suite once to detect integration breakage, without repeatedly rerunning unchanged tests.

## 8. Completion and handoff

The feature is complete when a user can manage plans, place/reposition/remove cameras, save/cancel safely, navigate a responsive zoomable plan, and use synchronized camera/event selection without losing data or creating cross-module coupling.

Finish docs/MAP_FEATURE.md with:

- Implemented vs deferred scope and concrete user instructions.
- Actual owned files and minimal shared files touched.
- API additions/changes, revision/conflict semantics, placement cardinality, coordinate convention, and image replacement/deletion policy.
- New migration and upgrade instructions if applicable.
- Test/QA results, current limitations, and any pre-existing failures.
- Integration notes for other feature branches, including exact public events/actions used and migration coordination needs.

Final response should include branch/base/worktree, concise delivered behavior, test outcomes, limitations, local run/migration commands, and a suggested commit message:

`feat(map): complete floor plan editing and camera placement workflows`

Do not commit or push. Do not claim the entire Vigilon MVP is finished. Leave the changes ready for user review and commit.
