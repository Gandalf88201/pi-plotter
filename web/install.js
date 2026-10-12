// π-plotter interface — Installing the Python modules a figure or analysis needs; the first start.
// The page is split into classic scripts loaded in order (see index.html); they share one global scope.
'use strict';

// ------------------------------------------------------------------ modules / installs
const installedMap = () => Object.fromEntries((state.status?.modules || []).map(m => [m.id, m]));
const missingOf = ids => { const m = installedMap(); return [...new Set(ids)].filter(id => m[id] && !m[id].installed); };
const kindNeeds = kind => missingOf(state.meta.kinds[kind]?.requires || []);

async function refreshStatus() {
  state.status = await api('/api/status');
  const updates = state.status.modules.filter(m => m.update && m.installed).length;
  const broken = [...state.status.modules, ...(state.status.user_modules || [])]
    .filter(m => m.installed && m.works === false).length;
  $('#updatesBadge').hidden = !(updates || broken);
  $('#updatesBadge').textContent = broken || updates;
  $('#updatesBadge').classList.toggle('danger', !!broken);
  const restart = state.status.restart_required;
  $('#restartBanner').hidden = !restart;
  $('#app').classList.toggle('with-banner', restart);
  return state.status;
}

function phaseText(job) {
  if (job.state === 'error') return t('phase.error', { error: job.error });
  if (job.state === 'cancelled') return t('phase.cancelled');
  return t('phase.' + job.phase, { detail: job.detail || '' });
}

function setBar(box, frac) {
  box.hidden = false;
  box.querySelector('.bar').style.width = Math.round(frac * 100) + '%';
}

async function runInstall(ids, upgrade, onUpdate, reinstall = false) {
  let job = await api('/api/modules/install', { ids, upgrade, reinstall });
  state.busyJob = job.id;
  while (job.state === 'running') {
    onUpdate(job);
    await new Promise(r => setTimeout(r, 400));
    job = await api('/api/jobs/' + job.id);
  }
  onUpdate(job);
  state.busyJob = null;
  await refreshStatus();
  return job;
}

// Ask to install missing modules; resolves true when they are installed.
function ensureModules(ids, reasonKey = 'install.reason.feature', vars = {}) {
  const need = missingOf(ids);
  if (!need.length) return Promise.resolve(true);
  const dlg = $('#installDialog');
  const mods = installedMap();
  $('#installReason').textContent = t(reasonKey, vars);
  $('#installList').innerHTML = '';
  need.forEach(id => {
    const m = mods[id];
    const li = document.createElement('li');
    li.innerHTML = `<b></b> <span class="lic"></span><small></small>`;
    li.querySelector('b').textContent = m.pip;
    li.querySelector('.lic').textContent = m.license;
    li.querySelector('small').textContent = (m.description[state.lang] || m.description.en || '') + ' ' + t('install.size');
    $('#installList').append(li);
  });
  const bar = $('#installProgress');
  bar.hidden = true;
  $('#installPhase').textContent = '';
  $('#installLogBox').hidden = true;
  const go = $('#installGo');
  go.disabled = false;
  go.textContent = t('install.button');
  return new Promise(resolve => {
    let running = false;
    let done = false;
    const finish = ok => { if (done) return; done = true; dlg.close(); resolve(ok); };
    go.onclick = async ev => {
      ev.preventDefault();
      if (running) return;
      running = true;
      go.disabled = true;
      try {
        const job = await runInstall(need, false, j => {
          setBar(bar, j.progress);
          $('#installPhase').textContent = phaseText(j);
        });
        if (job.state === 'done') { setBar(bar, 1); setTimeout(() => finish(true), 450); return; }
        $('#installLog').textContent = (job.log || []).join('\n');
        $('#installLogBox').hidden = !(job.log || []).length;
        go.disabled = false;
        go.textContent = t('setup.retry');
      } catch (e) {
        $('#installPhase').textContent = e.message;
        go.disabled = false;
      }
      running = false;
    };
    $('#installCancel').onclick = async ev => {
      ev.preventDefault();
      if (running && state.busyJob) { await api(`/api/jobs/${state.busyJob}/cancel`, {}).catch(() => {}); }
      finish(false);
    };
    dlg.onclose = () => finish(false);
    dlg.showModal();
  });
}

// ------------------------------------------------------------------ first start
async function showSetup() {
  $('#setup').hidden = false;
  $('#app').hidden = true;
  $('#setupPython').textContent = t('setup.python', { version: state.status.python, path: state.status.executable });
  const btn = $('#btnSetup');
  btn.onclick = async () => {
    btn.disabled = true;
    const bar = $('#setupProgress');
    setBar(bar, 0);
    try {
      const core = state.status.modules.filter(m => m.core && (!m.installed || m.outdated)).map(m => m.id);
      const job = await runInstall(core, state.status.modules.some(m => m.core && m.outdated), j => {
        setBar(bar, j.progress);
        $('#setupPhase').textContent = phaseText(j);
      });
      if (job.state === 'done' && state.status.core_ready) {
        $('#setup').hidden = true;
        return start();
      }
      $('#setupPhase').textContent = phaseText(job);
    } catch (e) {
      $('#setupPhase').textContent = e.message;
    }
    btn.disabled = false;
    btn.textContent = t('setup.retry');
  };
}
