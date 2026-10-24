const test = require('node:test');
const assert = require('node:assert/strict');
const { createPreviewManager, initialGridAssignments, focusGridSelection, assignGridCamera } = require('./monitoring.js');

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const waitFor = async predicate => {
  for (let i = 0; i < 100; i += 1) {
    if (predicate()) return;
    await wait(2);
  }
  assert.fail('condition did not become true');
};

function response({ frameId = 'frame-1', age = '0', status = 200 } = {}) {
  return new Response(status === 200 ? new Uint8Array([1, 2, 3]) : 'unavailable', {
    status,
    headers: status === 200 ? {
      'Content-Type': 'image/jpeg', 'X-Frame-ID': frameId, 'X-Captured-At': '2026-10-24T00:00:00Z',
      'X-Frame-Age-Ms': age, 'X-Simulation': 'SIMULATED', 'X-Frame-Width': '640', 'X-Frame-Height': '360'
    } : { 'Content-Type': 'application/json' }
  });
}

function managerOptions(overrides = {}) {
  let nextUrl = 0;
  return {
    urlApi: { createObjectURL: () => `blob:test-${++nextUrl}`, revokeObjectURL() {} },
    intervalMs: 10, initialBackoffMs: 12, maxBackoffMs: 24, timeoutMs: 100,
    staleAfterMs: 25, cacheGraceMs: 0, ...overrides
  };
}

test('deduplicates a source across subscribers and releases only after the last consumer', async () => {
  let calls = 0;
  const manager = createPreviewManager({ ...managerOptions(), fetchImpl: async () => { calls += 1; await wait(3); return response(); } });
  const states = [];
  const first = manager.subscribe(7, state => states.push(state));
  const second = manager.subscribe(7, state => states.push(state));
  await waitFor(() => states.some(state => state.status === 'fresh'));
  assert.equal(calls, 1);
  first.release();
  await wait(15);
  assert.ok(calls >= 2, 'remaining consumer keeps the shared refresh alive');
  second.release();
  manager.dispose();
});

test('caps global fetch concurrency at four and keeps one request in flight per source', async () => {
  let active = 0, maximum = 0;
  const manager = createPreviewManager({ ...managerOptions({ maxConcurrency: 12 }), fetchImpl: async () => {
    active += 1; maximum = Math.max(maximum, active); await wait(12); active -= 1; return response();
  } });
  const releases = [1, 2, 3, 4, 5, 6].map(id => manager.subscribe(id, () => {}));
  await waitFor(() => manager.snapshot().some(item => item.frameId));
  assert.equal(maximum, 4);
  assert.ok(manager.snapshot().every(item => item.inFlight <= 1));
  releases.forEach(subscription => subscription.release());
  manager.dispose();
});

test('measures displayed new-frame refresh without treating repeated identities as updates', async () => {
  let calls = 0;
  const manager = createPreviewManager({ ...managerOptions({ intervalMs: 8 }), fetchImpl: async () => {
    calls += 1; return response({ frameId: calls < 3 ? 'same' : `frame-${calls}` });
  } });
  const states = [];
  const subscription = manager.subscribe(14, state => states.push(state));
  await waitFor(() => states.some(state => state.previewRefreshHz !== null && state.previewRefreshHz !== undefined));
  assert.ok(states.filter(state => state.frameId === 'same').every(state => state.previewRefreshHz === null));
  assert.ok(states.some(state => state.frameId === 'frame-3' && state.previewRefreshHz > 0));
  subscription.release(); manager.dispose();
});

test('repeated frame identity does not refresh the displayed image receipt time', async () => {
  let calls = 0;
  const manager = createPreviewManager({ ...managerOptions({ staleAfterMs: 20 }), fetchImpl: async () => {
    calls += 1; return response({ frameId: 'same-frame', age: calls > 1 ? '45' : '0' });
  } });
  const states = [];
  const subscription = manager.subscribe(3, state => states.push(state));
  await waitFor(() => states.some(state => state.status === 'stale'));
  const fresh = states.find(state => state.status === 'fresh');
  const stale = states.find(state => state.status === 'stale');
  assert.equal(stale.frameId, fresh.frameId);
  assert.equal(stale.url, fresh.url);
  assert.ok(stale.frameAgeMs >= 45);
  subscription.release();
  manager.dispose();
});

