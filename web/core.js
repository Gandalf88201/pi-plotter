// π-plotter interface — Core of the page: state, translations, theme, calls to the local service, messages, helpers.
// The page is split into classic scripts loaded in order (see index.html); they share one global scope.
'use strict';

const TOKEN = document.querySelector('meta[name="pp-token"]').content;
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const store = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
};

const state = {
  lang: store.get('pp-lang') || ((navigator.language || 'en').toLowerCase().startsWith('it') ? 'it' : 'en'),
  meta: null, status: null, defaults: null, spec: null,
  file: null, dataset: null, source: null, recommend: [], history: [],
  renderSeq: 0, renderCtrl: null, renderTimer: null, fitDpi: 96, tab: 'figure', busyJob: null,
  axesGeom: [],                                     // where the axes lie in the figure drawn last (X-Axes)
  views: [], view: null, mainSpec: null, mainDataset: null, mainRecommend: null,   // see "figure copies"
};

// Number formatting follows the interface language (1.161 in Italian, 1,161 in English).
const LOCALE = () => (state.lang === 'it' ? 'it-IT' : 'en-US');

const LINESTYLES = ['-', '--', ':', '-.'];
// A short random id for things the user adds (layers, boxes, reference lines, copies of the figure).
const newId = () => Math.random().toString(16).slice(2, 10);
const MARKERS = ['', 'o', 's', '^', 'v', 'D', 'x', '+', '*', '.'];
const SCALES = ['linear', 'log', 'symlog', 'logit'];
const LEGEND_LOCS = ['best', 'upper right', 'upper left', 'lower left', 'lower right', 'center left', 'center right',
  'upper center', 'lower center', 'outside right', 'outside top', 'outside bottom'];
const PREFERRED_FONTS = ['Arial', 'Helvetica', 'Helvetica Neue', 'Times New Roman', 'Times', 'Calibri', 'Cambria',
  'Garamond', 'Georgia', 'Palatino', 'Liberation Sans', 'Liberation Serif', 'DejaVu Sans', 'DejaVu Serif', 'STIXGeneral', 'CMU Serif'];
const KIND_OPTS = {
  scatter: ['colorbar', 'vmin', 'vmax'], area: ['stacked'], errorbar: ['error_style', 'capsize'],
  regression: ['fit', 'fit_degree'], polar: ['polar_degrees'], bar: ['stacked', 'bar_width', 'agg', 'capsize'],
  barh: ['stacked', 'bar_width', 'agg', 'capsize'], box: ['show_fliers'], pie: ['agg'], hist: ['bins', 'density', 'stacked'],
  kde: ['fill'], heatmap: ['annotate', 'agg', 'colorbar', 'vmin', 'vmax'], contour: ['levels', 'contour_lines', 'colorbar', 'vmin', 'vmax'],
  hexbin: ['gridsize', 'colorbar'], hist2d: ['bins', 'density', 'colorbar'],
  surface3d: ['wireframe', 'elev', 'azim', 'colorbar', 'vmin', 'vmax'], scatter3d: ['connect', 'elev', 'azim'], waterfall: ['elev', 'azim'],
};
const OPT_DEF = {
  bins: { type: 'number', min: 2, step: 1 }, density: { type: 'check' }, stacked: { type: 'check' }, fill: { type: 'check' },
  levels: { type: 'number', min: 2, step: 1 }, contour_lines: { type: 'check' }, gridsize: { type: 'number', min: 5, step: 5 },
  fit: { type: 'select', options: ['linear', 'poly', 'exp', 'log', 'power'], prefix: 'fit.' },
  fit_degree: { type: 'number', min: 1, max: 9, step: 1 }, annotate: { type: 'check' }, capsize: { type: 'number', min: 0, step: 0.5 },
  error_style: { type: 'select', options: ['bars', 'band'], prefix: 'err.' }, colorbar: { type: 'check' },
  vmin: { type: 'nullable' }, vmax: { type: 'nullable' }, polar_degrees: { type: 'check' }, bar_width: { type: 'number', min: 0.1, max: 1, step: 0.05 },
  agg: { type: 'select', options: ['mean', 'median', 'sum', 'count', 'max', 'min'], prefix: 'agg.' }, show_fliers: { type: 'check' },
  elev: { type: 'number', min: -90, max: 90, step: 5 }, azim: { type: 'number', min: -180, max: 180, step: 5 },
  wireframe: { type: 'check' }, connect: { type: 'check' },
};
const UNIT_MM = { mm: 1, cm: 10, in: 25.4 };
const KIND_GROUPS = ['xy', 'cat', 'dist', 'map', 'multi', '3d'];

