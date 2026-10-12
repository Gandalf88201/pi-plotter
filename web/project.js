// Project files (.piplot): save the whole work in one file and open it again, here or on another computer.
// The page describes what it has (files and their settings, the figure, copies with analyses, result figures,
// the analyses' parameters); the service adds the data files and packs it all (piplotter/projects.py). On opening,
// every data set is rebuilt from its source — file and import options, blank table, list of edits, analysis.
'use strict';

window.Project = (() => {
  const P = { name: '' };
  const mainSpec = () => (state.view ? state.mainSpec : state.spec);
  const mainDataset = () => (state.view ? state.mainDataset : state.dataset);
  const stripView = v => ({ id: v.id, spec: clone(v.spec), runs: clone(v.runs || []),
    dataset: v.dataset ? { source: v.dataset.source, name: v.dataset.name, id: v.dataset.dataset_id } : null,
    result: clone(v.result || null) });

  // What the page has on screen, as plain data (no data values: those come from the sources and the files).
  function collect() {
    const ds = mainDataset();
    return {
      app: (document.querySelector('meta[name="pp-build"]') || {}).content || '',
      saved: new Date().toISOString(),
      lang: state.lang,
      files: Files.list().map(e => ({ id: e.id, name: e.name, source: e.ds.source, info: e.info || null,
        settings: Files.settingsOf(e.id) })),
      active: ds ? ds.dataset_id : null,
      main: ds ? { source: ds.source, name: ds.name } : null,
      spec: clone(mainSpec()),
      views: state.views.map(stripView),
      view: state.view,
      tab: state.tab,
      analysis: window.Analysis ? Analysis.exportState() : null,
    };
  }

  async function save() {
    if (!mainDataset()) return;
    const suggested = P.name || ((mainDataset().name || 'project').split(/[\\/›]/).pop().trim().replace(/\.[^.]+$/, ''));
    const name = prompt(t('project.name'), suggested);
    if (name === null) return;
    P.name = name.trim() || suggested;
    const btn = $('#btnSaveProject');
    btn.disabled = true;
    try {
      const res = await api('/api/project/save', { project: collect(), filename: P.name }, { raw: true });
      download(await res.blob(), `${P.name}.piplot`);
      toast(t('project.saved', { name: `${P.name}.piplot` }));
    } catch (e) {
      if (e.code === 'project') toast(e.message, true); else handleError(e);
    } finally {
      btn.disabled = !mainDataset();
    }
  }

  // ------------------------------------------------------------------ opening
  function upload(file) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/project/open');
      xhr.setRequestHeader('X-Token', TOKEN);
      xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
      xhr.upload.onprogress = e => {
        if (e.lengthComputable) setUpload(true, e.loaded / e.total, t('data.uploading', { name: file.name, pct: Math.round(100 * e.loaded / e.total) }));
      };
      xhr.onload = () => {
        let data = {};
        try { data = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
        if (xhr.status >= 400) reject(new ApiError(data.error || xhr.statusText, xhr.status, data)); else resolve(data);
      };
      xhr.onerror = () => reject(new ApiError(t('error.network'), 0, { code: 'network' }));
      xhr.send(file);
    });
  }

  async function open(file) {
    if (!file) return;
    if (mainDataset() && !confirm(t('project.replace'))) return;
    setDataError('');
    setUpload(true, 0, t('data.uploading', { name: file.name, pct: 0 }));
    try {
      const { project, name } = await upload(file);
      setUpload(true, 1, t('project.rebuilding'));
      await restore(project);
      P.name = name;
      toast(t('project.opened', { name: file.name }));
    } catch (e) {
      if (e.code === 'project') setDataError(`${file.name}: ${e.message}`); else handleError(e);
    } finally {
      setUpload(false);
    }
  }

  // Series styles of other files are keyed by their data set id: follow the new ids.
  function remapSpec(spec, ids) {
    const s = clone(spec);
    if (s.series) {
      const out = {};
      Object.entries(s.series).forEach(([k, v]) => {
        const m = /^([0-9a-f]+):(.*)$/.exec(k);
        out[m && ids[m[1]] ? `${ids[m[1]]}:${m[2]}` : k] = v;
      });
      s.series = out;
    }
    (s.overlays || []).forEach(o => { if (o.analysed && ids[o.analysed]) o.analysed = ids[o.analysed]; });
    return s;
  }

  async function reopen(source) {
    return api('/api/reopen', { source });
  }

  async function restore(p) {
    if (!p || !Array.isArray(p.files)) throw new ApiError(t('project.bad'), 422, { code: 'project' });
    // A clean page, as with New (without asking again).
    clearDataset();
    state.views = [];
    state.view = null;
    renderViewTabs();
    Files.clear();
    if (window.Analysis) Analysis.reset();
    if (p.lang && p.lang !== state.lang && typeof setLang === 'function') setLang(p.lang);

    const ids = {};                    // old data set id → new one
    const entries = [];
    for (const f of p.files) {
      const ds = await reopen(f.source);
      ids[f.id] = ds.dataset_id;
      entries.push({ f, ds });
    }
    entries.forEach(({ f, ds }) => Files.add(ds, f.info, false));
    entries.forEach(({ f, ds }) => {
      const st = clone(f.settings || {});
      Files.setSettings(ds.dataset_id, st);
    });
    let main = p.active && ids[p.active] ? entries.find(e => e.ds.dataset_id === ids[p.active]).ds : null;
    if (!main && p.main && p.main.source) {
      main = await reopen(p.main.source);
      if (p.active) ids[p.active] = main.dataset_id;
    }
    if (!main && entries.length) main = entries[0].ds;
    if (!main) throw new ApiError(t('project.bad'), 422, { code: 'project' });

    const entry = entries.find(e => e.ds.dataset_id === main.dataset_id);
    showFileControls(entry ? entry.f.info : null);
    applyDataset(main);                                     // the data and its controls…
    Object.assign(state.spec, remapSpec(p.spec || {}, ids)); // …then the figure as it was saved
    if (window.Analysis) Analysis.importState(p.analysis);
    applyDataset(main, true);

    // Copies of the figure (same data) and result figures (their own data, rebuilt from the source).
    const views = [];
    for (const v of p.views || []) {
      const view = { id: v.id, spec: remapSpec(v.spec || {}, ids), runs: (v.runs || []).map(r => ({ ...r, data: ids[r.data] || r.data })) };
      if (v.dataset) {
        try {
          view.dataset = await reopen(v.dataset.source);
          if (v.dataset.id) ids[v.dataset.id] = view.dataset.dataset_id;
        } catch (e) {
          continue;                                         // a result that cannot be rebuilt is left out
        }
        view.result = v.result ? { ...v.result, base: ids[v.result.base] || v.result.base } : null;
      }
      views.push(view);
    }
    state.views = views;
    renderViewTabs();
    Files.render();
    if (p.view && views.some(v => v.id === p.view)) showView(p.view);
    else setTab(p.tab === 'table' ? 'table' : 'figure');
    updateButtons();
  }

  function updateButtons() {
    const b = $('#btnSaveProject');
    if (b) b.disabled = !mainDataset();
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('#btnSaveProject').onclick = save;
    $('#btnOpenProject').onclick = () => $('#projectInput').click();
    $('#projectInput').onchange = e => { const f = e.target.files[0]; e.target.value = ''; open(f); };
  });

  const isProject = file => /\.piplot$/i.test(file.name || '');

  return { save, open, collect, restore, updateButtons, isProject };
})();
