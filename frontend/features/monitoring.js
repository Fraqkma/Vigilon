(() => {
  function renderPreview(camera, selectedCameraId, escapeHTML, formatTime) {
    const unavailable = !camera.enabled || camera.status !== 'ONLINE' || camera.preview_stale;
    return `<article class="cc-preview ${selectedCameraId===camera.id?'selected':''}"><button class="cc-preview-select" data-select-camera="${camera.id}">${escapeHTML(camera.name)} · ${escapeHTML(camera.enabled?camera.status:'DISABLED')} · ${camera.simulated?'SIMULATED':'REAL SOURCE'}</button><div class="cc-preview-frame"><img data-preview="${camera.id}" src="/api/cameras/${camera.id}/preview" alt="${escapeHTML(camera.name)} authenticated live preview">${unavailable?`<div class="cc-stale">${!camera.enabled?'DISABLED SOURCE':camera.status!=='ONLINE'?'OFFLINE SOURCE':'STALE FRAME'} · last frame ${escapeHTML(formatTime(camera.last_frame))}</div>`:''}</div><div class="cc-preview-foot">Frame ${escapeHTML(formatTime(camera.last_frame))} · ${camera.simulated?'SIMULATED':'REAL SOURCE'}</div></article>`;
  }
  window.VisorMonitoring = Object.freeze({renderPreview});
})();