// ------------------------------------------------------------------ i18n
function t(key, vars) {
  const dict = window.I18N[state.lang] || window.I18N.en;
  let s = dict[key] ?? window.I18N.en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m));
  return s;
}
// A figure that cannot be drawn: the server's message, in the interface language when it has a key.
function specMessage(e) {
  const key = e.data && e.data.key && 'error.' + e.data.key;
  if (!key || !(key in window.I18N.en)) return e.message;
  const vars = Object.fromEntries(Object.entries(e.data.values || {})
    .map(([k, v]) => [k, typeof v === 'number' ? v.toLocaleString(LOCALE()) : v]));
  return t(key, vars);
}
function applyI18n(root = document) {
  document.documentElement.lang = state.lang;
  $$('[data-i18n]', root).forEach(el => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-title]', root).forEach(el => { el.title = t(el.dataset.i18nTitle); });
  $$('[data-i18n-placeholder]', root).forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  $$('[data-i18n-html]', root).forEach(el => { el.innerHTML = t(el.dataset.i18nHtml); });   // our own strings, with <code>

  $$('.seg [data-lang]').forEach(b => b.classList.toggle('active', b.dataset.lang === state.lang));
  const manual = $('#btnManual');            // the manual opens in the language of the program
  if (manual) manual.href = '/manual?lang=' + state.lang;
}
function setLang(lang) {
  state.lang = lang;
  store.set('pp-lang', lang);
  applyI18n();
  if (state.meta) { buildStaticSelects(); buildKindGallery(); buildKindOptions(); buildMapping(false); buildSeries(); updateHints(); updateFigInfo(); }
  if ($('#modulesDialog').open) renderModules();
  if (window.Analysis) { window.Analysis.relabel(); window.Analysis.updateDerived(); }
  if (window.Files) Files.render();
  renderViewTabs();
  if (state.dataset) scheduleRender();
}

// ------------------------------------------------------------------ theme
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem('pp-theme', theme); } catch (e) { /* ignore */ }
}

// ------------------------------------------------------------------ API
class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.code = data.code; this.data = data; }
}
async function api(path, body, opts = {}) {
  let res;
  try {
    res = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'X-Token': TOKEN, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal: opts.signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(t('error.network'), 0, { code: 'network' });
  }
  if (!res.ok) {
    let data = {};
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (data.code === 'token') reloadForNewSession();
    throw new ApiError(data.error || res.statusText, res.status, data);
  }
  if (opts.raw) return res;
  return res.json();
}

// The service was restarted with another token: reload once to pick up the new page.
function reloadForNewSession() {
  let last = 0;
  try { last = Number(sessionStorage.getItem('pp-reload') || 0); } catch (e) { /* ignore */ }
  if (Date.now() - last < 10000) return;          // avoid a reload loop
  try { sessionStorage.setItem('pp-reload', String(Date.now())); } catch (e) { /* ignore */ }
  location.reload();
}

// ------------------------------------------------------------------ toasts
function toast(msg, err = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), err ? 7000 : 3500);
}

// ------------------------------------------------------------------ object path helpers
const getPath = (obj, path) => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
function setPath(obj, path, value) {
  const keys = path.split('.');
  let o = obj;
  keys.slice(0, -1).forEach(k => { if (typeof o[k] !== 'object' || o[k] === null) o[k] = {}; o = o[k]; });
  o[keys[keys.length - 1]] = value;
}
const clone = o => JSON.parse(JSON.stringify(o));
function merge(base, over) {
  const out = clone(base);
  for (const [k, v] of Object.entries(over || {})) {
    if (v && typeof v === 'object' && !Array.isArray(v) && out[k] && typeof out[k] === 'object' && !Array.isArray(out[k])) out[k] = merge(out[k], v);
    else out[k] = v;
  }
  return out;
}
