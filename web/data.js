// π-plotter interface — Opening data (files, examples), the data table hook and the copies of the figure with analyses.
// The page is split into classic scripts loaded in order (see index.html); they share one global scope.
'use strict';

// ------------------------------------------------------------------ data loading
function resetDataSpec(mapping, s = state.spec) {
  Object.assign(s, { kind: mapping.kind || 'line', x: mapping.x, y: mapping.y || [], y2: [], hue: null, z: mapping.z || null,
    xerr: mapping.xerr || null, yerr: mapping.yerr || null, series: {}, overlays: [], notes: [], refs: [] });
  s.inset = { ...(s.inset || {}), show: false, xmin: null, xmax: null, ymin: null, ymax: null };
  ['title', 'xlabel', 'ylabel', 'y2label', 'zlabel'].forEach(k => { s.text[k] = ''; });
  ['xmin', 'xmax', 'ymin', 'ymax', 'y2min', 'y2max', 'zmin', 'zmax'].forEach(k => { s.axes[k] = null; });
  s.moved = {};
  s.texts = {};
  s.legend.pos = null;
  zoomStacks.delete(s);
  s.style.vmin = null;
  s.style.vmax = null;
}

function applyDataset(ds, keepSpec = false) {
  if (!keepSpec) stashViews();   // copies belong to the data they were made from
  state.dataset = ds;
  state.source = ds.source;
  if (!ds.source || !ds.source.analysis) state.history = [];
  Bus.emit('dataset', { ds, keepSpec });
  state.recommend = ds.recommend || [];
  state.warnings = [];
  if (!keepSpec) resetDataSpec(ds.mapping);
  $('#datasetName').textContent = ds.name;
  $('#mappingCard').hidden = false;
  $('#emptyState').hidden = true;
  const base = (ds.name || 'figure').split(/[\\/›]/).pop().trim().replace(/\.[^.]+$/, '').replace(/[^\w.-]+/g, '_')
    .replace(/^_+|_+$/g, '').slice(0, 60);
  $('#exportName').value = base || 'figure';
  syncControls();
  buildKindGallery();
  buildKindOptions();
  buildMapping(true);
  buildSeries();
  buildTable();
  updateHints();
  updateFigInfo();
  if (state.tab === 'table' && !keepSpec) setTab('figure');     // a new table edit keeps the user in the table
  Bus.emit('dataset:shown', { ds });
  scheduleRender(0);
}

function setUpload(show, frac, text) {
  $('#uploadBox').hidden = !show;
  if (show) {
    $('#uploadBar').style.width = Math.round(frac * 100) + '%';
    $('#uploadText').textContent = text;
  }
}

function uploadFile(file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.setRequestHeader('X-Token', TOKEN);
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) setUpload(true, e.loaded / e.total, t('data.uploading', { name: file.name, pct: Math.round(100 * e.loaded / e.total) }));
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
      if (data.code === 'token') reloadForNewSession();
      if (xhr.status >= 400) reject(new ApiError(data.error || xhr.statusText, xhr.status, data));
      else resolve(data);
    };
    xhr.onerror = () => reject(new ApiError(t('error.network'), 0, { code: 'network' }));
    xhr.send(file);
  });
}

// Upload one file and read its first table; returns {ds, info} without showing it.
async function loadFile(file) {
  setUpload(true, 0, t('data.uploading', { name: file.name, pct: 0 }));
  let info = await uploadFile(file);
  setUpload(true, 1, t('data.reading', { name: file.name }));
  if (info.missing.length) {
    const ok = await ensureModules(info.missing, 'install.reason.file', { name: file.name });
    if (!ok) return null;
    info = await api('/api/file', { file_id: info.file_id });
  }
  let ds = await api('/api/open', { file_id: info.file_id, table: info.tables[0], options: {} });
  setUpload(false);
  ds = await askConversion(ds, info, {});
  return { ds, info };
}

