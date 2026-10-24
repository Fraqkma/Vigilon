/* Visor alert center: bell with unread count, popup toasts, optional sound and desktop notifications.
 *
 * Registers itself as session service "alerts" via window.VisorServices (docs/features/alerts.md); the shell
 * starts it after sign-in and stops it on logout or session expiry. It loads its own stylesheet.
 *   const alerts = window.VisorAlerts.start({ api, me, onNavigate })  // once per signed-in session
 *   alerts.attach(topbarSlot)    // appends its own bell element; other services share the same slot
 *   alerts.stop()                // stops polling and removes all alert UI
 *
 * Data: GET /api/alerts/feed?after_notification=&after_health= every 4 s (only newer rows are returned).
 * The first poll only remembers the newest ids, so signing in never replays a flood of old popups.
 * Incident popups: every new incident. Camera popups: a camera going OFFLINE, and recovering from OFFLINE.
 * Toasts and the panel live in one container under <body>, so page navigation does not remove them.
 */
(() => {
  const POLL_MS = 4000;
  if (!document.getElementById("al-style")) document.head.append(Object.assign(document.createElement("link"), { id: "al-style", rel: "stylesheet", href: "/assets/features/alerts.css" }));
  const MAX_TOASTS = 4;
  const PREF_KEY = "visor.alerts.prefs";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const words = (v) => String(v || "").replaceAll("_", " ");
  const clock = (v) => { try { return new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); } catch { return ""; } };
  const BELL = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6V11a7 7 0 0 0-5.5-6.84V3a1.5 1.5 0 0 0-3 0v1.16A7 7 0 0 0 5 11v5l-2 2v1h18v-1l-2-2Z"/></svg>';

  let api = null, onNavigate = null, timer = null, stopped = true, inFlight = false;
  let cursor = null;          // newest ids already seen {notification, health}
  let items = [];             // newest first, for the panel (max 30)
  let unread = 0, panelOpen = false, bell = null, root = null, audio = null;   // bell: our own element inside #topbarSlot
  let prefs = loadPrefs();

  function loadPrefs() {
    try { return { sound: true, desktop: false, ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") }; }
    catch { return { sound: true, desktop: false }; }
  }
  function savePrefs() { try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch { /* storage may be blocked */ } }

  // ---------- sound: browsers only allow audio after a user gesture, so create it on the first click ----------
  function unlockAudio() {
    if (audio) return;
    try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch { audio = null; }
  }
  function beep(urgent) {
    if (!prefs.sound || !audio) return;
    try {
      const tones = urgent ? [880, 660, 880] : [520];
      tones.forEach((hz, i) => {
        const osc = audio.createOscillator(), gain = audio.createGain(), t = audio.currentTime + i * 0.18;
        osc.frequency.value = hz; osc.type = "sine";
        gain.gain.setValueAtTime(0.0001, t); gain.gain.exponentialRampToValueAtTime(0.18, t + 0.02); gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.15);
        osc.connect(gain).connect(audio.destination); osc.start(t); osc.stop(t + 0.16);
      });
    } catch { /* audio is best effort */ }
  }

  // ---------- desktop notifications (only when the tab is in the background) ----------
  const desktopSupported = () => "Notification" in window;
  function desktopNotify(item) {
    if (!prefs.desktop || !desktopSupported() || Notification.permission !== "granted" || !document.hidden) return;
    try {
      const n = new Notification(item.type === "incident" ? `${words(item.event_type)} · ${item.camera}` : `Camera ${item.to === "OFFLINE" ? "offline" : "back online"} · ${item.camera}`,
        { body: item.type === "incident" ? `${item.severity || ""} ${item.simulated ? "· SIMULATED" : ""}`.trim() : item.category || "", tag: `vigilon-${item.key}` });
      n.onclick = () => { window.focus(); open(item); n.close(); };
    } catch { /* some browsers only allow notifications from a service worker */ }
  }

  // ---------- polling ----------
  function toItems(feed) {
    const list = [];
    for (const n of feed.notifications) {
      if (!n.incident) continue;
      list.push({ type: "incident", key: `n${n.id}`, id: n.id, read: n.read, at: n.created_at, incidentId: n.incident_id, ...n.incident });
    }
    for (const h of feed.health) {
      // Worker restarts (UNKNOWN -> ONLINE) and admin disables are history, not alerts
      if (h.to_status !== "OFFLINE" && !(h.to_status === "ONLINE" && h.from_status === "OFFLINE")) continue;
      list.push({ type: "health", key: `h${h.id}`, id: h.id, read: true, at: h.at, camera: h.camera, cameraId: h.camera_id, to: h.to_status, from: h.from_status, category: h.error_category });
    }
    return list.sort((a, b) => String(b.at).localeCompare(String(a.at)));
  }
  async function poll() {
    if (stopped || inFlight) return;
    if (document.hidden && !prefs.desktop) return;           // nothing to show while hidden
    inFlight = true;
    try {
      const query = cursor ? `?after_notification=${cursor.notification}&after_health=${cursor.health}&limit=20` : "?limit=20";
      const feed = await api(`/alerts/feed${query}`);
      if (stopped) return;
      const fresh = toItems(feed), primed = cursor !== null;
      cursor = feed.cursor; unread = feed.unread;
      items = [...fresh, ...items.filter((old) => !fresh.some((f) => f.key === old.key))].slice(0, 30);
      if (primed) [...fresh].reverse().forEach(announce);     // oldest first so the newest toast ends on top
      renderBell();
      if (panelOpen) renderPanel();
    } catch { /* keep polling; the shell handles an expired session */ }
    finally { inFlight = false; }
  }

  // ---------- toasts ----------
  function announce(item) {
    const box = root?.querySelector(".al-toasts");
    if (!box) return;
    const toast = document.createElement("div");
    const incident = item.type === "incident";
    toast.className = `al-toast ${incident ? `al-sev-${String(item.severity || "unknown").toLowerCase()}` : item.to === "OFFLINE" ? "al-health-bad" : "al-health-good"}`;
    toast.setAttribute("role", incident ? "alert" : "status");
    toast.innerHTML = incident
      ? `<div class="al-toast-head"><span class="al-chip">${esc(item.severity || "EVENT")}</span><strong>${esc(words(item.event_type))}</strong>${item.simulated ? '<span class="status sim">SIMULATED</span>' : ""}</div>
         <div class="al-toast-meta">${esc(item.camera)} · ${esc(clock(item.at))}</div>
         <div class="al-toast-actions"><button class="small" data-open>View event</button><button class="ghost small" data-dismiss>Dismiss</button></div>`
      : `<div class="al-toast-head"><span class="al-chip">${item.to === "OFFLINE" ? "CAMERA OFFLINE" : "RECOVERED"}</span><strong>${esc(item.camera)}</strong></div>
         <div class="al-toast-meta">${esc(item.to === "OFFLINE" ? item.category || "Source unavailable" : "Camera is sending frames again")} · ${esc(clock(item.at))}</div>
         <div class="al-toast-actions"><button class="secondary small" data-open>Camera health</button><button class="ghost small" data-dismiss>Dismiss</button></div>`;
    const remove = () => toast.remove();
    toast.querySelector("[data-open]").onclick = () => { remove(); open(item); };
    toast.querySelector("[data-dismiss]").onclick = remove;
    box.prepend(toast);
    [...box.children].slice(MAX_TOASTS).forEach((old) => old.remove());
    setTimeout(remove, incident ? 25000 : 10000);
    beep(incident);
    desktopNotify(item);
  }

  // ---------- navigation + read state ----------
  async function markRead(body) {
    try { unread = (await api("/alerts/read", { method: "POST", body: JSON.stringify(body) })).unread; } catch { /* stays unread */ }
  }
  function open(item) {
    closePanel();
    if (item.type === "incident") {
      if (!item.read) { item.read = true; markRead({ notification_ids: [item.id] }).then(renderBell); }
      onNavigate?.("control", { focus: { incidentId: item.incidentId } });
    } else onNavigate?.("health");
  }

  // ---------- bell + panel ----------
  function renderBell() {
    if (!bell || !bell.isConnected) return;
    const count = unread > 99 ? "99+" : String(unread);
    bell.innerHTML = `<button class="al-bell ${unread ? "has-unread" : ""}" data-al-bell aria-haspopup="dialog" aria-expanded="${panelOpen}" aria-label="Alerts, ${unread} unread">${BELL}<span>Alerts</span>${unread ? `<b class="al-count">${count}</b>` : ""}</button>`;
    bell.querySelector("[data-al-bell]").onclick = (e) => { e.stopPropagation(); panelOpen ? closePanel() : openPanel(); };
  }
  function openPanel() { panelOpen = true; renderPanel(); renderBell(); }
  function closePanel() { panelOpen = false; root?.querySelector(".al-panel")?.remove(); renderBell(); }
  function desktopLabel() {
    if (!desktopSupported()) return '<span class="muted small-text">Desktop alerts not supported in this browser</span>';
    if (Notification.permission === "denied") return '<span class="muted small-text">Desktop alerts blocked in browser settings</span>';
    return `<label class="check-row"><input type="checkbox" data-al-desktop ${prefs.desktop && Notification.permission === "granted" ? "checked" : ""}> Desktop alerts when this tab is in the background</label>`;
  }
  function renderPanel() {
    root?.querySelector(".al-panel")?.remove();
    if (!panelOpen || !root) return;
    const panel = document.createElement("section");
    panel.className = "al-panel"; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Alerts");
    panel.innerHTML = `<div class="al-panel-head"><div><h2>Alerts</h2><p class="muted small-text">${unread} unread incident alerts</p></div><div class="al-panel-tools"><button class="secondary small" data-al-readall ${unread ? "" : "disabled"}>Mark all read</button><button class="ghost small" data-al-close aria-label="Close alerts">Close</button></div></div>
      <div class="al-prefs"><label class="check-row"><input type="checkbox" data-al-sound ${prefs.sound ? "checked" : ""}> Sound for new incidents</label>${desktopLabel()}</div>
      <div class="al-list">${items.length ? items.map((it) => `<button class="al-item ${it.read ? "" : "unread"}" data-al-item="${esc(it.key)}">
          <span class="al-chip ${it.type === "health" ? (it.to === "OFFLINE" ? "bad" : "good") : ""}">${esc(it.type === "incident" ? it.severity || "EVENT" : it.to === "OFFLINE" ? "OFFLINE" : "ONLINE")}</span>
          <span class="al-item-text"><strong>${esc(it.type === "incident" ? words(it.event_type) : it.camera)}</strong><span class="muted small-text">${esc(it.type === "incident" ? it.camera : it.to === "OFFLINE" ? it.category || "Source unavailable" : "Recovered")} · ${esc(clock(it.at))}${it.simulated ? " · SIMULATED" : ""}</span></span>
          ${it.read ? "" : '<span class="al-dot" aria-label="unread"></span>'}</button>`).join("") : '<div class="empty">No alerts since you signed in. New incidents and camera outages appear here.</div>'}</div>`;
    root.append(panel);
    panel.querySelector("[data-al-close]").onclick = closePanel;
    panel.querySelector("[data-al-readall]").onclick = async () => { items.forEach((it) => { it.read = true; }); await markRead({ all: true }); renderPanel(); renderBell(); };
    panel.querySelector("[data-al-sound]").onchange = (e) => { prefs.sound = e.target.checked; savePrefs(); unlockAudio(); };
    panel.querySelector("[data-al-desktop]")?.addEventListener("change", async (e) => {
      if (e.target.checked && Notification.permission !== "granted") e.target.checked = (await Notification.requestPermission()) === "granted";
      prefs.desktop = e.target.checked; savePrefs(); renderPanel();
    });
    panel.querySelectorAll("[data-al-item]").forEach((b) => (b.onclick = () => { const it = items.find((x) => x.key === b.dataset.alItem); if (it) open(it); }));
    panel.addEventListener("click", (e) => e.stopPropagation());
  }
  const onDocumentClick = () => { unlockAudio(); if (panelOpen) closePanel(); };
  const onKey = (e) => { if (e.key === "Escape" && panelOpen) closePanel(); };
  const onVisible = () => { if (!document.hidden) poll(); };

  // ---------- lifecycle ----------
  function start(deps) {
    stop();
    api = deps.api; onNavigate = deps.onNavigate; stopped = false; cursor = null; items = []; unread = 0; panelOpen = false;
    root = document.createElement("div");
    root.className = "al-root";
    root.innerHTML = '<div class="al-toasts" aria-label="New alerts"></div>';
    document.body.append(root);
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", onVisible);
    poll();
    timer = setInterval(poll, POLL_MS);
    return { attach, stop };
  }
  // The shell re-creates the topbar on every render, so the bell is re-appended each time (never slot.innerHTML)
  function attach(slot) {
    if (!slot) return;
    if (!bell) { bell = document.createElement("span"); bell.className = "alert-slot"; }
    if (bell.parentElement !== slot) slot.append(bell);
    renderBell();
  }
  function stop() {
    stopped = true;
    if (timer) clearInterval(timer);
    timer = null;
    document.removeEventListener("click", onDocumentClick);
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("visibilitychange", onVisible);
    root?.remove(); root = null; bell?.remove(); bell = null; panelOpen = false;
  }

  window.VisorAlerts = Object.freeze({ start });
  (window.VisorServices = window.VisorServices || []).push({ id: "alerts", start });
})();
