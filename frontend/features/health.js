/* Camera Health page: current state, frame age, processed FPS, uptime, 24 h timeline and state history.
 *
 * Registers itself as sidebar page "health" via window.VisorPages (docs/features/camera-health.md) and
 * loads its own stylesheet, so the shell, index.html and style.css stay untouched:
 *   const page = window.VisorHealth.mount({ api, me, host, onNavigate, formatTime }); page.dispose();
 *
 * Data: GET /api/camera-health?hours=24|168 every 5 s; GET /api/camera-health/{id}/events for history.
 * "Processed FPS" is measured here from the change in the worker's processed-frame counter between two
 * polls, so it appears after the second poll. Enable/disable reuses PATCH /api/cameras/{id} (ADMIN).
 */
(() => {
  const POLL_MS = 5000;
  // Own stylesheet, loaded once (same cache rules as every /assets file)
  if (!document.getElementById("hl-style")) document.head.append(Object.assign(document.createElement("link"), { id: "hl-style", rel: "stylesheet", href: "/assets/features/health.css" }));
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const TONE = { ONLINE: "good", STALE: "warn", CONNECTING: "warn", OFFLINE: "bad", DISABLED: "", UNKNOWN: "" };
  const STATE_HELP = {
    ONLINE: "Fresh frames are arriving", STALE: "Connected, but no fresh frame for over 8 s", CONNECTING: "Worker is opening the source",
    OFFLINE: "Source unreachable or not decoding", DISABLED: "Monitoring switched off", UNKNOWN: "Worker not running — last known state only",
  };

  function mount({ api, me, host, onNavigate, formatTime }) {
    let disposed = false, timer = null, hours = 24, data = null, error = "", selected = null, history = null, busy = null;
    const samples = new Map();   // camera id -> {processed, t}
    const fps = new Map();       // camera id -> measured processed frames per second

    const age = (s) => (s == null ? "—" : s < 60 ? `${s.toFixed(1)} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${Math.round(s / 3600)} h`);
    const pct = (v) => (v == null ? "No history yet" : `${v.toFixed(1)}%`);

    async function load() {
      try {
        const next = await api(`/camera-health?hours=${hours}`);
        if (disposed) return;
        const t = Date.parse(next.generated_at) || Date.now();
        for (const c of next.cameras) {
          const prev = samples.get(c.id);
          if (prev && t > prev.t && c.processed >= prev.processed) fps.set(c.id, (c.processed - prev.processed) / ((t - prev.t) / 1000));
          samples.set(c.id, { processed: c.processed, t });
        }
        data = next; error = "";
        if (selected) history = await api(`/camera-health/${selected}/events?limit=50`).catch(() => history);
      } catch (e) { error = e.message; }
      if (!disposed) render();
    }

    function timeline(camera) {
      const start = Date.parse(data.generated_at) - hours * 3600 * 1000, span = hours * 3600 * 1000;
      const parts = camera.timeline.map((seg) => {
        const a = Math.max(0, (Date.parse(seg.start) - start) / span), b = Math.min(1, (Date.parse(seg.end) - start) / span);
        if (!(b > a)) return "";
        return `<span class="hl-seg hl-${esc(seg.status.toLowerCase())}" style="left:${(a * 100).toFixed(3)}%;width:${((b - a) * 100).toFixed(3)}%" title="${esc(seg.status)} · ${esc(formatTime(seg.start))} – ${esc(formatTime(seg.end))}"></span>`;
      }).join("");
      // History shorter than the window is labelled, so a mostly-unknown bar does not look like an outage
      const since = Date.parse(camera.history_since || "");
      const caption = !camera.history_since ? "No state recorded in this window" : since - start > 60000 ? `Recording since ${formatTime(camera.history_since)}` : "";
      return `<div class="hl-timeline" role="img" aria-label="${esc(camera.name)} state over the last ${hours} hours">${parts}</div>${caption ? `<div class="muted small-text hl-caption">${esc(caption)}</div>` : ""}`;
    }

    function summary(cameras) {
      const count = (s) => cameras.filter((c) => c.derived_state === s).length;
      const withHistory = cameras.filter((c) => c.uptime_pct != null && c.enabled);
      const avg = withHistory.length ? withHistory.reduce((n, c) => n + c.uptime_pct, 0) / withHistory.length : null;
      return `<div class="hl-summary">
        <article class="card"><div class="metric-label">Online</div><div class="metric">${count("ONLINE")}</div><div class="metric-note">of ${cameras.length} sources</div></article>
        <article class="card"><div class="metric-label">Stale / connecting</div><div class="metric">${count("STALE") + count("CONNECTING")}</div><div class="metric-note">Connected without fresh frames</div></article>
        <article class="card"><div class="metric-label">Offline</div><div class="metric">${count("OFFLINE")}</div><div class="metric-note">${count("DISABLED")} disabled · ${count("UNKNOWN")} unknown</div></article>
        <article class="card"><div class="metric-label">Average uptime</div><div class="metric">${avg == null ? "—" : `${avg.toFixed(1)}%`}</div><div class="metric-note">Last ${hours === 24 ? "24 hours" : "7 days"}, recorded time only</div></article>
      </div>`;
    }

    function row(c) {
      const measured = fps.get(c.id);
      return `<tr class="${selected === c.id ? "is-selected" : ""}">
        <td><strong>${esc(c.name)}</strong><div class="muted small-text">${esc(c.location || "No location")} · ${esc(c.source_type)}${c.simulated ? " · SIMULATED" : ""}</div></td>
        <td><span class="status ${TONE[c.derived_state] ?? ""}" title="${esc(STATE_HELP[c.derived_state] || "")}">${esc(c.derived_state)}</span>${c.derived_state === "OFFLINE" && c.error_category ? `<div class="muted small-text">${esc(c.error_category)}</div>` : ""}</td>
        <td><div>${c.frame_age_seconds == null ? "No frame yet" : `${esc(age(c.frame_age_seconds))} old`}</div><div class="muted small-text">${measured == null ? "fps: measuring…" : `${measured.toFixed(1)} fps`} · target ${esc(c.processing_fps)}</div></td>
        <td><div class="hl-uptime"><span>${esc(pct(c.uptime_pct))}</span>${c.uptime_pct == null ? "" : `<span class="hl-bar"><i style="width:${Math.max(0, Math.min(100, c.uptime_pct))}%"></i></span>`}</div></td>
        <td class="hl-timeline-cell">${timeline(c)}</td>
        <td><div>${esc(c.offline_events)} offline</div><div class="muted small-text">${esc(c.reconnects)} reconnects · ${esc(c.dropped)} dropped</div></td>
        <td><div class="hl-actions">
          <button class="secondary small" data-history="${c.id}" data-focus-key="history-${c.id}">${selected === c.id ? "Hide history" : "History"}</button>
          <button class="ghost small" data-settings="${c.id}" data-focus-key="settings-${c.id}">Settings</button>
          ${me.role === "ADMIN" ? `<button class="${c.enabled ? "ghost hl-disable" : ""} small" data-toggle="${c.id}" data-focus-key="toggle-${c.id}" ${busy === c.id ? "disabled" : ""}>${c.enabled ? "Disable" : "Enable"}</button>` : ""}
        </div></td></tr>`;
    }

    function historyPanel() {
      const camera = data?.cameras.find((c) => c.id === selected);
      if (!camera) return "";
      return `<section class="card hl-history" aria-label="State history for ${esc(camera.name)}"><div class="card-header"><div><h2>State history · ${esc(camera.name)}</h2><p class="muted small-text">Recorded by the worker when the camera changes state. Most recent first.</p></div><button class="ghost small" data-history="${camera.id}">Close</button></div>
        ${history == null ? '<div class="notice">Loading history…</div>' : history.length ? `<ol class="hl-events">${history.map((e) => `<li><span class="status ${TONE[e.to_status] ?? ""}">${esc(e.to_status)}</span><span>${esc(e.from_status || "—")} → ${esc(e.to_status)}${e.error_category ? ` · ${esc(e.error_category)}` : ""}</span><time class="muted small-text">${esc(formatTime(e.at))}</time></li>`).join("")}</ol>` : '<div class="empty">No recorded state changes yet. History starts once the worker runs with this version.</div>'}</section>`;
    }

    function render() {
      if (disposed) return;
      const focusKey = document.activeElement?.dataset?.focusKey, scroll = host.querySelector(".hl-table-wrap")?.scrollLeft || 0;
      const head = `<header class="page-head"><div class="page-title-wrap"><div class="eyebrow">Operations</div><h1>Camera Health</h1><p class="muted">Connection, frame freshness and uptime for every configured source.</p></div><div class="actions-row"><label class="field hl-window">Window<select data-hours><option value="24" ${hours === 24 ? "selected" : ""}>Last 24 hours</option><option value="168" ${hours === 168 ? "selected" : ""}>Last 7 days</option></select></label><button class="secondary" data-refresh>Refresh</button></div></header>`;
      if (!data) { host.innerHTML = `${head}${error ? `<p class="error" role="alert">${esc(error)}</p><button data-refresh>Retry</button>` : '<div class="notice">Loading camera health…</div>'}`; bind(); return; }
      const workerOff = data.worker.status !== "ONLINE";
      host.innerHTML = `${head}
        ${workerOff ? `<div class="notice warn" role="status"><strong>Ingestion worker is not running.</strong> ${data.worker.last_seen ? `Last heartbeat ${esc(formatTime(data.worker.last_seen))}.` : "No heartbeat recorded."} Camera states below are last known values, shown as UNKNOWN.</div>` : ""}
        ${error ? `<p class="error" role="alert">Refresh failed: ${esc(error)} — showing the previous result.</p>` : ""}
        ${summary(data.cameras)}
        ${data.cameras.length ? `<div class="hl-table-wrap"><table class="hl-table"><thead><tr><th>Camera</th><th>State</th><th>Frames</th><th>Uptime</th><th>Last ${hours === 24 ? "24 h" : "7 days"}</th><th>Reliability</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${data.cameras.map(row).join("")}</tbody></table></div>
          <div class="hl-legend" aria-label="Timeline legend"><span><i class="hl-online"></i>Online</span><span><i class="hl-offline"></i>Offline</span><span><i class="hl-disabled"></i>Disabled</span><span><i class="hl-unknown"></i>Unknown / no record</span><span class="muted small-text">Updated ${esc(formatTime(data.generated_at))}</span></div>` : '<div class="empty">No camera sources configured yet. Add one in Live Monitoring.</div>'}
        ${historyPanel()}`;
      const wrap = host.querySelector(".hl-table-wrap"); if (wrap) wrap.scrollLeft = scroll;
      bind();
      if (focusKey) host.querySelector(`[data-focus-key="${focusKey}"]`)?.focus();
    }

    function bind() {
      host.querySelector("[data-hours]")?.addEventListener("change", (e) => { hours = Number(e.target.value); samples.clear(); fps.clear(); data = null; render(); load(); });
      host.querySelectorAll("[data-refresh]").forEach((b) => (b.onclick = load));
      host.querySelectorAll("[data-history]").forEach((b) => (b.onclick = async () => {
        const id = Number(b.dataset.history);
        if (selected === id) { selected = null; history = null; render(); return; }
        selected = id; history = null; render();
        try { history = await api(`/camera-health/${id}/events?limit=50`); } catch (e) { history = []; error = e.message; }
        if (!disposed) render();
      }));
      host.querySelectorAll("[data-settings]").forEach((b) => (b.onclick = () => onNavigate("live", { cameraId: Number(b.dataset.settings) })));
      host.querySelectorAll("[data-toggle]").forEach((b) => (b.onclick = async () => {
        const c = data.cameras.find((x) => x.id === Number(b.dataset.toggle));
        if (!c || (c.enabled && !confirm(`Stop monitoring "${c.name}"? Its preview and detections stop until it is enabled again.`))) return;
        busy = c.id; render();
        try {
          // Same body the camera form sends; a blank connection keeps the stored source/credentials
          await api(`/cameras/${c.id}`, { method: "PATCH", body: JSON.stringify({ name: c.name, location: c.location || "", source_type: c.source_type, connection: "", clear_connection: false, enabled: !c.enabled, scenario: c.scenario || "normal", processing_fps: c.processing_fps, resize_limit: c.resize_limit, timeout_seconds: c.timeout_seconds, reconnect_min_seconds: c.reconnect_min_seconds, reconnect_max_seconds: c.reconnect_max_seconds }) });
        } catch (e) { error = e.message; }
        busy = null; await load();
      }));
    }

    render();
    load();
    timer = setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
    return { dispose() { disposed = true; if (timer) clearInterval(timer); timer = null; } };
  }

  window.VisorHealth = Object.freeze({ mount });
  (window.VisorPages = window.VisorPages || []).push({ id: "health", label: "Camera Health", icon: "◎", after: "incidents", mount });
})();