// Columns written like "1,003.3": ask before turning them into numbers; returns the data set to use.
async function askConversion(ds, info, baseOptions) {
  const sug = ((ds.options || {}).suggestions || []);
  if (!sug.length || !info) return ds;
  const dlg = $('#convertDialog');
  $('#convertText').textContent = t('conv.text', { file: info.name });
  const list = $('#convertList');
  list.innerHTML = '';
  sug.forEach(sg => {
    const li = document.createElement('li');
    const lab = document.createElement('label');
    lab.className = 'check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.dataset.col = sg.column;
    cb.dataset.style = sg.style;
    const b = document.createElement('b');
    b.textContent = sg.column;
    lab.append(cb, b);
    const small = document.createElement('small');
    small.textContent = t('conv.item', { example: sg.example, value: sg.value, count: sg.count.toLocaleString(LOCALE()),
      rows: sg.rows.toLocaleString(LOCALE()), style: t('conv.style.' + sg.style) });
    li.append(lab, small);
    list.append(li);
  });
  const answer = await new Promise(resolve => {
    dlg.onclose = () => resolve(dlg.returnValue || 'no');
    dlg.returnValue = '';
    dlg.showModal();
  });
  const convert = {};
  $$('input[type=checkbox]', list).forEach(cb => {
    convert[cb.dataset.col] = answer === 'yes' && cb.checked ? cb.dataset.style : 'none';
  });
  info.convert = convert;                  // remembered for this file (import options, reloads)
  if (!Object.values(convert).some(v => v !== 'none')) {
    ds.source = { ...ds.source, options: { ...(ds.source.options || {}), convert } };
    return ds;
  }
  const table = (ds.source && ds.source.table) || info.tables[0];
  const fresh = await api('/api/open', { file_id: info.file_id, table, options: { ...baseOptions, convert } });
  toast(t('conv.done'));
  return fresh;
}

function showFileControls(info) {
  state.file = info || null;
  const sel = $('#tableSelect');
  if (!info) {
    $('#tableField').hidden = true;
    $('#importOptions').hidden = true;
    return;
  }
  fillSelect(sel, info.tables.map(n => [n, n]));
  $('#tableField').hidden = info.tables.length < 2;
  sel.onchange = () => openTable(sel.value);
  const textual = info.format === 'text';
  const sheet = ['excel', 'xls', 'ods'].includes(info.format);
  $('#importOptions').hidden = !(textual || sheet);
  $$('[data-import="sep"], [data-import="decimal"]').forEach(el => { el.closest('.field').hidden = !textual; });
  $$('[data-import]').forEach(el => { el.value = el.tagName === 'SELECT' ? 'auto' : ''; });
}

// Open one or more files. The first becomes the figure; files opened together are combined in it.
async function openFiles(files) {
  files = Array.from(files || []).filter(Boolean);
  // A project (.piplot) opens as the whole work it was saved with.
  const project = files.find(f => window.Project && Project.isProject(f));
  if (project) return Project.open(project);
  if (!files.length) return;
  setDataError('');
  const loaded = [];
  for (const file of files) {
    try {
      const r = await loadFile(file);
      if (r) loaded.push(r);
    } catch (e) {
      setDataError(`${file.name}: ${e.message}`);
      if (e.code === 'missing_modules') handleError(e);
    }
  }
  setUpload(false);
  if (!loaded.length) return;
  loaded.forEach((r, i) => {
    const same = Files.list().find(e => e.ds.name === r.ds.name);
    if (same) Files.replace(same.id, r.ds, r.info);        // the same file again: refresh it
    else Files.add(r.ds, r.info, files.length > 1 && i > 0);
  });
  const first = loaded[0];
  showFileControls(first.info);
  applyDataset(first.ds);
  setTab('figure');
  toast(loaded.length > 1 ? t('files.opened', { n: loaded.length })
    : t('data.loaded', { rows: first.ds.rows.toLocaleString(LOCALE()), cols: first.ds.columns.length }));
}

const openFile = file => openFiles([file]);

function setDataError(message) {
  const box = $('#dataError');
  box.textContent = message || '';
  box.hidden = !message;
}

function importOptions() {
  const o = {};
  $$('[data-import]').forEach(el => {
    let v = el.value;
    if (v === '' || v === 'auto') return;
    if (el.dataset.import === 'sep' && v === '\t') v = '\t';
    o[el.dataset.import] = el.dataset.import === 'skiprows' ? Number(v) : v;
  });
  if (state.file && state.file.convert) o.convert = state.file.convert;
  return o;
}

