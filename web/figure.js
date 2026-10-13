// π-plotter interface — The figure on screen: drawing it, points clicked on it, rotating 3D, zooming, moving and rewriting texts.
// The page is split into classic scripts loaded in order (see index.html); they share one global scope.
'use strict';

// ------------------------------------------------------------------ rendering
function figInches() {
  const f = state.spec.figure;
  const k = UNIT_MM[f.units] / 25.4;
  return { w: Math.max(0.2, (f.width || 1) * k), h: Math.max(0.2, (f.height || 1) * k) };
}
function updateFigInfo() {
  const f = state.spec.figure;
  const fmt = $('#exportFormat').value;
  const { w, h } = figInches();
  $('#figInfo').textContent = state.dataset ? `${f.width} × ${f.height} ${f.units} · ${state.dataset.rows.toLocaleString(LOCALE())} × ${state.dataset.columns.length}` : '';
  const info = state.meta.export_formats[fmt] || {};
  let hint;
  if (fmt === 'html') hint = t('export.hint.html');
  else if (fmt === 'py') hint = t('export.hint.py');
  else if (info.raster) hint = t('export.hint.raster', { w: Math.round(w * f.dpi), h: Math.round(h * f.dpi), dpi: f.dpi });
  else hint = t('export.hint.vector');
  $('#exportHint').textContent = hint;
  $('[data-path="figure.dpi"]').closest('.field').classList.toggle('disabled', !info.raster);
}

function specForServer() {
  const s = clone(state.spec);
  s.lang = state.lang;
  s.name = state.dataset ? state.dataset.name : '';
  s.extra = (window.Files && !viewDataset()) ? Files.extraSpec() : [];
  s.main_pos = s.extra.length ? Files.position() : 0;
  const layout = currentLayout();
  if (layout) {                      // the figures it combines, as they are now
    s.extra = [];
    s.compose = layout.compose.map(layoutPanel).filter(Boolean);
  }
  return s;
}

// ------------------------------------------------------------------ points clicked on the figure
// The server says where each set of axes lies in the image (X-Axes), so a click becomes data x, y.
// An analysis field (e.g. baseline anchor points) starts a session with startPick and gets each point.
const Pick = { session: null };

function figureAxes(header) {
  try { return JSON.parse(decodeURIComponent(header || '[]')).filter(g => [g.xscale, g.yscale].every(v => v === 'linear' || v === 'log')); }
  catch (e) { return []; }
}

// Position along one axis: fraction f of the image → data value (linear or log axis), and back.
const axisValue = (f, lo, hi, lim, scale) => {
  const u = (f - lo) / (hi - lo);
  if (scale === 'log') return 10 ** (Math.log10(lim[0]) + u * (Math.log10(lim[1]) - Math.log10(lim[0])));
  return lim[0] + u * (lim[1] - lim[0]);
};
const axisFraction = (v, lo, hi, lim, scale) => {
  const t = scale === 'log' ? (Math.log10(v) - Math.log10(lim[0])) / (Math.log10(lim[1]) - Math.log10(lim[0]))
    : (v - lim[0]) / (lim[1] - lim[0]);
  return lo + t * (hi - lo);
};

// Data coordinates under a point of the screen, or null outside the axes.
function figureToData(clientX, clientY) {
  const r = $('#figure').getBoundingClientRect();
  if (!r.width || !r.height) return null;
  const fx = (clientX - r.left) / r.width, fy = 1 - (clientY - r.top) / r.height;
  const g = (state.axesGeom || []).find(a => fx >= a.box[0] && fx <= a.box[2] && fy >= a.box[1] && fy <= a.box[3]);
  if (!g) return null;
  return { x: axisValue(fx, g.box[0], g.box[2], g.xlim, g.xscale), y: axisValue(fy, g.box[1], g.box[3], g.ylim, g.yscale), g };
}

// A coordinate written with the precision the axis can show (≈ 1/2000 of its span).
function axisText(v, lim, scale) {
  if (scale === 'log' || !Number.isFinite(v)) return String(+v.toPrecision(4));
  const step = Math.abs(lim[1] - lim[0]) / 2000 || 1;
  return String(+v.toFixed(Math.min(12, Math.max(0, Math.ceil(-Math.log10(step))))));
}

function startPick(session) {
  stopPick();
  if (state.tab !== 'figure') setTab('figure');
  if (!(state.axesGeom || []).length) { toast(t('pick.unavailable'), true); return false; }
  Pick.session = session;
  const box = $('#figureBox');
  box.classList.add('picking');
  const hint = document.createElement('div');
  hint.className = 'pick-hint';
  hint.id = 'pickHint';
  hint.textContent = session.hint || t('pick.hint');
  box.append(hint);
  drawPickMarks();
  $('#stage').scrollIntoView({ block: 'nearest', behavior: 'smooth' });   // narrow screens: the figure is above
  return true;
}

