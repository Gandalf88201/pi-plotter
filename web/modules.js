// π-plotter interface — The Modules dialog: built-in modules and the user's own modules from PyPI.
// The page is split into classic scripts loaded in order (see index.html); they share one global scope.
'use strict';

// ------------------------------------------------------------------ modules dialog
function fmtWhen(ts) {
  if (!ts) return t('modules.never');
  return new Date(ts * 1000).toLocaleString(state.lang === 'it' ? 'it-IT' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}

function renderModules() {
  const st = state.status;
  const r = st.refresh || {};
  $('#modulesInfo').textContent = r.state === 'running' ? t('modules.info', { when: t('modules.checking') })
    : (r.state === 'offline' ? t('modules.offline') : t('modules.info', { when: fmtWhen(r.checked_at) }));
  const upd = st.modules.filter(m => m.installed && m.update);
  $('#btnUpdateAll').hidden = !upd.length;
  $('#btnUpdateAll').textContent = t('modules.update_all', { n: upd.length });
  const inst = [...st.modules, ...(st.user_modules || [])].filter(m => m.installed);    // the user's modules too
  const broken = inst.filter(m => m.works === false);
  const checking = st.checks?.state === 'running' || inst.some(m => m.works === null);
  const line = $('#modulesCheck');
  line.className = 'small check-line' + (broken.length ? ' bad' : (checking ? ' muted' : ' ok'));
  line.textContent = broken.length ? t('modules.check_bad', { n: broken.length })
    : (checking ? t('modules.check_running') : t('modules.check_ok', { n: inst.length }));
  $('#btnVerify').disabled = checking;
  const box = $('#modulesTable');
  box.innerHTML = '';
  const cats = ['core', 'plotting', 'analysis', 'styles', 'science', 'formats'];
  cats.forEach(cat => {
    const mods = st.modules.filter(m => m.category === cat);
    if (!mods.length) return;
    const sec = document.createElement('div');
    sec.className = 'mod-cat';
    const h = document.createElement('h3');
    h.textContent = t('cat.' + cat);
    sec.append(h);
    mods.forEach(m => {
      const row = document.createElement('div');
      row.className = 'mod-row';
      const info = document.createElement('div');
      const name = document.createElement('b');
      name.textContent = m.pip;
      const lic = document.createElement('span');
      lic.className = 'lic';
      lic.textContent = m.license;
      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = (m.description[state.lang] || m.description.en || '') + ' ';
      if (m.url) {
        const a = document.createElement('a');
        a.href = m.url; a.target = '_blank'; a.rel = 'noopener'; a.textContent = m.url.replace(/^https?:\/\//, '').replace(/\/$/, '');
        meta.append(a);
      }
      info.append(name, lic, meta);
      if (m.installed && m.works === false && m.import_error) {
        const err = document.createElement('div');
        err.className = 'import-error';
        err.textContent = m.import_error;
        info.append(err);
      }
      const status = document.createElement('span');
      status.className = 'status';
      if (!m.installed) { status.classList.add('no'); status.textContent = t('modules.missing'); }
      else if (m.works === false) { status.classList.add('bad'); status.textContent = t('modules.broken', { v: m.installed }); }
      else if (m.update) { status.classList.add('upd'); status.textContent = `${t('modules.installed', { v: m.installed })} → ${t('modules.newer', { v: m.latest })}`; }
      else { status.classList.add('ok'); status.textContent = t('modules.installed', { v: m.installed }); }
      if (m.installed && m.works !== false) status.textContent += ` · ${t(m.works ? 'modules.works' : 'modules.verifying')}`;
      if (m.restart) status.textContent += ` · ${t('modules.restart')}`;
      const actions = document.createElement('span');
      if (m.installed && m.works === false) {
        const b = document.createElement('button');
        b.className = 'btn small primary';
        b.textContent = t('modules.reinstall');
        b.onclick = () => installFromManager([m.id], false, true);
        actions.append(b);
      }
      if (!m.installed || m.update || m.outdated) {
        const b = document.createElement('button');
        b.className = 'btn small' + (m.installed ? '' : ' primary');
        b.textContent = m.installed ? t('modules.update', { v: m.latest || '' }) : t('modules.install');
        b.onclick = () => installFromManager([m.id], !!m.installed);
        actions.append(b);
      }
      row.append(info, status, actions);
      sec.append(row);
    });
    box.append(sec);
  });
  renderUserModules();
}

// ------------------------------------------------------------------ the user's own modules (from PyPI)
// Check (pip dry run: the package and everything it brings, with licences) → review → install.
// A licence that is not OSI-approved, or not recognised, needs the confirmation box ticked.
const licBadge = (license, status) => {
  const el = document.createElement('span');
  el.className = 'lic ' + (status || 'unknown');
  el.textContent = license || t('umod.status.unknown');
  el.title = t('umod.status.' + (status || 'unknown'));
  return el;
};

async function followJob(job, onUpdate, busy = true) {
  if (busy) state.busyJob = job.id;
  try {
    while (job.state === 'running') {
      onUpdate(job);
      await new Promise(r => setTimeout(r, 400));
      job = await api('/api/jobs/' + job.id);
    }
    onUpdate(job);
  } finally {
    if (busy) state.busyJob = null;
  }
  return job;
}

function renderUserModules() {
  const st = state.status;
  const online = st.online !== false;
  $('#umodOffline').hidden = online;
  $('#umodName').disabled = $('#umodCheck').disabled = !online || !!state.umodBusy;
  const list = $('#umodList');
  list.innerHTML = '';
  const mods = st.user_modules || [];
  if (!mods.length) {
    const p = document.createElement('p');
    p.className = 'small muted';
    p.textContent = t('umod.empty');
    list.append(p);
    return;
  }
  mods.forEach(m => {
    const row = document.createElement('div');
    row.className = 'mod-row';
    const info = document.createElement('div');
    const name = document.createElement('b');
    name.textContent = m.name;
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = [m.summary, m.imports.length ? t('umod.import', { names: m.imports.join(', ') }) : '',
      m.added ? t('umod.added', { date: m.added }) : '', m.accepted ? t('umod.accepted') : ''].filter(Boolean).join(' · ');
    info.append(name, licBadge(m.license, m.status), meta);
    const failed = m.import_failed || [];
    if (m.installed && (failed.length || (m.works === false && m.import_error))) info.append(importFailures(m));
    const users = m.installed && m.works !== false ? usedBy(m) : null;     // null: not known yet, or no use
    if (users === null && m.installed && m.works !== false && window.Analysis) window.Analysis.load().catch(() => {});
    if (users && users.length) {
      const used = document.createElement('div');
      used.className = 'meta';
      used.textContent = t('umod.used_by', { names: users.map(p => p.name[state.lang] || p.name.en).join(', ') });
      info.append(used);
    } else if (users) {                          // works, but nothing in π-plotter uses it: offer to start
      const unused = document.createElement('div');
      unused.className = 'umod-unused small';
      unused.textContent = t('umod.unused') + ' ';
      const make = document.createElement('button');
      make.className = 'btn small primary';
      make.textContent = t('umod.make_integration');
      make.title = t('umod.make_integration_hint');
      make.disabled = !!state.umodBusy;
      make.onclick = () => { $('#modulesDialog').close(); window.Analysis.newIntegration(m.name); };
      unused.append(make);
      info.append(unused);
    }
    if (m.packages.length > 1) {
      const det = document.createElement('details');
      const sum = document.createElement('summary');
      sum.textContent = t('umod.deps', { n: m.packages.length - 1 });
      const ul = document.createElement('ul');
      m.packages.filter(d => d.name.toLowerCase() !== m.name.toLowerCase()).forEach(d => {
        const li = document.createElement('li');
        li.textContent = `${d.name} ${d.version} `;
        li.append(licBadge(d.license, d.status));
        ul.append(li);
      });
      det.append(sum, ul);
      info.append(det);
    }
    const cite = document.createElement('input');
    cite.type = 'text';
    cite.className = 'cite';
    cite.value = m.cite || '';
    cite.placeholder = t('umod.cite');
    cite.onchange = async () => {
      try { state.status = await api('/api/modules/user/cite', { name: m.name, cite: cite.value }); } catch (e) { handleError(e); }
    };
    info.append(cite);
    const status = document.createElement('span');
    status.className = 'status';
    if (!m.installed) { status.classList.add('no'); status.textContent = t('umod.missing'); }
    else if (m.works === false) { status.classList.add('bad'); status.textContent = t('umod.unusable', { v: m.installed }); }
    else if (failed.length) { status.classList.add('upd'); status.textContent = t('umod.partial', { v: m.installed }); }
    else {
      status.classList.add('ok');
      const works = m.works === null ? t('modules.verifying')
        : (m.import_parts > 1 ? t('umod.works', { n: m.import_parts }) : t('modules.works'));
      status.textContent = `${t('modules.installed', { v: m.installed })} · ${works}`;
    }
    if (m.restart) status.textContent += ` · ${t('modules.restart')}`;
    const actions = document.createElement('span');
    const button = (label, cls, fn) => {
      const b = document.createElement('button');
      b.className = 'btn small' + (cls ? ' ' + cls : '');
      b.textContent = t(label);
      b.disabled = !!state.umodBusy;
      b.onclick = fn;
      actions.append(b);
    };
    if (!m.installed) {
      if (online) button('umod.reinstall', 'primary', () => umodInspect(m.name));
      button('umod.forget', '', () => umodUninstall(m.name, false));
    } else {
      button('umod.uninstall', '', () => umodUninstall(m.name, true));
    }
    row.append(info, status, actions);
    list.append(row);
  });
}

// The parts of a user's module that do not import, one line per cause (uvvispy: six parts, one missing module).
function importFailures(m) {
  const box = document.createElement('div');
  box.className = 'import-error' + (m.works === false ? '' : ' warn');
  const failed = m.import_failed || [];
  if (!failed.length) { box.textContent = m.import_error; return box; }
  const head = document.createElement('div');
  head.className = 'head';
  head.textContent = t(failed.length === 1 ? 'umod.part_failed' : 'umod.parts_failed', { n: failed.length, total: m.import_parts });
  box.append(head);
  const byCause = new Map();
  failed.forEach(([part, error]) => byCause.set(error, [...(byCause.get(error) || []), part]));
  byCause.forEach((parts, error) => {
    const line = document.createElement('div');
    line.textContent = `${error} — ${parts.join(', ')}`;
    box.append(line);
  });
  return box;
}

function umodBusy(on) {
  state.umodBusy = on;
  $$('#modulesTable button, #btnUpdateAll, #btnRefresh, #btnVerify').forEach(b => { b.disabled = on; });
  renderUserModules();
}

async function umodInspect(name) {
  name = (name || '').trim();
  if (!name) return;
  if (state.busyJob) { toast(t('modules.busy'), true); return; }
  $('#umodName').value = name;
  const review = $('#umodReview');
  const bar = $('#umodProgress');
  const phase = $('#umodPhase');
  review.hidden = true;
  umodBusy(true);
  try {
    let job = await api('/api/modules/user/inspect', { name });
    job = await followJob(job, j => { setBar(bar, j.progress); phase.textContent = t('umod.checking', { name }); }, false);
    phase.textContent = job.state === 'done' ? '' : (job.error || t('phase.cancelled'));
    if (job.state === 'done') showUmodReview(job);
  } catch (e) {
    phase.textContent = e.message;
  } finally {
    bar.hidden = true;
    umodBusy(false);
    renderModules();
  }
}

function showUmodReview(job) {
  const r = job.result;
  const box = $('#umodReview');
  box.innerHTML = '';
  const head = document.createElement('p');
  const b = document.createElement('b');
  b.textContent = `${r.name} ${r.version}`;
  head.append(b, licBadge(r.license, r.status), document.createTextNode(r.summary ? ' — ' + r.summary : ''));
  box.append(head);
  if (r.already) {
    const p = document.createElement('p');
    p.className = 'small muted';
    p.textContent = t('umod.already');
    box.append(p);
  }
  const p = document.createElement('p');
  p.className = 'small';
  p.textContent = t('umod.will_install', { n: r.packages.length });
  const table = document.createElement('table');
  r.packages.forEach(d => {
    const tr = document.createElement('tr');
    const c1 = document.createElement('td');
    c1.textContent = `${d.name} ${d.version}`;
    const c2 = document.createElement('td');
    c2.append(licBadge(d.license, d.status));
    const c3 = document.createElement('td');
    c3.className = 'muted';
    c3.textContent = t('umod.status.' + d.status) + (d.requested ? '' : ` · ${t('umod.dep')}`);
    tr.append(c1, c2, c3);
    table.append(tr);
  });
  box.append(p, table);
  let accept = null;
  if (r.needs_confirm) {
    const warn = document.createElement('p');
    warn.className = 'umod-warning small';
    warn.textContent = t('umod.not_osi');
    const lab = document.createElement('label');
    lab.className = 'confirm small';
    accept = document.createElement('input');
    accept.type = 'checkbox';
    const span = document.createElement('span');
    span.textContent = t('umod.accept');
    lab.append(accept, span);
    box.append(warn, lab);
  }
  const buttons = document.createElement('div');
  buttons.className = 'buttons';
  const cancel = document.createElement('button');
  cancel.className = 'btn small';
  cancel.textContent = t('umod.cancel');
  cancel.onclick = () => { box.hidden = true; };
  const go = document.createElement('button');
  go.className = 'btn small primary';
  go.textContent = t('umod.install');
  go.disabled = !!accept;
  if (accept) accept.onchange = () => { go.disabled = !accept.checked; };
  go.onclick = () => umodInstall(job.id, !!(accept && accept.checked), r.name);
  buttons.append(cancel, go);
  box.append(buttons);
  box.hidden = false;
}

async function umodInstall(inspection, accept, name) {
  if (state.busyJob) { toast(t('modules.busy'), true); return; }
  const bar = $('#umodProgress');
  const phase = $('#umodPhase');
  $('#umodReview').hidden = true;
  umodBusy(true);
  try {
    let job = await api('/api/modules/user/install', { inspection, accept });
    job = await followJob(job, j => { setBar(bar, j.progress); phase.textContent = `${j.title}: ${phaseText(j)}`; });
    const r = job.result || {};
    if (job.state === 'done') {
      phase.textContent = '';
      $('#umodName').value = '';
      toast(t((r.failed || []).length ? 'umod.installed_partial' : 'umod.installed', { name }));
    } else if (r.rolled_back) {            // installed, but it did not import: removed again
      phase.textContent = t(r.rollback_error ? 'umod.rollback_partial' : 'umod.rolled_back', { name: r.name, v: r.version });
      phase.append(importFailures({ works: false, import_failed: r.failed, import_parts: r.parts, import_error: r.error }));
      if (r.rollback_error) phase.append(Object.assign(document.createElement('div'), { className: 'import-error', textContent: r.rollback_error }));
    } else phase.textContent = job.state === 'error' ? phaseText(job) : t('phase.cancelled');
  } catch (e) {
    phase.textContent = e.message;
  } finally {
    setTimeout(() => { bar.hidden = true; }, 800);
    umodBusy(false);
    await umodChanged();
  }
}

async function umodUninstall(name, installed) {
  if (state.busyJob) { toast(t('modules.busy'), true); return; }
  if (installed && !confirm(t('umod.confirm_uninstall', { name }))) return;
  const phase = $('#umodPhase');
  umodBusy(true);
  try {
    let job = await api('/api/modules/user/uninstall', { name });
    job = await followJob(job, j => { phase.textContent = phaseText(j); });
    if (job.state === 'done') { phase.textContent = ''; toast(t('umod.removed', { name })); }
    else phase.textContent = job.error || t('phase.cancelled');
  } catch (e) {
    phase.textContent = e.message;
  } finally {
    umodBusy(false);
    await umodChanged();
  }
}

async function umodChanged() {
  try { await refreshStatus(); } catch (e) { /* shown by the next action */ }
  renderModules();
  pollRefresh();
  Bus.emit('modules:changed');
}

async function installFromManager(ids, upgrade, reinstall = false) {
  if (state.busyJob) { toast(t('modules.busy'), true); return; }
  $$('#modulesTable button, #btnUpdateAll, #btnRefresh, #btnVerify, #userModules button').forEach(b => { b.disabled = true; });
  const bar = $('#modulesProgress');
  try {
    const job = await runInstall(ids, upgrade, j => { setBar(bar, j.progress); $('#modulesPhase').textContent = `${j.title}: ${phaseText(j)}`; }, reinstall);
    if (job.state === 'error') toast(phaseText(job), true);
  } catch (e) {
    handleError(e);
  }
  setTimeout(() => { bar.hidden = true; }, 800);
  renderModules();
  if (state.meta) { buildStaticSelects(); buildKindGallery(); }
  pollRefresh();       // the import check runs again after every install
}

async function openModules() {
  await refreshStatus();
  renderModules();
  $('#modulesDialog').showModal();
  pollRefresh();
}

const backgroundChecks = () => state.status.refresh?.state === 'running' || state.status.checks?.state === 'running';

// Follow the PyPI check and the import check until both are over (each up to ~5 min).
let polling = false;
async function pollRefresh() {
  if (polling) return;
  polling = true;
  // Only the module dialog and the "needs module ↓" marks depend on these checks: the analysis form,
  // which the user may be filling in, is never rebuilt here.
  const installedSig = () => (state.status?.modules || []).map(m => `${m.id}=${m.installed || ''}`).join(',');
  const before = installedSig();
  try {
    for (let i = 0; i < 400 && backgroundChecks(); i++) {
      await new Promise(r => setTimeout(r, 700));
      await refreshStatus();
      if ($('#modulesDialog').open) renderModules();
    }
  } finally {
    polling = false;
  }
  if (installedSig() !== before) Bus.emit('modules:changed');
}