async function openTable(table) {
  if (!state.file) return;
  try {
    const old = state.dataset && state.dataset.dataset_id;
    let ds = await api('/api/open', { file_id: state.file.file_id, table, options: importOptions() });
    ds = await askConversion(ds, state.file, importOptions());
    Files.replace(old, ds, state.file);
    applyDataset(ds);
    setTab('figure');
    setDataError('');
    const o = ds.options || {};
    if (o.sep !== undefined) {
      const sepSel = $('[data-import="sep"]');
      sepSel.dataset.detected = o.sep;
    }
    toast(t('data.loaded', { rows: ds.rows.toLocaleString(LOCALE()), cols: ds.columns.length }));
  } catch (e) {
    handleError(e, () => openTable(table));
  }
}

async function openSample(name) {
  try {
    showFileControls(null);
    const ds = await api('/api/sample', { name });
    Files.add(ds, null, false);
    applyDataset(ds);
    setTab('figure');
    setDataError('');
  } catch (e) {
    handleError(e, () => openSample(name));
  }
}

async function reopenSource() {
  // After a restart result figures point to data the service no longer has: close them.
  if (viewDataset()) showView(null);
  state.views = state.views.filter(v => !v.dataset);
  renderViewTabs();
  const src = state.source;
  if (!src) return;
  try {
    const ds = await api('/api/reopen', { source: src });
    applyDataset(ds, true);
  } catch (e) {
    if (e.code === 'file_gone' || e.code === 'dataset_gone') return clearDataset(t('data.gone'));
    handleError(e);
  }
}

function clearDataset(message) {
  stashViews();
  state.dataset = null;
  state.source = null;
  state.file = null;
  state.history = [];
  $('#datasetName').textContent = '';
  $('#mappingCard').hidden = true;
  $('#tableField').hidden = true;
  $('#importOptions').hidden = true;
  $('#figureBox').hidden = true;
  $('#errorBox').hidden = true;
  $('#emptyState').hidden = false;
  $('#btnExport').disabled = true;
  $('#hints').innerHTML = '';
  Bus.emit('dataset', { ds: null });
  Bus.emit('dataset:shown', { ds: null });
  if (message) { toast(message, true); setDataError(message); }
}

function handleError(e, retry) {
  if (e && e.code === 'missing_modules') {
    ensureModules(e.data.modules).then(ok => { if (ok && retry) retry(); });
    return;
  }
  console.error(e);
  const msg = e.code === 'unsupported' ? `${t('error.unsupported')} ${e.message}` : (e.message || String(e));
  toast(msg, true);
  if (['unsupported', 'read_error', 'import_error', 'file_gone', 'token', 'network'].includes(e.code)) setDataError(msg);
}

// ------------------------------------------------------------------ data table
// The Data table tab: a small spreadsheet (web/table.js).
function buildTable() {
  if (window.TableEditor) TableEditor.render();
}