function stopPick() {
  const s = Pick.session;
  Pick.session = null;
  $('#figureBox').classList.remove('picking');
  ['#pickHint', '#pickLayer', '#pickReadout'].forEach(id => { const el = $(id); if (el) el.remove(); });
  if (s && s.onStop) s.onStop();
}

// The session's points over the image: a dot where the height is given, a vertical line where the
// height will be read from the signal.
function drawPickMarks() {
  const old = $('#pickLayer');
  if (old) old.remove();
  if (!Pick.session || !(state.axesGeom || []).length) return;
  const box = $('#figureBox');
  const img = $('#figure').getBoundingClientRect();
  const outer = box.getBoundingClientRect();
  const g = state.axesGeom[0];
  const layer = document.createElement('div');
  layer.className = 'pick-layer';
  layer.id = 'pickLayer';
  const left = v => img.left - outer.left + img.width * axisFraction(v, g.box[0], g.box[2], g.xlim, g.xscale);
  const top = v => img.top - outer.top + img.height * (1 - axisFraction(v, g.box[1], g.box[3], g.ylim, g.yscale));
  (Pick.session.marks() || []).forEach(({ x, y }) => {
    const m = document.createElement('div');
    if (y === null || y === undefined) {
      m.className = 'pick-vline';
      m.style.left = left(x) + 'px';
      m.style.top = top(g.ylim[1]) + 'px';
      m.style.height = (top(g.ylim[0]) - top(g.ylim[1])) + 'px';
    } else {
      m.className = 'pick-dot';
      m.style.left = left(x) + 'px';
      m.style.top = top(y) + 'px';
    }
    layer.append(m);
  });
  box.append(layer);
}

function initPick() {
  const img = $('#figure');
  img.addEventListener('click', e => {
    if (!Pick.session) return;
    const p = figureToData(e.clientX, e.clientY);
    if (!p) { toast(t('pick.outside')); return; }
    Pick.session.onPoint({ x: axisText(p.x, p.g.xlim, p.g.xscale), y: axisText(p.y, p.g.ylim, p.g.yscale) });
    drawPickMarks();
  });
  img.addEventListener('mousemove', e => {
    if (!Pick.session) return;
    let tip = $('#pickReadout');
    const p = figureToData(e.clientX, e.clientY);
    if (!p) { if (tip) tip.remove(); return; }
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'pick-readout';
      tip.id = 'pickReadout';
      $('#figureBox').append(tip);
    }
    const outer = $('#figureBox').getBoundingClientRect();
    tip.textContent = `x ${axisText(p.x, p.g.xlim, p.g.xscale)}   y ${axisText(p.y, p.g.ylim, p.g.yscale)}`;
    tip.style.left = (e.clientX - outer.left + 14) + 'px';
    tip.style.top = (e.clientY - outer.top + 14) + 'px';
  });
  img.addEventListener('mouseleave', () => { const tip = $('#pickReadout'); if (tip) tip.remove(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && Pick.session) stopPick();
    if (e.key === 'Escape' && BoxPick.fn) stopBoxPick();
  });
}

// ------------------------------------------------------------------ rotating a 3D figure
// Drag on a 3D figure: a canvas over the image draws a light copy of the data at the new view, with
// Matplotlib's own projection (web/view3d.js), so it moves smoothly; on release the view is kept
// (elevation and azimuth fields) and the figure is drawn again. Double-click: the default view.
const Rotate = { id: null, data: null, loading: null, drag: null };

function view3dReady(id) {
  Rotate.id = id || null;
  Rotate.data = null;
  Rotate.loading = null;
  const img = $('#figure');
  img.classList.toggle('rotatable', !!Rotate.id);
  const kind = state.spec.kind;
  img.title = Rotate.id ? t('view3d.hint') : kind === 'polar' ? t('zoom.hint_wheel') : NO_BOX_ZOOM.has(kind) ? t('move.hint') : t('zoom.hint');
}

function view3dData() {
  if (Rotate.data) return Promise.resolve(Rotate.data);
  if (!Rotate.loading) {
    const id = Rotate.id;
    Rotate.loading = api('/api/view3d/' + id).then(d => { if (Rotate.id === id) Rotate.data = d; return d; });
  }
  return Rotate.loading;
}

