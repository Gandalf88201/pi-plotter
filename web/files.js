// Several data files: the list of loaded files, combining them in one figure (same axes or one
// panel per file), and a health check of the local service (connection lost, newer version).
'use strict';

window.Files = (() => {
  const F = { list: [], settings: {} };       // list: {id, ds, info, name}; settings[id]: {enabled, x, y, yerr}

  const active = () => (state.dataset ? state.dataset.dataset_id : null);
  const layout = () => {
    state.spec.layout = Object.assign({ mode: 'single', ncols: 2, share: true, letters: true, titles: true },
      state.spec.layout || {});
    return state.spec.layout;
  };

  function uniqueName(name) {
    const names = new Set(F.list.map(e => e.name));
    if (!names.has(name)) return name;
    let k = 2;
    while (names.has(`${name} (${k})`)) k++;
    return `${name} (${k})`;
  }

  function add(ds, info, enabled) {
    F.list.push({ id: ds.dataset_id, ds, info, name: uniqueName(ds.name) });
    F.settings[ds.dataset_id] = { enabled: !!enabled };
  }

  function replace(oldId, ds, info) {
    const e = F.list.find(x => x.id === oldId);
    if (!e) return add(ds, info, false);
    const st = F.settings[oldId] || { enabled: false };
    delete F.settings[oldId];
    F.settings[ds.dataset_id] = st;
    Object.assign(e, { id: ds.dataset_id, ds, info });
  }

  function clear() {
    F.list = [];
    F.settings = {};
    render();
  }

  // The active file is the one analyses work on. In a combined figure, choosing another file keeps the
  // figure as it is (kind, style, texts, limits): each file goes on drawing the columns it drew, the new
  // one as the main file and the previous one among the others. Rebuilding it from the new file's
  // defaults turned Lines into a histogram with no Y column, so analysing the second curve lost the figure.
  function activate(id) {
    const e = F.list.find(x => x.id === id);
    if (!e || id === active()) return;
    const views = stashViews();         // back to the figure (and its spec) if a result was on screen
    const prev = F.list.find(x => x.id === active());
    const combined = !!prev && !!F.settings[e.id] && F.settings[e.id].enabled;
    const r = combined ? resolved(e) : null;
    showFileControls(e.info);
    if (!r || !r.y.length) {
      if (prev && F.list.some(x => x.id !== prev.id && F.settings[x.id] && F.settings[x.id].enabled)) {
        F.settings[prev.id].enabled = true;      // keep the same set of files
      }
      applyDataset(e.ds);
      setTab('figure');
      return;
    }
    const s = state.spec;
    const cols = new Set(e.ds.columns.map(c => c.name));
    const keep = c => (c && cols.has(c) ? c : null);
    const prevKey = `${prev.id}:`, newKey = `${e.id}:`;
    // The new file takes the main place, the previous one goes among the others, in the figure and in its
    // copies with analyses (they show the same files, so the fits of every file can gather on one copy).
    // Styles chosen in the Series panel follow their curve: the main file's keys have no prefix.
    const swap = sp => {
      const series = {};
      Object.entries(sp.series || {}).forEach(([k, v]) => {
        if (k.startsWith(newKey)) series[k.slice(newKey.length)] = v;
        else if (k.startsWith('overlay:') || F.list.some(x => k.startsWith(`${x.id}:`))) series[k] = v;
        else series[prevKey + k] = v;
      });
      Object.assign(sp, { x: r.x, y: [...r.y], yerr: r.yerr, xerr: null, y2: (sp.y2 || []).filter(c => cols.has(c)),
        hue: keep(sp.hue), z: keep(sp.z), series });
    };
    F.settings[prev.id] = { enabled: true, x: s.x || null, y: [...s.y], yerr: s.yerr || null };
    F.settings[e.id] = { enabled: true };
    swap(s);
    s.overlays = [];
    const copies = views.filter(v => !v.dataset);
    copies.forEach(v => swap(v.spec));
    applyDataset(e.ds, true);
    state.views = copies;
    renderViewTabs();
    setTab('figure');
  }

  function remove(id) {
    const i = F.list.findIndex(x => x.id === id);
    if (i < 0) return;
    F.list.splice(i, 1);
    delete F.settings[id];
    if (id === active()) {
      const next = F.list[0];
      if (next) {
        showFileControls(next.info);
        applyDataset(next.ds);
      } else {
        clearDataset();
      }
    } else {
      render();
      scheduleRender(0);
    }
  }

  // Columns used for another file: the user's choice, else the same names as the current figure, else its defaults.
  function resolved(e) {
    const st = F.settings[e.id] || {};
    const cols = new Set(e.ds.columns.map(c => c.name));
    const has = c => c && cols.has(c);
    const s = state.spec;
    const x = st.x !== undefined ? st.x : (has(s.x) ? s.x : e.ds.mapping.x);
    let y = st.y;
    if (!y) {
      y = s.y.filter(has);
      if (!y.length) y = (e.ds.mapping.y || []).slice(0, Math.max(1, s.y.length));
      // Files whose own suggestion is a histogram have no Y: draw their first numeric column, as the figure does.
      if (!y.length && s.y.length) y = e.ds.columns.filter(c => c.kind === 'numeric' && c.name !== x).slice(0, 1).map(c => c.name);
    }
    const yerr = st.yerr !== undefined ? st.yerr : (has(s.yerr) ? s.yerr : null);
    return { x: x || null, y: y.filter(has), yerr: has(yerr) ? yerr : null };
  }

  function extraSpec() {
    if (!state.dataset || !F.list.some(e => e.id === active())) return [];
    // pos: place in the list, so the figure draws (and colours) the files in that order whichever is active.
    return F.list.filter(e => e.id !== active() && F.settings[e.id] && F.settings[e.id].enabled).map(e => {
      const r = resolved(e);
      return { id: e.id, dataset_id: e.id, source: e.ds.source, name: e.name, enabled: true, pos: F.list.indexOf(e), ...r };
    });
  }

  // Place of the active file in the list (spec.main_pos), 0 when it is not one of the loaded files.
  function position() {
    return Math.max(0, F.list.findIndex(e => e.id === active()));
  }

  // ---------------------------------------------------------------- UI
  function render() {
    renderList();
    renderCombine();
  }

  function renderList() {
    const box = $('#loadedList');
    box.innerHTML = '';
    $('#loadedBox').hidden = !F.list.length;
    F.list.forEach(e => {
      const row = document.createElement('div');
      row.className = 'file-row' + (e.id === active() ? ' active' : '');
      row.title = t('files.activate');
      const name = document.createElement('span');
      name.className = 'fname';
      name.textContent = e.name;
      const meta = document.createElement('span');
      meta.className = 'meta';
      meta.textContent = `${e.ds.rows.toLocaleString(LOCALE())}×${e.ds.columns.length}`;
      const x = document.createElement('button');
      x.className = 'x';
      x.type = 'button';
      x.textContent = '✕';
      x.title = t('files.remove');
      x.onclick = ev => { ev.stopPropagation(); remove(e.id); };
      row.append(name, meta, x);
      row.onclick = () => activate(e.id);
      box.append(row);
    });
  }

  function renderCombine() {
    const box = $('#combineBox');
    const others = F.list.filter(e => e.id !== active());
    const show = !!state.dataset && F.list.some(e => e.id === active()) && others.length > 0;
    box.hidden = !show;
    if (!show) return;
    const lay = layout();
    $$('#layoutSeg [data-layout]').forEach(b => {
      b.classList.toggle('active', b.dataset.layout === lay.mode);
      b.onclick = () => { lay.mode = b.dataset.layout; renderCombine(); buildSeries(); scheduleRender(0); };
    });
    $('#panelOpts').hidden = lay.mode !== 'panels';
    const bindOpt = (id, key, type) => {
      const el = $('#' + id);
      if (type === 'check') el.checked = !!lay[key]; else el.value = lay[key];
      el.onchange = () => { lay[key] = type === 'check' ? el.checked : Math.max(1, Number(el.value) || 1); scheduleRender(0); };
    };
    bindOpt('panelCols', 'ncols', 'num');
    bindOpt('panelShare', 'share', 'check');
    bindOpt('panelLetters', 'letters', 'check');
    bindOpt('panelTitles', 'titles', 'check');

    const list = $('#combineList');
    list.innerHTML = '';
    others.forEach(e => {
      const st = F.settings[e.id] = F.settings[e.id] || { enabled: false };
      const r = resolved(e);
      const card = document.createElement('div');
      card.className = 'combine-file' + (st.enabled ? '' : ' off');
      const head = document.createElement('label');
      head.className = 'head';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!st.enabled;
      const nm = document.createElement('span');
      nm.textContent = e.name;
      head.append(cb, nm);
      cb.onchange = () => { st.enabled = cb.checked; renderCombine(); buildSeries(); scheduleRender(0); };
      const body = document.createElement('div');
      body.className = 'body';
      const cols = e.ds.columns.map(c => [c.name, c.name]);
      const fx = document.createElement('div');
      fx.className = 'field';
      fx.innerHTML = `<label>${t('map.x')}</label>`;
      const sx = document.createElement('select');
      fillSelect(sx, [['', t('map.index')], ...cols], r.x || '');
      sx.onchange = () => { st.x = sx.value || null; scheduleRender(0); };
      fx.append(sx);
      const fy = document.createElement('div');
      fy.className = 'field';
      fy.innerHTML = `<label>${t('map.y')}</label>`;
      const cl = document.createElement('div');
      columnPicker(cl, {
        columns: e.ds.columns, selected: r.y, tags: false,
        pickable: c => c.kind === 'numeric' && c.name !== resolved(e).x,
        onChange: list => { st.y = list; buildSeries(); scheduleRender(0); },
      });
      fy.append(cl);
      const fe = document.createElement('div');
      fe.className = 'field';
      fe.innerHTML = `<label>${t('map.yerr')}</label>`;
      const se = document.createElement('select');
      fillSelect(se, [['', t('map.none')], ...cols], r.yerr || '');
      se.onchange = () => { st.yerr = se.value || null; scheduleRender(0); };
      fe.append(se);
      body.append(fx, fy, fe);
      card.append(head, body);
      list.append(card);
    });
  }

  // ---------------------------------------------------------------- health of the local service
  const BUILD = (document.querySelector('meta[name="pp-build"]') || {}).content || '';
  let healthBusy = false;

  function banner(kind) {
    const b = $('#healthBanner');
    b.hidden = !kind;
    $('#app').classList.toggle('with-banner', !b.hidden || !$('#restartBanner').hidden);
    if (!kind) return;
    $('#healthText').textContent = t(kind === 'down' ? 'health.down' : 'health.stale');
    const btn = $('#btnHealth');
    btn.textContent = t(kind === 'down' ? 'health.retry' : 'health.reload');
    btn.onclick = () => (kind === 'down' ? health() : location.reload());
  }

  async function health() {
    if (healthBusy) return;
    healthBusy = true;
    try {
      const st = await api('/api/status');
      banner(st.build && BUILD && !BUILD.startsWith('{{') && st.build !== BUILD ? 'stale' : null);
    } catch (e) {
      if (e.code === 'network') banner('down');
    } finally {
      healthBusy = false;
    }
  }

  setInterval(health, 15000);
  window.addEventListener('focus', health);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) health(); });

  // For project files (web/project.js): a file's settings in the figure, and putting them back.
  const settingsOf = id => clone(F.settings[id] || { enabled: false });
  const setSettings = (id, st) => { F.settings[id] = { enabled: false, ...(st || {}) }; };

  return { add, replace, clear, activate, remove, render, extraSpec, position, health, settingsOf, setSettings,
    list: () => F.list };
})();
