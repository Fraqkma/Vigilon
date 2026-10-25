const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function helpers(confirm = () => true) {
  let restored = 0;
  const context = {window: {}, document: {activeElement: {isConnected: true, focus: () => restored++}}, confirm};
  vm.runInNewContext(fs.readFileSync(`${__dirname}/ui.js`, 'utf8'), context);
  return {ui: context.window.VisorUI, restored: () => restored};
}

test('keyboard geometry accepts a bounded zone and optional directed line', () => {
  const {ui} = helpers();
  const geometry = {points: [[0, 0], [1, 0], [1, 1], [0, 1]], line: [[0.2, 0.5], [0.8, 0.5]]};
  assert.equal(JSON.stringify(ui.parseGeometry(JSON.stringify(geometry))), JSON.stringify(geometry));
});

test('keyboard geometry rejects out-of-frame, degenerate and malformed coordinates', () => {
  const {ui} = helpers();
  for (const value of [null, {}, {points: [[0, 0], [0.5, 0.5], [1, 1]]}, {points: [[0, 0], [2, 0], [1, 1]]}, {points: [['0', 0], [1, 0], [1, 1]]}, {points: [[0, 0], [1, 0], [1, 1]], line: [[0.5, 0.5], [0.5, 0.5]]}]) {
    assert.throws(() => ui.parseGeometry(JSON.stringify(value)));
  }
});

test('dialog Escape preserves a rejected draft, then cleans up and returns focus once closed', () => {
  let allow = false, closed = 0, cleanup = 0, removed = 0, prevented = 0;
  const {ui, restored} = helpers(() => allow), handlers = {};
  const dialog = {id: 'test', querySelector: () => null, setAttribute() {}, showModal() {}, remove: () => removed++, close() { closed++; handlers.close(); }, addEventListener: (name, handler) => { handlers[name] = handler; }};
  ui.dialog(dialog, {dirty: () => true, cleanup: () => cleanup++});
  handlers.cancel({preventDefault: () => prevented++});
  assert.equal(closed, 0);
  assert.equal(cleanup, 0);
  allow = true;
  handlers.cancel({preventDefault: () => prevented++});
  assert.equal(prevented, 2);
  assert.equal(closed, 1);
  assert.equal(cleanup, 1);
  assert.equal(removed, 1);
  assert.equal(restored(), 1);
});