function view3dLayer() {
  let c = $('#view3dLayer');
  if (!c) {
    c = document.createElement('canvas');
    c.id = 'view3dLayer';
    c.className = 'view3d-layer';
    $('#figureBox').append(c);
  }
  const img = $('#figure').getBoundingClientRect();
  const outer = $('#figureBox').getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  Object.assign(c.style, { left: (img.left - outer.left) + 'px', top: (img.top - outer.top) + 'px',
    width: img.width + 'px', height: img.height + 'px' });
  c.width = Math.round(img.width * dpr);
  c.height = Math.round(img.height * dpr);
  return c;
}

function removeView3dLayer() {
  const c = $('#view3dLayer');
  if (c) c.remove();
}

function paintView3d(d, view = d.cur) {
  View3D.draw(d.canvas, d.data, view.elev, view.azim, {
    dpr: window.devicePixelRatio || 1,
    readout: t('view3d.readout', { elev: Math.round(view.elev), azim: Math.round(view.azim) }),
  });
}

function setView3d(elev, azim) {
  state.spec.style.elev = elev;
  state.spec.style.azim = azim;
  $$('#kindOptions [data-path="style.elev"], #kindOptions [data-path="style.azim"]')
    .forEach(el => writeControl(el, getPath(state.spec, el.dataset.path)));
  scheduleRender(0);                 // the preview stays until the new figure is shown
}

function initRotate() {
  const img = $('#figure');
  img.addEventListener('pointerdown', async e => {
    if (!Rotate.id || Pick.session || e.button !== 0 || movableAt(e.clientX, e.clientY)) return;
    e.preventDefault();
    img.setPointerCapture(e.pointerId);
    const d = { x: e.clientX, y: e.clientY, data: null };
    Rotate.drag = d;
    img.classList.add('rotating');
    let data;
    try { data = await view3dData(); } catch (err) { if (Rotate.drag === d) Rotate.drag = null; img.classList.remove('rotating'); return; }
    if (Rotate.drag !== d) return;                     // released before the data arrived
    const v = data.axes[0];
    Object.assign(d, { data, elev: v.elev, azim: v.azim, cur: { elev: v.elev, azim: v.azim }, canvas: view3dLayer() });
    paintView3d(d);
  });
  img.addEventListener('pointermove', e => {
    const d = Rotate.drag;
    if (!d || !d.data) return;
    const r = img.getBoundingClientRect();
    // As Matplotlib's own mouse rotation: a drag across the whole figure turns it by 180°.
    d.cur = { elev: Math.max(-90, Math.min(90, d.elev + (e.clientY - d.y) / r.height * 180)),
      azim: View3D.normAngle(d.azim - (e.clientX - d.x) / r.width * 180) };
    if (!d.frame) d.frame = requestAnimationFrame(() => { d.frame = 0; paintView3d(d); });
  });
  const end = () => {
    const d = Rotate.drag;
    if (!d) return;
    Rotate.drag = null;
    img.classList.remove('rotating');
    if (!d.data) return;
    if (d.frame) cancelAnimationFrame(d.frame);
    const elev = Math.round(d.cur.elev), azim = Math.round(d.cur.azim);
    if (elev === Math.round(d.elev) && azim === Math.round(d.azim)) { removeView3dLayer(); return; }
    paintView3d(d, { elev, azim });
    setView3d(elev, azim);
  };
  img.addEventListener('pointerup', end);
  img.addEventListener('pointercancel', end);
  img.addEventListener('dblclick', e => {
    if (!Rotate.id || Pick.session || movableAt(e.clientX, e.clientY)) return;
    const def = state.defaults?.style || {};
    setView3d(def.elev ?? 25, def.azim ?? -60);
  });
}

// ------------------------------------------------------------------ zooming, moving and rewriting texts
// Drag a box on the axes to zoom: its corners become the axis limits (the fields of the Axes panel) and
// the figure is drawn again with ticks for the new range; a thin box zooms one axis only. The mouse
// wheel zooms around the pointer, and is the way to zoom polar (the radius) and 3D figures (the three
// ranges). Double-click or the buttons over the figure go back. Every text the server lists (X-Movables:
// titles, axis labels, colour-bar label, legend, slice and value labels) can be dragged, and rewritten
// with a double-click; the figure keeps it (spec.moved, legend.pos, spec.text, spec.texts) in the preview
// and in every export.
const NO_BOX_ZOOM = new Set(['pie', 'pairplot', 'polar', 'surface3d', 'scatter3d', 'waterfall']);
const LIMIT_KEYS = ['xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax'];
const zoomStacks = new WeakMap();                  // spec → the limits before each zoom
const Drag = { items: [], zoom: [], face: '#ffffff', url: null, op: null };
const Wheel = { limits: null, timer: 0 };
// A box dragged on the figure gives a region to BoxPick.fn (e.g. the inset's) instead of zooming.
const BoxPick = { fn: null };

