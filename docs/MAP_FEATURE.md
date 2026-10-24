# Map feature

## Gap assessment

| Requirement | Existing implementation | Gap | Change | Owned paths |
| --- | --- | --- | --- | --- |
| Manage named plans and labels | Authenticated `/api/plans` CRUD and PNG/JPEG upload | UI had create/rename/location fields but no plan delete; metadata fields auto-saved | Add deliberate delete confirmation and keep metadata save explicit | `frontend/features/control-center.js`, `backend/app/main.py` |
| View and select cameras | Static fitted image, normalized markers | No pan/zoom/list, health state only color, stale health could survive failed refresh | Add bounded zoom, pointer anchored zoom, pan/fit, searchable camera list, text health labels and incident counts | `frontend/features/maps.js`, coordinator, scoped CSS |
| Edit placements safely | Normalized coordinates saved immediately; unique camera placement globally | No draft/cancel, atomic batch or stale-edit detection; another-plan save moved camera silently | Draft placement changes with Save/Cancel, revision CAS, return 409 for stale revision or camera on another plan | `backend/app/db.py`, migration `0005`, `backend/app/main.py`, coordinator |
| Replace image | Upload replaced the asset and kept normalized placements | No explicit policy/warning; data revision was not checked | Require explicit keep/clear policy, review warning, stage new file before DB commit, delete old file after success | `/api/plans/{id}/image`, coordinator |
| Coordinate correctness | Normalized image coordinates; geometry helper mapped fitted image clicks | No shared transform for viewport/pan/zoom, no helper tests | Add pure fit/image-screen/inverse/zoom helpers and Node tests; coordinate origin is top-left, x right, y down | `frontend/features/maps.js`, `frontend/features/maps.test.js` |
| Cross-panel selection | Coordinator selected camera from event rows | Selection could jump to a plan despite draft edits | Preserve draft/plan on external selection; reveal unique matching plan only when clean; keep existing selection for ambiguous matches | Coordinator only |
| Empty/error/accessibility states | Plan empty view and API retry | No read-only guidance, unplaced list, explicit unavailable health or marker text | Add search/list, view-only note, labelled controls, text equivalents and honest refresh errors | Coordinator and scoped CSS |

## Implemented behavior and instructions

- Administrators can create a plan, edit its name/location label, upload a PNG/JPEG, edit camera placements, save/cancel, replace the image, and delete the plan. Operators can view plans and select cameras but cannot mutate them; backend mutations remain `ADMIN`-only.
- Create or select a plan in Control Center. To place a camera, choose **Edit placements**, select an unplaced camera from the camera list, then click inside the image. Drag a placed marker to reposition it. **Save placements** commits the full set; **Cancel** restores the latest server version. Markers can also be unplaced by saving a set without them.
- Use `+`, `−`, and **Fit** for keyboard/touch friendly navigation. Drag empty map space to pan; wheel zoom is handled only when the pointer is over the plan. Image margins reject placement clicks.
- Replace image asks whether to keep normalized positions for review against the replacement geometry or clear them. Even identical dimensions/aspect ratio do not imply the same geometry. The previous image and placements remain if validation or persistence fails.
- Delete confirmation states the count of placements removed. Deleting a plan does not delete cameras, incidents, rules, or evidence. The next surviving plan is selected by the coordinator; otherwise the empty state is shown.
- Camera marker location is the configured camera location on the plan. It does not locate a detected person, vehicle, or fire.

## Contracts and persistence

- Existing endpoints remain: `GET/POST /api/plans`, `PATCH/DELETE /api/plans/{id}`, `GET/POST /api/plans/{id}/image`, and `PUT /api/plans/{id}/placements`. Image reads are authenticated and private/no-store. Mutations require administrator authorization and existing CSRF protections.
- Plan responses now include an integer `revision`. Placement replacement requires `{"revision": n, "placements": [...]}`. A compare-and-swap update increments the revision in the same DB transaction as the full placement-set update. Stale versions return HTTP 409 with reload/reapply guidance. Image replacement requires `revision` and `placement_policy=keep|clear`; it also increments revision. Upload bytes are validated and staged to a generated private file before DB commit; on DB failure the staged file is removed, and the previous image is deleted only after success.
- Placement coordinates are finite normalized values in `[0,1]` over decoded image dimensions, with origin at top-left, x increasing right, and y increasing down. Migration `0005_map_revision` adds revision (default `1`) to floor plans. Existing placement cardinality from migration `0004_control_center` is one placement per camera across all plans. An attempt to add a camera already located on another plan returns HTTP 409; there is no implicit relocation.
- Plan deletion removes its image and placements, while preserving cameras and incident history. Image `keep` preserves normalized values but asks the operator to review them; `clear` removes placements in the same plan transaction as image metadata replacement.
- API addition: response revision metadata, required placement request revision, image replacement query arguments and 409 stale/cross-plan conflicts. Other shared camera/incident contracts did not change.