function setTab(tab) {
  state.tab = tab;
  $$('.tab[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab && (tab !== 'figure' || !state.view)));
  renderViewTabs();
  const hasData = !!state.dataset;
  $('#tableBox').hidden = tab !== 'table' || !hasData;
  $('#figureBox').hidden = tab !== 'figure' || !hasData;
  $('#consoleBox').hidden = tab !== 'console';                  // the console works with or without data
  $('#emptyState').hidden = hasData || tab === 'console';
  if (tab === 'console') $('#consoleInput').focus();
  if (tab !== 'figure') $('#errorBox').hidden = true;
  if (tab === 'figure') scheduleRender(0);
}

// ------------------------------------------------------------------ figure copies
// Analyses never change the original figure. Curves that share its axes (fits, bands, smoothing…)
// are drawn on a copy of it; results with axes of their own (ACF, spectrum, Q–Q…) open as a figure
// of their own data. Each has its own spec and a tab closed with ×. While one is shown, state.spec
// (and, for a result, state.dataset) are its own; the original ones wait in state.main*.
const localName = obj => (obj && typeof obj === 'object') ? (obj[state.lang] || obj.en || '') : (obj ?? '');

function viewTitle(v) {
  if (v.compose) return t('layout.tab', { n: v.compose.length });
  const names = v.runs.map(r => localName(r.name));
  return v.dataset ? [localName(v.result.name), ...names].join(' + ') : `${t('tab.figure')} + ${names.join(' + ')}`;
}

// The data set of the result figure on screen, if any (copies of the figure use the original data).
function viewDataset() {
  const v = state.view && state.views.find(x => x.id === state.view);
  return (v && v.dataset) || null;
}

function renderViewTabs() {
  const box = $('#viewTabs');
  if (!box) return;
  const add = $('#btnLayout');
  if (add) add.hidden = !(state.view ? state.mainDataset : state.dataset);
  box.innerHTML = '';
  state.views.forEach(v => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tab view-tab' + (state.tab === 'figure' && state.view === v.id ? ' active' : '');
    const label = document.createElement('span');
    label.className = 'view-label';
    label.textContent = viewTitle(v);
    b.title = viewTitle(v);
    // Made from an earlier version of the data: being run again, or could not be (see the analysis panel).
    const old = window.Analysis && Analysis.viewOutdated ? Analysis.viewOutdated(v) : null;
    if (old) {
      b.classList.add('outdated', old);
      b.title += ` — ${t(old === 'busy' ? 'view.outdated_busy' : 'view.outdated')}`;
    }
    const x = document.createElement('span');
    x.className = 'view-close';
    x.textContent = '×';
    x.title = t('view.close');
    x.setAttribute('role', 'button');
    x.setAttribute('aria-label', t('view.close'));
    x.onclick = e => { e.stopPropagation(); closeView(v.id); };
    b.append(label, x);
    b.onclick = () => showView(v.id);
    box.append(b);
  });
}

// ------------------------------------------------------------------ layouts of several figures
// A layout is a tab whose figure combines others (v.compose: 'main' and ids of copies / result figures), read live
// at each drawing, so a change in one of them shows in the layout too.
function currentLayout() {
  const v = state.view && state.views.find(x => x.id === state.view);
  return v && v.compose ? v : null;
}

function layoutPanel(id) {
  const mainDs = state.view ? state.mainDataset : state.dataset;
  const mainSpec = state.view ? state.mainSpec : state.spec;
  if (!mainDs) return null;
  const extra = window.Files ? Files.extraSpec() : [];
  const v = id === 'main' ? null : state.views.find(x => x.id === id);
  if (id !== 'main' && (!v || v.compose)) return null;
  const ds = (v && v.dataset) || mainDs;
  const s = clone(v ? v.spec : mainSpec);
  Object.assign(s, { lang: state.lang, name: ds.name, extra: v && v.dataset ? [] : extra,
    main_pos: v && v.dataset ? 0 : (window.Files ? Files.position() : 0) });
  return { dataset_id: ds.dataset_id, source: ds.source, spec: s };
}

const layoutCandidates = () => ['main', ...state.views.filter(v => !v.compose).map(v => v.id)];

function newLayout() {
  const ids = layoutCandidates();
  const base = state.view ? state.mainSpec : state.spec;
  if (!base) return;
  const ncols = ids.length > 1 ? 2 : 1, nrows = Math.ceil(ids.length / ncols);
  const s = clone(base);
  Object.assign(s, { overlays: [], notes: [], refs: [], moved: {}, texts: {} });
  s.inset = { ...(s.inset || {}), show: false };
  s.layout = { ...(s.layout || {}), ncols, letters: true };
  s.text = { ...s.text, title: '' };
  s.figure = { ...s.figure, width: +(base.figure.width * ncols).toFixed(1), height: +(base.figure.height * nrows).toFixed(1) };
  const v = { id: newId(), spec: s, runs: [], compose: ids };
  state.views.push(v);
  renderViewTabs();
  showView(v.id);
}