function parseMovables(header) {
  try {
    const d = JSON.parse(decodeURIComponent(header || '{}'));
    return { items: d.items || [], zoom: d.zoom || [], face: d.face || '#ffffff' };
  } catch (e) { return { items: [], zoom: [], face: '#ffffff' }; }
}

const zoomStack = () => { if (!zoomStacks.has(state.spec)) zoomStacks.set(state.spec, []); return zoomStacks.get(state.spec); };
const canZoom = () => !Pick.session && !Rotate.id && !NO_BOX_ZOOM.has(state.spec.kind) && (state.axesGeom || []).length > 0;
const currentLimits = () => Object.fromEntries(LIMIT_KEYS.map(k => [k, state.spec.axes[k] ?? null]));

// The draggable text under a point of the screen (the smallest, when they overlap), or null.
function movableAt(clientX, clientY) {
  if (Pick.session || Drag.op) return null;
  const r = $('#figure').getBoundingClientRect();
  if (!r.width || !r.height) return null;
  const fx = (clientX - r.left) / r.width, fy = 1 - (clientY - r.top) / r.height;
  const sx = 3 / r.width, sy = 3 / r.height;         // a few pixels of slack around small labels
  const area = m => (m.box[2] - m.box[0]) * (m.box[3] - m.box[1]);
  return Drag.items.filter(m => fx >= m.box[0] - sx && fx <= m.box[2] + sx && fy >= m.box[1] - sy && fy <= m.box[3] + sy)
    .sort((a, b) => area(a) - area(b))[0] || null;
}

// A box in figure fractions (from the bottom left) → pixels in #figureBox.
function boxPixels(box) {
  const img = $('#figure').getBoundingClientRect(), outer = $('#figureBox').getBoundingClientRect();
  return { left: img.left - outer.left + box[0] * img.width, top: img.top - outer.top + (1 - box[3]) * img.height,
    width: (box[2] - box[0]) * img.width, height: (box[3] - box[1]) * img.height };
}

function overlayDiv(cls, px) {
  const d = document.createElement('div');
  d.className = cls;
  Object.assign(d.style, { left: px.left + 'px', top: px.top + 'px', width: px.width + 'px', height: px.height + 'px' });
  $('#figureBox').append(d);
  return d;
}

function clearDragMarks() { $$('.move-ghost, .move-mask, .move-hover, .zoom-box').forEach(el => el.remove()); }

// A limit as the Axes panel writes it: a date for date axes, else a number with the precision the axis shows.
function limitValue(v, lim, scale, date) {
  if (date) return new Date(Math.round(v * 86400000)).toISOString().slice(0, 19).replace('T00:00:00', '');
  return Number(axisText(v, lim, scale));
}

function setLimits(limits) {
  LIMIT_KEYS.forEach(k => { state.spec.axes[k] = limits[k] ?? null; });
  $$('[data-path^="axes."]').forEach(el => writeControl(el, getPath(state.spec, el.dataset.path)));
  updateFigTools();
  scheduleRender(0);
}

function zoomTo(g, a, b) {
  const img = $('#figure').getBoundingClientRect();
  const w = Math.abs(a.x - b.x), h = Math.abs(a.y - b.y);
  if (w < 6 && h < 6) return false;                  // a click, not a box
  const fx = c => (c - img.left) / img.width, fy = c => 1 - (c - img.top) / img.height;
  const capture = BoxPick.fn;
  const limits = capture ? { xmin: null, xmax: null, ymin: null, ymax: null } : currentLimits();
  if (!capture) zoomStack().push({ ...limits });
  if (w >= 6) {                                       // a box only a few pixels high zooms x alone (and y the reverse)
    const xs = [a.x, b.x].map(c => axisValue(fx(c), g.box[0], g.box[2], g.xlim, g.xscale)).sort((p, q) => p - q);
    limits.xmin = limitValue(xs[0], g.xlim, g.xscale, g.xdate);
    limits.xmax = limitValue(xs[1], g.xlim, g.xscale, g.xdate);
  }
  if (h >= 6) {
    const ys = [a.y, b.y].map(c => axisValue(fy(c), g.box[1], g.box[3], g.ylim, g.yscale)).sort((p, q) => p - q);
    limits.ymin = limitValue(ys[0], g.ylim, g.yscale, false);
    limits.ymax = limitValue(ys[1], g.ylim, g.yscale, false);
  } else {
    limits.ymin = limits.ymax = null;                 // x alone: y follows the data in the new range
  }
  if (capture) {
    stopBoxPick();
    capture(limits);
    return true;
  }
  setLimits(limits);
  return true;
}

