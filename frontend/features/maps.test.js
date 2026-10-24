const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const window = {};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, 'maps.js'), 'utf8'), { window, Object, Number, Math, TypeError });
const maps = window.VisorMaps;
const near = (a, b) => assert.ok(Math.abs(a-b) < 1e-9, `${a} != ${b}`);

for (const [name, image, viewport] of [
  ['landscape letterboxed', [1600, 900], [900, 500]],
  ['portrait letterboxed', [600, 1200], [900, 500]],
]) test(`${name}: image/screen transforms round-trip`, () => {
  const fit = maps.fittedRect(...image, ...viewport);
  const rect = {left: 80, top: 40, width: viewport[0], height: viewport[1]};
  for (const point of [{x:0,y:0},{x:0.25,y:0.75},{x:1,y:1}]) {
    const screen = maps.imageToScreen(point, fit, {zoom:1.8,panX:-23,panY:17});
    const restored = maps.screenToImage(rect.left+screen.x, rect.top+screen.y, rect, fit, {zoom:1.8,panX:-23,panY:17});
    near(restored.x,point.x); near(restored.y,point.y);
  }
});

test('fit updates after viewport resize and rejects letterbox margins', () => {
  const portrait = maps.fittedRect(600,1200,900,500);
  const rect = {left:20,top:30,width:900,height:500};
  assert.equal(maps.screenToImage(rect.left+portrait.left-1,rect.top+portrait.top+10,rect,portrait),null);
  const landscape = maps.fittedRect(1600,900,500,800);
  assert.ok(landscape.left < 1); assert.ok(landscape.top > 0);
  assert.equal(maps.screenToImage(20,30,rect,null),null);
});

test('pointer anchored zoom preserves the image coordinate under the pointer', () => {
  const fit=maps.fittedRect(1600,900,900,500),rect={left:50,top:70,width:900,height:500};
  const before=maps.screenToImage(360,270,rect,fit,{zoom:1,panX:0,panY:0});
  const zoomed=maps.zoomAt({zoom:1,panX:0,panY:0},1.5,360,270,rect,fit);
  const after=maps.screenToImage(360,270,rect,fit,zoomed);
  near(before.x,after.x); near(before.y,after.y);
  assert.equal(maps.clamp(zoomed.zoom*100,100,500),150);
});

test('normalized placements reject invalid values and preserve unrelated cameras', () => {
  const items=[{camera_id:1,x:0.2,y:0.3},{camera_id:2,x:0.6,y:0.7}];
  assert.deepEqual(maps.removeCamera(items,1),[items[1]]);
  assert.equal(maps.normalizedPoint(5,5,{left:10,top:10,width:100,height:100}),null);
  assert.throws(()=>maps.placeCamera(items,1,{x:NaN,y:0.3}),TypeError);
});