function buildLayoutCard() {
  const v = currentLayout();
  $('#layoutCard').hidden = !v;
  document.body.classList.toggle('layout-view', !!v);   // kinds and suggestions belong to each figure, not to the layout
  if (!v) return;
  const box = $('#layoutList');
  box.innerHTML = '';
  const ids = [...v.compose, ...layoutCandidates().filter(id => !v.compose.includes(id))];
  ids.forEach(id => {
    const other = state.views.find(x => x.id === id);
    if (id !== 'main' && !other) return;
    const lab = document.createElement('label');
    lab.className = 'check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = v.compose.includes(id);
    const k = v.compose.indexOf(id);
    const span = document.createElement('span');
    span.textContent = (k >= 0 ? `(${String.fromCharCode(97 + k)}) ` : '') + (id === 'main' ? t('tab.figure') : viewTitle(other));
    cb.onchange = () => {
      v.compose = cb.checked ? [...v.compose, id] : v.compose.filter(x => x !== id);
      buildLayoutCard();
      renderViewTabs();
      scheduleRender(0);
    };
    lab.append(cb, span);
    box.append(lab);
    // How many columns and rows of the grid this figure takes.
    if (k >= 0) {
      const lay = v.spec.layout = v.spec.layout || {};
      const ncols = Math.max(1, Number(lay.ncols) || 2);
      const now = (lay.span || {})[id] || [1, 1];
      const size = document.createElement('span');
      size.className = 'layout-span';
      [[0, 'layout.span_cols', ncols], [1, 'layout.span_rows', 3]].forEach(([i, key, max]) => {
        const sel = document.createElement('select');
        sel.title = t(key);
        sel.setAttribute('aria-label', t(key));
        for (let n = 1; n <= max; n++) sel.append(new Option(`${i ? '↕' : '↔'} ${n}`, n));
        sel.value = String(Math.min(now[i], max));
        sel.onchange = () => {
          const next = [...((lay.span || {})[id] || [1, 1])];
          next[i] = Number(sel.value);
          lay.span = { ...(lay.span || {}), [id]: next };
          scheduleRender(0);
        };
        size.append(sel);
      });
      box.append(size);
    }
  });
}

function refreshSpecUI() {
  buildLayoutCard();
  syncControls();
  updatePalettePreview();
  buildKindGallery();
  buildKindOptions();
  buildMapping(true);
  buildSeries();
  updateFigInfo();
}

// Show the original figure (id null), one of its copies or a result figure.
function showView(id, force = false) {
  const v = id ? state.views.find(x => x.id === id) : null;
  if (force || (v ? v.id : null) !== state.view) {
    if (!state.view) {
      state.mainSpec = state.spec;
      state.mainDataset = state.dataset;
      state.mainRecommend = state.recommend;
    }
    const before = state.dataset;
    state.view = v ? v.id : null;
    state.spec = v ? v.spec : state.mainSpec;
    state.dataset = (v && v.dataset) || state.mainDataset;
    state.recommend = (v && v.dataset) ? (v.dataset.recommend || []) : state.mainRecommend;
    if (!v) state.mainSpec = state.mainDataset = state.mainRecommend = null;
    refreshSpecUI();
    if (force || state.dataset !== before) {
      buildTable();
      updateHints();
      Bus.emit('view:shown', { id: state.view });
    }
  }
  setTab('figure');
}

// A new copy of the original figure (not shown yet).
function newView() {
  const v = { id: Math.random().toString(16).slice(2, 10), spec: clone(state.view ? state.mainSpec : state.spec), runs: [] };
  v.spec.overlays = (v.spec.overlays || []).filter(o => !o.analysis_run);
  state.views.push(v);
  return v;
}

function closeView(id) {
  const i = state.views.findIndex(v => v.id === id);
  if (i < 0) return;
  const shown = state.view === id;
  if (shown) showView(null);
  state.views.splice(i, 1);
  renderViewTabs();
  Bus.emit('views:changed');
}

// Leave the copies (back to the original spec) and hand them over, e.g. to keep them in the history.
function stashViews() {
  const saved = state.views;
  if (state.view) {
    state.spec = state.mainSpec;
    state.dataset = state.mainDataset;
    state.recommend = state.mainRecommend;
    state.mainSpec = state.mainDataset = state.mainRecommend = null;
    state.view = null;
  }
  state.views = [];
  renderViewTabs();
  return saved;
}