function startBoxPick(hint, fn) {
  stopPick();
  if (state.tab !== 'figure') setTab('figure');
  if (!canZoom()) { toast(t('pick.unavailable'), true); return; }
  BoxPick.fn = fn;
  const el = document.createElement('div');
  el.className = 'pick-hint';
  el.id = 'boxPickHint';
  el.textContent = hint;
  $('#figureBox').append(el);
}

function stopBoxPick() {
  BoxPick.fn = null;
  const el = $('#boxPickHint');
  if (el) el.remove();
}

function zoomBack(all = false) {
  const stack = zoomStack();
  if (!stack.length) return;
  const limits = all ? stack[0] : stack[stack.length - 1];
  stack.length = all ? 0 : stack.length - 1;
  setLimits(limits);
}

// Where a dragged text ends: value labels and titles keep an offset in points, the legend its corner.
function dropMovable(m, dx, dy) {
  const img = $('#figure').getBoundingClientRect();
  const { w, h } = figInches();
  if (m.kind === 'legend') {
    const fx = m.box[0] + dx / img.width, fy = m.box[3] - dy / img.height, ref = m.ref;
    state.spec.legend.pos = [+((fx - ref[0]) / (ref[2] - ref[0])).toFixed(4), +((fy - ref[1]) / (ref[3] - ref[1])).toFixed(4)];
  } else {
    const ddx = dx / img.width * w * 72, ddy = -dy / img.height * h * 72;
    state.spec.moved = { ...(state.spec.moved || {}), [m.id]: [+(m.offset[0] + ddx).toFixed(2), +(m.offset[1] + ddy).toFixed(2)] };
  }
  updateFigTools();
  scheduleRender(0);
}

function resetMovable(m) {
  if (m.kind === 'legend') state.spec.legend.pos = null;
  else if (state.spec.moved && m.id in state.spec.moved) {
    const { [m.id]: _, ...rest } = state.spec.moved;
    state.spec.moved = rest;
  } else return;
  updateFigTools();
  scheduleRender(0);
}

function resetPositions() {
  state.spec.moved = {};
  state.spec.legend.pos = null;
  updateFigTools();
  scheduleRender(0);
}

function updateFigTools() {
  let bar = $('#figTools');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'figTools';
    bar.className = 'fig-tools';
    bar.innerHTML = '<button type="button" class="btn small" data-act="back"></button><button type="button" class="btn small" data-act="all"></button><button type="button" class="btn small" data-act="pos"></button>';
    bar.querySelector('[data-act="back"]').onclick = () => zoomBack(false);
    bar.querySelector('[data-act="all"]').onclick = () => zoomBack(true);
    bar.querySelector('[data-act="pos"]').onclick = resetPositions;
    $('#figureBox').append(bar);
  }
  const depth = zoomStack().length;
  const moved = Object.keys(state.spec.moved || {}).length > 0 || !!state.spec.legend.pos;
  const [back, all, pos] = $$('button', bar);
  back.textContent = t('zoom.back');
  all.textContent = t('zoom.reset');
  pos.textContent = t('move.reset');
  back.hidden = !depth;
  all.hidden = depth < 2;
  pos.hidden = !moved;
  bar.hidden = !depth && !moved;
}

