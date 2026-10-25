/* Shared presentation helpers. Authentication and feature state remain with their owners. */
(() => {
  const paths = {
    control: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    live: '<rect x="3" y="5" width="13" height="14" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>',
    incidents: '<path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3v1"/>',
    analysis: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="m10 8 6 4-6 4z"/>',
    modules: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/>',
    overview: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    settings: '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  };
  function icon(name) { return `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.control}</svg>`; }
  function dialog(dialog, {dirty = () => false, cleanup = () => {}} = {}) {
    const previous = document.activeElement;
    const heading = dialog.querySelector('h2,h3');
    if (heading) { heading.id ||= `${dialog.id || 'visor-dialog'}-title`; dialog.setAttribute('aria-labelledby', heading.id); }
    const close = () => { if (dirty() && !confirm('Discard unsaved changes?')) return; dialog.close(); };
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('close', () => { cleanup(); dialog.remove(); if (previous?.isConnected) previous.focus(); }, {once: true});
    dialog.querySelector('[data-close-dialog],[data-close]')?.addEventListener('click', close);
    dialog.showModal();
    return close;
  }
  function parseGeometry(text) {
    const value = JSON.parse(text);
    const points = value.points, line = value.line || [];
    const valid = point => Array.isArray(point) && point.length === 2 && point.every(n => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1);
    if (!Array.isArray(points) || points.length < 3 || points.length > 64 || !points.every(valid)) throw Error('Enter 3–64 zone points as [x, y], with coordinates from 0 to 1.');
    const area = points.reduce((sum, p, i) => { const next = points[(i + 1) % points.length]; return sum + p[0] * next[1] - next[0] * p[1]; }, 0);
    if (Math.abs(area) < 1e-8) throw Error('The zone must enclose an area.');
    if (!Array.isArray(line) || (line.length !== 0 && (line.length !== 2 || !line.every(valid) || (line[0][0] === line[1][0] && line[0][1] === line[1][1])))) throw Error('A crossing line needs two distinct [x, y] points from 0 to 1, or an empty array.');
    return {points, line};
  }
  window.VisorUI = Object.freeze({icon, dialog, parseGeometry});
})();