test('auth failures stop retries while transient failures use bounded backoff', async () => {
  let calls = 0;
  const forbidden = createPreviewManager({ ...managerOptions(), fetchImpl: async () => { calls += 1; return response({ status: 403 }); } });
  const access = forbidden.subscribe(8, () => {});
  await waitFor(() => forbidden.snapshot()[0]?.status === 'forbidden');
  await wait(35);
  assert.equal(calls, 1);
  access.release(); forbidden.dispose();

  calls = 0;
  const transient = createPreviewManager({ ...managerOptions(), fetchImpl: async () => { calls += 1; return response({ status: 503 }); } });
  const retry = transient.subscribe(9, () => {});
  await waitFor(() => calls >= 2);
  assert.equal(transient.snapshot()[0].status, 'worker-unavailable');
  retry.release(); transient.dispose();
});

test('expired sessions notify the shell once and never retry with private frames retained', async () => {
  let calls = 0, redirected = 0;
  const manager = createPreviewManager({ ...managerOptions(), onUnauthorized: () => { redirected += 1; }, fetchImpl: async () => { calls += 1; return response({ status: 401 }); } });
  const subscription = manager.subscribe(12, () => {});
  await waitFor(() => manager.snapshot()[0]?.status === 'unauthorized');
  await wait(30);
  assert.equal(calls, 1);
  assert.equal(redirected, 1);
  subscription.release(); manager.clearAll();
  assert.equal(manager.snapshot().length, 0);
  manager.dispose();
});

test('timeouts abort and use capped retry delays, then accept a genuinely newer frame', async () => {
  let calls = 0;
  const manager = createPreviewManager({ ...managerOptions({ timeoutMs: 12, intervalMs: 8, initialBackoffMs: 10, maxBackoffMs: 20 }), fetchImpl: async (_url, { signal }) => {
    calls += 1;
    if (calls === 1) return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true }));
    return response({ frameId: `frame-${calls}` });
  } });
  const states = [];
  const subscription = manager.subscribe(13, state => states.push(state));
  await waitFor(() => states.some(state => state.status === 'timeout'));
  await waitFor(() => states.some(state => state.frameId === 'frame-2'));
  assert.equal(states.find(state => state.frameId === 'frame-2').freshness, 'fresh');
  assert.ok(calls >= 2);
  subscription.release(); manager.dispose();
});

test('hidden documents abort active work and resume without retaining an old response', async () => {
  const documentRef = new EventTarget();
  Object.defineProperty(documentRef, 'hidden', { value: false, writable: true });
  let aborted = 0, calls = 0;
  const manager = createPreviewManager({ ...managerOptions({ documentRef }), fetchImpl: (_url, { signal }) => new Promise((resolve, reject) => {
    calls += 1;
    signal.addEventListener('abort', () => { aborted += 1; reject(new DOMException('Aborted', 'AbortError')); }, { once: true });
    setTimeout(() => resolve(response({ frameId: `frame-${calls}` })), 35);
  }) });
  const subscription = manager.subscribe(10, () => {});
  await waitFor(() => manager.snapshot()[0]?.inFlight === 1);
  documentRef.hidden = true;
  documentRef.dispatchEvent(new Event('visibilitychange'));
  await waitFor(() => aborted === 1);
  assert.equal(manager.snapshot()[0].inFlight, 0);
  documentRef.hidden = false;
  documentRef.dispatchEvent(new Event('visibilitychange'));
  await waitFor(() => calls >= 2);
  subscription.release(); manager.dispose();
});

test('late responses after the last release cannot become a displayed frame', async () => {
  let resolveFetch;
  const manager = createPreviewManager({ ...managerOptions(), fetchImpl: () => new Promise(resolve => { resolveFetch = resolve; }) });
  const states = [];
  const subscription = manager.subscribe(11, state => states.push(state));
  await waitFor(() => !!resolveFetch);
  subscription.release();
  resolveFetch(response());
  await wait(5);
  assert.equal(states.some(state => state.frameId), false);
  manager.dispose();
});

test('grid assignment is unique and external selection replaces one deterministic slot', () => {
  const cameras = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }, { id: 6, source_type: 'file' }];
  assert.deepEqual(initialGridAssignments(cameras, 3), [3, 1, 2, 4]);
  const grid = focusGridSelection([1, 2, null, 4], 1, 5);
  assert.deepEqual(grid.assignments, [1, 5, null, 4]);
  assert.equal(grid.activeSlot, 1);
  const duplicate = assignGridCamera(grid.assignments, 3, 1);
  assert.deepEqual(duplicate, { ok: false, focusSlot: 0 });
  assert.deepEqual(assignGridCamera(grid.assignments, 2, null), { ok: true, assignments: [1, 5, null, 4] });
});
