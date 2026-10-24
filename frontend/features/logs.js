/* Event Logs page: incidents, operator actions and camera health changes in one searchable list.
 *
 * Registers itself as sidebar page "logs" via window.VisorPages (docs/features/event-logs.md) and loads its
 * own stylesheet, so the shell, index.html and style.css stay untouched:
 *   const page = window.VisorLogs.mount({ api, me, host, onNavigate, formatTime }); page.dispose();
 *
 * Data: GET /api/logs (filters + offset/limit), GET /api/logs/export.csv (same filters, max 5,000 rows),
 * GET /api/incidents/{id} for the read-only detail drawer. Actions on incidents stay in the Control Center.
 */
(() => {
  const PAGE = 50;
  if (!document.getElementById("lg-style")) document.head.append(Object.assign(document.createElement("link"), { id: "lg-style", rel: "stylesheet", href: "/assets/features/logs.css" }));
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const words = (v) => String(v || "").replaceAll("_", " ");
  const RANGES = [["1h", "Last hour", 3600e3], ["24h", "24 hours", 86400e3], ["7d", "7 days", 604800e3], ["30d", "30 days", 2592000e3], ["all", "All time", 0]];
  const KIND_LABEL = { INCIDENT: "Incident", ACTION: "Operator action", HEALTH: "Camera health" };
  const EVENT_TYPES = ["OBSTRUCTION", "PERSON_DOWN", "SMOKE_FIRE", "ZONE_ENTRY", "LINE_CROSSING", "DWELL", "PERSON_DETECTED", "VEHICLE_DETECTED", "SMOKE_DETECTED", "FIRE_DETECTED"];
  const TONE = { NEW: "bad", ACKNOWLEDGED: "good", RESOLVED: "good", FALSE_ALARM: "", ONLINE: "good", OFFLINE: "bad", DISABLED: "", UNKNOWN: "" };
  // Evidence: the boxed evidence view from the event-action feature when it is merged, otherwise the plain snapshot
  const evidence = (i) => window.VisorIncidents?.renderEvidence ? window.VisorIncidents.renderEvidence(i, esc)
    : i.snapshot_available ? `<img class="lg-evidence" src="/api/incidents/${i.id}/evidence" alt="Incident snapshot">` : '<div class="notice">Historical snapshot is unavailable or expired.</div>';
  const blank = () => ({ range: "24h", from: "", to: "", kinds: ["INCIDENT", "ACTION", "HEALTH"], camera: "", eventType: "", status: "", severity: "", source: "", healthStatus: "", search: "" });

  function mount({ api, me, host, onNavigate, formatTime }) {
    let disposed = false, filters = blank(), offset = 0, result = null, loading = false, error = "", cameras = [], detail = null, request = 0;

    // Datetime-local inputs are in the browser's local time; the API receives UTC ISO strings.
    const toIso = (local) => { const t = Date.parse(local); return Number.isFinite(t) ? new Date(t).toISOString() : null; };
    function query() {
      const q = new URLSearchParams({ kinds: filters.kinds.join(",") });
      if (filters.range === "custom") {
        const start = toIso(filters.from), end = toIso(filters.to);
        if (start) q.set("start", start);
        if (end) q.set("end", end);
      } else {
        const ms = RANGES.find((r) => r[0] === filters.range)?.[2];
        if (ms) q.set("start", new Date(Date.now() - ms).toISOString());
      }
      for (const [key, param] of [["camera", "camera_id"], ["eventType", "event_type"], ["status", "status"], ["severity", "severity"], ["source", "source_mode"], ["healthStatus", "health_status"], ["search", "search"]])
        if (filters[key]) q.set(param, filters[key]);
      return q;
    }

    async function load() {
      const mine = ++request;
      loading = true; error = ""; render();
      try {
        const q = query(); q.set("limit", PAGE); q.set("offset", offset);
        const next = await api(`/logs?${q}`);
        if (disposed || mine !== request) return;   // a newer search replaced this one
        result = next;
      } catch (e) { if (mine === request) error = e.message; }
      loading = false;
      if (!disposed) render();
    }

    function readForm() {
      const form = host.querySelector("[data-log-form]");
      if (!form) return;
      const v = Object.fromEntries(new FormData(form));
      filters = { ...filters, from: v.from || "", to: v.to || "", camera: v.camera || "", eventType: v.eventType || "", status: v.status || "", severity: v.severity || "", source: v.source || "", healthStatus: v.healthStatus || "", search: (v.search || "").trim(),
        kinds: [...form.querySelectorAll("[name=kind]:checked")].map((i) => i.value) };
      if (filters.from || filters.to) filters.range = "custom";
      if (!filters.kinds.length) filters.kinds = ["INCIDENT", "ACTION", "HEALTH"];
    }

    function rowDetails(r) {
      if (r.kind === "ACTION") return `${esc(r.actor)}${r.note ? ` · “${esc(r.note)}”` : ""}`;
      if (r.kind === "HEALTH") return esc(r.error_category || (r.to_status === "OFFLINE" ? "Source unavailable" : ""));
      return `${esc(r.severity || "")}${r.simulated ? ' · <span class="status sim">SIMULATED</span>' : ""}`;
    }
    function row(r) {
      const what = r.kind === "HEALTH" ? `${esc(r.from_status || "—")} → ${esc(r.to_status)}` : r.kind === "ACTION" ? `${esc(words(r.event_type))}: ${esc(r.from_status)} → ${esc(r.to_status)}` : `${esc(words(r.event_type))} detected`;
      return `<tr class="lg-${r.kind.toLowerCase()}">
        <td><time>${esc(formatTime(r.at))}</time></td>
        <td><span class="lg-kind lg-kind-${r.kind.toLowerCase()}">${esc(KIND_LABEL[r.kind])}</span></td>
        <td><strong>${esc(r.camera)}</strong><div class="muted small-text">${esc(r.location || "")}</div></td>
        <td>${what}</td>
        <td><span class="status ${TONE[r.status] ?? ""}">${esc(words(r.status))}</span></td>
        <td class="lg-details">${rowDetails(r)}</td>
        <td>${r.incident_id ? `<button class="secondary small" data-detail="${r.incident_id}">Details</button>` : ""}</td></tr>`;
    }

    function detailPanel() {
      if (!detail) return "";
      if (detail.loading) return '<section class="card lg-detail"><div class="notice">Loading incident…</div></section>';
      if (detail.error) return `<section class="card lg-detail"><p class="error">${esc(detail.error)}</p><button class="ghost small" data-close-detail>Close</button></section>`;
      const i = detail.record;
      return `<section class="card lg-detail" aria-label="Incident ${i.id}"><div class="card-header"><div><h2>Incident ${i.id} · ${esc(words(i.event_type))}</h2><p class="muted">${esc(i.camera)} · ${esc(i.location)} · ${i.simulated ? "SIMULATED" : "LIVE"} · first seen ${esc(formatTime(i.first_seen))}</p></div><div class="actions-row"><span class="status ${TONE[i.status] ?? ""}">${esc(words(i.status))}</span><button class="small" data-open-control="${i.id}">Open in Control Center</button><button class="ghost small" data-close-detail>Close</button></div></div>
        <div class="grid two-col"><div>${evidence(i)}</div><div><h3>Operator history</h3>${i.history?.length ? `<ol class="lg-history">${i.history.map((h) => `<li><strong>${esc(h.actor)}</strong> · ${esc(h.from)} → ${esc(h.to)}<div class="muted small-text">${esc(formatTime(h.at))}${h.note ? ` · ${esc(h.note)}` : ""}</div></li>`).join("")}</ol>` : '<p class="muted">No operator action recorded yet.</p>'}<p class="muted small-text">Severity ${esc(i.severity)} · last seen ${esc(formatTime(i.last_seen))}</p></div></div></section>`;
    }

    function render() {
      if (disposed) return;
      const f = filters, items = result?.items || [];
      const select = (name, label, options, value) => `<label class="field">${label}<select name="${name}"><option value="">All</option>${options.map(([v, t]) => `<option value="${esc(v)}" ${String(value) === String(v) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>`;
      host.innerHTML = `<header class="page-head"><div class="page-title-wrap"><div class="eyebrow">Operations</div><h1>Event Logs</h1><p class="muted">Search incidents, operator actions and camera health changes. Newest first.</p></div><div class="actions-row"><button class="secondary" data-export>Export CSV</button></div></header>
        <form class="card lg-filters" data-log-form>
          <div class="lg-ranges" role="group" aria-label="Time range">${RANGES.map(([id, label]) => `<button type="button" class="${f.range === id ? "" : "secondary"} small" data-range="${id}" aria-pressed="${f.range === id}">${label}</button>`).join("")}<span class="muted small-text">or</span>
            <label class="field">From (your time)<input type="datetime-local" name="from" value="${esc(f.from)}"></label><label class="field">To<input type="datetime-local" name="to" value="${esc(f.to)}"></label></div>
          <fieldset class="lg-kinds"><legend class="sr-only">Record types</legend>${Object.entries(KIND_LABEL).map(([k, label]) => `<label class="check-row"><input type="checkbox" name="kind" value="${k}" ${f.kinds.includes(k) ? "checked" : ""}> ${label}</label>`).join("")}</fieldset>
          <div class="lg-fields">
            ${select("camera", "Camera", cameras.map((c) => [c.id, c.name]), f.camera)}
            ${select("eventType", "Event type", EVENT_TYPES.map((t) => [t, words(t)]), f.eventType)}
            ${select("status", "Incident status", ["NEW", "ACKNOWLEDGED", "RESOLVED", "FALSE_ALARM"].map((s) => [s, words(s)]), f.status)}
            ${select("severity", "Severity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => [s, s]), f.severity)}
            ${select("source", "Source", [["LIVE", "Live"], ["SIMULATED", "Simulated"]], f.source)}
            ${select("healthStatus", "Camera state", ["ONLINE", "OFFLINE", "DISABLED", "UNKNOWN"].map((s) => [s, s]), f.healthStatus)}
            <label class="field lg-search">Search<input name="search" maxlength="120" placeholder="Camera, location, event, person or note" value="${esc(f.search)}"></label>
          </div>
          <div class="actions-row"><button type="submit">Search</button><button type="button" class="secondary" data-reset>Reset</button><span class="muted small-text">Incident filters (type, status, severity, source) hide camera-health rows; camera state hides incident rows.</span></div>
        </form>
        ${error ? `<p class="error" role="alert">${esc(error)}</p>` : ""}
        <div class="lg-result-head"><span role="status">${loading ? "Searching…" : result ? (items.length ? `Showing ${offset + 1}–${offset + items.length}${result.has_more ? "" : " (end)"}` : "No records match these filters.") : ""}</span>
          <div class="actions-row"><button class="secondary small" data-page="-1" ${offset === 0 || loading ? "disabled" : ""}>Newer</button><button class="secondary small" data-page="1" ${!result?.has_more || loading ? "disabled" : ""}>Older</button></div></div>
        ${items.length ? `<div class="lg-table-wrap"><table class="lg-table"><thead><tr><th>Time</th><th>Type</th><th>Camera</th><th>What happened</th><th>Status</th><th>Details</th><th><span class="sr-only">Open</span></th></tr></thead><tbody>${items.map(row).join("")}</tbody></table></div>` : ""}
        ${detailPanel()}`;
      bind();
    }

    function bind() {
      const form = host.querySelector("[data-log-form]");
      form.onsubmit = (e) => { e.preventDefault(); readForm(); offset = 0; load(); };
      host.querySelectorAll("[data-range]").forEach((b) => (b.onclick = () => { readForm(); filters.range = b.dataset.range; filters.from = ""; filters.to = ""; offset = 0; load(); }));
      host.querySelector("[data-reset]").onclick = () => { filters = blank(); offset = 0; detail = null; load(); };
      host.querySelectorAll("[data-page]").forEach((b) => (b.onclick = () => { offset = Math.max(0, offset + Number(b.dataset.page) * PAGE); load(); }));
      host.querySelector("[data-export]").onclick = () => {
        readForm();
        const a = document.createElement("a");
        a.href = `/api/logs/export.csv?${query()}`; a.download = "vigilon-logs.csv"; document.body.append(a); a.click(); a.remove();
      };
      host.querySelectorAll("[data-detail]").forEach((b) => (b.onclick = async () => {
        const id = Number(b.dataset.detail);
        detail = { loading: true }; render();
        try { detail = { record: await api(`/incidents/${id}`) }; } catch (e) { detail = { error: e.message }; }
        if (!disposed) { render(); host.querySelector(".lg-detail")?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
      }));
      host.querySelector("[data-close-detail]")?.addEventListener("click", () => { detail = null; render(); });
      host.querySelector("[data-open-control]")?.addEventListener("click", (e) => onNavigate("control", { focus: { incidentId: Number(e.currentTarget.dataset.openControl) } }));
    }

    api("/cameras").then((list) => { if (!disposed) { cameras = list; render(); } }).catch(() => {});
    load();
    return { dispose() { disposed = true; request++; } };
  }

  window.VisorLogs = Object.freeze({ mount });
  (window.VisorPages = window.VisorPages || []).push({ id: "logs", label: "Event Logs", icon: "≡", after: "incidents", mount });
})();