// The mouse wheel zooms around the pointer (Shift: x alone, y follows the data); on polar axes it
// zooms the radius, on 3D axes the three ranges around their centre. A burst of wheel steps is one
// zoom (one step back), drawn once the wheel pauses.
function onWheel(e) {
  if (Pick.session || Drag.op) return;
  const r = $('#figure').getBoundingClientRect();
  if (!r.width || !r.height) return;
  const fx = (e.clientX - r.left) / r.width, fy = 1 - (e.clientY - r.top) / r.height;
  const inside = b => fx >= b[0] && fx <= b[2] && fy >= b[1] && fy <= b[3];
  let d = e.deltaY || e.deltaX;
  if (e.deltaMode === 1) d *= 16; else if (e.deltaMode === 2) d *= r.height;
  if (!d) return;
  const f = Math.min(4, Math.max(0.25, Math.exp(d * 0.0025)));        // > 1 zooms out
  const round = v => Number(v.toPrecision(6));
  const next = Wheel.limits ? { ...Wheel.limits } : currentLimits();
  const other = (Drag.zoom || []).find(a => inside(a.box));
  let view = Wheel.view;
  if (other && other.type === '3d') {
    view = view || { x: [...other.xlim].sort((a, b) => a - b), y: [...other.ylim].sort((a, b) => a - b), z: [...other.zlim].sort((a, b) => a - b) };
    ['x', 'y', 'z'].forEach(k => {
      const mid = (view[k][0] + view[k][1]) / 2, half = (view[k][1] - view[k][0]) / 2 * f;
      view[k] = [mid - half, mid + half];
      next[k + 'min'] = round(view[k][0]);
      next[k + 'max'] = round(view[k][1]);
    });
  } else if (other && other.type === 'polar') {
    view = view || { r: [...other.rlim] };
    view.r = [view.r[0], view.r[0] + (view.r[1] - view.r[0]) * f];
    next.ymin = round(view.r[0]);
    next.ymax = round(view.r[1]);
  } else {
    if (!canZoom()) return;
    const p = figureToData(e.clientX, e.clientY);
    if (!p) return;
    const g = p.g;
    view = view || { x: [...g.xlim], y: [...g.ylim] };   // in screen order: left → right, bottom → top
    const fwd = scale => (scale === 'log' ? Math.log10 : v => v), back = scale => (scale === 'log' ? v => 10 ** v : v => v);
    const zoomAxis = (lim, u, scale) => {
      const [a, b] = lim.map(fwd(scale)), c = a + u * (b - a);
      return [c - (c - a) * f, c + (b - c) * f].map(back(scale));
    };
    view.x = zoomAxis(view.x, (fx - g.box[0]) / (g.box[2] - g.box[0]), g.xscale);
    const xs = [...view.x].sort((a, b) => a - b);
    next.xmin = limitValue(xs[0], g.xlim, g.xscale, g.xdate);
    next.xmax = limitValue(xs[1], g.xlim, g.xscale, g.xdate);
    if (e.shiftKey) {
      next.ymin = next.ymax = null;                    // x alone: y follows the data in the new range
    } else {
      view.y = zoomAxis(view.y, (fy - g.box[1]) / (g.box[3] - g.box[1]), g.yscale);
      const ys = [...view.y].sort((a, b) => a - b);
      next.ymin = limitValue(ys[0], g.ylim, g.yscale, false);
      next.ymax = limitValue(ys[1], g.ylim, g.yscale, false);
    }
  }
  e.preventDefault();
  if (!Wheel.limits) zoomStack().push(currentLimits());
  Wheel.limits = next;
  Wheel.view = view;
  clearTimeout(Wheel.timer);
  Wheel.timer = setTimeout(() => { Wheel.limits = Wheel.view = null; }, 700);
  LIMIT_KEYS.forEach(k => { state.spec.axes[k] = next[k] ?? null; });
  $$('[data-path^="axes."]').forEach(el => writeControl(el, getPath(state.spec, el.dataset.path)));
  updateFigTools();
  scheduleRender(150);
}

// Double-click a text: rewrite it. Titles and axis labels go to their fields (the Text panel shows them),
// the legend's title to its own; other texts (value and slice labels, panel titles) to spec.texts.
function closeEditor() {
  const ed = $('#textEditor');
  if (ed) ed.remove();
  document.removeEventListener('pointerdown', Drag.outside, true);
}

function setText(m, value) {                         // value null: back to the automatic text
  if (m.field) {
    setPath(state.spec, m.field, value ?? '');
    $$(`[data-path="${m.field}"]`).forEach(el => writeControl(el, value ?? ''));
    if (m.field.startsWith('legend.')) saveStyle();
  } else {
    const texts = { ...(state.spec.texts || {}) };
    if (value === null || !value.trim()) delete texts[m.id]; else texts[m.id] = value;
    state.spec.texts = texts;
  }
  closeEditor();
  scheduleRender(0);
}

