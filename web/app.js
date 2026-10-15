// π-plotter interface — About, restart, and the start of the page (runs last: every other script is loaded).
// The page is split into classic scripts loaded in order (see index.html); they share one global scope.
'use strict';

// ------------------------------------------------------------------ about
function openAbout() {
  $('#aboutVersion').textContent = 'v' + (state.meta?.version || '');
  const box = $('#aboutRefs');
  box.innerHTML = '';
  const ul = document.createElement('ul');
  ul.className = 'refs small';
  (state.status?.modules || []).forEach(m => {
    const li = document.createElement('li');
    const b = document.createElement('b');
    b.textContent = m.pip;
    const lic = document.createElement('span');
    lic.className = 'lic';
    lic.textContent = m.license;
    li.append(b, lic, document.createTextNode(m.cite ? ' — ' + m.cite : ''));
    ul.append(li);
  });
  (state.status?.user_modules || []).forEach(m => {           // added by the user: third-party
    const li = document.createElement('li');
    const b = document.createElement('b');
    b.textContent = m.name;
    li.append(b, licBadge(m.license, m.status), document.createTextNode(` (${t('umod.title')})` + (m.cite ? ' — ' + m.cite : '')));
    ul.append(li);
  });
  box.append(ul);
  $('#aboutDialog').showModal();
}

// ------------------------------------------------------------------ restart
async function restartService() {
  const btn = $('#btnRestart');
  btn.disabled = true;
  btn.textContent = t('restart.wait');
  try { await api('/api/restart', {}); } catch (e) { /* the connection may drop */ }
  await new Promise(r => setTimeout(r, 1200));
  for (let i = 0; i < 60; i++) {
    try {
      await refreshStatus();
      break;
    } catch (e) {
      await new Promise(r => setTimeout(r, 500));
    }
  }
  btn.disabled = false;
  btn.textContent = t('restart.button');
  state.meta = await api('/api/meta');
  buildStaticSelects();
  buildKindGallery();
  await reopenSource();
  toast(t('restart.done'));
}

// ------------------------------------------------------------------ start
function bindGlobal() {
  $$('.seg [data-lang]').forEach(b => { b.onclick = () => setLang(b.dataset.lang); });
  $('#btnNew').onclick = newSession;
  $('#btnTheme').onclick = () => setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  $('#btnModules').onclick = () => openModules().catch(handleError);
  $('#btnAbout').onclick = openAbout;
  $('#btnRestart').onclick = restartService;
  $('#btnRefresh').onclick = async () => { await api('/api/modules/refresh', {}); await refreshStatus(); renderModules(); pollRefresh(); };
  $('#btnVerify').onclick = async () => { await api('/api/modules/verify', {}); await refreshStatus(); renderModules(); pollRefresh(); };
  $('#umodCheck').onclick = () => umodInspect($('#umodName').value);
  $('#umodName').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); umodInspect($('#umodName').value); } };
  $('#btnUpdateAll').onclick = () => installFromManager(state.status.modules.filter(m => m.installed && m.update).map(m => m.id), true);
  $$('dialog [data-close]').forEach(b => { b.onclick = () => b.closest('dialog').close(); });
}