## Geometry and lifecycle

`VisorMaps.fittedRect` computes the contain-fit image bounds inside the stage. `imageToScreen`, `screenToImage`, and `zoomAt` share that fit and the view `{zoom, panX, panY}`. The image plus markers use the same CSS translate-then-scale transform with top-left origin. Inverse pointer mapping subtracts viewport offset and pan and divides by zoom and fitted image dimensions; margins return `null`. Dragging clamps to normalized image edges; numeric normalized X/Y fields provide a keyboard alternative. JPEG EXIF orientation is normalized at upload so decoded dimensions match the displayed image. Map resize observers disconnect on each redraw and on coordinator disposal. Existing request generation/abort behavior prevents stale collection responses from replacing newer state.

The coordinator integration remains the public `ControlCenter.mount({api, me, host, onNavigate})` lifecycle and `snapshot()` state. It uses the current selected camera/incident/plan coordinator fields; no second global selection store or cross-panel DOM access was added. Incoming incident refreshes update badges without changing selected camera or map view. Selecting an incident reveals a unique matching plan or retains the current matching plan; if a draft is dirty, it does not change plans.

## Files and boundaries

- Map implementation: `frontend/features/maps.js`, `frontend/features/control-center.js` map panel/bindings, `frontend/features/control-center.css`, `frontend/features/maps.test.js`.
- Backend and test: `backend/app/db.py`, `backend/app/main.py`, `backend/migrations/versions/0005_map_revision.py`, `backend/tests/test_vertical_slice.py`.
- Integration/documentation: `frontend/app.js` checks the coordinator's public `confirmLeave()` before shell navigation/logout; `frontend/index.html` versions the changed assets; this document and a short status-ledger entry.
- No camera reader, monitoring renderer, incidents renderer/actions, rules, notification, AI Hub, video analysis, shared API transport, or shell routes were changed. Migration `0005` follows the committed head `0004_control_center`; contributors adding migrations must coordinate the single linear Alembic head.

## Verification and limits

Verification performed on 2026-10-24:

- Focused geometry unit checks: **5 passed** (`node --test frontend/features/maps.test.js`).
- Focused backend Control Center/Map API test: **1 passed**, covering upload, keep/clear, EXIF orientation normalization, stale image rollback, revision conflict, cross-plan camera conflict, finite/bounded coordinates, authorization, and plan deletion preserving a camera and incident.
- Full backend regression suite on an isolated SQLite DB: **29 passed**, one pre-existing Starlette/AnyIO deprecation warning. One sandboxed attempt could not clean pytest temp files due Windows `PermissionError`; the authorized outside-sandbox rerun passed.
- JavaScript syntax checks (`maps.js`, coordinator, and shell), Python compileall, and `git diff --check`: passed.
- Alembic fresh SQLite migration and upgrade from revision `0004_control_center` to head `0005_map_revision`: passed. PostgreSQL/Compose was unavailable/not run.
- Playwright on an isolated local SQLite/API setup: created a plan and synthetic test camera, uploaded a generated PNG through the preview dialog, placed/saved a camera, reloaded and confirmed persistence, and resized to 1440?900, 768?1024, and 375?812 without horizontal page overflow. Verified authenticated image loading, keep/clear replacement behavior, coordinate edit/cancel, zoom/fit, camera selection across plans, dirty-draft preservation, plan-switch confirmation, and shell-navigation confirmation. Map image API returned authenticated PNG. The worker was not started, so its preview correctly reported offline/unavailable. Cross-tab revision conflict recovery, live worker behavior, and real-camera/model/PostgreSQL behavior were not browser-verified; backend tests cover stale revision behavior.

Exact focused commands from the repository root:

```powershell
node --test frontend/features/maps.test.js
node --check frontend/features/maps.js
node --check frontend/features/control-center.js
$env:PYTHONPATH='backend'; $env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest -q --tb=short backend/tests/test_vertical_slice.py::test_control_center_floor_plan_placements_image_and_context_permissions
```

Apply the migration with `python -m app.commands migrate` before starting the API/worker after updating. PostgreSQL/Compose behavior, physical camera behavior, and real model inference remain unverified for this Map feature.

## Integration notes

Public actions are existing Control Center interactions: `data-select-camera` selects a camera, `data-event` selects an incident, and `data-plan` selects a plan. The read-only public snapshot exposes the coordinated `cameraId`, `incidentId`, and `planId`; map geometry helpers are pure globals under `VisorMaps`. Other feature branches should continue to select through the coordinator or consume its snapshot, not query map markup. Placement persistence is replace-all for the selected plan, with one-camera/one-plan cardinality and required revision. Coordinate owner is the map feature; plan-location and device-context metadata remain separate. Feature branches that add a schema revision should coordinate migration order with the integration owner.