function editMovable(m) {
  closeEditor();
  const box = $('#figureBox');
  const px = boxPixels(m.box);
  const legend = m.kind === 'legend';
  const own = m.field ? !!getPath(state.spec, m.field) : m.id in (state.spec.texts || {});
  const moved = legend ? !!state.spec.legend.pos : !!(state.spec.moved || {})[m.id];
  const ed = document.createElement('div');
  ed.className = 'text-editor';
  ed.id = 'textEditor';
  const multi = !legend && (m.text || '').includes('\n');
  ed.innerHTML = '<label class="small muted"></label>' + (multi ? '<textarea rows="5" spellcheck="false"></textarea>' : '<input type="text" spellcheck="false">') +
    '<div class="text-editor-row"><button type="button" class="btn small primary" data-act="ok"></button>' +
    '<button type="button" class="btn small" data-act="auto"></button><button type="button" class="btn small" data-act="place"></button></div>' +
    '<p class="small muted"></p>';
  $('label', ed).textContent = t(legend ? 'edit.legend' : 'edit.text');
  $('p', ed).textContent = t('edit.math') + (multi ? ' ' + t('edit.multiline') : '');
  const input = $(multi ? 'textarea' : 'input', ed);
  input.value = legend ? (state.spec.legend.title || '') : m.text;
  const [ok, auto, place] = $$('button', ed);
  ok.textContent = t('edit.ok');
  auto.textContent = t('edit.auto');
  place.textContent = t('edit.place');
  auto.hidden = !own;
  place.hidden = !moved;
  const apply = () => {
    if (!own && !legend && input.value === m.text) { closeEditor(); return; }   // unchanged automatic text
    setText(m, input.value);
  };
  ok.onclick = apply;
  auto.onclick = () => setText(m, null);
  place.onclick = () => { closeEditor(); resetMovable(m); };
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && (!multi || e.ctrlKey || e.metaKey)) { e.preventDefault(); apply(); }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeEditor(); }
  });
  box.append(ed);
  const room = box.clientWidth - ed.offsetWidth - 4;
  ed.style.left = Math.max(4, Math.min(px.left, room)) + 'px';
  const below = px.top + px.height + 6;
  ed.style.top = (below + ed.offsetHeight < box.clientHeight ? below : Math.max(4, px.top - ed.offsetHeight - 6)) + 'px';
  Drag.outside = ev => { if (!ed.contains(ev.target)) closeEditor(); };
  document.addEventListener('pointerdown', Drag.outside, true);
  input.focus();
  input.select();
}

function initDrag() {
  const img = $('#figure');
  const box = $('#figureBox');
  img.addEventListener('pointermove', e => {
    if (Drag.op) return;
    const m = movableAt(e.clientX, e.clientY);
    $$('.move-hover').forEach(el => el.remove());
    img.classList.toggle('movable', !!m);
    img.classList.toggle('zoomable', !m && canZoom() && !!figureToData(e.clientX, e.clientY));
    if (m) overlayDiv('move-hover', boxPixels(m.box));
  });
  img.addEventListener('mouseleave', () => { if (!Drag.op) $$('.move-hover').forEach(el => el.remove()); });
  img.addEventListener('pointerdown', e => {
    if (e.button !== 0 || Pick.session || Drag.op) return;
    const m = movableAt(e.clientX, e.clientY);
    if (m) {
      e.preventDefault();
      img.setPointerCapture(e.pointerId);
      clearDragMarks();
      const px = boxPixels(m.box);
      const r = img.getBoundingClientRect(), outer = box.getBoundingClientRect();
      const mask = overlayDiv('move-mask', px);
      mask.style.background = Drag.face;
      const ghost = overlayDiv('move-ghost', px);
      Object.assign(ghost.style, { backgroundImage: `url("${Drag.url}")`, backgroundSize: `${r.width}px ${r.height}px`,
        backgroundPosition: `${-(px.left - (r.left - outer.left))}px ${-(px.top - (r.top - outer.top))}px` });
      Drag.op = { type: 'move', m, x: e.clientX, y: e.clientY, px, ghost };
      return;
    }
    if (!canZoom()) return;
    const p = figureToData(e.clientX, e.clientY);
    if (!p) return;
    e.preventDefault();
    img.setPointerCapture(e.pointerId);
    clearDragMarks();
    Drag.op = { type: 'zoom', g: p.g, x: e.clientX, y: e.clientY, rect: overlayDiv('zoom-box', { left: 0, top: 0, width: 0, height: 0 }) };
  });
  img.addEventListener('pointermove', e => {
    const op = Drag.op;
    if (!op) return;
    const dx = e.clientX - op.x, dy = e.clientY - op.y;
    if (op.type === 'move') {
      op.ghost.style.left = (op.px.left + dx) + 'px';
      op.ghost.style.top = (op.px.top + dy) + 'px';
      return;
    }
    // The box stays inside the axes it started in.
    const r = img.getBoundingClientRect(), outer = box.getBoundingClientRect();
    const ax0 = r.left + op.g.box[0] * r.width, ax1 = r.left + op.g.box[2] * r.width;
    const ay0 = r.top + (1 - op.g.box[3]) * r.height, ay1 = r.top + (1 - op.g.box[1]) * r.height;
    op.cx = Math.min(ax1, Math.max(ax0, e.clientX));
    op.cy = Math.min(ay1, Math.max(ay0, e.clientY));
    const thinY = Math.abs(op.cy - op.y) < 6, thinX = Math.abs(op.cx - op.x) < 6;
    const left = thinX ? ax0 : Math.min(op.x, op.cx), right = thinX ? ax1 : Math.max(op.x, op.cx);
    const top = thinY ? ay0 : Math.min(op.y, op.cy), bottom = thinY ? ay1 : Math.max(op.y, op.cy);
    Object.assign(op.rect.style, { left: (left - outer.left) + 'px', top: (top - outer.top) + 'px',
      width: (right - left) + 'px', height: (bottom - top) + 'px' });
    op.rect.classList.toggle('thin', thinX || thinY);
  });
  const end = e => {
    const op = Drag.op;
    if (!op) return;
    Drag.op = null;
    if (op.type === 'move') {
      const dx = e.clientX - op.x, dy = e.clientY - op.y;
      if (e.type === 'pointercancel' || Math.hypot(dx, dy) < 3) { clearDragMarks(); return; }
      dropMovable(op.m, dx, dy);                     // the ghost stays until the new figure is shown
      return;
    }
    op.rect.remove();
    if (e.type !== 'pointercancel' && op.cx !== undefined) zoomTo(op.g, { x: op.x, y: op.y }, { x: op.cx, y: op.cy });
  };
  img.addEventListener('pointerup', end);
  img.addEventListener('pointercancel', end);
  img.addEventListener('dblclick', e => {
    if (Pick.session) return;
    const m = movableAt(e.clientX, e.clientY);
    if (m) editMovable(m);
    else if (canZoom() && zoomStack().length) zoomBack(true);
  });
  img.addEventListener('wheel', onWheel, { passive: false });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || !Drag.op) return;
    if (Drag.op.rect) Drag.op.rect.remove();
    Drag.op = null;
    clearDragMarks();
  });
}