function bindApp() {
  $('#fileInput').onchange = e => { const files = Array.from(e.target.files); e.target.value = ''; openFiles(files); };
  $$('[data-sample]').forEach(b => { b.onclick = () => openSample(b.dataset.sample); });
  $('#insetPick').onclick = () => startBoxPick(t('inset.pick_hint'), lim => {
    state.spec.inset = { ...state.spec.inset, show: true, xmin: lim.xmin, xmax: lim.xmax, ymin: lim.ymin, ymax: lim.ymax };
    syncControls();
    scheduleRender(0);
  });
  // A break picked on the figure: the stretch dragged across is added to the axis's breaks.
  ['x', 'y'].forEach(axis => {
    $(`#${axis}breakPick`).onclick = () => startBoxPick(t(`axes.break_hint_${axis}`), lim => {
      const lo = lim[`${axis}min`], hi = lim[`${axis}max`];
      if (lo === null || lo === undefined || hi === null || hi === undefined) { toast(t('axes.break_none')); return; }
      const before = String(state.spec.axes[`${axis}break`] || '').trim();
      state.spec.axes[`${axis}break`] = (before ? before + '; ' : '') + `${lo} – ${hi}`;
      syncControls();
      scheduleRender(0);
    });
  });
  $('#btnLayout').onclick = newLayout;
  $('#refAddLine').onclick = () => addRef(false);
  $('#refAddBand').onclick = () => addRef(true);
  $('#btnReimport').onclick = () => openTable($('#tableSelect').value || (state.file && state.file.tables[0]));
  document.addEventListener('change', onControlChange);
  document.addEventListener('input', e => { if (e.target.dataset && e.target.dataset.path && e.target.tagName === 'INPUT' && e.target.type !== 'checkbox') onControlChange(e); });
  $('#sizePreset').onchange = e => {
    const p = state.meta.size_presets[e.target.value];
    if (!p) return;
    const k = UNIT_MM[state.spec.figure.units];
    state.spec.figure.width = +(p[0] / k).toFixed(3);
    state.spec.figure.height = +(p[1] / k).toFixed(3);
    syncControls();
    saveStyle();
    updateFigInfo();
    scheduleRender(0);
  };
  $('#exportFormat').onchange = () => { store.set('pp-export-format', $('#exportFormat').value); updateFigInfo(); };
  $('#btnExport').onclick = exportFigure;
  $('#btnSaveTpl').onclick = saveTemplate;
  $('#tplInput').onchange = e => { if (e.target.files[0]) loadTemplate(e.target.files[0]); e.target.value = ''; };
  $$('.tab[data-tab]').forEach(b => { b.onclick = () => (b.dataset.tab === 'figure' ? showView(null) : setTab(b.dataset.tab)); });
  let resizeTimer = null;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => scheduleRender(0), 250); });
  initPick();
  initRotate();
  initDrag();
  // drag & drop anywhere
  let depth = 0;
  const veil = $('#dropVeil');
  window.addEventListener('dragenter', e => { if (e.dataTransfer.types.includes('Files')) { depth++; veil.classList.add('on'); e.preventDefault(); } });
  window.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) veil.classList.remove('on'); });
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => {
    e.preventDefault();
    depth = 0;
    veil.classList.remove('on');
    if (e.dataTransfer.files.length) openFiles(e.dataTransfer.files);
  });
}

async function start() {
  state.meta = await api('/api/meta');
  state.defaults = state.meta.default_spec;
  setState({ spec: merge(state.defaults, store.get('pp-style', {})) });
  $('#app').hidden = false;
  $('#formatList').textContent = 'CSV · TXT · DAT · Excel · ODS · JSON · Parquet · HDF5 · NetCDF · MATLAB · NumPy · FITS · SPSS · Stata · SAS · XML · SQLite · JCAMP-DX · ZIP · PNG · JPEG · TIFF';
  $('#formatList').title = state.meta.extensions.join('  ');
  buildStaticSelects();
  buildKindGallery();
  buildKindOptions();
  buildSeries();
  updateFigInfo();
  bindApp();
  state.ready = true;                     // the page answers to the user from here on (tests wait for it)
  Bus.emit('ready');
  refreshStatus().then(pollRefresh).catch(() => {});   // badge shows updates and broken modules
  // The icons of the user's modules need the analyses that use them, also before any data is open.
  if ((state.status.user_modules || []).length && window.Analysis) window.Analysis.load().catch(() => {});
}

async function boot() {
  applyI18n();
  bindGlobal();
  try {
    await refreshStatus();
  } catch (e) {
    toast(e.message, true);
    return;
  }
  if (!state.status.core_ready) return showSetup();
  await start();
}

boot();
