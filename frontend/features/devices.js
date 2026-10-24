(() => {
  function renderLocation(camera, plan, isAdmin, contextOpen, expanded, escapeHTML, contextForm) {
    return `<section class="cc-panel cc-context ${expanded==='context'?'is-expanded':''}"><div class="cc-panel-head"><div><h2>Location context</h2><p class="muted small-text">Configured location and responsible contact.</p></div><div class="cc-tools"><button class="secondary small" data-expand="context">${expanded==='context'?'Restore':'Expand'}</button><button class="secondary small" data-hide-context>Hide column</button></div></div>${camera?`<div class="cc-device-name">${escapeHTML(camera.name)}</div><div class="cc-definition"><span>Camera location</span><strong>${escapeHTML(camera.location||'Unknown')}</strong><span>Plan area</span><strong>${escapeHTML(plan?.location_label||'Not set')}</strong><span>Responsible contact</span><strong>${escapeHTML(camera.responsible_contact||'Not configured')}</strong></div>${camera.response_notes?`<p class="notice">${escapeHTML(camera.response_notes)}</p>`:''}<div class="cc-tools"><a href="#" data-existing="live" data-camera-target="${camera.id}">Settings, rules &amp; zones</a><a href="#" data-existing="analysis">Video analysis</a><a href="#" data-existing="incidents">Incident history</a>${isAdmin?'<button class="secondary small" data-context>Edit context</button>':''}</div>${contextOpen?contextForm(camera):''}`:'<div class="empty">Select a camera to see configured location context.</div>'}</section>`;
  }
  function renderDevice(camera, expanded, escapeHTML, formatTime, isAdmin = false) {
    const details = camera ? `${photoBlock(camera.id, camera.name, photoVersion(camera), isAdmin, escapeHTML)}<div class="cc-device-name">${escapeHTML(camera.manufacturer||'Manufacturer unknown')} ${escapeHTML(camera.model||'')}</div><div class="cc-definition"><span>Health</span><strong>${escapeHTML(camera.enabled?camera.status:'DISABLED')}</strong><span>Frame</span><strong>${escapeHTML(camera.preview_stale?'STALE':'Freshness reported')}</strong><span>Last frame</span><strong>${escapeHTML(formatTime(camera.last_frame))}</strong></div>${camera.specifications?`<p class="muted small-text">${escapeHTML(camera.specifications)}</p>`:'<p class="muted small-text">No device specifications recorded.</p>'}` : '<div class="empty">Select a camera to see device details.</div>';
    return `<section class="cc-panel cc-device ${expanded==='device'?'is-expanded':''}"><div class="cc-panel-head"><div><h2>Device details</h2><p class="muted small-text">Optional photo, model and specifications.</p></div><button class="secondary small" data-expand="device">${expanded==='device'?'Restore':'Expand'}</button></div>${details}</section>`;
  }
  function renderContextForm(camera, escapeHTML) {
    return `<form data-context-form class="cc-context-form"><label class="field">Manufacturer<input name="manufacturer" maxlength="120" value="${escapeHTML(camera.manufacturer||'')}"></label><label class="field">Model<input name="model" maxlength="120" value="${escapeHTML(camera.model||'')}"></label><label class="field">Specifications<input name="specifications" maxlength="500" value="${escapeHTML(camera.specifications||'')}"></label><label class="field">Responsible contact<input name="responsible_contact" maxlength="200" value="${escapeHTML(camera.responsible_contact||'')}"></label><label class="field">Response notes<textarea name="response_notes" maxlength="1000">${escapeHTML(camera.response_notes||'')}</textarea></label><button>Save context</button><button type="button" class="secondary" data-context-cancel>Cancel</button></form>`;
  }
  // ---- Device photo (docs/features/device-image.md) ----
  // After an upload or removal the server list catches up on the next Control Center refresh; until then
  // this override keeps the panel showing what the admin just did.
  const photoOverride = new Map();   // camera id -> device_image_version | null
  function photoVersion(camera) {
    if (!photoOverride.has(camera.id)) return camera.device_image_version ?? null;
    if (photoOverride.get(camera.id) === (camera.device_image_version ?? null)) { photoOverride.delete(camera.id); return camera.device_image_version ?? null; }
    return photoOverride.get(camera.id);
  }
  function photoBlock(id, name, version, isAdmin, escapeHTML) {
    const url = `/api/cameras/${id}/device-image?v=${version}`;
    const picture = version
      ? `<a class="dv-photo-link" href="${url}" target="_blank" rel="noopener" title="Open full size"><img class="dv-photo-img" src="${url}" alt="Device photo of ${escapeHTML(name)}" loading="lazy"></a>`
      : `<div class="dv-photo-empty">No device photo${isAdmin ? ' yet' : ''}</div>`;
    const tools = isAdmin
      ? `<div class="dv-photo-tools"><label class="button secondary small dv-photo-pick">${version ? 'Replace photo' : 'Add photo'}<input type="file" accept="image/png,image/jpeg" class="sr-only" data-device-photo="${id}"></label>${version ? `<button type="button" class="ghost small" data-device-photo-remove="${id}">Remove</button>` : ''}<span class="muted small-text" role="status" data-device-photo-status></span></div>`
      : '';
    return `<div class="dv-photo" data-device-photo-block="${id}" data-camera-name="${escapeHTML(name)}">${picture}${tools}</div>`;
  }
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  function redraw(block, id, version, message) {
    photoOverride.set(id, version);
    block.outerHTML = photoBlock(id, block.dataset.cameraName || '', version, true, esc);
    const status = document.querySelector(`[data-device-photo-block="${id}"] [data-device-photo-status]`);
    if (status && message) status.textContent = message;
  }
  async function send(method, id, body, type) {
    const response = await fetch(`/api/cameras/${id}/device-image`, {method, body, credentials: 'same-origin', headers: type ? {'Content-Type': type} : {}});
    if (!response.ok) { let detail = ''; try { detail = (await response.json()).detail; } catch {} throw Error(detail || `Request failed (${response.status})`); }
    return response.status === 204 ? null : response.json();
  }
  // Delegated once: the Control Center re-renders this panel on every refresh
  if (!document.getElementById('dv-style')) document.head.append(Object.assign(document.createElement('link'), {id: 'dv-style', rel: 'stylesheet', href: '/assets/features/devices.css'}));
  document.addEventListener('change', async (event) => {
    const input = event.target.closest?.('[data-device-photo]');
    if (!input) return;
    const id = Number(input.dataset.devicePhoto), file = input.files?.[0], block = input.closest('[data-device-photo-block]');
    const status = block?.querySelector('[data-device-photo-status]');
    if (!file || !block) return;
    if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 8 * 1024 * 1024) { if (status) status.textContent = 'Choose a PNG or JPEG no larger than 8 MiB.'; input.value = ''; return; }
    if (status) status.textContent = 'Uploading…';
    try { const result = await send('POST', id, file, file.type); redraw(block, id, result.device_image_version, 'Photo saved.'); }
    catch (error) { if (status) status.textContent = error.message; input.value = ''; }
  });
  document.addEventListener('click', async (event) => {
    const button = event.target.closest?.('[data-device-photo-remove]');
    if (!button) return;
    const id = Number(button.dataset.devicePhotoRemove), block = button.closest('[data-device-photo-block]');
    if (!block || !confirm('Remove this device photo?')) return;
    button.disabled = true;
    try { await send('DELETE', id); redraw(block, id, null, 'Photo removed.'); }
    catch (error) { button.disabled = false; const status = block.querySelector('[data-device-photo-status]'); if (status) status.textContent = error.message; }
  });
  window.VisorDevices = Object.freeze({renderLocation,renderDevice,renderContextForm});
})();
