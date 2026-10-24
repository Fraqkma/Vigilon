(() => {
  // Coordinates are normalized to the decoded image: origin top-left, x right, y down.
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
  function fittedRect(imageWidth, imageHeight, viewportWidth, viewportHeight) {
    if (![imageWidth, imageHeight, viewportWidth, viewportHeight].every(Number.isFinite) ||
        imageWidth <= 0 || imageHeight <= 0 || viewportWidth <= 0 || viewportHeight <= 0) return null;
    const scale = Math.min(viewportWidth / imageWidth, viewportHeight / imageHeight);
    const width = imageWidth * scale, height = imageHeight * scale;
    return Object.freeze({ left: (viewportWidth-width)/2, top: (viewportHeight-height)/2, width, height, scale });
  }
  function imageToScreen(point, fit, view = {}) {
    if (!point || !fit || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
    const zoom = Number.isFinite(view.zoom) ? view.zoom : 1;
    const panX = Number.isFinite(view.panX) ? view.panX : 0;
    const panY = Number.isFinite(view.panY) ? view.panY : 0;
    return Object.freeze({ x: panX + fit.left + point.x * fit.width * zoom, y: panY + fit.top + point.y * fit.height * zoom });
  }
  function screenToImage(clientX, clientY, rect, fit, view = {}, { clampToImage = false } = {}) {
    if (!rect || !fit || !Number.isFinite(clientX) || !Number.isFinite(clientY) || fit.width <= 0 || fit.height <= 0) return null;
    const zoom = Number.isFinite(view.zoom) ? view.zoom : 1;
    if (zoom <= 0) return null;
    const x = (clientX - rect.left - (view.panX || 0) - fit.left) / (fit.width * zoom);
    const y = (clientY - rect.top - (view.panY || 0) - fit.top) / (fit.height * zoom);
    if (!clampToImage && (x < 0 || x > 1 || y < 0 || y > 1)) return null;
    return Object.freeze({ x: clamp(x, 0, 1), y: clamp(y, 0, 1) });
  }
  function zoomAt(view, factor, clientX, clientY, rect, fit) {
    const oldZoom = clamp(view.zoom || 1, 1, 5), nextZoom = clamp(oldZoom * factor, 1, 5);
    if (nextZoom === oldZoom || !fit || !rect) return Object.freeze({ ...view, zoom: nextZoom });
    const imagePoint = screenToImage(clientX, clientY, rect, fit, view, { clampToImage: true });
    const localX = clientX - rect.left, localY = clientY - rect.top;
    return Object.freeze({ zoom: nextZoom, panX: localX - fit.left - imagePoint.x * fit.width * nextZoom,
      panY: localY - fit.top - imagePoint.y * fit.height * nextZoom });
  }
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
  window.VisorMaps=Object.freeze({normalizedPoint,placeCamera,removeCamera,fittedRect,imageToScreen,screenToImage,zoomAt,clamp});
})();
