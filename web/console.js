// The Python console: code typed here runs in a Python process of π-plotter's (piplotter/console.py) that keeps its
// variables from one run to the next. df is the data of the figure on screen, files the open files, spec the
// figure; new_table(frame, name) opens a table, run(analysis, …) runs an analysis. The value of the last line is
// shown (tables as tables), so are the figures made with plt.
'use strict';

window.Console = (() => {
  const C = { history: [], pos: 0, busy: false, started: false };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function scrollDown() {
    const log = $('#consoleLog');
    log.scrollTop = log.scrollHeight;
  }

  function output(entry, o) {
    if (o.type === 'image') {
      const img = el('img', 'con-image');
      img.onload = scrollDown;                       // its height is known only once it is decoded
      img.src = `data:image/png;base64,${o.png}`;
      img.alt = 'figure';
      entry.append(img);
    } else if (o.type === 'table') {
      const box = el('div', 'con-table');
      box.innerHTML = o.html;                        // made by pandas on the server, cells escaped
      entry.append(box);
      if (o.shape) entry.append(el('div', 'con-note', `${o.shape[0]} × ${o.shape[1]}`));
    } else {                                       // messages of the console itself are translated
      entry.append(el('pre', `con-${o.type}`, o.code ? t(`con.${o.code}`, { s: o.seconds }) : o.text));
    }
  }

  function tableLine(entry, ds) {
    const line = el('div', 'con-made');
    line.append(el('span', '', t('con.table', { name: ds.name, rows: ds.rows })));
    const show = el('button', 'btn small', t('con.show'));
    show.type = 'button';
    show.onclick = () => { Files.activate(ds.dataset_id); setTab('table'); };
    line.append(show);
    entry.append(line);
  }

  function busy(on) {
    C.busy = on;
    $('#conRun').disabled = on;
    $('#conStop').hidden = !on;
    $('#conRun').textContent = on ? t('con.running') : t('con.run');
  }

  async function run() {
    const input = $('#consoleInput');
    const code = input.value;
    if (!code.trim() || C.busy) return;
    if (C.history[C.history.length - 1] !== code) C.history.push(code);
    C.pos = C.history.length;
    const entry = el('div', 'con-entry');
    entry.append(el('pre', 'con-code', code));
    $('#consoleLog').append(entry);
    scrollDown();
    busy(true);
    if (!C.started) entry.append(el('div', 'con-note', t('con.starting')));
    try {
      const files = Files.list().map(e => ({ name: e.name, dataset_id: e.id }));
      const out = await api('/api/console/run', { code, dataset_id: state.dataset ? state.dataset.dataset_id : null,
        files, spec: state.dataset ? specForServer() : {}, lang: state.lang });
      C.started = !out.restarted;
      $$('.con-note', entry).forEach(n => n.remove());
      out.outputs.forEach(o => output(entry, o));
      (out.tables || []).forEach(ds => { Files.add(ds, null, false); tableLine(entry, ds); });
      if ((out.tables || []).length) Files.render();
      $('#conVars').textContent = out.variables && out.variables.length ? `${t('con.vars')} ${out.variables.join(', ')}` : '';
      if (!out.outputs.some(o => o.type === 'error')) input.value = '';
    } catch (e) {
      output(entry, { type: 'error', text: e.message || String(e) });
    } finally {
      busy(false);
      scrollDown();
      input.focus();
    }
  }

  async function stop() {
    try { await api('/api/console/stop', {}); } catch (e) { handleError(e); }
  }

  async function reset() {
    try {
      await api('/api/console/reset', {});
      C.started = false;
      $('#conVars').textContent = '';
      $('#consoleLog').append(el('div', 'con-note', t('con.reset_done')));
      scrollDown();
    } catch (e) {
      handleError(e);
    }
  }

  function onKey(e) {
    const input = e.target;
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === 'Enter' && (mod || e.shiftKey)) {
      e.preventDefault();
      run();
    } else if (mod && (e.key === 'ArrowUp' || e.key === 'ArrowDown') && C.history.length) {
      e.preventDefault();
      C.pos = Math.max(0, Math.min(C.history.length, C.pos + (e.key === 'ArrowUp' ? -1 : 1)));
      input.value = C.history[C.pos] ?? '';
    } else if (e.key === 'Tab' && !e.shiftKey) {
      e.preventDefault();                          // indent instead of leaving the box
      const s = input.selectionStart;
      input.setRangeText('    ', s, input.selectionEnd, 'end');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('#conRun').onclick = run;
    $('#conStop').onclick = stop;
    $('#conReset').onclick = reset;
    $('#conClear').onclick = () => { $('#consoleLog').innerHTML = ''; };
    $('#consoleInput').addEventListener('keydown', onKey);
  });

  return { run, stop, reset, history: () => C.history };
})();