function scheduleRender(delay = 200) {
  clearTimeout(state.renderTimer);
  state.renderTimer = setTimeout(renderNow, delay);
}

async function renderNow() {
  if (!state.dataset || state.tab !== 'figure') return;
  if (window.Analysis && !viewDataset()) Analysis.suggestSoon();   // analyses that suit this figure
  const seq = ++state.renderSeq;
  if (state.renderCtrl) state.renderCtrl.abort();
  const ctrl = new AbortController();
  state.renderCtrl = ctrl;
  const stage = $('#stage');
  const img = $('#figure');
  const { w, h } = figInches();
  const fit = Math.max(20, Math.min((stage.clientWidth - 56) / w, (stage.clientHeight - 56) / h));
  const dpi = Math.round(Math.min(Math.max(fit * (window.devicePixelRatio || 1), 50), 450));
  $('#spinner').hidden = false;
  img.classList.add('loading');
  try {
    const res = await api('/api/render', { dataset_id: state.dataset.dataset_id, spec: specForServer(), dpi }, { raw: true, signal: ctrl.signal });
    const blob = await res.blob();
    if (seq !== state.renderSeq) return;
    seriesDrawn(res.headers.get('X-Series'));
    state.axesGeom = figureAxes(res.headers.get('X-Axes'));
    view3dReady(res.headers.get('X-View3D'));
    Object.assign(Drag, parseMovables(res.headers.get('X-Movables')));
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      if (Drag.url && Drag.url !== url) URL.revokeObjectURL(Drag.url);   // kept: a dragged text shows a piece of it
      Drag.url = url;
      removeView3dLayer();
      drawPickMarks();
      if (!Drag.op) clearDragMarks();
      updateFigTools();
    };
    img.src = url;
    img.style.width = Math.round(w * fit) + 'px';
    img.style.height = Math.round(h * fit) + 'px';
    $('#figureBox').hidden = false;
    $('#errorBox').hidden = true;
    $('#btnExport').disabled = false;
  } catch (e) {
    if (e.name === 'AbortError' || seq !== state.renderSeq) return;
    removeView3dLayer();
    if (e.code === 'missing_modules') {
      if (await ensureModules(e.data.modules)) { buildKindGallery(); scheduleRender(0); }
    } else if (e.code === 'dataset_gone') {
      await reopenSource();
    } else {
      $('#errorBox').textContent = specMessage(e);
      $('#errorBox').hidden = false;
    }
  } finally {
    if (seq === state.renderSeq) {
      $('#spinner').hidden = true;
      img.classList.remove('loading');
    }
  }
}
