# Visor feature modules

## Current composition

The existing shell remains in `frontend/app.js`; it owns authentication, primary navigation and the shared authenticated `api(path, options)` transport. The Control Center coordinator is `frontend/features/control-center.js`, with styles scoped by the `.cc-` prefix in `frontend/features/control-center.css`. It is mounted through `window.ControlCenter.mount({api, me, host, onNavigate})` and returns `{snapshot(), dispose(), confirmLeave()}`. `snapshot()` is a read-only snapshot of the current plan, camera, incident, mode and loaded collections. `confirmLeave()` lets the shell guard navigation/logout when placement drafts are dirty. `dispose()` clears its poll timer, invalidates requests, releases observers and revokes preview object URLs. Shell navigation and logout dispose it after the guard succeeds.

The coordinator composes six visible panels: floor plans/placements, monitoring, location context, device details, incident queue, and incident details/actions. Panel renderers and map geometry helpers are separate pure modules with explicit inputs/outputs; the coordinator owns cross-panel selection and API actions. Existing Live Monitoring, Incidents, Video Analysis, AI Modules, Settings and Overview remain independent shell destinations.

## Panel module interfaces

- `frontend/features/maps.js`: `VisorMaps.fittedRect`, `imageToScreen`, `screenToImage`, and `zoomAt` share the fitted-image/view transform; inverse mapping rejects letterbox margins. The coordinate origin is top-left, x right, y down. `placeCamera(placements,cameraId,point)` and `removeCamera(placements,cameraId)` return new placement arrays.
- `frontend/features/monitoring.js`: `VisorMonitoring.renderPreview(camera,selectedCameraId,escapeHTML,formatTime)` returns one escaped preview card using only the existing preview endpoint.
- `frontend/features/incidents.js`: `VisorIncidents.renderEvent(incident,camera,isSelected,escapeHTML,formatTime)` and `renderDetail(incident,camera,isPending,escapeHTML,formatTime)` return queue/detail markup. The coordinator binds selection and authorized actions.
- `frontend/features/devices.js`: `VisorDevices.renderLocation(camera,plan,isAdmin,contextOpen,expanded,escapeHTML,contextForm)` and `renderDevice(camera,expanded,escapeHTML,formatTime)` return panel markup; `renderContextForm(camera,escapeHTML)` renders the optional metadata form.

Each renderer receives public data and formatting callbacks. These files do not query or mutate another panel's DOM. Script load order in `frontend/index.html` is maps, monitoring, devices, incidents, then coordinator. Changes to shared selection/API shape still belong to the integration owner.

## Dependencies and lifecycle

- Control Center depends on the shell authenticated API transport and current session role. The transport honors `AbortSignal`, returns API errors to the caller, and redirects an expired authenticated session to login.
- Incident action feedback is kept in coordinator state so a full refresh cannot erase a rejection message.
- Floor plan reads and mutations use `/api/plans`; camera context edits use `/api/cameras/{id}/context`.
- Monitoring uses the existing authenticated worker preview route. It never creates upstream camera sessions.
- Event queue, evidence and actions use `/api/incidents`, `/api/incidents/{id}/evidence`, and `/api/incidents/{id}/action`.
- Polling runs every seven seconds while visible. Navigation/logout calls `dispose`; stale refresh responses are ignored by a generation counter, and plan-image ResizeObservers are disconnected on redraw/dispose. At most four grid previews render.
- The location/device column can be hidden and restored; per-panel expand/restore remains available.
- No fixture provider is enabled in production UI. Tests seed isolated database fixtures; API failures render an error and explicit Retry action, never synthetic fallback content.

## Extension example

```js
const mounted = window.ControlCenter.mount({ api, me, host, onNavigate: page => navigate(page) });
// Optional read-only current coordination state:
const current = mounted.snapshot(); // selected plan/camera/incident and view mode
// Required when replacing the page or logging out:
mounted.dispose();
```

Keep server entities authoritative. Add a UI state field only when it coordinates a current cross-panel selection or view choice. New shell/shared API changes go through the integration owner; feature-only behavior should remain within the feature directory and scoped CSS.
