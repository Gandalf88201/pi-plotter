// π-plotter analysis panel (right sidebar): runs built-in and user plugins on the current data,
// draws their curves and error bands over the open figure, shows the numbers, and can turn a
// result into a figure of its own. Plugin editor included.
'use strict';

window.Analysis = (() => {
  // shared: the baseline parameters (baseline, bl_…) of the last analysis run on data with these columns,
  // offered again by every analysis that has them — define the baseline once, then analyse.
  const A = { list: null, current: null, params: {}, results: {}, editing: null, shared: {} };
  const CATS = ['recipe', 'fit', 'timeseries', 'stats', 'signal', 'custom'];
  const L = obj => (obj && typeof obj === 'object') ? (obj[state.lang] || obj.en || '') : (obj ?? '');
  // Layers drawn over the original figure (others belong only to the result's own plot).
  const figureOverlays = res => res.overlays.filter(o => o.on_figure !== false);

  // ---------------------------------------------------------------- list
  async function load(force = false) {
    if (A.list && !force) return A.list;
    if (A.loading && !force) return A.loading;
    A.loading = api('/api/analyses', {}).then(list => {
      A.list = list;
      analysesChanged();                 // the icons of the user's modules follow the list
      return list;
    }).finally(() => { A.loading = null; });
    return A.loading;
  }

  async function show() {
    const has = !!state.dataset;
    $('#anEmpty').hidden = has;
    $('#anBody').hidden = !has;
    if (!has) return;
    try {
      await load();
    } catch (e) {
      return handleError(e, show);
    }
    renderList();
    suggestSoon();
    if (!A.current || !A.list.plugins.some(p => p.id === A.current)) {
      A.current = (A.list.plugins.find(p => p.id === 'fit_curve') || A.list.plugins[0] || {}).id || null;
    }
    if (A.current) renderMain(A.current);
  }

  // ---------------------------------------------------------------- suggested for this figure (advisor.py)
  // The service reads the figure (kind, columns, units, curves, files) and ranks the analyses that suit it,
  // with the reason and starting values; asked again whenever the figure changes in a way that matters.
  let suggestTimer = null;
  let suggestKey = '';
  function suggestSoon() {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(suggest, 300);
  }

  async function suggest() {
    if (!state.dataset) return;
    if (!A.list) {
      try { await load(); } catch (e) { return; }      // the first figure may come before the list of analyses
    }
    const spec = specForServer();
    const key = [state.dataset.dataset_id, spec.kind, spec.x, (spec.y || []).join('\u0001'), spec.hue,
      (spec.extra || []).length].join('\u0002');
    if (key === suggestKey) return;
    suggestKey = key;
    try {
      A.suggest = await api('/api/analyses/suggest', { dataset_id: state.dataset.dataset_id, spec });
    } catch (e) {
      A.suggest = null;
    }
    renderSuggest();
    renderList();
  }

  const suggestions = () => ((A.suggest && A.suggest.suggestions) || []).filter(s => A.list.plugins.some(p => p.id === s.id));

  function renderSuggest() {
    const box = $('#anSuggest');
    box.innerHTML = '';
    const list = suggestions();
    box.hidden = !list.length;
    if (!list.length) return;
    const head = document.createElement('div');
    head.className = 'small muted';
    head.textContent = t('an.suggested');
    box.append(head);
    list.forEach(s => {
      const p = A.list.plugins.find(q => q.id === s.id);
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip' + (s.id === A.current ? ' active' : '');
      b.textContent = L(p.name);
      b.title = L(s.reason);
      b.onclick = () => pick(s);
      box.append(b);
    });
  }

  // A suggestion: that analysis, with its starting values (e.g. Curve fitting of the histogram, Gaussian).
  function pick(s) {
    A.current = s.id;
    if (s.preset && Object.keys(s.preset).length) {
      A.params[paramKey(s.id)] = { ...(A.params[paramKey(s.id)] || {}), ...s.preset };
    }
    renderList();
    renderSuggest();
    renderMain(s.id);
  }

  function renderList() {
    const sel = $('#anSelect');
    sel.innerHTML = '';
    const sug = suggestions();
    if (sug.length) {
      const g = document.createElement('optgroup');
      g.label = '★ ' + t('an.suggested');
      sug.forEach(s => {
        const p = A.list.plugins.find(q => q.id === s.id);
        const o = document.createElement('option');
        o.value = s.id;
        o.dataset.suggest = '1';
        o.textContent = L(p.name);
        o.title = L(s.reason);
        g.append(o);
      });
      sel.append(g);
    }
    CATS.forEach(cat => {
      const items = A.list.plugins.filter(p => p.category === cat);
      if (!items.length) return;
      const g = document.createElement('optgroup');
      g.label = t('an.cat.' + cat);
      items.forEach(p => {
        const o = document.createElement('option');
        o.value = p.id;
        let tag = '';
        if (p.missing.length) tag = `  (↓ ${p.missing.join(', ')})`;
        else if (p.blocked.length) tag = `  (✕ ${p.blocked.map(b => b[0]).join(', ')})`;
        else if (p.source === 'user') tag = `  (${p.outdated ? t('an.outdated') : p.overrides ? t('an.custom') : t('an.user')})`;
        o.textContent = L(p.name) + tag;
        o.title = L(p.description);
        g.append(o);
      });
      sel.append(g);
    });
    if (A.current) sel.value = A.current;
    sel.onchange = () => {
      const opt = sel.selectedOptions[0];
      const s = opt && opt.dataset.suggest ? sug.find(x => x.id === sel.value) : null;
      if (s) pick(s); else { A.current = sel.value; renderSuggest(); renderMain(sel.value); }
    };
    const err = $('#anErrors');
    err.innerHTML = '';
    if (A.list.errors.length) {
      const d = document.createElement('div');
      d.className = 'an-errors';
      d.textContent = t('an.load_errors') + '\n' + A.list.errors.map(e => `• ${e.file}: ${e.error}`).join('\n');
      err.append(d);
      A.list.errors.forEach(e => {
        if (e.source !== 'user') return;
        const b = document.createElement('button');
        b.className = 'btn small';
        b.textContent = t('an.edit') + ' ' + e.file;
        b.onclick = () => openEditor({ file: e.file });
        err.append(b);
      });
    }
  }

  // ---------------------------------------------------------------- form
  function roleValue(role) {
    const s = state.spec;
    const cols = new Set(state.dataset.columns.map(c => c.name));
    const has = c => c && cols.has(c);
    const numeric = state.dataset.columns.filter(c => c.kind === 'numeric').map(c => c.name);
    const ys = s.y.filter(has).length ? s.y.filter(has) : numeric.filter(c => c !== s.x).slice(0, 1);
    switch (role) {
      case 'x': return has(s.x) ? s.x : '';
      case 'y': return ys[0] || '';
      case 'y2': return ys[1] || (s.y2 || []).find(has) || numeric.find(c => c !== ys[0] && c !== s.x) || '';
      case 'ys': return ys;
      case 'xs': return has(s.x) ? [s.x] : [];
      case 'xerr': case 'yerr': case 'hue': case 'z': return has(s[role]) ? s[role] : '';
      default: return null;
    }
  }

  function defaultValue(prm) {
    const d = prm.default;
    if (prm.type === 'column' || prm.type === 'columns') {
      const v = typeof d === 'string' ? roleValue(d) : null;
      if (v !== null) return v;
      return d ?? (prm.type === 'columns' ? [] : '');
    }
    return d ?? (prm.type === 'bool' ? false : '');
  }

  function renderMain(id) {
    A.current = id;
    $('#anSelect').value = id;
    const p = plugin();
    const main = $('#anMain');
    main.innerHTML = '';
    const head = document.createElement('div');
    head.className = 'an-head';
    const desc = document.createElement('p');
    desc.className = 'an-desc';
    desc.textContent = L(p.description);
    desc.title = p.file + (p.source === 'user' ? ` (${t('an.user')})` : '');
    const edit = document.createElement('button');
    edit.className = 'btn small';
    edit.textContent = p.source === 'user' ? t('an.edit') : t('an.customize');
    edit.title = p.source === 'user' ? p.file : t('an.customize_hint');
    edit.onclick = () => (p.source === 'user' ? openEditor({ file: p.file }) : customize(p.id));
    head.append(desc, edit);
    main.append(head);
    if (p.steps && p.steps.length) {           // recipes: what will be done, in order
      const ol = document.createElement('ol');
      ol.className = 'an-steps';
      p.steps.forEach(s => { const li = document.createElement('li'); li.textContent = L(s); ol.append(li); });
      main.append(ol);
    }

    stopPick();
    const values = { ...(A.params[paramKey(id)] || {}) };
    const shared = A.shared[columnsKey()] || {};
    p.params.forEach(prm => {
      if (!isBaselineParam(prm.id) || shared[prm.id] === undefined) return;
      if (prm.type === 'choice' && !prm.choices.some(c => c.value === shared[prm.id])) return;
      values[prm.id] = shared[prm.id];
    });
    const form = document.createElement('div');
    form.className = 'an-form';
    p.params.filter(prm => !prm.hidden).forEach(prm => form.append(field(prm, values[prm.id] !== undefined ? values[prm.id] : defaultValue(prm))));
    main.append(form);
    // Parameters with show_if: {other: [values]} appear only when the other parameter has one of those values.
    const applyShowIf = () => {
      const now = readForm();
      p.params.forEach(prm => {
        if (!prm.show_if) return;
        const el = $(`#anMain [data-param="${CSS.escape(prm.id)}"]`);
        if (el) el.hidden = !Object.entries(prm.show_if).every(([k, vals]) => [].concat(vals).includes(now[k]));
      });
      if (Pick.session && Pick.session.owner && Pick.session.owner.closest('[hidden]')) stopPick();
      drawPickMarks();                      // e.g. the height of the points: on the signal or as clicked
    };
    form.addEventListener('change', applyShowIf);
    applyShowIf();

    const actions = document.createElement('div');
    actions.className = 'an-actions';
    const run = document.createElement('button');
    run.className = 'btn primary';
    run.textContent = t('an.run');
    run.onclick = () => runAnalysis(run);
    const rst = document.createElement('button');
    rst.className = 'btn';
    rst.textContent = t('an.reset');
    rst.title = t('an.reset_hint');
    rst.onclick = () => { forget(id); delete A.params[paramKey(id)]; renderMain(id); };
    actions.append(run, rst);
    // The same analysis, with these settings, on every loaded file: one row per file (Origin's Batch Processing).
    const n = window.Files && Files.active() ? Files.list().length : 0;
    if (n > 1 && !viewDataset()) {
      const all = document.createElement('button');
      all.className = 'btn';
      all.textContent = t('an.batch', { n });
      all.title = t('an.batch_hint');
      all.onclick = () => runBatch(all);
      actions.insertBefore(all, rst);
    }
    if (p.missing.length) {
      const note = document.createElement('span');
      note.className = 'small muted';
      note.textContent = t('an.needs', { mods: p.missing.join(', ') });
      actions.append(note);
    } else if (p.blocked.length) {             // installed, but (a part of) a module it needs does not import
      run.disabled = true;
      const note = document.createElement('span');
      note.className = 'small an-blocked';
      note.textContent = t('an.blocked', { mods: p.blocked.map(b => b[0]).join(', ') });
      note.title = p.blocked.map(b => `${b[0]}: ${b[1]}`).join('\n');
      actions.append(note);
    }
    main.append(actions);
    const res = document.createElement('div');
    res.className = 'an-results';
    res.id = 'anResults';
    main.append(res);
    const kept = resultFor(id);
    if (kept) renderResult(kept);
  }

  // Results are kept per analysis and per data set, so they stay on screen after drawing them on a
  // copy of the figure, after plotting a result and coming back, or after looking at another analysis.
  const resultKey = (id, dsId) => `${id}|${dsId}`;
  function resultFor(id) {
    const ids = [state.dataset, state.mainDataset, ...state.history.map(h => h.dataset)].filter(Boolean).map(d => d.dataset_id);
    const view = state.views.find(v => v.id === state.view);
    if (view && view.result) ids.unshift(view.result.base);         // a result figure (e.g. of a batch): its numbers
    for (const dsId of ids) if (A.results[resultKey(id, dsId)]) return A.results[resultKey(id, dsId)];
    return null;
  }
  function forget(id) {
    Object.keys(A.results).forEach(k => { if (k.startsWith(id + '|')) delete A.results[k]; });
  }

  function plugin() { return A.list.plugins.find(p => p.id === A.current); }
  // Remembered parameters apply only to data with the same columns.
  function columnsKey() { return state.dataset.columns.map(c => c.name).join('\u0001'); }
  function paramKey(id) { return id + '|' + columnsKey(); }
  const isBaselineParam = id => id === 'baseline' || id.startsWith('bl_');

  function field(prm, value) {
    const f = document.createElement('div');
    f.className = 'field' + (['text', 'columns', 'points'].includes(prm.type) ? ' wide' : '');
    f.dataset.param = prm.id;
    f.dataset.type = prm.type;
    const label = document.createElement('label');
    label.textContent = L(prm.label);
    let input;
    const cols = state.dataset.columns;
    if (prm.type === 'column') {
      input = document.createElement('select');
      fillSelect(input, [...(prm.optional ? [['', t('map.none')]] : []), ...cols.map(c => [c.name, c.name])], value || '');
    } else if (prm.type === 'columns') {
      input = document.createElement('div');
      input.picker = columnPicker(input, { columns: cols, selected: value || [], tags: false, onChange: () => {} });
    } else if (prm.type === 'points') {
      input = pointsField(value);
    } else if (prm.type === 'choice') {
      input = document.createElement('select');
      fillSelect(input, prm.choices.map(c => [c.value, L(c.label)]), value);
    } else if (prm.type === 'bool') {
      const lab = document.createElement('label');
      lab.className = 'check';
      input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = !!value;
      const sp = document.createElement('span');
      sp.textContent = L(prm.label);
      lab.append(input, sp);
      f.append(lab);
      return f;
    } else {
      input = document.createElement('input');
      input.type = prm.type === 'text' ? 'text' : 'number';
      if (prm.type === 'int') input.step = '1';
      if (prm.type === 'float') input.step = 'any';
      if (prm.min !== undefined && prm.min !== null) input.min = prm.min;
      if (prm.max !== undefined && prm.max !== null) input.max = prm.max;
      if (prm.optional) input.placeholder = 'auto';
      input.value = value ?? '';
    }
    f.append(label, input);
    if (prm.help) {
      const h = document.createElement('span');
      h.className = 'help';
      h.textContent = L(prm.help);
      f.append(h);
    }
    return f;
  }

  // Points typed one per line ("x y", or "x" alone for the height of the signal there), or clicked on the
  // figure: a click always writes its x and its y, so the point stays exactly where it was clicked.
  function pointsField(value) {
    const wrap = document.createElement('div');
    wrap.className = 'points-field';
    const area = document.createElement('textarea');
    area.rows = 4;
    area.spellcheck = false;
    area.placeholder = t('an.points_ph');
    area.value = Array.isArray(value) ? value.map(q => (q[1] === null || q[1] === undefined ? `${q[0]}` : `${q[0]} ${q[1]}`)).join('\n') : (value || '');
    const bar = document.createElement('div');
    bar.className = 'mini';
    const pick = document.createElement('button');
    pick.type = 'button';
    pick.className = 'btn small primary';
    pick.textContent = t('an.figpick');
    const undo = document.createElement('button');
    undo.type = 'button';
    undo.className = 'btn small';
    undo.textContent = t('an.figpick_undo');
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'btn small';
    clear.textContent = t('an.figpick_clear');
    const lines = () => area.value.split(/\n/).filter(l => l.trim());
    const changed = () => { area.dispatchEvent(new Event('change', { bubbles: true })); drawPickMarks(); };
    pick.onclick = () => {
      if (Pick.session && Pick.session.owner === area) { stopPick(); return; }
      const ok = startPick({
        owner: area,
        onPoint: ({ x, y }) => { area.value = [...lines(), `${x} ${y}`].join('\n'); changed(); },
        marks: () => parsePoints(area.value).map(([x, y]) => ({ x, y: y ?? null })),
        onStop: () => { pick.textContent = t('an.figpick'); pick.classList.add('primary'); },
      });
      if (ok) { pick.textContent = t('an.figpick_stop'); pick.classList.remove('primary'); }
    };
    undo.onclick = () => { area.value = lines().slice(0, -1).join('\n'); changed(); };
    clear.onclick = () => { area.value = ''; changed(); };
    area.addEventListener('input', drawPickMarks);
    bar.append(pick, undo, clear);
    wrap.append(area, bar);
    return wrap;
  }

  // [[x, y|null], …] from the text of a points field (lines that are not points are skipped here; the
  // service reports them when the analysis runs).
  function parsePoints(text) {
    const num = tok => Number(/^[-+]?\d+,\d+$/.test(tok) ? tok.replace(',', '.') : tok);
    return text.split(/[;\n]+/).map(l => l.trim().split(/\s+/).filter(Boolean).map(num))
      .filter(v => (v.length === 1 || v.length === 2) && v.every(Number.isFinite))
      .map(v => [v[0], v.length === 2 ? v[1] : null]);
  }

  function readForm() {
    const out = {};
    $$('#anMain .an-form [data-param]').forEach(f => {
      const type = f.dataset.type;
      if (type === 'columns') out[f.dataset.param] = $('.col-pick', f).picker.get();
      else if (type === 'points') out[f.dataset.param] = $('textarea', f).value;
      else if (type === 'bool') out[f.dataset.param] = $('input', f).checked;
      else {
        const el = $('select, input', f);
        out[f.dataset.param] = (type === 'int' || type === 'float') ? (el.value === '' ? null : Number(el.value)) : el.value;
      }
    });
    return out;
  }

  // ---------------------------------------------------------------- run & results
  // Parameters with hidden: true are not in the form: they keep their last value (the table of results
  // writes them, e.g. the user's own IR assignments) until Reset; extra overrides them for this run.
  async function runAnalysis(btn, extra = {}) {
    const p = plugin();
    if (p.missing.length) {
      if (!(await ensureModules(p.missing))) return;
      await load(true);
      renderList();
    }
    stopPick();
    const last = A.params[paramKey(p.id)] || {};
    const params = { ...Object.fromEntries(p.params.filter(q => q.hidden).map(q => [q.id, last[q.id] ?? q.default ?? ''])),
      ...readForm(), ...extra };
    A.params[paramKey(p.id)] = params;
    if ('baseline' in params) {
      A.shared[columnsKey()] = Object.fromEntries(Object.entries(params).filter(([k]) => isBaselineParam(k)));
    }
    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = t('an.running');
    try {
      const res = await api('/api/analyses/run', { dataset_id: state.dataset.dataset_id, id: p.id, params,
        spec: specForServer(), lang: state.lang });
      A.results[resultKey(p.id, res.analysed_dataset)] = res;
      renderResult(res);
      // Curves on the data's axes go on a copy of the figure; results with axes of their own
      // (ACF, spectrum, Q–Q…) open as a figure of their own. The original figure never changes.
      if (figureOverlays(res).length) showOnCopy(res);
      else if (res.dataset) showResult(res);
    } catch (e) {
      if (e.code === 'missing_modules') {
        if (await ensureModules(e.data.modules)) { await load(true); renderList(); return runAnalysis(btn, extra); }
      } else if (e.code === 'dataset_gone') {
        await reopenSource();
      } else {
        const box = $('#anResults');
        box.innerHTML = '';
        const err = document.createElement('div');
        err.className = 'error-box';
        err.style.position = 'static';
        err.textContent = e.message;
        box.append(err);
      }
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  async function runBatch(btn) {
    const p = plugin();
    if (p.missing.length) {
      if (!(await ensureModules(p.missing))) return;
      await load(true);
      renderList();
    }
    stopPick();
    const last = A.params[paramKey(p.id)] || {};
    const params = { ...Object.fromEntries(p.params.filter(q => q.hidden).map(q => [q.id, last[q.id] ?? q.default ?? ''])),
      ...readForm() };
    A.params[paramKey(p.id)] = params;
    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = t('an.running');
    try {
      const s = state.spec;
      const res = await api('/api/analyses/batch', { id: p.id, params, files: Files.batchList(), spec: specForServer(),
        main: { x: s.x || null, y: [...(s.y || [])], yerr: s.yerr || null }, lang: state.lang });
      A.results[resultKey(p.id, res.analysed_dataset)] = res;
      renderResult(res);
      showResult(res);                       // the table of the files, plotted: first number against the file
    } catch (e) {
      const box = $('#anResults');
      box.innerHTML = '';
      const err = document.createElement('div');
      err.className = 'error-box';
      err.style.position = 'static';
      err.textContent = e.message;
      box.append(err);
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  // ---------------------------------------------------------------- values of a result in the figure
  // Any result can write its numbers in a box on the figure on screen (as fits do by themselves): the numbers it
  // keeps under fixed names (fitted parameters with errors, R²…), then the lines of its summary.
  const SYMBOLS = { mu: 'μ', sigma: 'σ', tau: 'τ', tau1: 'τ₁', tau2: 'τ₂', A1: 'A₁', A2: 'A₂', gamma: 'γ', beta: 'β', phi: 'φ',
    x0: 'x₀', Km: 'K_m', Vmax: 'V_max', Ea: 'E_a', r2: 'R²', adj_r2: 'adj. R²', rmse: 'RMSE', aic: 'AIC', bic: 'BIC', n: 'N' };
  const MINOR = new Set(['aic', 'bic', 'n', 'adj_r2', 'bins']);

  function plusMinus(v, e) {
    if (typeof v !== 'number') return String(v);
    if (e === null || e === undefined || !Number.isFinite(e) || e <= 0) return String(+v.toPrecision(4));
    const a = Math.abs(v);
    if (a >= 1e6 || (a < 1e-4 && v !== 0)) return `${v.toExponential(3)} ± ${+e.toPrecision(2)}`;
    const digits = Math.min(12, Math.max(0, 1 - Math.floor(Math.log10(e))));
    return `${v.toFixed(digits)} ± ${e.toFixed(digits)}`;
  }

  function valueLines(res) {
    const out = (res.values || []).map(v => ({ text: `${SYMBOLS[v.key] ?? v.key} = ${plusMinus(v.value, v.error)}`,
      main: !MINOR.has(v.key), label: SYMBOLS[v.key] ?? v.key }));
    const have = new Set(out.map(o => o.label));
    (res.summary || []).forEach(s => {
      if (have.has(s.label) || s.value === null || s.value === undefined) return;
      const unit = s.unit ? ` ${s.unit}` : '';
      out.push({ text: typeof s.value === 'number' ? `${s.label} = ${plusMinus(s.value, s.error)}${unit}` : `${s.label}: ${s.value}${unit}`,
        main: !out.length || out.length < 4, label: s.label });
    });
    // Tables (e.g. descriptive statistics, normality tests): each number as "row · column = value", a mean with
    // its standard error (or a value with its std. error) as one line. The first lines are ticked when nothing
    // above was offered.
    const fromTables = [];
    (res.tables || []).filter(tb => !tb.edit).slice(0, 3).forEach(tb => {
      const rows = tb.rows.slice(0, 20);
      const named = rows.length > 1 || typeof (rows[0] || [])[0] === 'string';
      const col = name => tb.columns.indexOf(name);
      const value = ['mean', 'media', 'value', 'valore'].find(c => col(c) >= 0);
      const error = ['SEM', 'ES', 'std. error', 'errore std.', 'errore standard'].find(c => col(c) >= 0);
      const pairs = value && error ? [[value, error]] : [];
      rows.forEach(r => {
        const head = named ? `${r[0]} · ` : '';
        const used = new Set();
        pairs.forEach(([a, b]) => {
          if (typeof r[col(a)] !== 'number') return;
          fromTables.push({ text: `${head}${a} = ${plusMinus(r[col(a)], r[col(b)])}`, main: true });
          used.add(col(a)).add(col(b));
        });
        tb.columns.forEach((c, j) => {
          if ((named && j === 0) || used.has(j) || r[j] === null || r[j] === undefined) return;
          const v = r[j];
          fromTables.push({ text: `${head}${c} = ${typeof v === 'number' ? plusMinus(v, null) : v}`, main: !pairs.length });
        });
      });
    });
    const first = !out.length;
    fromTables.slice(0, 60).forEach((l, i) => out.push({ ...l, main: first && l.main && i < 6 }));
    return out;
  }

  async function valuesToFigure(res) {
    const lines = valueLines(res);
    const list = $('#valuesList');
    const text = $('#valuesText');
    list.innerHTML = '';
    let picked = 0;
    lines.forEach((l, i) => {
      const li = document.createElement('li');
      const lab = document.createElement('label');
      lab.className = 'check';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.dataset.i = i;
      cb.checked = l.main && picked < 6;
      if (cb.checked) picked++;
      const span = document.createElement('span');
      span.textContent = l.text;
      lab.append(cb, span);
      li.append(lab);
      list.append(li);
    });
    const fill = () => {
      text.value = $$('input[type=checkbox]', list).filter(cb => cb.checked).map(cb => lines[+cb.dataset.i].text).join('\n');
    };
    list.onchange = fill;
    fill();
    const dlg = $('#valuesDialog');
    const answer = await new Promise(resolve => {
      // Add answers at once (the close event can come late or not at all in a hidden page); Esc and Cancel close.
      $('#valuesAdd').onclick = ev => { ev.preventDefault(); dlg.close('yes'); resolve('yes'); };
      dlg.onclose = () => resolve(dlg.returnValue || 'no');
      dlg.returnValue = '';
      dlg.showModal();
    });
    if (answer !== 'yes' || !text.value.trim()) return;
    state.spec.notes = state.spec.notes || [];
    state.spec.notes.push({ id: newId(), text: text.value.trim(), source: res.plugin.name[state.lang] || res.plugin.name.en });
    buildOverlays();
    scheduleRender(0);
    toast(t('val.added'));
  }

  function fmt(v) {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') {
      if (Number.isInteger(v)) return v.toLocaleString(state.lang === 'it' ? 'it-IT' : 'en-US');
      const a = Math.abs(v);
      return (a !== 0 && (a < 1e-3 || a >= 1e6)) ? v.toExponential(4) : String(+v.toPrecision(6));
    }
    if (typeof v === 'boolean') return v ? '✓' : '✗';
    return String(v);
  }

  function htmlTable(columns, rows) {
    const table = document.createElement('table');
    const tr = document.createElement('tr');
    columns.forEach(c => { const th = document.createElement('th'); th.textContent = c; tr.append(th); });
    const thead = document.createElement('thead');
    thead.append(tr);
    const tbody = document.createElement('tbody');
    rows.forEach(r => {
      const row = document.createElement('tr');
      r.forEach(v => {
        const td = document.createElement('td');
        td.textContent = fmt(v);
        if (typeof v === 'number') td.className = 'num';
        row.append(td);
      });
      tbody.append(row);
    });
    table.append(thead, tbody);
    return table;
  }

  function toCSV(columns, rows) {
    const esc = v => { const s = v === null || v === undefined ? '' : String(v); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    return [columns.map(esc).join(','), ...rows.map(r => r.map(esc).join(','))].join('\n') + '\n';
  }

  // A table the user can edit (edit: see Result.table in plugins.py): cells of the columns in edit.fields
  // are text boxes, "Add a peak" appends a row, ✕ removes one. Apply sends the lines — edit.entries as they
  // are now, changed by what was typed here — back as the analysis' hidden parameter and runs it again.
  function editableTable(columns, rows, edit, bar) {
    const col = name => columns.indexOf(name);
    const keyCol = col(edit.key), originCol = col(edit.origin);
    const fields = Object.entries(edit.fields).map(([field, name]) => [field, col(name)]).filter(([, i]) => i >= 0);
    const entries = clone(edit.entries || []);
    const at = (list, pos) => list.find(e => Math.abs(e.position - pos) < 0.06);
    const table = document.createElement('table');
    table.className = 'editable';
    const hr = document.createElement('tr');
    [...columns, ''].forEach(c => { const th = document.createElement('th'); th.textContent = c; hr.append(th); });
    const thead = document.createElement('thead');
    thead.append(hr);
    const tbody = document.createElement('tbody');
    table.append(thead, tbody);
    const lists = {};
    Object.entries(edit.suggest || {}).forEach(([field, values]) => {
      const dl = document.createElement('datalist');
      dl.id = `suggest-${field}-${newId()}`;
      values.forEach(v => { const o = document.createElement('option'); o.value = v; dl.append(o); });
      lists[field] = dl;
      table.append(dl);
    });
    const body = [];                          // {tr, pos (null for a new row), inputs: [[field, input]], key}
    function addRow(values, isNew) {
      const tr = document.createElement('tr');
      const row = { tr, pos: isNew ? null : values[keyCol], inputs: [], key: null };
      columns.forEach((c, i) => {
        const td = document.createElement('td');
        const field = (fields.find(([, j]) => j === i) || [])[0];
        if (i === keyCol && isNew) {
          const inp = document.createElement('input');
          inp.type = 'number';
          inp.step = 'any';
          inp.placeholder = 'cm⁻¹';
          inp.title = t('an.edit_new_hint');
          row.key = inp;
          td.append(inp);
        } else if (field) {
          const inp = document.createElement('input');
          inp.type = 'text';
          inp.value = values[i] ?? '';
          inp.dataset.orig = inp.value;
          if (lists[field]) inp.setAttribute('list', lists[field].id);
          inp.oninput = () => td.classList.toggle('changed', inp.value !== inp.dataset.orig);
          row.inputs.push([field, inp]);
          td.append(inp);
        } else {
          td.textContent = values[i] === undefined ? '' : fmt(values[i]);
          if (typeof values[i] === 'number') td.className = 'num';
        }
        tr.append(td);
      });
      const del = document.createElement('td');
      const x = document.createElement('button');
      x.type = 'button';
      x.className = 'row-del';
      x.textContent = '✕';
      x.title = t('an.edit_del');
      x.onclick = () => { row.removed = true; tr.hidden = true; if (isNew) tr.remove(); };
      del.append(x);
      tr.append(del);
      if (!isNew && at(entries, row.pos) && !at(entries, row.pos).remove) tr.classList.add('mine');
      tbody.append(tr);
      body.push(row);
      return row;
    }
    rows.forEach(r => addRow(r, false));
    const lines = () => {
      const out = clone(entries);
      body.forEach(row => {
        const pos = row.pos === null ? Number(String(row.key.value).replace(',', '.')) : row.pos;
        if (!Number.isFinite(pos) || (row.pos === null && row.key.value === '')) return;
        let e = at(out, pos);
        if (row.removed) {
          if (row.pos === null) return;
          if (e && e.added) out.splice(out.indexOf(e), 1);
          else { if (e) out.splice(out.indexOf(e), 1); out.push({ position: pos, remove: true }); }
          return;
        }
        row.inputs.forEach(([field, inp]) => {
          const v = inp.value.trim();
          if (row.pos !== null && inp.value === inp.dataset.orig) return;          // untouched: the entry stays as it is
          if (!e) { e = { position: pos, ...(row.pos === null ? { added: true } : {}) }; out.push(e); }
          if (v) e[field] = v; else delete e[field];
        });
        if (row.pos === null && !e) out.push({ position: pos, added: true });       // a bare position: the program assigns it
      });
      return out.filter(e => e.remove || e.added || Object.keys(edit.fields).some(f => e[f]));
    };
    const apply = (btn, json) => runAnalysis(btn, { [edit.param]: json });
    const add = document.createElement('button');
    add.className = 'btn small';
    add.textContent = t('an.edit_add');
    add.title = t('an.edit_add_hint');
    add.onclick = () => { const row = addRow([], true); row.key.focus(); };
    const go = document.createElement('button');
    go.className = 'btn small primary';
    go.textContent = t('an.edit_apply');
    go.title = t('an.edit_apply_hint');
    go.onclick = () => apply(go, JSON.stringify(lines()));
    const restore = document.createElement('button');
    restore.className = 'btn small';
    restore.textContent = t('an.edit_restore');
    restore.hidden = !entries.length;
    restore.onclick = () => apply(restore, '');
    bar.prepend(add, go, restore);
    return table;
  }

  function tableBlock(box, title, columns, rows, open = false, edit = null) {
    const det = document.createElement('details');
    det.open = open;
    const sum = document.createElement('summary');
    sum.textContent = title + (rows.length > 1 ? `  (${rows.length})` : '');
    const wrap = document.createElement('div');
    wrap.className = 'tbl';
    const bar = document.createElement('div');
    bar.className = 'mini';
    wrap.append(edit ? editableTable(columns, rows, edit, bar) : htmlTable(columns, rows));
    const copy = document.createElement('button');
    copy.className = 'btn small';
    copy.textContent = t('an.copy');
    copy.onclick = async () => {
      const tsv = [columns.join('\t'), ...rows.map(r => r.map(v => v ?? '').join('\t'))].join('\n');
      try { await navigator.clipboard.writeText(tsv); toast(t('an.copied')); } catch (e) { toast(e.message, true); }
    };
    const csv = document.createElement('button');
    csv.className = 'btn small';
    csv.textContent = 'CSV';
    csv.onclick = () => download(new Blob([toCSV(columns, rows)], { type: 'text/csv' }), `${title.replace(/[^\w.-]+/g, '_')}.csv`);
    bar.append(copy, csv);
    det.append(sum, wrap);
    if (edit) {
      const hint = document.createElement('p');
      hint.className = 'small muted';
      hint.textContent = t('an.edit_hint');
      det.append(hint);
    }
    det.append(bar);
    box.append(det);
  }

  // The copy of the figure that shows this result, if one is open.
  const copyOf = res => state.views.find(v => v.runs.some(r => r.run === res.run_id));
  // The figure of this result's own data, if one is open.
  const resultViewOf = res => state.views.find(v => v.dataset && v.result.run === res.run_id);

  function renderResult(res) {
    const box = $('#anResults');
    if (!box) return;
    box.innerHTML = '';
    const bar = document.createElement('div');
    bar.className = 'an-actions';
    if (figureOverlays(res).length) {
      const v = copyOf(res);
      const ov = document.createElement('button');
      ov.className = 'btn small primary';
      ov.textContent = v ? t('an.goto_copy') : t('an.overlay');
      ov.title = t('an.overlay_hint');
      ov.onclick = () => (v && state.views.includes(v) ? showView(v.id) : showOnCopy(res));
      bar.append(ov);
    }
    if (res.dataset) {
      const plot = document.createElement('button');
      plot.className = figureOverlays(res).length ? 'btn small' : 'btn small primary';
      const rv = resultViewOf(res);
      plot.textContent = rv ? t('an.goto_plot') : t('an.plot');
      plot.title = t('an.plot_hint', { rows: res.dataset.rows.toLocaleString(LOCALE()), cols: res.dataset.columns.length });
      plot.onclick = () => (rv && state.views.includes(rv) ? showView(rv.id) : showResult(res));
      bar.append(plot);
    }
    if (valueLines(res).length && state.dataset) {
      const vb = document.createElement('button');
      vb.className = 'btn small';
      vb.textContent = t('an.values');
      vb.title = t('an.values_hint');
      vb.onclick = () => valuesToFigure(res);
      bar.append(vb);
    }
    if (bar.children.length) box.append(bar);
    res.texts.forEach(text => {
      const p = document.createElement('p');
      p.className = /^[a-zA-Z]+ ?=|^y =|^k =/.test(text) || /~/.test(text) ? 'eq' : 'small';
      p.textContent = text;
      box.append(p);
    });
    if (res.summary.length) {
      const rows = res.summary.map(s => [s.label, [fmt(s.value), s.error !== null && s.error !== undefined ? '± ' + fmt(s.error) : '',
        s.unit || ''].filter(Boolean).join(' ')]);
      tableBlock(box, t('an.summary'), [t('an.quantity'), t('an.value')], rows, true);
    }
    res.tables.forEach((tb, i) => tableBlock(box, tb.title, tb.columns, tb.rows, i === 0, tb.edit));
    if (res.references.length) {
      const det = document.createElement('details');
      const sum = document.createElement('summary');
      sum.textContent = t('an.refs');
      const ul = document.createElement('ul');
      ul.className = 'refs';
      res.references.forEach(r => { const li = document.createElement('li'); li.textContent = r; ul.append(li); });
      det.append(sum, ul);
      box.append(det);
    }
  }

  // Overlay descriptor for a figure spec; gets a fixed colour so the panel shows the real one.
  // others: series drawn by the other files of the figure (on a copy of it), so a fit never takes a curve's colour.
  const stripOverlay = (o, res, spec, index, others = 0) => {
    const { dataset, ...rest } = o;
    const out = { ...clone(rest), id: Math.random().toString(16).slice(2, 12), analysis_run: res.plugin.id,
      analysed: res.analysed_dataset,
      source_name: `${L(res.plugin.name)} · ${state.dataset ? state.dataset.name : ''}` };
    out.style = out.style || {};
    const pal = state.meta.palettes[spec.style.palette] || [];
    if (!out.style.color && pal.length) out.style.color = pal[(spec.y.length + others + index) % pal.length];
    return out;
  };

  // Draw the result's curves and bands on a copy of the figure (the original stays as it is).
  // The copy on screen gets the layers; otherwise the copy already showing this analysis, otherwise a
  // new copy. Running the same analysis again replaces its layers.
  function showOnCopy(res) {
    if (!state.dataset || state.dataset.dataset_id !== res.analysed_dataset) {
      toast(t('ov.other_data'), true);
      return;
    }
    if (!res.run_id) res.run_id = newId();
    // The same analysis run again on the same file replaces its layers; on another file of a combined figure
    // (e.g. one Gaussian per distribution) it adds them, so every curve can be analysed on one copy.
    const mine = (id, data) => id === res.plugin.id && (!data || data === res.analysed_dataset);
    const v = state.views.find(x => x.id === state.view)
      || [...state.views].reverse().find(x => !x.dataset && x.runs.some(r => r.id === res.plugin.id))
      || newView();
    const s = v.spec;
    s.overlays = (s.overlays || []).filter(o => !mine(o.analysis_run, o.analysed));
    const others = window.Files ? Files.extraSpec().reduce((n, e) => n + e.y.length, 0) : 0;
    figureOverlays(res).forEach(o => s.overlays.push(stripOverlay(o, res, s, s.overlays.length, others)));
    v.runs = v.runs.filter(r => !mine(r.id, r.data));
    v.runs.push({ id: res.plugin.id, name: res.plugin.name, run: res.run_id, data: res.analysed_dataset });
    // A fit weighted by an error column: show the data with those error bars (on the copy only).
    const sigma = res.params && (res.params.sigma || res.params.yerr);
    if (sigma && !s.yerr && ['line', 'scatter', 'errorbar'].includes(s.kind)) {
      s.kind = 'errorbar';
      s.yerr = sigma;
      s.series = s.series || {};
      s.y.forEach(c => { s.series[c] = { ...(s.series[c] || {}), linestyle: 'none', marker: (s.series[c] || {}).marker || 'o' }; });
      toast(t('ov.errors_used', { col: sigma }));
    }
    if (state.view === v.id) { refreshSpecUI(); setTab('figure'); } else showView(v.id);
    viewsChanged();
  }

  // Keep the result buttons ("Show on a copy" / "Go to the copy") in step with the open copies.
  function viewsChanged() {
    const res = A.current && state.dataset ? resultFor(A.current) : null;
    if (res && $('#anResults')) renderResult(res);
  }

  function reset() {
    A.results = {};
    if (A.current && state.dataset) delete A.params[paramKey(A.current)];
    const m = $('#anMain');
    if (m) m.innerHTML = '';
    show();
  }

  // Open the result's own data as a figure in its own tab (styled like the original figure); running
  // the same analysis on the same data again updates that tab.
  function showResult(res) {
    if (!res.run_id) res.run_id = newId();
    const pl = res.plot || {};
    const s = clone(state.view ? state.mainSpec : state.spec);
    resetDataSpec(res.dataset.mapping || {}, s);
    s.layout = { ...(s.layout || {}), mode: 'single' };
    ['kind', 'x', 'y', 'y2', 'hue', 'z', 'xerr', 'yerr'].forEach(k => { if (pl[k] !== undefined) s[k] = clone(pl[k]); });
    s.series = clone(pl.series || {});
    s.overlays = (pl.overlays || []).map((o, i) => stripOverlay(o, res, s, i));
    ['text', 'axes', 'style', 'legend'].forEach(k => { if (pl[k]) s[k] = merge(s[k], pl[k]); });
    let v = state.views.find(x => x.dataset && x.result.id === res.plugin.id && x.result.base === res.analysed_dataset);
    if (v) Object.assign(v, { spec: s, dataset: res.dataset, runs: [] });
    else {
      v = { id: newId(), spec: s, runs: [], dataset: res.dataset, result: { id: res.plugin.id, base: res.analysed_dataset } };
      state.views.push(v);
    }
    v.result.name = res.plugin.name;
    v.result.run = res.run_id;
    showView(v.id, true);
    viewsChanged();
  }

  // ---------------------------------------------------------------- analyses that follow the data
  // The table of the figure changed (an edit, an undo): every analysis made from the old version — layers on the
  // copies of the figure, result figures, the numbers in the panel — runs again, with the same parameters, on the
  // new one. Layers keep their style, their id (a value box the user moved stays where it was) and visibility.
  let refreshing = Promise.resolve();
  function dataChanged(oldDs, newDs) {
    refreshing = refreshing.then(() => refresh(oldDs.dataset_id, newDs.dataset_id)).catch(e => handleError(e));
    return refreshing;
  }

  async function rerun(src, dsId) {
    return api('/api/analyses/run', { dataset_id: dsId, id: src.analysis, params: src.params || {},
      spec: src.spec || specForServer(), lang: state.lang });
  }

  async function refresh(oldId, nextId) {
    const jobs = [];
    state.views.forEach(v => {
      if (v.dataset) {
        if (v.result && v.result.base === oldId && v.dataset.source && v.dataset.source.analysis) jobs.push({ v, src: v.dataset.source });
        return;
      }
      const seen = new Set();
      (v.spec.overlays || []).forEach(o => {
        if (o.analysed !== oldId || !o.source || !o.source.analysis || seen.has(o.analysis_run)) return;
        seen.add(o.analysis_run);
        const { overlay, ...src } = o.source;
        jobs.push({ v, src, pid: o.analysis_run });
      });
    });
    if (!jobs.length) return;
    toast(t('an.refreshing', { n: jobs.length }));
    let changed = false;
    for (const job of jobs) {
      let res;
      try {
        res = await rerun(job.src, nextId);
      } catch (e) {
        toast(`${t('an.refresh_failed')}: ${e.message}`, true);
        continue;
      }
      A.results[resultKey(res.plugin.id, nextId)] = res;
      if (job.v.dataset) {                                   // a result figure: its new data, same style
        job.v.dataset = res.dataset;
        job.v.result.base = nextId;
        if (state.view === job.v.id) state.dataset = res.dataset;
      } else {
        const s = job.v.spec;
        const others = window.Files ? Files.extraSpec().reduce((n, e) => n + e.y.length, 0) : 0;
        const before = s.overlays.filter(o => o.analysis_run === job.pid && o.analysed === oldId);
        const fresh = figureOverlays(res).map((o, i) => {
          const out = stripOverlay(o, res, s, s.overlays.length + i, others);
          const was = before[i];
          if (was) {
            Object.assign(out, { id: was.id, style: was.style, hidden: was.hidden, band: was.band, note_shown: was.note_shown,
              label: was.label });
            if (s.texts) delete s.texts[`note:${was.id}`];   // a rewritten box would show the old values
          }
          return out;
        });
        const at = s.overlays.indexOf(before[0]);
        s.overlays = s.overlays.filter(o => !before.includes(o));
        s.overlays.splice(at < 0 ? s.overlays.length : at, 0, ...fresh);
        job.v.runs.forEach(r => { if (r.id === job.pid && r.data === oldId) { r.data = nextId; r.run = newId(); } });
      }
      if (A.current === res.plugin.id) renderResult(res);
      changed = true;
    }
    if (changed) {
      if (state.view && state.views.some(v => v.id === state.view)) refreshSpecUI();
      scheduleRender(0);
    }
  }

  function back() { showView(null); }

  function updateDerived() {
    const derived = !!(state.dataset && state.dataset.source && state.dataset.source.analysis);
    $('#derivedBox').hidden = !derived;
    if (derived) $('#derivedName').textContent = t('an.derived', { name: state.dataset.name });
    $('#btnBack').hidden = !state.view;
  }

  // ---------------------------------------------------------------- plugin files
  async function customize(id) {
    try {
      const r = await api('/api/plugins/customize', { id });
      await load(true);
      renderList();
      openEditor({ file: r.file });
    } catch (e) { handleError(e); }
  }

  async function newPlugin() {
    const name = prompt(t('an.new_name'), state.lang === 'it' ? 'la mia analisi' : 'my analysis');
    if (!name) return;
    try {
      const r = await api('/api/plugins/new', { name });
      await load(true);
      const created = A.list.plugins.find(p => p.file === r.file);
      if (created) A.current = created.id;
      show();
      openEditor({ file: r.file });
    } catch (e) { handleError(e); }
  }

  // The first analysis using one of the user's modules (Modules › Your modules, or "New function"
  // in the module's icon): created in the plugins folder and opened in the editor.
  async function newIntegration(name) {
    try {
      const r = await api('/api/plugins/integration', { name });
      await load(true);
      const created = A.list.plugins.find(p => p.file === r.file);
      if (created) A.current = created.id;
      show();
      openEditor({ file: r.file });
    } catch (e) { handleError(e); }
  }

  // A function chosen from a module's icon: shown in the analysis panel, ready to run on the open data.
  async function select(id) {
    const card = $('#analysisCard');
    card.open = true;
    if (!state.dataset) toast(t('tools.need_data'), true);
    else {
      A.current = id;
      await show();
    }
    card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  async function openEditor(ref) {
    try {
      const r = await api('/api/plugins/read', ref);
      A.editing = r.file;
      $('#pluginFile').textContent = r.file;
      $('#pluginPath').textContent = t('an.editor_hint', { dir: A.list ? A.list.user_dir : '' });
      $('#pluginCode').value = r.code;
      $('#pluginErrors').hidden = true;
      $('#pluginDialog').showModal();
    } catch (e) { handleError(e); }
  }

  async function save() {
    try {
      const r = await api('/api/plugins/save', { file: A.editing, code: $('#pluginCode').value });
      await load(true);
      renderList();
      if (r.errors.length) {
        $('#pluginErrors').textContent = r.errors.map(e => e.error).join('\n');
        $('#pluginErrors').hidden = false;
        return;
      }
      $('#pluginErrors').hidden = true;
      toast(t('an.saved'));
      const p = A.list.plugins.find(q => q.file === A.editing && q.source === 'user');
      if (p) { A.current = p.id; renderList(); renderMain(p.id); }
    } catch (e) {
      $('#pluginErrors').textContent = e.message;
      $('#pluginErrors').hidden = false;
    }
  }

  async function disable() {
    if (!A.editing || !confirm(t('an.disable_confirm', { file: A.editing }))) return;
    try {
      await api('/api/plugins/disable', { file: A.editing });
      $('#pluginDialog').close();
      await load(true);
      if (!A.list.plugins.some(p => p.id === A.current)) A.current = null;
      show();
    } catch (e) { handleError(e); }
  }

  function bind() {
    $('#btnNewPlugin').onclick = newPlugin;
    $('#btnPluginFolder').onclick = () => api('/api/plugins/folder', {}).then(r => toast(r.path)).catch(handleError);
    $('#btnReloadPlugins').onclick = async () => { await api('/api/plugins/reload', {}).catch(handleError); await load(true); show(); toast(t('an.reloaded')); };
    $('#btnSavePlugin').onclick = save;
    $('#btnDisablePlugin').onclick = disable;
    $('#btnBack').onclick = back;
    const code = $('#pluginCode');
    code.addEventListener('keydown', e => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const { selectionStart: a, selectionEnd: b, value } = code;
        code.value = value.slice(0, a) + '    ' + value.slice(b);
        code.selectionStart = code.selectionEnd = a + 4;
      } else if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        save();
      }
    });
  }
  bind();

  // Modules were installed or removed: refresh the "needs module ↓" marks of the list, keep the form.
  async function modulesChanged() {
    if (!A.list) return;
    try { await load(true); renderList(); } catch (e) { /* the list stays as it was */ }
  }

  // For project files: the analysis chosen and the parameters remembered for each analysis and set of columns.
  const exportState = () => clone({ current: A.current, params: A.params, shared: A.shared });
  function importState(s) {
    if (!s) return;
    A.current = s.current || A.current;
    A.params = s.params || {};
    A.shared = s.shared || {};
    A.results = {};
  }

  return { dataChanged, exportState, importState, suggestSoon, show, updateDerived, load, renderList, reset, viewsChanged, modulesChanged, newIntegration, select,
    list: () => A.list, relabel: () => { if (A.list) show(); } };
})();
