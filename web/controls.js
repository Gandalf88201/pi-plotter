// π-plotter interface — The controls of the figure: selects, kinds of plot, the user's module tools, variables (mapping), series styles, hints.
// The page is split into classic scripts loaded in order (see index.html); they share one global scope.
'use strict';

// ------------------------------------------------------------------ static selects
function fillSelect(sel, items, current) {
  sel.innerHTML = '';
  items.forEach(([value, label, group]) => {
    let parent = sel;
    if (group) {
      parent = sel.querySelector(`optgroup[data-g="${group}"]`);
      if (!parent) { parent = document.createElement('optgroup'); parent.label = t('cmapgrp.' + group); parent.dataset.g = group; sel.append(parent); }
    }
    const o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    parent.append(o);
  });
  if (current !== undefined) sel.value = current;
}

function buildStaticSelects() {
  const m = state.meta;
  fillSelect($('#styleSelect'), Object.keys(m.styles).map(k => [k, t('style.' + k) + (missingOf(m.styles[k].requires).length ? ' ↓' : '')]));
  fillSelect($('#paletteSelect'), [...Object.keys(m.palettes), 'style'].map(k => [k, t('pal.' + k)]));
  const cm = [];
  Object.entries(m.colormaps).forEach(([g, names]) => names.forEach(n => cm.push([n, n.replace('cmc.', ''), g])));
  fillSelect($('#cmapSelect'), cm);
  $$('.ls-select').forEach(s => fillSelect(s, LINESTYLES.map(v => [v, t('ls.' + v)])));
  $$('.marker-select').forEach(s => fillSelect(s, MARKERS.map(v => [v, t('mk.' + v)])));
  $$('.scale-select').forEach(s => fillSelect(s, SCALES.map(v => [v, t('scale.' + v)])));
  fillSelect($('#legendLoc'), LEGEND_LOCS.map(v => [v, t('loc.' + v)]));
  const fonts = m.fonts || [];
  const pref = PREFERRED_FONTS.filter(f => fonts.includes(f));
  fillSelect($('#fontSelect'), [['', t('text.font_default')], ...pref.map(f => [f, f]), ...fonts.filter(f => !pref.includes(f)).map(f => [f, f])]);
  fillSelect($('#sizePreset'), [['', t('fig.custom')], ...Object.entries(m.size_presets).map(([k, [w]]) => [k, `${t('preset.' + k)} · ${w} mm`])]);
  fillSelect($('#exportFormat'), Object.keys(m.export_formats).map(k => [k, t('fmt.' + k) + (missingOf(m.export_formats[k].requires).length ? ' ↓' : '')]),
    store.get('pp-export-format', 'pdf'));
  syncControls();
  updatePalettePreview();
}

function paletteColors(palette = state.spec.style.palette) {
  const fixed = state.meta.palettes[palette];
  if (fixed && fixed.length) return fixed;
  const pv = state.meta.palette_previews || {};
  return (palette === 'style' ? (pv.style || {})[state.spec.style.base] : pv[palette]) || [];
}

function updatePalettePreview() {
  const pal = paletteColors();
  $('#paletteSwatches').innerHTML = pal.slice(0, 10).map(c => `<span style="background:${c}"></span>`).join('');
}

// ------------------------------------------------------------------ spec <-> controls
function readControl(el) {
  const type = el.dataset.type;
  if (el.type === 'checkbox') return el.checked;
  const v = el.value;
  if (type === 'number') return v === '' ? null : Number(v);
  if (type === 'nullable') return v.trim() === '' ? null : (isNaN(Number(v)) ? v.trim() : Number(v));
  return v;
}
function writeControl(el, value) {
  if (el.type === 'checkbox') el.checked = !!value;
  else el.value = value ?? '';
}
function syncControls() {
  $$('[data-path]').forEach(el => writeControl(el, getPath(state.spec, el.dataset.path)));
  const f = state.spec.figure;
  const preset = Object.entries(state.meta.size_presets).find(([, [w, h]]) =>
    Math.abs(w - f.width * UNIT_MM[f.units]) < 0.05 && Math.abs(h - f.height * UNIT_MM[f.units]) < 0.05);
  $('#sizePreset').value = preset ? preset[0] : '';
}

function onControlChange(ev) {
  const el = ev.target;
  if (!el.dataset || !el.dataset.path) return;
  const path = el.dataset.path;
  const value = readControl(el);
  const old = getPath(state.spec, path);
  if (path === 'figure.units') return changeUnits(old, value);
  setPath(state.spec, path, value);
  if (path === 'legend.loc') { state.spec.legend.pos = null; updateFigTools(); }   // a chosen place replaces a dragged one
  if (path === 'style.palette') { updatePalettePreview(); buildSeries(); }
  if (path === 'style.base') updatePalettePreview();
  if (path === 'figure.width' || path === 'figure.height') syncControls();
  if (path === 'style.base' || path === 'style.cmap') {
    const need = path === 'style.base' ? state.meta.styles[value]?.requires || [] : (String(value).startsWith('cmc.') ? ['cmcrameri'] : []);
    if (missingOf(need).length) {
      ensureModules(need).then(ok => {
        if (!ok) { setPath(state.spec, path, old); writeControl(el, old); }
        buildStaticSelects();
        scheduleRender();
      });
      return;
    }
  }
  saveStyle();
  updateFigInfo();
  scheduleRender(ev.type === 'input' && el.type === 'text' ? 450 : 200);
}

