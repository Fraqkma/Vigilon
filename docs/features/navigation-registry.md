# Feature registry and cross-page navigation

Branch: `feature/registry-navigation` (base for camera health, alerts, event logs and device image).

## Why

Each feature should arrive as its own pull request that touches only its own files. Before this branch,
adding a page meant editing the shell nav list, the page switch in `render()`, the topbar and
`backend/app/main.py`, so every feature PR collided with every other one. The registry moves those
shared edits here once.

## Frontend: pages and session services

Feature scripts load before `app.js` and register themselves:

```js
// A page in the sidebar. `after` places it next to an existing nav id ('incidents', 'live', ...).
(window.VisorPages = window.VisorPages || []).push({
  id: 'health', label: 'Camera Health', icon: '♥', after: 'incidents',
  mount({ api, me, host, onNavigate, formatTime }) { /* render into host */ return { dispose() {} }; },
});

// A service that lives for the whole signed-in session (for example an alert bell).
(window.VisorServices = window.VisorServices || []).push({
  id: 'alerts',
  start({ api, me, onNavigate }) {
    return {
      attach(slot) { /* append your own element into #topbarSlot; never replace slot.innerHTML */ },
      stop() { /* clear timers */ },
    };
  },
});
```

Shell guarantees:

- `render()` disposes the previous page instance before mounting the next one.
- Services start after sign-in and stop on logout or session expiry. `attach(slot)` runs after every
  shell render because the topbar is re-created.
- `#topbarSlot` is shared. Each service appends and owns one child element.
- A page id that already exists in the built-in nav is ignored, so a feature cannot replace a shell page.

### Loading feature scripts

A feature branch does not edit `index.html`. `GET /` adds a deferred `<script>` for every
`frontend/features/*.js` that `index.html` does not already list (alphabetical, `*.test.js` skipped),
just before `app.js`, so features register before the shell starts. A feature injects its own
stylesheet from its script (for example `features/health.css`).

## Cross-page navigation

`onNavigate(target, options)` is passed to Control Center and to every feature page:

| Call | Result |
| --- | --- |
| `onNavigate('live', { cameraId })` | Opens Live Monitoring with that camera's settings, rules and zones dialog |
| `onNavigate('control', { focus: { incidentId } })` | Opens Control Center and selects that incident, even outside the current list filter |

Control Center unsaved-map protection (`confirmLeave()`) still runs first.

The Location context panel link is now **Settings, rules & zones** and opens the selected camera's
existing settings dialog (per-camera rules and zones live there).

## Backend: feature routers

Every module in `backend/app/features/` that defines `build_router(deps)` is mounted automatically at
startup in alphabetical order. `deps` is a `FeatureDeps` with `current_user`, `require_admin`,
`utc_iso`, `incident_dict` and `camera_dict`, so features reuse the shell's auth and public shapes
instead of importing `main.py` (which would be circular).

```python
# backend/app/features/example_api.py
from fastapi import APIRouter, Depends

def build_router(deps) -> APIRouter:
    router = APIRouter(tags=["example"])

    @router.get("/api/example")
    def example(user=Depends(deps.current_user)):
        return {"ok": True}

    return router
```

This branch ships one router: `incidents_api.py` with `GET /api/incidents/{id}` (same JSON shape as an
item from `GET /api/incidents`, operator or admin, 404 when missing).

## Caching

Responses under `/assets/` now carry `Cache-Control: no-cache`. Browsers still keep the file but
revalidate it (a cheap 304 with ETag), so merged feature branches never run stale JS or CSS and feature
PRs do not need to bump the `?v=` numbers in `index.html`.

## Tests

`backend/tests/test_feature_registry.py`: incident detail 200/401/404 and same shape as the list,
deterministic router discovery, no duplicate route, feature script injection (once, before `app.js`,
no test files) and the asset revalidation header.
