// The Python console: code typed here runs in a Python process of π-plotter's (piplotter/console.py) that keeps its
// variables from one run to the next. df is the data of the figure on screen, files the open files, spec the
// figure; new_table(frame, name) opens a table, run(analysis, …) runs an analysis. The value of the last line is
// shown (tables as tables), so are the figures made with plt. Tab completes names (from the console's variables);
// Run on every file runs the code once per open file and gathers the last values in one table. The code run is kept
// in projects, and can be run again from there.
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

  async function run(given) {
    const input = $('#consoleInput');
    const code = typeof given === 'string' ? given : input.value;
    if (!code.trim() || C.busy) return;
    hideCompletions();
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
      if (!out.outputs.some(o => o.type === 'error') && typeof given !== 'string') input.value = '';
      return !out.outputs.some(o => o.type === 'error');
    } catch (e) {
      output(entry, { type: 'error', text: e.message || String(e) });
    } finally {
      busy(false);
      scrollDown();
      input.focus();
    }
  }

  // The same code once per open file (df = that file, name = its name): the value of each last line, one row each.
  async function runEach() {
    const input = $('#consoleInput');
    const code = input.value;
    const files = Files.list().map(e => ({ name: e.name, dataset_id: e.id }));
    if (!code.trim() || C.busy || !files.length) return;
    hideCompletions();
    if (C.history[C.history.length - 1] !== code) C.history.push(code);
    C.pos = C.history.length;
    const entry = el('div', 'con-entry');
    entry.append(el('pre', 'con-code', code), el('div', 'con-note', t('con.each_running', { n: files.length })));
    $('#consoleLog').append(entry);
    scrollDown();
    busy(true);
    try {
      const out = await api('/api/console/each', { code, files, spec: state.dataset ? specForServer() : {}, lang: state.lang });
      $$('.con-note', entry).forEach(n => n.remove());
      out.runs.forEach(r => {
        if (!r.outputs.length) return;
        entry.append(el('div', 'con-file', r.name));
        r.outputs.forEach(o => output(entry, o));
      });
      if (out.table) {
        Files.add(out.table, null, false);
        Files.render();
        tableLine(entry, out.table);
      } else {
        entry.append(el('div', 'con-note', t('con.each_none')));
      }
    } catch (e) {
      output(entry, { type: 'error', text: e.message || String(e) });
    } finally {
      busy(false);
      scrollDown();
    }
  }

  // ---------------------------------------------------------------- completion (Tab)
  function hideCompletions() {
    const box = $('#conComplete');
    if (box) { box.hidden = true; box.innerHTML = ''; }
  }

  function insertCompletion(input, word, choice) {
    const s = input.selectionStart;
    input.setRangeText(choice, s - word.length, s, 'end');
    hideCompletions();
    input.focus();
  }

  async function complete(input) {
    const before = input.value.slice(0, input.selectionStart);
    let res;
    try { res = await api('/api/console/complete', { text: before }); } catch (e) { return; }
    const found = res.completions || [];
    if (!found.length) return;
    const word = res.word || '';
    if (found.length === 1) { insertCompletion(input, word, found[0]); return; }
    let common = found[0];                       // the part they share goes in at once
    found.forEach(f => { while (!f.startsWith(common)) common = common.slice(0, -1); });
    if (common.length > word.length) insertCompletion(input, word, common);
    const box = $('#conComplete');
    box.innerHTML = '';
    const typed = common.length > word.length ? common : word;
    found.forEach(f => {
      const b = el('button', 'btn small', f);
      b.type = 'button';
      b.onclick = () => insertCompletion(input, typed, f);
      box.append(b);
    });
    box.hidden = false;
  }

  // ---------------------------------------------------------------- the code in projects
  const exportState = () => ({ history: C.history.slice(-200), input: $('#consoleInput') ? $('#consoleInput').value : '' });

  function importState(s) {
    C.history = Array.isArray(s && s.history) ? s.history.filter(c => typeof c === 'string') : [];
    C.pos = C.history.length;
    const log = $('#consoleLog');
    if (!log) return;
    log.innerHTML = '';
    $('#consoleInput').value = (s && s.input) || '';
    if (!C.history.length) return;
    const entry = el('div', 'con-entry');
    entry.append(el('div', 'con-note', t('con.saved_code', { n: C.history.length })));
    C.history.forEach(code => entry.append(el('pre', 'con-code con-saved', code)));
    const again = el('button', 'btn small', t('con.run_again'));
    again.type = 'button';
    again.onclick = async () => {
      again.disabled = true;
      for (const code of C.history.slice()) {
        if (!(await run(code))) break;              // stop at the first error, as a script would
      }
    };
    entry.append(again);
    log.append(entry);
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
      e.preventDefault();                          // complete a name, or indent at the start of a line
      const s = input.selectionStart;
      const line = input.value.slice(0, s).split('\n').pop();
      if (/[\w.]$|\[\s*["'][^"']*$/.test(line) && s === input.selectionEnd) complete(input);
      else input.setRangeText('    ', s, input.selectionEnd, 'end');
    } else if (e.key === 'Escape') {
      hideCompletions();
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('#conRun').onclick = () => run();
    $('#conEach').onclick = runEach;
    $('#conStop').onclick = stop;
    $('#conReset').onclick = reset;
    $('#conClear').onclick = () => { $('#consoleLog').innerHTML = ''; };
    $('#consoleInput').addEventListener('keydown', onKey);
  });

  Bus.on('session:new', () => importState(null));

  return { run, runEach, stop, reset, exportState, importState, history: () => C.history };
})();
