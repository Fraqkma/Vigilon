(() => {
  function normalizedPoint(clientX, clientY, rect) {
    if (!rect || !Number.isFinite(clientX) || !Number.isFinite(clientY) || rect.width <= 0 || rect.height <= 0) return null;
    const x=(clientX-rect.left)/rect.width, y=(clientY-rect.top)/rect.height;
    return x<0||x>1||y<0||y>1?null:Object.freeze({x,y});
  }
  function placeCamera(placements, cameraId, point) {
    if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y) || point.x<0 || point.x>1 || point.y<0 || point.y>1) throw new TypeError('Camera point must use normalized coordinates in [0,1].');
    return [...placements.filter(item=>item.camera_id!==cameraId),{camera_id:cameraId,x:point.x,y:point.y}];
  }
  function removeCamera(placements, cameraId) { return placements.filter(item=>item.camera_id!==cameraId); }
  window.VisorMaps=Object.freeze({normalizedPoint,placeCamera,removeCamera});
})();
