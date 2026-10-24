(() => {
  function renderEvent(incident, camera, selected, escapeHTML, formatTime) {
    return `<button class="cc-event ${selected?'active':''}" data-event="${incident.id}"><span class="cc-severity ${escapeHTML(incident.severity||'unknown').toLowerCase()}">${escapeHTML(incident.severity||'Severity unknown')}</span><strong>${escapeHTML(incident.event_type.replaceAll('_',' '))}</strong><span>${escapeHTML(camera?.name||`Camera ${incident.camera_id}`)}</span><span>${escapeHTML(incident.status)} · ${escapeHTML(formatTime(incident.first_seen))}${incident.simulated?' · SIMULATED':''}</span></button>`;
  }
  /* Event action panel for the incident selected in the Event list.
     The evidence is shown large and opens the review dialog: the same incident enlarged, with every action
     next to it, so the operator looks first and then chooses what to do (docs/features/event-action.md).
     Action buttons keep the data-action / data-action-note contract that control-center.js already binds. */
  function renderDetail(incident, camera, pending, escapeHTML, formatTime) {
    const e = escapeHTML, cameraName = camera?.name || `Camera ${incident.camera_id}`, open = !TERMINAL.includes(incident.status);
    const title = `<div class="cc-detail-title"><span class="cc-severity ${e(incident.severity||'unknown').toLowerCase()}">${e(incident.severity||'Severity unknown')}</span><h3>${e(words(incident.event_type))}</h3><p>${e(cameraName)} · ${e(formatTime(incident.first_seen))} · ${e(incident.status)}</p>${incident.simulated?'<span class="status sim">SIMULATED</span>':''}</div>`;
    const evidence = incident.snapshot_available
      ? `<button type="button" class="ev-zoom" data-review-open aria-label="Enlarge evidence and choose an action">${evidenceImage(incident, e)}<span class="ev-zoom-hint" aria-hidden="true">⤢ Enlarge</span></button>${evidenceBox(incident) ? '' : '<p class="muted small-text">No detection box recorded for this snapshot.</p>'}`
      : '<div class="notice">Historical snapshot is unavailable or expired. This is separate from camera live status.</div>';
    const review = `<div class="cc-tools ev-review-row"><button type="button" class="${open?'':'secondary '}small" data-review-open>${open?'Enlarge &amp; choose action':'Enlarge evidence'}</button></div>`;
    const zone = `<p class="muted small-text">${e(incident.config_snapshot?.zone?'Rule zone recorded with incident':'No rule/zone context recorded.')}</p>`;
    return `${title}${evidence}${review}${zone}${auditTrail(incident, e, formatTime)}${actionControls(incident, pending, e)}${reviewDialog(incident, cameraName, pending, e, formatTime)}`;
  }
  const TERMINAL = ['RESOLVED','FALSE_ALARM'];
  const words = (value) => String(value || '').replaceAll('_', ' ');
  function auditTrail(incident, e, formatTime) {
    return `<div class="cc-audit">${(incident.history||[]).map(item=>`<div><strong>${e(item.to)}</strong> · ${e(item.actor||'Operator')}<div class="muted small-text">${e(formatTime(item.at))}${item.note?` · ${e(item.note)}`:''}</div></div>`).join('')||'<span class="muted small-text">No operator history.</span>'}</div>`;
  }
  function actionControls(incident, pending, e) {
    if (TERMINAL.includes(incident.status)) return '<p class="notice">This incident is in a terminal state.</p>';
    return `<div class="cc-tools"><button data-action="ACKNOWLEDGED" ${incident.status==='ACKNOWLEDGED'||pending?'disabled':''}>Acknowledge</button><button class="secondary" data-action="RESOLVED" ${pending?'disabled':''}>Resolve</button><button class="danger" data-action="FALSE_ALARM" ${pending?'disabled':''}>False alarm</button></div><label class="field">Operator note <textarea data-action-note maxlength="500" ${pending?'disabled':''}></textarea></label>${pending?'<p class="muted small-text" role="status">Saving operator action…</p>':''}`;
  }
  /* The enlarged review: big evidence on the left, facts and the same actions on the right.
     It lives inside the Control Center host, so the 7 s refresh pauses while it is open (dialog[open] check). */
  function reviewDialog(incident, cameraName, pending, e, formatTime) {
    const meta = incident.metadata || {}, score = Number.isFinite(meta.confidence) ? `${Math.round(meta.confidence * 100)}%` : '—';
    const big = incident.snapshot_available ? `${evidenceImage(incident, e)}${evidenceBox(incident) ? '' : '<p class="muted small-text">No detection box recorded for this snapshot.</p>'}` : '<div class="notice">Historical snapshot is unavailable or expired.</div>';
    return `<dialog class="ev-review" aria-labelledby="ev-review-title-${incident.id}"><div class="ev-review-body">
      <div class="ev-review-media">${big}</div>
      <div class="ev-review-side">
        <div class="ev-review-head"><div><span class="cc-severity ${e(incident.severity||'unknown').toLowerCase()}">${e(incident.severity||'Severity unknown')}</span>${incident.simulated?' <span class="status sim">SIMULATED</span>':''}<h2 id="ev-review-title-${incident.id}">${e(words(incident.event_type))}</h2></div><button type="button" class="ghost small" data-review-close aria-label="Close review">Close</button></div>
        <dl class="ev-facts"><dt>Camera</dt><dd>${e(cameraName)}</dd><dt>First seen</dt><dd>${e(formatTime(incident.first_seen))}</dd><dt>Last seen</dt><dd>${e(formatTime(incident.last_seen))}</dd><dt>Status</dt><dd>${e(words(incident.status))}</dd><dt>Confidence</dt><dd>${e(score)}</dd></dl>
        <h3>Choose an action</h3>${actionControls(incident, pending, e)}
        <h3>Operator history</h3>${auditTrail(incident, e, formatTime)}
      </div></div></dialog>`;
  }
  /* Detected area as normalized [x1,y1,x2,y2] in the snapshot, or null when it cannot be placed honestly.
     Simulated fixtures store normalized geometry; real detections store original-pixel xyxy plus frame_size. */
  function evidenceBox(incident) {
    const meta = incident.metadata || {}, geometry = meta.geometry || {};
    let box = null;
    if (Array.isArray(geometry.normalized) && geometry.normalized.length === 4) box = geometry.normalized.map(Number);
    else if (Array.isArray(geometry.xyxy) && geometry.xyxy.length === 4 && Array.isArray(meta.frame_size) && meta.frame_size[0] > 0 && meta.frame_size[1] > 0) {
      const [w, h] = meta.frame_size.map(Number), [x1, y1, x2, y2] = geometry.xyxy.map(Number);
      box = [x1 / w, y1 / h, x2 / w, y2 / h];
    }
    if (!box || box.some((v) => !Number.isFinite(v))) return null;
    const [x1, y1, x2, y2] = box.map((v) => Math.min(1, Math.max(0, v)));
    return x2 > x1 && y2 > y1 ? [x1, y1, x2, y2] : null;
  }
  /* Snapshot with the detected area drawn on top: percent positions inside an image-sized wrapper (no canvas).
     Only <span>s, so it can sit inside the clickable zoom button. */
  function evidenceImage(incident, escapeHTML) {
    const box = evidenceBox(incident), meta = incident.metadata || {}, inner = meta.metadata || {};
    const score = Number.isFinite(meta.confidence) ? ` ${Math.round(meta.confidence * 100)}%` : '';
    const text = incident.simulated ? `SIMULATED ${words(incident.event_type)}` : `${inner.label || words(incident.event_type)}${score}`;
    const overlay = box ? `<span class="cc-box" style="left:${(box[0] * 100).toFixed(2)}%;top:${(box[1] * 100).toFixed(2)}%;width:${((box[2] - box[0]) * 100).toFixed(2)}%;height:${((box[3] - box[1]) * 100).toFixed(2)}%"><em>${escapeHTML(text)}</em></span>` : '';
    return `<span class="cc-evidence-wrap"><img class="cc-evidence" src="/api/incidents/${incident.id}/evidence" alt="Historical incident snapshot${box ? ' with detected area outlined' : ''}">${overlay}</span>`;
  }
  /* Read-only evidence for other pages (for example the Event Logs detail panel). */
  function renderEvidence(incident, escapeHTML) {
    if (!incident.snapshot_available) return '<div class="notice">Historical snapshot is unavailable or expired. This is separate from camera live status.</div>';
    return `<div class="ev-static">${evidenceImage(incident, escapeHTML)}</div>${evidenceBox(incident) ? '' : '<p class="muted small-text">No detection box recorded for this snapshot.</p>'}`;
  }

  // Review dialog wiring, registered once. Delegated, so it survives every Control Center re-render.
  if (!document.getElementById('ev-style')) document.head.append(Object.assign(document.createElement('link'), {id:'ev-style', rel:'stylesheet', href:'/assets/features/incidents.css'}));
  document.addEventListener('click', (event) => {
    const opener = event.target.closest?.('[data-review-open]');
    if (opener) {
      const dialog = opener.closest('.cc-detail, body')?.querySelector('dialog.ev-review');
      if (dialog && !dialog.open) {
        const typed = document.querySelector('[data-action-note]')?.value || '';
        dialog.querySelectorAll('[data-action-note]').forEach((box) => { box.value = typed; });   // carry a note already typed in the panel
        dialog.showModal();
        dialog.querySelector('[data-action]:not([disabled]), [data-review-close]')?.focus();
      }
      return;
    }
    if (event.target.closest?.('[data-review-close]')) { event.target.closest('dialog')?.close(); return; }
    if (event.target.matches?.('dialog.ev-review')) event.target.close();   // click on the dimmed backdrop
  });
  // The panel and the dialog each have a note box; keep them identical so whichever control-center.js reads is right
  document.addEventListener('input', (event) => {
    if (!event.target.matches?.('[data-action-note]')) return;
    document.querySelectorAll('[data-action-note]').forEach((box) => { if (box !== event.target) box.value = event.target.value; });
  });
  window.VisorIncidents = Object.freeze({renderEvent,renderDetail,renderEvidence,evidenceBox});
})();
