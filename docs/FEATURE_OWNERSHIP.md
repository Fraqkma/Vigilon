# Feature ownership packages

These packages define file boundaries for contributors; they do not change the existing AI/camera/PM team assignments. Shared contracts, migration revisions and lockfiles require integration-owner review. Each schema change must be coordinated into the current Alembic head before another migration is started.

## Integration owner

- **Owns:** `frontend/app.js`, `frontend/index.html`, shared `frontend/style.css` tokens, `backend/migrations/versions/`, cross-feature API contract docs.
- **Interface:** authenticated `api(path, options)`, session role, shell route navigation, and migration head.
- **Prerequisites:** agree API shape and page lifecycle with affected feature owners.
- **Acceptance:** old routes continue to work; logout/navigation dispose feature resources; one linear migration head; docs match OpenAPI/code.
- **Avoid editing:** feature implementation internals except to integrate a versioned public interface.

## Map contributor (can work independently after API contract review)

- **Owns:** normalized geometry helpers in `frontend/features/maps.js`; floor-plan panel composition and event binding in the coordinator; `/api/plans` and placement contracts/tests in backend.
- **Interface:** plan CRUD, authenticated image route, replace-all normalized placement contract.
- **Prerequisites:** shared DB model/migration review from integration owner; existing camera IDs.
- **Acceptance:** bounded decoded PNG/JPEG; normalized coordinates survive resize/reload; geometry helpers are pure; invalid references/coordinates denied; removing a marker/plan never deletes camera/history.
- **Avoid editing:** shell, global API transport, incident action implementation, unrelated migrations.

## Monitoring and device contributor (can work independently after shared contract review)

- **Owns:** pure preview renderer in `frontend/features/monitoring.js`; device/context renderers and form in `frontend/features/devices.js`; optional camera context endpoint and tests. Shared selection and polling remain in the coordinator.
- **Interface:** authenticated worker preview plus `/api/cameras/{id}/context`; camera state comes from existing API.
- **Prerequisites:** shared API fields reviewed; no source credential access in browser.
- **Acceptance:** capped 2×2 previews, visible stale/offline state and REAL/SIMULATED source distinction, disposal on navigation, optional values shown as unknown.
- **Avoid editing:** adapter/worker source lifecycle, camera credentials, shared routes/styles outside feature scope.

## Incident contributor (can work independently using existing APIs)

- **Owns:** pure incident row/detail renderers in `frontend/features/incidents.js` and incident-focused tests. Queue polling, selected-incident coordination and action requests remain in the coordinator.
- **Interface:** bounded existing incident list, authenticated evidence, existing action endpoint and history.
- **Prerequisites:** no duplicate incident persistence; transitions remain server-authoritative.
- **Acceptance:** selection updates camera context; polling does not steal selection; action rejection remains visible; no duplicate pending action; missing evidence differs from offline camera.
- **Avoid editing:** incident schema/transitions unless coordinated; physical alarm controls; source ingestion.

## Subsequent rules and recorded-video contributors

- **Owns:** existing rule editor in `frontend/app.js`/camera detail and recorded-video workflow in `frontend/analysis.js` plus its existing feature UI.
- **Interface:** existing camera rule and authenticated FILE job APIs; shell navigation callback for cross-links.
- **Prerequisites:** module lifecycle/navigation contract; integration review for shared routes or persistence.
- **Acceptance:** all existing rule, AI Hub and video analysis workflows remain accessible; no change to simulation boundaries or model readiness claims.
- **Avoid editing:** Control Center private DOM, camera/incident persistence duplicates, dependency locks without integration review.

Pure map, monitoring, device and incident rendering now has separate feature files and documented function contracts. The coordinator retains cross-panel API actions and map markup/bindings; contributors can change their renderer modules independently, while coordinator state or shared API changes require integration-owner review. Cross-feature work should avoid editing the coordinator concurrently.
