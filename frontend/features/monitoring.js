(() => {
  const DEFAULT_INTERVAL_MS = 1400;
  const DEFAULT_TIMEOUT_MS = 5000;
  const DEFAULT_STALE_AFTER_MS = 8000;
  const MAX_PREVIEW_BYTES = 20 * 1024 * 1024;
  const pagePreferences = new Map();

  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const cameraId = value => value === null || value === undefined || value === '' ? null : Number(value);
  const availableCameras = cameras => (cameras || []).filter(camera => camera && camera.source_type !== 'file');

  function initialGridAssignments(cameras, selectedId, size = 4) {
    const list = availableCameras(cameras);
    const selected = cameraId(selectedId);
    const ids = list.map(camera => camera.id);
    const result = Array(size).fill(null);
    if (selected && ids.includes(selected)) result[0] = selected;
    for (const id of ids) {
      if (result.filter(Boolean).length >= size) break;
      if (!result.includes(id)) result[result.findIndex(item => item === null)] = id;
    }
    return result;
  }

  function assignGridCamera(assignments, slot, id) {
    const grid = Array.from({ length: 4 }, (_, index) => cameraId(assignments?.[index]));
    const target = Math.max(0, Math.min(3, Number(slot) || 0));
    const selected = cameraId(id);
    const duplicate = selected === null ? -1 : grid.findIndex((value, index) => value === selected && index !== target);
    if (duplicate >= 0) return { ok: false, focusSlot: duplicate };
    grid[target] = selected;
    return { ok: true, assignments: grid };
  }

  function focusGridSelection(assignments, activeSlot, selectedId) {
    const grid = Array.from({ length: 4 }, (_, index) => cameraId(assignments?.[index]));
    const selected = cameraId(selectedId);
    const existing = grid.findIndex(id => id === selected);
    if (existing >= 0) return { assignments: grid, activeSlot: existing, replacedSlot: null };
    let target = Number.isInteger(activeSlot) && activeSlot >= 0 && activeSlot < 4 ? activeSlot : -1;
    if (target < 0) target = grid.findIndex(id => id === null);
    if (target < 0) target = 0;
    grid[target] = selected;
    return { assignments: grid, activeSlot: target, replacedSlot: target };
  }

  function createPreviewManager(options = {}) {
    const fetchImpl = options.fetchImpl || globalThis.fetch?.bind(globalThis);
    const documentRef = options.documentRef || globalThis.document;
    const urlApi = options.urlApi || globalThis.URL;
    const now = options.now || (() => globalThis.performance?.now?.() ?? Date.now());
    const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS;
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const staleAfterMs = options.staleAfterMs ?? DEFAULT_STALE_AFTER_MS;
    const initialBackoffMs = options.initialBackoffMs ?? 1000;
    const maxBackoffMs = options.maxBackoffMs ?? 8000;
    const cacheGraceMs = options.cacheGraceMs ?? 1200;
    const maxConcurrency = Math.max(1, Math.min(4, options.maxConcurrency ?? 4));
    let onUnauthorized = options.onUnauthorized || (() => {});
    const entries = new Map();
    let queue = [];
    let activeRequests = 0;
    let unauthorizedHandled = false;
    let disposed = false;

    function isDocumentVisible() { return !documentRef?.hidden; }
    function hasActiveConsumer(entry) { return [...entry.consumers.values()].some(consumer => consumer.active); }
    function canRun(entry) { return !disposed && isDocumentVisible() && entry.consumers.size > 0 && hasActiveConsumer(entry); }

    function snapshotEntry(entry) {
      const elapsed = entry.frameId && entry.receivedAt !== null ? Math.max(0, now() - entry.receivedAt) : 0;
      const age = entry.frameId ? Math.max(0, entry.frameAgeAtReceipt + elapsed) : null;
      const stale = age !== null && age > staleAfterMs;
      return Object.freeze({
        cameraId: entry.id,
        status: entry.status,
        freshness: entry.frameId ? (stale ? 'stale' : 'fresh') : 'unknown',
        stale,
        frameId: entry.frameId,
        capturedAt: entry.capturedAt,
        frameAgeMs: age,
        previewRefreshHz: entry.previewRefreshHz,
        width: entry.width,
        height: entry.height,
        simulated: entry.simulated,
        url: entry.objectUrl,
        error: entry.error,
        inFlight: entry.inFlight ? 1 : 0,
        consumers: entry.consumers.size
      });
    }

    function publish(entry) {
      const state = snapshotEntry(entry);
      for (const consumer of entry.consumers.values()) {
        try { consumer.listener(state); } catch { /* A view callback must not stop other camera consumers. */ }
      }
    }

    function clearEntryResources(entry) {
      if (entry.cacheTimer) clearTimeout(entry.cacheTimer);
      entry.cacheTimer = null;
      if (entry.nextTimer) clearTimeout(entry.nextTimer);
      entry.nextTimer = null;
      if (entry.staleTimer) clearTimeout(entry.staleTimer);
      entry.staleTimer = null;
      if (entry.controller) entry.controller.abort();
      entry.controller = null;
      entry.generation += 1;
      if (entry.objectUrl) urlApi.revokeObjectURL(entry.objectUrl);
      entry.objectUrl = null;
      entry.frameId = null;
      entry.receivedAt = null;
      entry.frameAgeAtReceipt = 0;
      entry.status = 'idle';
      entry.error = '';
    }

    function createEntry(id) {
      return {
        id, consumers: new Map(), status: 'idle', error: '', objectUrl: null, frameId: null,
        capturedAt: null, width: null, height: null, simulated: null, receivedAt: null,
        frameAgeAtReceipt: 0, lastNewFrameAt: null, previewRefreshHz: null, failures: 0, inFlight: false, controller: null, generation: 0,
        queued: false, nextTimer: null, staleTimer: null, cacheTimer: null
      };
    }

    function schedule(entry, delay = intervalMs) {
      if (!canRun(entry) || entry.inFlight || entry.queued || entry.nextTimer) return;
      entry.nextTimer = setTimeout(() => {
        entry.nextTimer = null;
        enqueue(entry);
      }, Math.max(0, delay));
    }

    function enqueue(entry) {
      if (!canRun(entry) || entry.inFlight || entry.queued) return;
      entry.queued = true;
      queue.push(entry);
      pump();
    }

    function pump() {
      while (!disposed && activeRequests < maxConcurrency && queue.length) {
        const entry = queue.shift();
        entry.queued = false;
        if (!canRun(entry) || entry.inFlight) continue;
        activeRequests += 1;
        fetchEntry(entry).finally(() => {
          activeRequests = Math.max(0, activeRequests - 1);
          pump();
        });
      }
    }

    async function fetchEntry(entry) {
      const controller = new AbortController();
      const generation = ++entry.generation;
      entry.controller = controller;
      entry.inFlight = true;
      entry.status = entry.frameId ? 'refreshing' : 'loading';
      entry.error = '';
      publish(entry);
      let timedOut = false;
      const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
      try {
        const response = await fetchImpl(`/api/cameras/${encodeURIComponent(entry.id)}/preview`, {
          method: 'GET', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
          headers: { Accept: 'image/jpeg' }
        });
        if (generation !== entry.generation || !entry.consumers.size || !isDocumentVisible()) return;
        if (response.status === 401) {
          entry.status = 'unauthorized'; entry.error = 'Session expired'; entry.failures = 0;
          publish(entry);
          if (!unauthorizedHandled) { unauthorizedHandled = true; onUnauthorized(); }
          return;
        }
        if (response.status === 403) { entry.status = 'forbidden'; entry.error = 'Preview access denied'; entry.failures = 0; publish(entry); return; }
        if (response.status === 404) { entry.status = 'missing'; entry.error = 'Camera is no longer available'; entry.failures = 0; publish(entry); return; }
        if (response.status === 503) { entry.status = 'worker-unavailable'; entry.error = 'Preview is not available'; throw Object.assign(new Error(entry.error), { previewStatus: 'worker-unavailable' }); }
        if (!response.ok) throw Object.assign(new Error('Preview request failed'), { previewStatus: 'error' });
        if (!(response.headers.get('content-type') || '').toLowerCase().startsWith('image/jpeg')) {
          throw Object.assign(new Error('Preview response was not JPEG'), { previewStatus: 'error' });
        }
        const length = Number(response.headers.get('content-length'));
        if (Number.isFinite(length) && length > MAX_PREVIEW_BYTES) throw Object.assign(new Error('Preview frame exceeded its size limit'), { previewStatus: 'error' });
        const blob = await response.blob();
        if (blob.size > MAX_PREVIEW_BYTES) throw Object.assign(new Error('Preview frame exceeded its size limit'), { previewStatus: 'error' });
        if (generation !== entry.generation || !entry.consumers.size || !isDocumentVisible()) return;
        const id = response.headers.get('x-frame-id');
        const capturedAt = response.headers.get('x-captured-at');
        if (!id || !capturedAt) throw Object.assign(new Error('Preview frame identity is unavailable'), { previewStatus: 'error' });
        const age = Math.max(0, Number(response.headers.get('x-frame-age-ms')) || 0);
        if (entry.frameId !== id) {
          const url = urlApi.createObjectURL(blob);
          const oldUrl = entry.objectUrl;
          entry.objectUrl = url;
          if (oldUrl) urlApi.revokeObjectURL(oldUrl);
          entry.frameId = id;
          entry.capturedAt = capturedAt;
          entry.width = Number(response.headers.get('x-frame-width')) || null;
          entry.height = Number(response.headers.get('x-frame-height')) || null;
          entry.simulated = response.headers.get('x-simulation') === 'SIMULATED';
          const receivedAt = now();
          if (entry.lastNewFrameAt !== null && receivedAt > entry.lastNewFrameAt) {
            const sample = 1000 / (receivedAt - entry.lastNewFrameAt);
            entry.previewRefreshHz = entry.previewRefreshHz === null ? sample : entry.previewRefreshHz * 0.7 + sample * 0.3;
          }
          entry.lastNewFrameAt = receivedAt;
          entry.receivedAt = receivedAt;
        }
        entry.frameAgeAtReceipt = age;
        entry.status = snapshotEntry(entry).stale ? 'stale' : 'fresh';
        entry.error = '';
        entry.failures = 0;
        publish(entry);
        if (entry.staleTimer) clearTimeout(entry.staleTimer);
        const untilStale = Math.max(0, staleAfterMs - (entry.frameAgeAtReceipt + Math.max(0, now() - entry.receivedAt)) + 1);
        entry.staleTimer = setTimeout(() => {
          entry.staleTimer = null;
          if (entry.frameId && snapshotEntry(entry).stale && entry.status === 'fresh') { entry.status = 'stale'; publish(entry); }
        }, untilStale);
      } catch (error) {
        if (generation !== entry.generation) return;
        if (controller.signal.aborted && !timedOut) {
          entry.status = entry.consumers.size ? 'paused' : 'idle';
        } else {
          entry.failures += 1;
          if (timedOut) { entry.status = 'timeout'; entry.error = 'Preview request timed out'; }
          else if (error?.previewStatus) { entry.status = error.previewStatus; entry.error = error.message; }
          else { entry.status = 'error'; entry.error = 'Preview request failed'; }
        }
        publish(entry);
      } finally {
        clearTimeout(timeout);
        if (entry.controller === controller) entry.controller = null;
        entry.inFlight = false;
        if (generation === entry.generation) {
          if (canRun(entry) && !['unauthorized', 'forbidden', 'missing'].includes(entry.status)) {
            const delay = entry.failures ? Math.min(maxBackoffMs, initialBackoffMs * (2 ** Math.min(6, entry.failures - 1))) : intervalMs;
            schedule(entry, delay);
          } else if (entry.consumers.size && !canRun(entry)) {
            entry.status = 'paused'; publish(entry);
          }
        }
      }
    }

    function subscribe(idValue, listener, { active = true } = {}) {
      if (disposed) throw new Error('Preview manager is disposed');
      const id = cameraId(idValue);
      if (!Number.isInteger(id) || id <= 0) throw new TypeError('A valid camera id is required');
      let entry = entries.get(id);
      if (!entry) { entry = createEntry(id); entries.set(id, entry); }
      if (entry.cacheTimer) { clearTimeout(entry.cacheTimer); entry.cacheTimer = null; }
      const token = Symbol(String(id));
      entry.consumers.set(token, { listener, active: !!active });
      listener(snapshotEntry(entry));
      if (active && isDocumentVisible()) enqueue(entry);
      return {
        setActive(value) {
          const consumer = entry.consumers.get(token);
          if (!consumer || consumer.active === !!value) return;
          consumer.active = !!value;
          if (canRun(entry)) enqueue(entry);
          else if (!hasActiveConsumer(entry)) pauseEntry(entry);
        },
        retry() {
          entry.failures = 0;
          entry.status = entry.frameId ? 'refreshing' : 'loading';
          if (entry.nextTimer) { clearTimeout(entry.nextTimer); entry.nextTimer = null; }
          publish(entry);
          enqueue(entry);
        },
        release() {
          if (!entry.consumers.delete(token)) return;
          if (!entry.consumers.size) {
            pauseEntry(entry);
            entry.cacheTimer = setTimeout(() => {
              if (!entry.consumers.size) { clearEntryResources(entry); entries.delete(id); }
            }, cacheGraceMs);
          } else if (!hasActiveConsumer(entry)) pauseEntry(entry);
        }
      };
    }

    function pauseEntry(entry) {
      if (entry.nextTimer) { clearTimeout(entry.nextTimer); entry.nextTimer = null; }
      if (entry.queued) { queue = queue.filter(item => item !== entry); entry.queued = false; }
      if (entry.controller && !entry.controller.signal.aborted) {
        entry.generation += 1;
        entry.controller.abort();
      }
      entry.status = entry.consumers.size ? 'paused' : 'idle';
      publish(entry);
    }

    function onVisibilityChange() {
      if (!isDocumentVisible()) {
        for (const entry of entries.values()) { pauseEntry(entry); entry.status = 'suspended'; publish(entry); }
        return;
      }
      let offset = 0;
      for (const entry of entries.values()) {
        if (canRun(entry)) {
          if (entry.nextTimer) { clearTimeout(entry.nextTimer); entry.nextTimer = null; }
          const delay = offset;
          offset += 80;
          entry.nextTimer = setTimeout(() => { entry.nextTimer = null; enqueue(entry); }, delay);
        } else if (entry.consumers.size) { entry.status = 'paused'; publish(entry); }
      }
    }
    documentRef?.addEventListener?.('visibilitychange', onVisibilityChange);

    function snapshot() { return [...entries.values()].map(entry => snapshotEntry(entry)); }
    function clearAll() {
      unauthorizedHandled = false;
      queue = [];
      for (const entry of entries.values()) clearEntryResources(entry);
      entries.clear();
    }
    function dispose() {
      if (disposed) return;
      disposed = true;
      documentRef?.removeEventListener?.('visibilitychange', onVisibilityChange);
      clearAll();
    }
    return Object.freeze({ subscribe, snapshot, clearAll, dispose, setUnauthorizedHandler: handler => { onUnauthorized = handler || (() => {}); }, get activeRequests() { return activeRequests; } });
  }

  const previewManager = createPreviewManager({ onUnauthorized: () => previewManager.onUnauthorized?.() });

  function cameraHealth(camera) {
    if (!camera) return 'Unknown';
    if (!camera.enabled) return 'Disabled';
    if (camera.status === 'ONLINE') return 'Online';
    if (camera.status === 'OFFLINE') return 'Offline';
    if (camera.status === 'CONNECTING') return 'Connecting';
    return 'Unknown';
  }

  function frameStatus(camera, preview, workerState) {
    if (!camera) return { title: 'No camera assigned', message: 'Choose a camera for this view.', tone: 'unknown' };
    if (!camera.enabled) return { title: 'Source disabled', message: 'This camera is disabled.', tone: 'offline' };
    if (camera.status === 'OFFLINE') return { title: 'Source offline', message: `Camera reader is offline${camera.error_category ? ` · ${camera.error_category}` : ''}.`, tone: 'offline' };
    if (camera.status === 'CONNECTING') return { title: 'Connecting', message: 'The source reader is connecting.', tone: 'pending' };
    if (preview?.status === 'unauthorized') return { title: 'Session expired', message: 'Sign in again to continue viewing.', tone: 'offline' };
    if (preview?.status === 'forbidden') return { title: 'Access denied', message: 'Your account cannot view this preview.', tone: 'offline' };
    if (preview?.status === 'missing') return { title: 'Camera unavailable', message: 'This source may have been removed.', tone: 'offline' };
    if (workerState === 'OFFLINE') return { title: 'Ingestion worker unavailable', message: 'No current worker lease is reported.', tone: 'offline' };
    if (preview?.status === 'worker-unavailable') return { title: 'Preview unavailable', message: 'The worker has not published an available frame.', tone: 'offline' };
    if (preview?.status === 'timeout' || preview?.status === 'error') return { title: 'Preview request failed', message: preview.error || 'Retry the authenticated preview request.', tone: 'offline' };
    if (preview?.freshness === 'stale' || camera.preview_stale) return { title: 'Stale frame', message: `Last captured ${preview?.capturedAt || camera.last_frame || 'time unavailable'}.`, tone: 'stale' };
    if (preview?.status === 'paused' || preview?.status === 'suspended') return { title: preview.status === 'paused' ? 'Preview inactive' : 'Page hidden', message: preview.status === 'paused' ? 'This tile is paused or outside the visible view; source monitoring continues.' : 'Preview requests resume when this page is visible.', tone: 'pending' };
    if (preview?.freshness === 'fresh') return { title: 'Fresh frame', message: 'Displayed frame identity is current.', tone: 'fresh' };
    if (preview?.status === 'loading' || preview?.status === 'refreshing') return { title: 'Loading preview', message: 'Waiting for an authenticated worker frame.', tone: 'pending' };
    return { title: 'Frame state unknown', message: 'Waiting for frame identity and capture time.', tone: 'unknown' };
  }

  function mountViewer(options) {
    const host = options.host;
    if (!host) throw new TypeError('A viewer host is required');
    const state = {
      cameras: availableCameras(options.cameras), selectedCameraId: cameraId(options.selectedCameraId),
      mode: options.mode === 'grid' ? 'grid' : 'single', assignments: options.assignments || null,
      workerState: options.workerState || 'UNKNOWN', compact: !!options.compact, paused: false,
      expanded: false, subscriptions: new Map(), previewStates: new Map(), observer: null, disposed: false
    };
    const manager = options.manager || previewManager;
    const formatTime = options.formatTime || (value => value ? new Date(value).toLocaleString() : 'No frame yet');

    function camerasInView() {
      const byId = new Map(state.cameras.map(camera => [camera.id, camera]));
      if (state.mode === 'grid') {
        const assignments = state.assignments || initialGridAssignments(state.cameras, state.selectedCameraId);
        return assignments.map((id, slot) => ({ slot, camera: byId.get(id) || null }));
      }
      return [{ slot: 0, camera: byId.get(state.selectedCameraId) || null }];
    }

    function renderShell() {
      const tiles = camerasInView();
      const populated = tiles.filter(tile => tile.camera);
      const oldIds = [...state.subscriptions.values()].map(item => `${item.slot}:${item.cameraId}`).sort().join('|');
      const newIds = populated.map(item => `${item.slot}:${item.camera.id}`).sort().join('|');
      host.innerHTML = `<div class="lm-viewer ${state.compact ? 'lm-viewer-compact' : ''} ${state.expanded ? 'lm-viewer-expanded' : ''} ${state.mode === 'grid' ? 'lm-viewer-grid' : 'lm-viewer-single'}" data-viewer-mode="${state.mode}"><div class="lm-viewer-toolbar"><span class="lm-viewer-caption">${state.mode === 'grid' ? '2×2 live views' : 'Selected camera'}</span><div class="lm-viewer-actions"><button type="button" class="secondary small" data-lm-pause aria-pressed="${state.paused}">${state.paused ? 'Resume display' : 'Pause display'}</button><button type="button" class="secondary small" data-lm-expand aria-pressed="${state.expanded}">${state.expanded ? 'Restore' : 'Expand'}</button><button type="button" class="secondary small" data-lm-fullscreen>Full screen</button></div></div><div class="lm-tile-grid">${tiles.map(({ slot, camera }) => camera ? `<article class="lm-tile ${camera.id === state.selectedCameraId ? 'is-selected' : ''}" data-lm-tile data-slot="${slot}" data-camera-id="${camera.id}"><header class="lm-tile-header"><button type="button" class="lm-tile-select" data-lm-select="${camera.id}" aria-pressed="${camera.id === state.selectedCameraId}">${escapeHTML(camera.name)}</button><span class="status">${escapeHTML(cameraHealth(camera))}</span></header><div class="lm-frame" data-lm-frame><img data-lm-image alt="${escapeHTML(camera.name)} authenticated camera preview" hidden><div class="lm-frame-state" data-lm-state role="status">Waiting for preview.</div><span class="lm-source-label">${camera.simulated ? 'SIMULATED SOURCE' : 'REAL SOURCE'}</span></div><footer class="lm-tile-footer"><span data-lm-meta>Frame time unavailable · freshness unknown</span><span class="lm-tile-controls"><button type="button" class="secondary small" data-lm-retry="${camera.id}">Retry preview</button>${options.onCameraDetails ? `<button type="button" class="secondary small" data-lm-details="${camera.id}">Camera details</button>` : ''}</span></footer></article>` : `<article class="lm-tile lm-empty-tile" data-slot="${slot}"><strong>Empty slot ${slot + 1}</strong><span>Choose a camera from the list.</span></article>`).join('')}</div></div>`;
      bindViewerActions();
      if (oldIds !== newIds) bindSubscriptions(tiles);
      else refreshTileStates();
    }

    function paintTile(slot, camera, preview) {
      if (state.disposed) return;
      const tile = host.querySelector(`[data-lm-tile][data-slot="${slot}"][data-camera-id="${camera.id}"]`);
      if (!tile) return;
      const image = tile.querySelector('[data-lm-image]');
      const status = frameStatus(camera, preview, state.workerState);
      if (preview?.url && image.dataset.url !== preview.url) {
        image.src = preview.url;
        image.dataset.url = preview.url;
        image.hidden = false;
      }
      image.alt = `${camera.name} ${camera.simulated ? 'simulated' : 'real source'} preview; ${status.title}`;
      const overlay = tile.querySelector('[data-lm-state]');
      overlay.textContent = `${status.title} · ${status.message}`;
      overlay.className = `lm-frame-state ${status.tone}`;
      overlay.hidden = status.tone === 'fresh' && !state.paused;
      const meta = tile.querySelector('[data-lm-meta]');
      const captured = preview?.capturedAt || camera.last_frame;
      const ageSeconds = preview?.frameAgeMs === null || preview?.frameAgeMs === undefined ? null : Math.max(0, Math.floor(preview.frameAgeMs / 1000));
      const refresh = preview?.previewRefreshHz === null || preview?.previewRefreshHz === undefined ? 'refresh rate measuring' : `new frames ${preview.previewRefreshHz.toFixed(1)}/s`;
      const sourceRate = Number(camera.processing_fps) > 0 ? `source target ${camera.processing_fps} fps` : 'source rate unknown';
      meta.textContent = `Captured ${formatTime(captured)} · ${preview?.freshness || (camera.preview_stale ? 'stale' : 'unknown')}${ageSeconds === null ? '' : ` · age ${ageSeconds}s`} · ${refresh} · ${sourceRate}`;
      tile.dataset.frameId = preview?.frameId || '';
      tile.dataset.freshness = preview?.freshness || 'unknown';
      const statusBadge = tile.querySelector('.status');
      statusBadge.textContent = !camera.enabled ? 'DISABLED' : camera.status || 'UNKNOWN';
      statusBadge.className = `status ${!camera.enabled || camera.status === 'OFFLINE' ? 'bad' : camera.status === 'ONLINE' ? 'good' : 'warn'}`;
    }

    function refreshTileStates() {
      for (const [slot, record] of state.subscriptions) paintTile(slot, record.camera, state.previewStates.get(record.cameraId));
      for (const tile of host.querySelectorAll('.lm-empty-tile')) {
        if (!tile.querySelector('.lm-empty-controls')) tile.insertAdjacentHTML('beforeend', '<span class="lm-empty-controls">Select a slot, then choose a camera.</span>');
      }
    }

    function bindSubscriptions(tiles) {
      state.observer?.disconnect();
      state.observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(records => {
        for (const record of records) {
          const slot = Number(record.target.dataset.slot);
          const subscription = state.subscriptions.get(slot);
          if (subscription) { subscription.visible = record.isIntersecting && record.intersectionRatio > 0.05; subscription.subscription.setActive(subscription.visible && !state.paused); }
        }
      }, { threshold: [0, 0.05] }) : null;
      for (const record of state.subscriptions.values()) record.subscription.release();
      state.subscriptions.clear();
      state.previewStates.clear();
      for (const { slot, camera } of tiles) {
        if (!camera) continue;
        const tile = host.querySelector(`[data-lm-tile][data-slot="${slot}"][data-camera-id="${camera.id}"]`);
        const visible = !state.observer;
        const subscription = manager.subscribe(camera.id, preview => {
          state.previewStates.set(camera.id, preview);
          paintTile(slot, camera, preview);
        }, { active: visible && !state.paused });
        state.subscriptions.set(slot, { cameraId: camera.id, camera, subscription, visible });
        if (state.observer && tile) state.observer.observe(tile);
      }
    }

    function bindViewerActions() {
      host.querySelectorAll('[data-lm-select]').forEach(button => button.addEventListener('click', () => {
        const id = Number(button.dataset.lmSelect);
        const slot = Number(button.closest('[data-slot]')?.dataset.slot) || 0;
        state.selectedCameraId = id;
        options.onSelectCamera?.(id, slot);
        if (state.mode === 'grid') options.onFocusSlot?.(slot, id);
        updateHighlights();
      }));
      host.querySelectorAll('[data-lm-retry]').forEach(button => button.addEventListener('click', () => state.subscriptions.get(Number(button.closest('[data-slot]')?.dataset.slot))?.subscription.retry()));
      host.querySelectorAll('[data-lm-details]').forEach(button => button.addEventListener('click', () => options.onCameraDetails?.(Number(button.dataset.lmDetails))));
      host.querySelector('[data-lm-pause]')?.addEventListener('click', () => setPaused(!state.paused));
      host.querySelector('[data-lm-expand]')?.addEventListener('click', () => { state.expanded = !state.expanded; host.querySelector('.lm-viewer')?.classList.toggle('lm-viewer-expanded', state.expanded); const button = host.querySelector('[data-lm-expand]'); button.textContent = state.expanded ? 'Restore' : 'Expand'; button.setAttribute('aria-pressed', String(state.expanded)); });
      host.querySelector('[data-lm-fullscreen]')?.addEventListener('click', async () => {
        const target = host.querySelector('.lm-viewer');
        try { if (document.fullscreenElement === target) await document.exitFullscreen(); else if (target?.requestFullscreen) await target.requestFullscreen(); else { const button = host.querySelector('[data-lm-fullscreen]'); if (button) { button.textContent = 'Full screen unavailable'; button.disabled = true; } } }
        catch { const button = host.querySelector('[data-lm-fullscreen]'); if (button) button.textContent = 'Full screen unavailable'; }
      });
    }

    function updateHighlights() {
      host.querySelectorAll('[data-lm-tile]').forEach(tile => {
        const selected = Number(tile.dataset.cameraId) === state.selectedCameraId;
        tile.classList.toggle('is-selected', selected);
        tile.querySelector('[data-lm-select]')?.setAttribute('aria-pressed', String(selected));
      });
    }

    function setPaused(paused) {
      state.paused = !!paused;
      for (const record of state.subscriptions.values()) record.subscription.setActive(!state.paused && record.visible);
      const button = host.querySelector('[data-lm-pause]');
      if (button) { button.textContent = state.paused ? 'Resume display' : 'Pause display'; button.setAttribute('aria-pressed', String(state.paused)); }
      refreshTileStates();
    }

    function update(next = {}) {
      if (state.disposed) return;
      const previousIds = camerasInView().map(tile => `${tile.slot}:${tile.camera?.id || ''}`).join('|');
      if (next.cameras) state.cameras = availableCameras(next.cameras);
      if ('selectedCameraId' in next) state.selectedCameraId = cameraId(next.selectedCameraId);
      if ('workerState' in next) state.workerState = next.workerState || 'UNKNOWN';
      if ('mode' in next) state.mode = next.mode === 'grid' ? 'grid' : 'single';
      if ('assignments' in next) state.assignments = next.assignments;
      const existing = new Set(state.cameras.map(camera => camera.id));
      if (state.assignments) state.assignments = state.assignments.map(id => existing.has(cameraId(id)) ? cameraId(id) : null);
      const nextIds = camerasInView().map(tile => `${tile.slot}:${tile.camera?.id || ''}`).join('|');
      if (previousIds !== nextIds) renderShell();
      else {
        for (const record of state.subscriptions.values()) record.camera = state.cameras.find(camera => camera.id === record.cameraId) || record.camera;
        refreshTileStates(); updateHighlights();
      }
    }

    function dispose() {
      if (state.disposed) return;
      state.disposed = true;
      state.observer?.disconnect();
      for (const record of state.subscriptions.values()) record.subscription.release();
      state.subscriptions.clear();
      state.previewStates.clear();
      host.replaceChildren();
    }

    renderShell();
    return Object.freeze({ update, dispose, setPaused, snapshot: () => Object.freeze({ mode: state.mode, selectedCameraId: state.selectedCameraId, assignments: state.assignments ? [...state.assignments] : null, paused: state.paused }) });
  }

  function mountLivePage(options) {
    const host = options.host;
    const userKey = String(options.userId ?? 'session');
    let pref = pagePreferences.get(userKey);
    if (!pref) {
      pref = { mode: 'single', activeSlot: 0, assignments: initialGridAssignments(options.cameras, options.selectedCameraId), search: '', health: '' };
      pagePreferences.set(userKey, pref);
    }
    const state = { cameras: availableCameras(options.cameras), selectedCameraId: cameraId(options.selectedCameraId), workerState: options.workerState || 'UNKNOWN', disposed: false, message: '' };
    if (state.selectedCameraId && !state.cameras.some(camera => camera.id === state.selectedCameraId)) state.message = 'The selected source is not available for live preview in this view.';
    const eligible = () => state.cameras;
    let viewer = null;
    let viewerHost = null;

    function listMarkup() {
      const query = pref.search.toLocaleLowerCase();
      const filtered = eligible().filter(camera => (!query || `${camera.name} ${camera.location || ''}`.toLocaleLowerCase().includes(query)) && (!pref.health || (pref.health === 'DISABLED' ? !camera.enabled : camera.status === pref.health)));
      return `<label class="field lm-filter">Search cameras<input data-lm-search type="search" value="${escapeHTML(pref.search)}" placeholder="Name or location"></label><label class="field lm-filter">Health<select data-lm-health><option value="">All health states</option>${['ONLINE','CONNECTING','OFFLINE','DISABLED','UNKNOWN'].map(value => `<option value="${value}" ${pref.health === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label><div class="lm-camera-list" role="list" aria-label="Available cameras">${filtered.length ? filtered.map(camera => `<button type="button" class="lm-camera-option ${camera.id === state.selectedCameraId ? 'selected' : ''}" data-lm-camera-option="${camera.id}" role="listitem"><span><strong>${escapeHTML(camera.name)}</strong><small>${escapeHTML(camera.location || 'No location')} · ${camera.simulated ? 'SIMULATED' : 'REAL SOURCE'}</small></span><span class="status ${!camera.enabled || camera.status === 'OFFLINE' ? 'bad' : camera.status === 'ONLINE' ? 'good' : 'warn'}">${escapeHTML(!camera.enabled ? 'DISABLED' : camera.status || 'UNKNOWN')}</span></button>`).join('') : '<div class="empty">No cameras match the current filters.</div>'}</div>`;
    }

    function assignmentMarkup() {
      if (pref.mode !== 'grid') return '';
      const cameras = eligible();
      return `<div class="lm-slot-picker" aria-label="Grid camera assignments">${Array.from({ length: 4 }, (_, slot) => `<div class="lm-slot-control"><button type="button" class="secondary small ${pref.activeSlot === slot ? 'active' : ''}" data-lm-slot="${slot}" aria-pressed="${pref.activeSlot === slot}">Slot ${slot + 1}${pref.assignments[slot] ? ` · ${escapeHTML(cameras.find(camera => camera.id === pref.assignments[slot])?.name || 'Camera missing')}` : ' · Empty'}</button><select data-lm-assign="${slot}" aria-label="Assign camera to slot ${slot + 1}"><option value="">Empty slot</option>${cameras.map(camera => `<option value="${camera.id}" ${pref.assignments[slot] === camera.id ? 'selected' : ''}>${escapeHTML(camera.name)}</option>`).join('')}</select></div>`).join('')}</div>`;
    }

    function build() {
      if (state.disposed) return;
      const retained = host.querySelector('[data-live-viewer]');
      host.innerHTML = `<header class="page-head"><div class="page-title-wrap"><div class="eyebrow">Operations</div><h1>Live Monitoring</h1><p class="muted">Authenticated worker-published frames. Source health, worker state and frame freshness are shown separately.</p></div><div class="actions-row">${options.me?.role === 'ADMIN' ? '<button type="button" data-lm-add-camera>Add camera</button>' : ''}<button type="button" class="secondary" data-lm-open-control>Open Control Center</button></div></header><div class="lm-layout"><aside class="lm-camera-sidebar"><div class="lm-list-heading"><h2>Cameras</h2><span>${eligible().length}</span></div>${listMarkup()}<div data-lm-message class="notice" role="status" ${state.message ? '' : 'hidden'}>${escapeHTML(state.message)}</div></aside><section class="lm-main"><div class="lm-page-toolbar"><div class="lm-mode-actions"><button type="button" class="secondary small ${pref.mode === 'single' ? 'active' : ''}" data-lm-mode="single" aria-pressed="${pref.mode === 'single'}">Single</button><button type="button" class="secondary small ${pref.mode === 'grid' ? 'active' : ''}" data-lm-mode="grid" aria-pressed="${pref.mode === 'grid'}">2×2 grid</button><span class="lm-worker-state">Ingestion worker: ${escapeHTML(state.workerState)}</span></div></div>${assignmentMarkup()}<div class="lm-viewer-shell"><div data-live-viewer class="lm-viewer-mount"></div></div><p class="muted small-text">Pause affects this display only. Source ingestion and configured AI processing continue. Captured time and age come from the worker-published frame metadata; refresh rate is independent of source and inference FPS.</p></section></div>`;
      const mount = host.querySelector('[data-live-viewer]');
      if (retained) { mount.replaceWith(retained); viewerHost = retained; viewer?.update({ cameras: state.cameras, selectedCameraId: state.selectedCameraId, mode: pref.mode, assignments: pref.assignments, workerState: state.workerState }); }
      else { viewerHost = mount; viewer = mountViewer({ host: mount, cameras: state.cameras, selectedCameraId: state.selectedCameraId, mode: pref.mode, assignments: pref.assignments, workerState: state.workerState, onSelectCamera: selectCamera, onFocusSlot: slot => { pref.activeSlot = slot; }, onCameraDetails: options.onCameraDetails }); }
      bind();
    }

    function selectCamera(id, slot = pref.activeSlot) {
      const camera = state.cameras.find(item => item.id === Number(id));
      if (!camera) return;
      if (pref.mode === 'grid') {
        pref.activeSlot = slot;
        const result = assignGridCamera(pref.assignments, slot, camera.id);
        if (result.ok) pref.assignments = result.assignments;
        else { pref.activeSlot = result.focusSlot; state.message = `${camera.name} is already in slot ${result.focusSlot + 1}; focused the existing slot.`; }
      }
      state.selectedCameraId = camera.id;
      options.onCameraSelected?.(camera.id);
      build();
    }

    function bind() {
      host.querySelector('[data-lm-search]')?.addEventListener('input', event => { pref.search = event.target.value; const selection = event.target.selectionStart; build(); const input = host.querySelector('[data-lm-search]'); input.focus(); input.setSelectionRange(selection, selection); });
      host.querySelector('[data-lm-health]')?.addEventListener('change', event => { pref.health = event.target.value; build(); });
      host.querySelectorAll('[data-lm-mode]').forEach(button => button.addEventListener('click', () => {
        pref.mode = button.dataset.lmMode;
        if (pref.mode === 'grid') {
          if (!pref.assignments?.length) pref.assignments = initialGridAssignments(state.cameras, state.selectedCameraId);
          const focus = focusGridSelection(pref.assignments, pref.activeSlot, state.selectedCameraId);
          pref.assignments = focus.assignments; pref.activeSlot = focus.activeSlot;
        }
        build();
      }));
      host.querySelectorAll('[data-lm-slot]').forEach(button => button.addEventListener('click', () => {
        pref.activeSlot = Number(button.dataset.lmSlot);
        const id = pref.assignments[pref.activeSlot];
        if (id) { state.selectedCameraId = id; options.onCameraSelected?.(id); }
        build();
      }));
      host.querySelectorAll('[data-lm-assign]').forEach(select => select.addEventListener('change', () => {
        const slot = Number(select.dataset.lmAssign), id = cameraId(select.value);
        const result = assignGridCamera(pref.assignments, slot, id);
        if (!result.ok) {
          pref.activeSlot = result.focusSlot;
          state.message = `That camera is already assigned to slot ${result.focusSlot + 1}. The existing slot is focused.`;
          state.selectedCameraId = id;
          options.onCameraSelected?.(id);
        } else {
          pref.assignments = result.assignments; pref.activeSlot = slot; state.message = '';
          if (id) { state.selectedCameraId = id; options.onCameraSelected?.(id); }
          else if (state.selectedCameraId && !pref.assignments.includes(state.selectedCameraId)) { state.selectedCameraId = null; options.onCameraSelected?.(null); }
        }
        build();
      }));
      host.querySelectorAll('[data-lm-camera-option]').forEach(button => button.addEventListener('click', () => selectCamera(Number(button.dataset.lmCameraOption))));
      host.querySelector('[data-lm-open-control]')?.addEventListener('click', options.onOpenControlCenter);
      host.querySelector('[data-lm-add-camera]')?.addEventListener('click', options.onAddCamera);
    }

    function update(next = {}) {
      if (state.disposed) return;
      if (next.cameras) state.cameras = availableCameras(next.cameras);
      if ('workerState' in next) state.workerState = next.workerState || 'UNKNOWN';
      if ('selectedCameraId' in next) {
        const nextId = cameraId(next.selectedCameraId);
        if (nextId !== state.selectedCameraId) {
          state.selectedCameraId = nextId;
          if (pref.mode === 'grid' && nextId) {
            const focused = focusGridSelection(pref.assignments, pref.activeSlot, nextId);
            pref.assignments = focused.assignments; pref.activeSlot = focused.activeSlot;
          }
        }
      }
      const available = new Set(state.cameras.map(camera => camera.id));
      pref.assignments = Array.from({ length: 4 }, (_, slot) => available.has(cameraId(pref.assignments?.[slot])) ? cameraId(pref.assignments[slot]) : null);
      if (state.selectedCameraId && !available.has(state.selectedCameraId)) state.selectedCameraId = null;
      build();
    }

    function dispose() { state.disposed = true; viewer?.dispose(); viewer = null; viewerHost = null; host.replaceChildren(); }
    build();
    return Object.freeze({ update, dispose, snapshot: () => Object.freeze({ ...pref, assignments: [...pref.assignments], selectedCameraId: state.selectedCameraId }) });
  }

  const api = Object.freeze({
    createPreviewManager, initialGridAssignments, focusGridSelection, assignGridCamera,
    mountViewer, mountLivePage, clearPrivateFrames: () => previewManager.clearAll(),
    clearSession: () => { previewManager.clearAll(); pagePreferences.clear(); },
    setUnauthorizedHandler: handler => { previewManager.setUnauthorizedHandler(handler); }
  });
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.VisorMonitoring = api;
})();