function changeUnits(from, to) {
  const f = state.spec.figure;
  const k = UNIT_MM[from] / UNIT_MM[to];
  f.width = +(f.width * k).toFixed(to === 'in' ? 3 : 2);
  f.height = +(f.height * k).toFixed(to === 'in' ? 3 : 2);
  f.units = to;
  syncControls();
  saveStyle();
  updateFigInfo();
}

const STYLE_KEYS = ['figure', 'style', 'axes', 'legend', 'text'];
function styleSnapshot() {
  const s = {};
  STYLE_KEYS.forEach(k => { s[k] = clone(state.spec[k]); });
  ['title', 'xlabel', 'ylabel', 'y2label', 'zlabel'].forEach(k => delete s.text[k]);
  ['xmin', 'xmax', 'ymin', 'ymax', 'y2min', 'y2max', 'zmin', 'zmax'].forEach(k => delete s.axes[k]);
  delete s.style.vmin; delete s.style.vmax;
  delete s.legend.pos;                               // where the legend was dragged belongs to that figure
  return s;
}
function saveStyle() { store.set('pp-style', styleSnapshot()); }

// ------------------------------------------------------------------ kinds gallery
function buildKindGallery() {
  const box = $('#kindGallery');
  box.innerHTML = '';
  const recTop = new Set(state.recommend.slice(0, 3).map(r => r.kind));
  KIND_GROUPS.forEach((g, gi) => {
    if (gi) box.append(Object.assign(document.createElement('span'), { className: 'kind-sep' }));
    Object.entries(state.meta.kinds).filter(([, k]) => k.group === g).forEach(([name]) => {
      const b = document.createElement('button');
      b.className = 'kind';
      b.dataset.kind = name;
      b.classList.toggle('active', state.spec.kind === name);
      b.classList.toggle('rec', recTop.has(name));
      b.classList.toggle('needs', kindNeeds(name).length > 0);
      b.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${window.KIND_ICONS[name] || ''}</svg><span></span>`;
      b.querySelector('span').textContent = t('kind.' + name);
      const rec = state.recommend.find(r => r.kind === name);
      b.title = t('kind.' + name) + (rec ? ` — ${t('rec.reason.' + rec.reason)}` : '');
      b.onclick = () => setKind(name);
      box.append(b);
    });
  });
  const tools = moduleTools();
  if (tools.length) box.append(Object.assign(document.createElement('span'), { className: 'kind-sep' }));
  tools.forEach(({ module: m, plugins }) => {
    const b = document.createElement('button');
    b.className = 'kind tool' + (m.import_failed.length ? ' partial' : '');
    b.dataset.tool = m.key;
    b.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${window.MODULE_ICON}</svg><span></span>`;
    b.querySelector('span').textContent = m.name;
    b.title = t('tools.title', { name: m.name, n: plugins.length }) + (m.import_failed.length ? ' — ' + t('tools.partial') : '');
    b.onclick = e => { e.stopPropagation(); openToolMenu(b, m, plugins); };
    box.append(b);
  });
  const active = box.querySelector('.kind.active');
  if (active) box.scrollLeft = Math.max(0, active.offsetLeft - box.clientWidth / 2 + active.offsetWidth / 2);
}

// ------------------------------------------------------------------ the user's modules as tools
// A module added from PyPI shows up after the plot types once it imports and analyses use it (its
// integration: plugins listing it in "requires"); its icon opens the list of those functions.
const canonName = s => String(s).toLowerCase().replace(/[-_.]+/g, '-');
const usedBy = m => {
  const list = window.Analysis && window.Analysis.list();
  return list ? list.plugins.filter(p => p.requires.some(r => canonName(r) === m.key)) : null;
};
function moduleTools() {
  return (state.status?.user_modules || [])
    .filter(m => m.installed && m.works !== false)
    .map(m => ({ module: m, plugins: usedBy(m) || [] }))
    .filter(x => x.plugins.length);
}

// The analyses were (re)loaded: icons and the "used by" notes of the modules follow them.
function analysesChanged() {
  if (state.meta) buildKindGallery();
  if ($('#modulesDialog').open) renderUserModules();
}

function openToolMenu(anchor, m, plugins) {
  closeToolMenu();
  const menu = document.createElement('div');
  menu.className = 'tool-menu';
  menu.id = 'toolMenu';
  const head = document.createElement('div');
  head.className = 'tool-head';
  head.textContent = `${m.name} ${m.installed}`;
  menu.append(head);
  if (m.import_failed.length) {
    const warn = document.createElement('div');
    warn.className = 'tool-warn small';
    warn.textContent = t('tools.partial');
    menu.append(warn);
  }
  plugins.forEach(p => {
    const b = document.createElement('button');
    b.className = 'tool-item';
    const name = document.createElement('b');
    name.textContent = p.name[state.lang] || p.name.en;
    const desc = document.createElement('span');
    desc.className = 'small muted';
    desc.textContent = p.description[state.lang] || p.description.en;
    b.append(name, desc);
    if (p.blocked.length) {
      b.disabled = true;
      desc.textContent = t('tools.unavailable', { why: p.blocked.map(x => `${x[0]}: ${x[1]}`).join('; ') });
    }
    b.onclick = () => { closeToolMenu(); window.Analysis.select(p.id); };
    menu.append(b);
  });
  const add = document.createElement('button');
  add.className = 'btn small tool-new';
  add.textContent = t('tools.new');
  add.onclick = () => { closeToolMenu(); window.Analysis.newIntegration(m.name); };
  menu.append(add);
  document.body.append(menu);
  const r = anchor.getBoundingClientRect();
  menu.style.top = `${r.bottom + 4}px`;
  menu.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - menu.offsetWidth - 8))}px`;
  setTimeout(() => {
    document.addEventListener('click', closeToolMenuOutside);
    document.addEventListener('keydown', closeToolMenuKey);
  });
}
function closeToolMenuOutside(e) { if (!e.target.closest('#toolMenu')) closeToolMenu(); }
function closeToolMenuKey(e) { if (e.key === 'Escape') closeToolMenu(); }
function closeToolMenu() {
  document.removeEventListener('click', closeToolMenuOutside);
  document.removeEventListener('keydown', closeToolMenuKey);
  $('#toolMenu')?.remove();
}

// Kinds that refuse to draw without a Y column (as in plotting._draw_panel).
const Y_KINDS = new Set(['line', 'scatter', 'step', 'area', 'errorbar', 'regression', 'stem', 'polar', 'hexbin',
  'hist2d', 'contour', 'surface3d', 'scatter3d', 'waterfall']);

async function setKind(kind) {
  const need = kindNeeds(kind);
  if (need.length && !(await ensureModules(need))) return;
  state.spec.kind = kind;
  if (['corr', 'pairplot'].includes(kind) && state.spec.y.length < 2 && state.dataset) {
    state.spec.y = state.dataset.columns.filter(c => c.kind === 'numeric').slice(0, 5).map(c => c.name);
  }
  // Kinds drawn against X need a Y column: a histogram has none, so going from it to Lines took the first
  // numeric one only when the user found it, and until then every redraw was refused.
  if (Y_KINDS.has(kind) && !state.spec.y.length && state.dataset) {
    const first = state.dataset.columns.find(c => c.kind === 'numeric' && c.name !== state.spec.x);
    if (first) state.spec.y = [first.name];
  }
  buildKindGallery();
  buildKindOptions();
  buildMapping(false);
  updateHints();
  scheduleRender(0);
}

function buildKindOptions() {
  const box = $('#kindOptions');
  box.innerHTML = '';
  const opts = KIND_OPTS[state.spec.kind] || [];
  const wrap = document.createElement('div');
  wrap.className = 'grid2';
  opts.forEach(name => {
    const def = OPT_DEF[name];
    const path = 'style.' + name;
    if (def.type === 'check') {
      const lab = document.createElement('label');
      lab.className = 'check';
      lab.style.gridColumn = '1 / -1';
      lab.innerHTML = `<input type="checkbox" data-path="${path}"><span></span>`;
      lab.querySelector('span').textContent = t('opt.' + name);
      box.append(lab);
      return;
    }
    const f = document.createElement('div');
    f.className = 'field';
    const label = document.createElement('label');
    label.textContent = t('opt.' + name);
    f.append(label);
    let input;
    if (def.type === 'select') {
      input = document.createElement('select');
      fillSelect(input, def.options.map(o => [o, t(def.prefix + o)]));
    } else {
      input = document.createElement('input');
      input.type = def.type === 'nullable' ? 'text' : 'number';
      input.placeholder = 'auto';
      ['min', 'max', 'step'].forEach(a => { if (def[a] !== undefined) input[a] = def[a]; });
      input.dataset.type = def.type === 'nullable' ? 'nullable' : 'number';
    }
    input.dataset.path = path;
    f.append(input);
    wrap.append(f);
  });
  if (wrap.children.length) box.prepend(wrap);
  $$('[data-path]', box).forEach(el => writeControl(el, getPath(state.spec, el.dataset.path)));
  const usesCmap = ['heatmap', 'contour', 'hexbin', 'hist2d', 'surface3d'].includes(state.spec.kind) || (state.spec.kind === 'scatter' && state.spec.z);
  $('[data-for="cmap"]').classList.toggle('disabled', !usesCmap);
}

// ------------------------------------------------------------------ mapping
function columnOptions(includeNone, noneLabel) {
  const cols = state.dataset ? state.dataset.columns : [];
  const items = includeNone ? [['', noneLabel || t('map.none')]] : [];
  return items.concat(cols.map(c => [c.name, c.name]));
}
const KIND_TAG = { numeric: '123', category: 'abc', datetime: 'date' };

// Choice of several columns, quick with tens of thousands of them: the rows are drawn a page at a
// time as the list scrolls. "All" and "None" act on the columns the filter shows; Shift+click ticks
// or clears a whole block; the filter also takes a range of numeric names (19600-19840) or of
// positions (#1-500). Returns {get, set}; onChange gets the chosen names in column order.
const PICK_PAGE = 200;
const PICK_TOOLS_FROM = 8;          // fewer columns: just the list

function columnPicker(box, { columns, selected, onChange, tags = true, pickable = c => c.kind === 'numeric' }) {
  box.innerHTML = '';
  box.classList.add('col-pick');
  const names = columns.map(c => c.name);
  const known = new Set(names);
  const sel = new Set(selected.filter(n => known.has(n)));
  let shown = names.map((_, i) => i);
  let drawn = 0;
  let anchor = null;                // position in `shown` of the last row ticked
  let shift = false;

  const list = document.createElement('div');
  list.className = 'checklist';
  list.title = t('pick.shift');
  const tools = document.createElement('div');
  tools.className = 'pick-tools';
  tools.innerHTML = '<input type="search" class="pick-filter" spellcheck="false"><button type="button" class="btn small pick-all"></button><button type="button" class="btn small pick-none"></button><span class="pick-count"></span>';
  const filter = tools.querySelector('.pick-filter');
  filter.placeholder = t('pick.filter');
  filter.title = t('pick.filter_help');
  tools.querySelector('.pick-all').textContent = t('pick.all');
  tools.querySelector('.pick-all').title = t('pick.all_help');
  tools.querySelector('.pick-none').textContent = t('pick.none');
  const count = tools.querySelector('.pick-count');
  if (names.length >= PICK_TOOLS_FROM) box.append(tools);
  box.append(list);

  const row = k => {
    const c = columns[shown[k]];
    const lab = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = c.name;
    cb.dataset.k = k;
    cb.checked = sel.has(c.name);
    const name = document.createElement('span');
    name.textContent = c.name;
    lab.append(cb, name);
    if (tags) {
      const tag = document.createElement('span');
      tag.className = 'kind-tag';
      tag.textContent = KIND_TAG[c.kind] || c.kind;
      lab.append(tag);
    }
    return lab;
  };
  const more = () => {
    const page = document.createDocumentFragment();
    const end = Math.min(shown.length, drawn + PICK_PAGE);
    for (let k = drawn; k < end; k++) page.append(row(k));
    drawn = end;
    list.append(page);
  };
  const redraw = () => {
    list.innerHTML = '';
    drawn = 0;
    anchor = null;
    if (!shown.length && names.length) list.innerHTML = `<p class="small muted">${t('pick.nomatch')}</p>`;
    more();
  };
  const showCount = () => {
    let n = 0;
    names.forEach(x => { if (sel.has(x)) n++; });
    count.textContent = t('pick.count', { n: n.toLocaleString(LOCALE()), total: names.length.toLocaleString(LOCALE()) }) +
      (shown.length < names.length ? ` · ${t('pick.shown', { n: shown.length.toLocaleString(LOCALE()) })}` : '');
  };
  const tickDrawn = () => $$('input', list).forEach(i => { i.checked = sel.has(i.value); });
  const changed = () => { showCount(); onChange(names.filter(n => sel.has(n))); };

  list.addEventListener('scroll', () => {
    if (drawn < shown.length && list.scrollTop + list.clientHeight > list.scrollHeight - 300) more();
  });
  list.addEventListener('pointerdown', e => { shift = e.shiftKey; }, true);
  list.addEventListener('keydown', e => { shift = e.shiftKey; }, true);
  list.addEventListener('change', e => {
    const k = Number(e.target.dataset.k);
    const on = e.target.checked;
    const [lo, hi] = shift && anchor !== null ? [Math.min(anchor, k), Math.max(anchor, k)] : [k, k];
    for (let j = lo; j <= hi; j++) on ? sel.add(names[shown[j]]) : sel.delete(names[shown[j]]);
    if (hi > lo) tickDrawn();
    anchor = k;
    shift = false;
    changed();
  });
  tools.querySelector('.pick-all').onclick = () => {
    shown.forEach(i => { if (pickable(columns[i])) sel.add(names[i]); });
    tickDrawn();
    changed();
  };
  tools.querySelector('.pick-none').onclick = () => {
    shown.forEach(i => sel.delete(names[i]));
    tickDrawn();
    changed();
  };
  let timer = null;
  filter.oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      shown = matchColumns(names, filter.value);
      redraw();
      showCount();
    }, 120);
  };

  redraw();
  showCount();
  return {
    get: () => names.filter(n => sel.has(n)),
    set(list) { sel.clear(); list.forEach(n => { if (known.has(n)) sel.add(n); }); tickDrawn(); showCount(); },
  };
}

// Positions of the columns that match a filter: text in the name, or a range "a-b" (also a..b, a:b)
// of numeric names, or "#a-b" of positions counted from 1.
function matchColumns(names, query) {
  const q = query.trim();
  const all = names.map((_, i) => i);
  if (!q) return all;
  const low = q.toLocaleLowerCase();
  const text = i => names[i].toLocaleLowerCase().includes(low);
  const m = q.match(/^(#)?\s*(-?\d+(?:[.,]\d+)?)\s*(?:\.\.|[-–:])\s*(-?\d+(?:[.,]\d+)?)$/);
  if (!m) return all.filter(text);
  const [a, b] = [m[2], m[3]].map(v => Number(v.replace(',', '.')));
  const [lo, hi] = [Math.min(a, b), Math.max(a, b)];
  const inRange = m[1]
    ? i => i + 1 >= lo && i + 1 <= hi
    : i => { const s = names[i].trim(); const v = Number(s.replace(',', '.')); return s !== '' && Number.isFinite(v) && v >= lo && v <= hi; };
  return all.filter(i => inRange(i) || text(i));
}

function buildChecklist(box, selected, key) {
  box.picker = columnPicker(box, {
    columns: state.dataset?.columns || [],
    selected,
    pickable: c => c.kind === 'numeric' && c.name !== state.spec.x,
    onChange: list => {
      state.spec[key] = list;
      buildSeries();
      refreshRecommend();
      scheduleRender(0);
    },
  });
}

function buildMapping(rebuildLists = true) {
  if (!state.dataset) return;
  const s = state.spec;
  const inputs = state.meta.kinds[s.kind].inputs;
  const cat = ['box', 'violin', 'strip', 'swarm'].includes(s.kind);
  const dist = state.meta.kinds[s.kind].group === 'dist';
  $$('#mappingCard [data-role]').forEach(el => { el.hidden = !inputs.includes(el.dataset.role); });
  $('[data-role="y2"]').hidden = !state.meta.twin_kinds.includes(s.kind);
  $('[data-role="x"] label').textContent = cat ? t('map.groups') : t('map.x');
  $('[data-role="y"] label').textContent = (cat || dist) ? t('map.values') : t('map.y');
  const selects = { mapX: ['x', true, t('map.index')], mapHue: ['hue', true], mapZ: ['z', true], mapXerr: ['xerr', true], mapYerr: ['yerr', true] };
  Object.entries(selects).forEach(([id, [key, none, noneLabel]]) => {
    const sel = $('#' + id);
    fillSelect(sel, columnOptions(none, noneLabel), s[key] || '');
    sel.onchange = () => {
      s[key] = sel.value || null;
      if (key === 'z') buildKindOptions();
      if (key === 'hue') buildSeries();
      refreshRecommend();
      scheduleRender(0);
    };
  });
  if (rebuildLists || !$('#mapY').picker) {
    buildChecklist($('#mapY'), s.y, 'y');
    buildChecklist($('#mapY2'), s.y2, 'y2');
  } else {
    $('#mapY').picker.set(s.y);
  }
}

// ------------------------------------------------------------------ series styling
// Colour of a layer as the last figure drew it (null before the first render of this figure).
const drawnOverlayColor = o => (state.drawnOverlays && state.drawnOverlays.spec === state.spec && state.drawnOverlays.color[o.id]) || null;

// After a render: show in the Overlays panel the colours the layers really got.
function syncOverlayColors() {
  $$('#overlayList .overlay-row').forEach(row => {
    const o = (state.spec.overlays || []).find(x => x.id === row.dataset.id);
    const input = row.querySelector('input[type=color]');
    const real = o && drawnOverlayColor(o);
    if (real && document.activeElement !== input) input.value = real;
  });
}

function buildOverlays() {
  const list = state.spec.overlays || [];
  const notes = state.spec.notes || [];
  $('#overlayCard').hidden = !list.length && !notes.length;
  $('#overlayCount').textContent = (list.length + notes.length) || '';
  const box = $('#overlayList');
  box.innerHTML = '';
  buildNotes(box, notes);
  buildRefs();
  const pal = paletteColors();
  list.forEach((o, i) => {
    o.style = o.style || {};
    const row = document.createElement('div');
    row.className = 'overlay-row' + (o.hidden ? ' hidden-layer' : '');
    row.dataset.id = o.id;
    row.innerHTML = `<div class="src"></div><input type="color"><input type="text"><button class="reset" type="button">✕</button>
      <div class="opts"><select class="ls"></select><div class="mk-row"><select class="mk"></select><input type="number" class="ms" step="0.5" min="0"></div>
      <label class="check"><input type="checkbox" class="band"><span></span></label>
      <label class="check"><input type="checkbox" class="show"><span></span></label>
      <label class="check"><input type="checkbox" class="note"><span></span></label></div>`;
    row.querySelector('.src').textContent = o.source_name || '';
    const color = row.querySelector('input[type=color]');
    const fixed = /^#[0-9a-f]{6}$/i.test(o.style.color || '') ? o.style.color : null;
    color.value = fixed || drawnOverlayColor(o) || pal[(state.spec.y.length + i) % (pal.length || 1)] || '#000000';
    const label = row.querySelector('input[type=text]');
    label.value = o.label || '';
    const ls = row.querySelector('.ls');
    fillSelect(ls, [...LINESTYLES.map(v => [v, t('ls.' + v)]), ['none', t('ov.markers')]], o.style.linestyle || '-');
    // The layer's own markers (e.g. peak markers): shape and size, independent of the series' markers.
    const mk = row.querySelector('.mk');
    fillSelect(mk, MARKERS.map(v => [v, `${t('ov.marker')}: ${t('mk.' + v)}`]), o.style.marker || '');
    const ms = row.querySelector('.ms');
    ms.value = o.style.markersize ?? '';
    ms.placeholder = 'auto';
    ms.title = t('ov.marker_size');
    const band = row.querySelector('.band');
    band.checked = o.band !== false && !!(o.lo && o.hi);
    band.disabled = !(o.lo && o.hi);
    band.nextElementSibling.textContent = o.band_label ? `${t('ov.band')} (${o.band_label})` : t('ov.band');
    const show = row.querySelector('.show');
    show.checked = !o.hidden;
    show.nextElementSibling.textContent = t('ov.visible');
    // The box of values an analysis wrote for this layer (e.g. a fit's μ, σ, R²): shown unless unticked.
    const note = row.querySelector('.note');
    note.closest('label').hidden = !o.note;
    note.checked = o.note_shown !== false;
    note.nextElementSibling.textContent = t('ov.note');
    note.onchange = () => { o.note_shown = note.checked; scheduleRender(0); };
    color.oninput = () => { o.style.color = color.value; scheduleRender(250); };
    label.oninput = () => { o.label = label.value; scheduleRender(400); };
    ls.onchange = () => {
      o.style.linestyle = ls.value;
      if (ls.value === 'none' && !o.style.marker) { o.style.marker = 'o'; mk.value = 'o'; }   // something must show
      scheduleRender(0);
    };
    mk.onchange = () => {
      o.style.marker = mk.value || null;
      if (!mk.value && o.style.linestyle === 'none') { o.style.linestyle = '-'; ls.value = '-'; }
      scheduleRender(0);
    };
    ms.oninput = () => {
      if (ms.value === '' || !(Number(ms.value) >= 0)) delete o.style.markersize; else o.style.markersize = Number(ms.value);
      scheduleRender(300);
    };
    band.onchange = () => { o.band = band.checked; scheduleRender(0); };
    show.onchange = () => { o.hidden = !show.checked; row.classList.toggle('hidden-layer', o.hidden); scheduleRender(0); };
    const rm = row.querySelector('.reset');
    rm.title = t('ov.remove');
    rm.onclick = () => { state.spec.overlays.splice(i, 1); buildOverlays(); scheduleRender(0); };
    box.append(row);
  });
}

// Boxes of values put in the figure from any analysis (spec.notes): text, colour, visible, remove. A box rewritten
// on the figure (double-click) keeps its text in spec.texts until it is edited here.
function buildNotes(box, notes) {
  notes.forEach((n, i) => {
    const key = `note:${n.id}`;
    const row = document.createElement('div');
    row.className = 'overlay-row' + (n.hidden ? ' hidden-layer' : '');
    row.innerHTML = `<div class="src"></div><input type="color"><textarea class="note-text" rows="2" spellcheck="false"></textarea>
      <button class="reset" type="button">✕</button><div class="opts"><label class="check"><input type="checkbox" class="show"><span></span></label></div>`;
    row.querySelector('.src').textContent = t('ov.box') + (n.source ? ` · ${n.source}` : '');
    const color = row.querySelector('input[type=color]');
    color.value = /^#[0-9a-f]{6}$/i.test(n.color || '') ? n.color : '#222222';
    color.oninput = () => { n.color = color.value; scheduleRender(250); };
    const text = row.querySelector('textarea');
    text.value = (state.spec.texts || {})[key] ?? n.text;
    text.oninput = () => { n.text = text.value; if (state.spec.texts) delete state.spec.texts[key]; scheduleRender(400); };
    const show = row.querySelector('.show');
    show.checked = !n.hidden;
    show.nextElementSibling.textContent = t('ov.visible');
    show.onchange = () => { n.hidden = !show.checked; row.classList.toggle('hidden-layer', n.hidden); scheduleRender(0); };
    const rm = row.querySelector('.reset');
    rm.title = t('ov.remove');
    rm.onclick = () => {
      notes.splice(i, 1);
      if (state.spec.texts) delete state.spec.texts[key];
      if (state.spec.moved) delete state.spec.moved[key];
      buildOverlays();
      scheduleRender(0);
    };
    box.append(row);
  });
}

// Reference lines and bands (spec.refs): vertical at an x or horizontal at a y, a band when "to" is given.
// A new one is placed by clicking on the figure (one click for a line, two for a band); the numbers can be typed.
function buildRefs() {
  const refs = state.spec.refs || [];
  $('#refCount').textContent = refs.length || '';
  const box = $('#refList');
  box.innerHTML = '';
  refs.forEach((r, i) => {
    const row = document.createElement('div');
    row.className = 'overlay-row' + (r.hidden ? ' hidden-layer' : '');
    row.innerHTML = `<div class="src"></div><input type="color"><input type="text" class="label"><button class="reset" type="button">✕</button>
      <div class="opts"><select class="axis"></select><div class="ref-pos"><input type="text" class="value"><input type="text" class="to"><select class="ls"></select></div>
      <button class="btn small pick" type="button"></button><label class="check"><input type="checkbox" class="show"><span></span></label></div>`;
    const band = () => r.to !== undefined && r.to !== null && r.to !== '';
    const src = row.querySelector('.src');
    const title = () => { src.textContent = t(band() ? 'ref.band' : 'ref.line'); };
    title();
    const color = row.querySelector('input[type=color]');
    color.value = /^#[0-9a-f]{6}$/i.test(r.color || '') ? r.color : (band() ? '#8a8a8a' : '#555555');
    color.oninput = () => { r.color = color.value; scheduleRender(250); };
    const label = row.querySelector('.label');
    label.placeholder = t('ref.label');
    label.value = r.label || '';
    label.oninput = () => { r.label = label.value; if (state.spec.texts) delete state.spec.texts[`ref:${r.id}`]; scheduleRender(400); };
    const axis = row.querySelector('.axis');
    fillSelect(axis, [['x', t('ref.axis_x')], ['y', t('ref.axis_y')]], r.axis);
    axis.onchange = () => { r.axis = axis.value; scheduleRender(0); };
    const value = row.querySelector('.value');
    value.placeholder = t('ref.at');
    value.title = t('ref.at');
    value.value = r.value ?? '';
    value.oninput = () => { r.value = value.value.trim(); scheduleRender(500); };
    const to = row.querySelector('.to');
    to.placeholder = t('ref.to');
    to.title = t('ref.to');
    to.value = r.to ?? '';
    to.oninput = () => { r.to = to.value.trim() || null; title(); ls.disabled = band(); scheduleRender(500); };
    const ls = row.querySelector('.ls');
    fillSelect(ls, LINESTYLES.map(v => [v, t('ls.' + v)]), r.linestyle || '--');
    ls.disabled = band();
    ls.onchange = () => { r.linestyle = ls.value; scheduleRender(0); };
    const pick = row.querySelector('.pick');
    pick.textContent = t('ref.pick');
    pick.onclick = () => placeRef(r, band());
    const show = row.querySelector('.show');
    show.checked = !r.hidden;
    show.nextElementSibling.textContent = t('ov.visible');
    show.onchange = () => { r.hidden = !show.checked; row.classList.toggle('hidden-layer', r.hidden); scheduleRender(0); };
    const rm = row.querySelector('.reset');
    rm.title = t('ov.remove');
    rm.onclick = () => {
      refs.splice(i, 1);
      if (state.spec.texts) delete state.spec.texts[`ref:${r.id}`];
      if (state.spec.moved) delete state.spec.moved[`ref:${r.id}`];
      buildRefs();
      scheduleRender(0);
    };
    box.append(row);
  });
}

// Click on the figure where a reference goes: its x (vertical) or y (horizontal); a band takes two clicks.
function placeRef(r, band) {
  const got = [];
  const ok = startPick({
    owner: $('#refList'),
    hint: t(band ? 'ref.pick_band' : 'ref.pick_line'),
    marks: () => [],
    onPoint: ({ x, y }) => {
      got.push(r.axis === 'x' ? x : y);
      if (band && got.length < 2) return;
      r.value = got[0];
      if (band) r.to = got[1];
      stopPick();
      buildRefs();
      scheduleRender(0);
    },
  });
  if (!ok) buildRefs();
}

function addRef(band) {
  state.spec.refs = state.spec.refs || [];
  const g = (state.axesGeom || [])[0];
  const mid = g ? axisText((g.xlim[0] + g.xlim[1]) / 2, g.xlim, g.xscale) : 0;
  const r = { id: newId(), axis: 'x', value: mid, to: null, label: '', linestyle: '--' };
  if (band && g) r.to = axisText(g.xlim[0] + (g.xlim[1] - g.xlim[0]) * 0.6, g.xlim, g.xscale);
  state.spec.refs.push(r);
  $('#refCard').open = true;
  buildRefs();
  scheduleRender(0);
  placeRef(r, band);
}

function newSession() {
  if (state.dataset && !confirm(t('new.confirm'))) return;
  clearDataset();
  state.spec = merge(state.defaults, store.get('pp-style', {}));
  state.spec.overlays = [];
  Bus.emit('session:new');
  setDataError('');
  $('#fileInput').value = '';
  $('#tableSelect').innerHTML = '';
  $('#seriesList').innerHTML = '';
  syncControls();
  buildKindGallery();
  buildKindOptions();
  buildOverlays();
  updateFigInfo();
  setTab('figure');
  toast(t('new.done'));
}

// The series the last figure really drew, in drawing order: [{key, label, color}] (sent by the server
// with each render). The Series panel shows exactly these rows and colours, so panel = figure.
function seriesDrawn(header) {
  let list = null;
  try { list = header ? JSON.parse(decodeURIComponent(header)) : null; } catch (e) { list = null; }
  if (!Array.isArray(list)) return;
  // Analysis layers: their real colours go to the Overlays panel.
  state.drawnOverlays = { spec: state.spec, color: Object.fromEntries(list.filter(e => e.overlay).map(e => [e.overlay, e.color])) };
  syncOverlayColors();
  list = list.filter(e => !e.overlay);
  state.drawn = { list, spec: state.spec };
  const box = $('#seriesList');
  // Other rows than the figure's series (categories, groups, another view): rebuild the panel,
  // unless the user is typing in it. In every case the swatches take the colours really drawn,
  // also when the panel was built (with a guess) before this render.
  const shown = $$('.series', box).map(r => r.dataset.key).join('\u0002');
  if (shown !== list.map(e => e.key).join('\u0002') && !box.contains(document.activeElement)) {
    buildSeriesRows();
    return;
  }
  const color = Object.fromEntries(list.map(e => [e.key, e.color]));
  $$('.series', box).forEach(row => {
    const input = row.querySelector('input[type=color]');
    if (color[row.dataset.key] && document.activeElement !== input) input.value = color[row.dataset.key];
  });
}

function buildSeries() {
  buildOverlays();
  buildSeriesRows();
}

// One row per series, as many as the figure reports colours for (plotting.ColorLog.MAX_SERIES).
const MAX_SERIES_ROWS = 200;

function buildSeriesRows() {
  const box = $('#seriesList');
  box.innerHTML = '';
  const s = state.spec;
  const cols = [...s.y, ...(state.meta.twin_kinds.includes(s.kind) ? s.y2 : [])];
  const extraAll = (window.Files && !viewDataset()) ? Files.extraSpec().flatMap(e =>
    e.y.map(c => ({ key: `${e.id}:${c}`, title: `${e.name} · ${c}` }))) : [];
  const extraRows = (s.layout || {}).mode !== 'panels' ? extraAll : [];
  const base = [...cols.map(c => ({ key: c, title: c })), ...extraRows];
  const titles = Object.fromEntries([...base, ...extraAll].map(r => [r.key, r.title]));
  const titleOf = key => titles[key] || (key.includes('::') ? key.split('::').map((k, i) => (i ? k : titles[k] || k)).join(' · ') : key);
  // After a render of this figure: its real series (groups and categories included) and colours.
  const drawn = state.drawn && state.drawn.spec === s ? state.drawn.list : null;
  if (drawn && !drawn.length) {        // drawn, but this kind of figure has no colour per series
    box.innerHTML = `<p class="small muted">${t('series.none')}</p>`;
    return;
  }
  const rows = drawn ? drawn.map(e => ({ key: e.key, title: titleOf(e.key), color: e.color })) : (s.hue ? [] : base);
  if (!rows.length) {
    box.innerHTML = `<p class="small muted">${t('series.empty')}</p>`;
    return;
  }
  const pal = paletteColors(s.style.palette);
  rows.slice(0, MAX_SERIES_ROWS).forEach(({ key: col, title, color: real }, i) => {
    const over = s.series[col] || {};
    const row = document.createElement('div');
    row.className = 'series';
    row.dataset.key = col;
    row.innerHTML = `<div class="name"><span></span><button class="reset" type="button"></button></div>
      <input type="color"><input type="text">
      <div class="opts"><select class="ls"></select><select class="mk"></select><input type="number" class="lw" step="0.1" min="0"></div>`;
    row.querySelector('.name span').textContent = title;
    row.querySelector('.reset').textContent = t('series.reset');
    const color = row.querySelector('input[type=color]');
    color.value = over.color || real || pal[i % (pal.length || 1)] || '#000000';
    const label = row.querySelector('input[type=text]');
    label.placeholder = title;
    label.title = t('series.label');
    label.value = over.label || '';
    const ls = row.querySelector('.ls');
    fillSelect(ls, [['', '—'], ...LINESTYLES.map(v => [v, t('ls.' + v)])], over.linestyle || '');
    const mk = row.querySelector('.mk');
    fillSelect(mk, [['__', '—'], ...MARKERS.map(v => [v, t('mk.' + v)])], over.marker === undefined ? '__' : over.marker);
    const lw = row.querySelector('.lw');
    lw.placeholder = String(s.style.linewidth);
    lw.value = over.linewidth ?? '';
    const update = () => {
      const o = {};
      if (color.dataset.touched || over.color) o.color = color.value;
      if (label.value) o.label = label.value;
      if (ls.value) o.linestyle = ls.value;
      if (mk.value !== '__') o.marker = mk.value;
      if (lw.value !== '') o.linewidth = Number(lw.value);
      if (Object.keys(o).length) s.series[col] = o; else delete s.series[col];
      scheduleRender(250);
    };
    color.oninput = () => { color.dataset.touched = '1'; update(); };
    [label, lw].forEach(el => { el.oninput = update; });
    [ls, mk].forEach(el => { el.onchange = update; });
    row.querySelector('.reset').onclick = () => { delete s.series[col]; buildSeriesRows(); scheduleRender(0); };
    box.append(row);
  });
  if (rows.length > MAX_SERIES_ROWS) {
    const p = document.createElement('p');
    p.className = 'small muted';
    p.textContent = t('series.more', { n: (rows.length - MAX_SERIES_ROWS).toLocaleString(LOCALE()) });
    box.append(p);
  }
}

// ------------------------------------------------------------------ recommendations & hints
let recTimer = null;
function refreshRecommend() {
  clearTimeout(recTimer);
  recTimer = setTimeout(async () => {
    if (!state.dataset) return;
    try {
      const s = state.spec;
      const r = await api('/api/recommend', { dataset_id: state.dataset.dataset_id, kind: s.kind,
        mapping: { x: s.x, y: s.y, z: s.z, hue: s.hue, xerr: s.xerr, yerr: s.yerr } });
      state.recommend = r.recommend;
      state.warnings = r.warnings;
      buildKindGallery();
      updateHints();
    } catch (e) { /* recommendations are optional */ }
  }, 150);
}

function updateHints() {
  const box = $('#hints');
  box.innerHTML = '';
  if (!state.dataset) return;
  const top = state.recommend.slice(0, 4);
  if (top.length) {
    const span = document.createElement('span');
    span.className = 'hint';
    span.append(t('rec.title') + ' ');
    top.forEach((r, i) => {
      const chip = document.createElement('button');
      chip.className = 'chip';
      chip.textContent = `${t('kind.' + r.kind)} · ${t('rec.reason.' + r.reason)}`;
      chip.onclick = () => setKind(r.kind);
      if (r.kind === state.spec.kind) chip.style.borderColor = 'var(--accent)';
      span.append(chip, i < top.length - 1 ? ' ' : '');
    });
    box.append(span);
  }
  (state.warnings || []).forEach(w => {
    const span = document.createElement('span');
    span.className = 'hint';
    span.innerHTML = '<span class="warn">⚠</span> ';
    span.append(t('warn.' + w));
    box.append(span);
  });
}
