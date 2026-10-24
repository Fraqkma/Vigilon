// Event action evidence: detection box placement and the review dialog markup (node --test frontend/features/incidents.test.js)
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// Minimal browser stand-ins: incidents.js loads its stylesheet and registers delegated listeners at start-up
const listeners = {};
const document = {
  getElementById: () => null,
  head: { append() {} },
  createElement: () => ({}),
  addEventListener: (type, fn) => { listeners[type] = fn; },
};
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'incidents.js'), 'utf8'), { window, document, Object, Number, Math, Array, String });
const incidents = window.VisorIncidents;
const box = (incident) => { const b = incidents.evidenceBox(incident); return b && Array.from(b); };   // copy out of the vm realm
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const base = { id: 7, camera_id: 2, event_type: 'SMOKE_FIRE', status: 'NEW', severity: 'HIGH', simulated: false, snapshot_available: true, first_seen: 't0', last_seen: 't1', history: [] };

test('normalized geometry is used as-is and clamped', () => {
  assert.deepEqual(box({ metadata: { geometry: { normalized: [0.25, 0.4, 0.75, 0.75] } } }), [0.25, 0.4, 0.75, 0.75]);
  assert.deepEqual(box({ metadata: { geometry: { normalized: [-1, 0, 2, 0.5] } } }), [0, 0, 1, 0.5]);
});

test('pixel xyxy needs the recorded frame size', () => {
  const meta = { geometry: { xyxy: [96, 54, 480, 270] } };
  assert.equal(box({ metadata: meta }), null);                       // older incidents: no guessing
  assert.deepEqual(box({ metadata: { ...meta, frame_size: [960, 540] } }), [0.1, 0.1, 0.5, 0.5]);
});

test('degenerate or broken boxes are not drawn', () => {
  assert.equal(box({ metadata: { geometry: { normalized: [0.5, 0.5, 0.5, 0.9] } } }), null);
  assert.equal(box({ metadata: { geometry: { normalized: [0, 'x', 1, 1] } } }), null);
  assert.equal(box({}), null);
});

test('open incident: enlarge button, review dialog and the same actions in both places', () => {
  const html = incidents.renderDetail({ ...base, metadata: { confidence: 0.82, geometry: { normalized: [0.1, 0.1, 0.5, 0.5] } } }, { name: 'Lobby <1>' }, false, esc, (v) => v);
  assert.ok(html.includes('data-review-open') && html.includes('<dialog class="ev-review"'));
  assert.equal(html.match(/data-action="RESOLVED"/g).length, 2);                         // panel + dialog
  assert.equal(html.match(/data-action-note/g).length, 2);
  assert.ok(html.includes('Lobby &lt;1&gt;') && !html.includes('Lobby <1>'));             // escaped
  assert.ok(html.includes('class="cc-box"') && html.includes('82%'));
});

test('terminal incident shows no action buttons and no snapshot means a notice', () => {
  const html = incidents.renderDetail({ ...base, status: 'RESOLVED', snapshot_available: false }, null, false, esc, (v) => v);
  assert.ok(!html.includes('data-action='));
  assert.ok(html.includes('terminal state') && html.includes('unavailable or expired'));
});

test('review wiring is delegated once at load', () => {
  assert.equal(typeof listeners.click, 'function');
  assert.equal(typeof listeners.input, 'function');
});
