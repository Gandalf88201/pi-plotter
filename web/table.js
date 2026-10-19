// The Data table tab as a small spreadsheet: type in a cell, paste a block copied from a spreadsheet, add or
// delete rows and columns, rename a column, fill a column with a formula; undo. Every change is sent to the
// service as operations (piplotter/tables.py), which returns a new version of the table: the figure and the
// analyses use it at once, and the previous version is kept for Undo.
'use strict';

window.TableEditor = (() => {
  const PAGE = 200;
  const T = { start: 0, page: null, sel: null, rows: new Set(), undo: [], busy: false };

  const editable = () => !!state.dataset && !viewDataset();
  const typing = e => e.target instanceof Element && !!e.target.closest('input, textarea, select, [contenteditable]');
  const cols = () => (T.page ? T.page.columns : []);

  async function load(start = T.start) {
    const ds = state.dataset;
    if (!ds) return;
    try {
      T.page = await api('/api/table/rows', { dataset_id: ds.dataset_id, start, count: PAGE, col_start: 0 });
      T.start = T.page.start;
    } catch (e) {
      if (e.code === 'dataset_gone') return;
      handleError(e);
      return;
    }
    draw();
  }

  // ------------------------------------------------------------------ drawing
  function render() {
    const ds = state.dataset;
    const box = $('#tableBox');
    if (!ds) { box.innerHTML = ''; return; }
    if (T.page && T.dsId === ds.dataset_id) { draw(); return; }
    if (T.dsId !== ds.dataset_id) { T.start = 0; T.sel = null; T.rows.clear(); T.undo = []; }   // another table
    T.dsId = ds.dataset_id;
    // The preview that came with the data set, until the page arrives.
    T.page = { start: 0, total: ds.rows, columns: ds.columns.slice(0, ds.preview_cols ?? ds.columns.length).map(c => c.name),
      rows: ds.preview };
    draw();
    if (ds.rows > ds.preview.length || T.start || ds.masked) load();
  }

  function button(label, title, onclick, cls = '') {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn small ' + cls;
    b.textContent = label;
    if (title) b.title = title;
    b.onclick = onclick;
    return b;
  }

  function toolbar() {
    const bar = document.createElement('div');
    bar.className = 'table-tools';
    const ds = state.dataset;
    if (editable()) {
      bar.append(
        button(t('table.add_row'), t('table.add_row_hint'), () => send([{ op: 'add_rows', n: 1, at: T.rows.size ? Math.min(...T.rows) + 1 : null }])),
        button(t('table.add_col'), '', () => send([{ op: 'add_col' }])),
        button(t('table.del_rows', { n: T.rows.size }), '', () => send([{ op: 'del_rows', rows: [...T.rows] }]).then(ok => { if (ok) T.rows.clear(); })),
        button(t('table.formula'), t('table.formula_hint'), formulaForm),
        button(t('table.undo'), t('table.undo_hint'), undo));
      bar.children[2].hidden = !T.rows.size;
      bar.lastChild.disabled = !T.undo.length;
      // Excluding rows: out of every analysis and of the curves (grey crosses on the figure); the data stay.
      const masked = new Set((T.page && T.page.masked) || []);
      const picked = [...T.rows];
      const exclude = button(t('table.exclude', { n: picked.filter(r => !masked.has(r)).length }), t('table.exclude_hint'),
        () => send([{ op: 'mask', rows: picked, value: true }]).then(ok => { if (ok) T.rows.clear(); }));
      exclude.hidden = !picked.some(r => !masked.has(r));
      const include = button(t('table.include', { n: picked.filter(r => masked.has(r)).length }), '',
        () => send([{ op: 'mask', rows: picked, value: false }]).then(ok => { if (ok) T.rows.clear(); }));
      include.hidden = !picked.some(r => masked.has(r));
      bar.append(exclude, include, button(t('table.exclude_pick'), t('table.exclude_pick_hint'), excludeOnFigure));
    } else {
      const p = document.createElement('span');
      p.className = 'small muted';
      p.textContent = t('table.readonly');
      bar.append(p);
    }
    // The whole table as a file (rows the user excluded left out): CSV for any program, Excel for spreadsheets.
    const base = String(ds.name || 'data').replace(/\.[A-Za-z0-9]{1,5}$/, '').replace(/ › /g, ' - ');
    bar.append(button(t('table.save_csv'), t('table.save_hint'), () => downloadTable(ds.dataset_id, 'csv', base)),
      button(t('table.save_xlsx'), t('table.save_hint'), () => downloadTable(ds.dataset_id, 'xlsx', base)));
    const nav = document.createElement('span');
    nav.className = 'table-nav small';
    const total = T.page ? T.page.total : ds.rows;
    const end = Math.min(total, T.start + (T.page ? T.page.rows.length : 0));
    const info = document.createElement('span');
    info.textContent = t('data.loaded', { rows: total.toLocaleString(LOCALE()), cols: ds.columns.length.toLocaleString(LOCALE()) }) +
      (total > PAGE ? ` — ${(T.start + 1).toLocaleString(LOCALE())}–${end.toLocaleString(LOCALE())}` : '') +
      (cols().length < ds.columns.length ? ` · ${t('data.first_cols', { n: cols().length })}` : '');
    nav.append(info);
    if (total > PAGE) {
      const prev = button('‹', t('table.prev'), () => load(Math.max(0, T.start - PAGE)));
      prev.disabled = T.start === 0;
      const next = button('›', t('table.next'), () => load(T.start + PAGE));
      next.disabled = end >= total;
      const go = document.createElement('input');
      go.type = 'number';
      go.min = 1;
      go.max = total;
      go.placeholder = t('table.goto');
      go.className = 'goto';
      go.onchange = () => { const r = Math.max(1, Math.min(total, Number(go.value) || 1)); load(Math.floor((r - 1) / PAGE) * PAGE); };
      nav.append(prev, next, go);
    }
    bar.append(nav);
    return bar;
  }

  function draw() {
    const ds = state.dataset;
    const box = $('#tableBox');
    if (!ds || !T.page) return;
    const keepScroll = box.scrollTop;
    // A cell being typed in survives the redraw (the rows of a new version arrive while the next value is typed).
    const open = $('#tableBox input.cell-input');
    const carry = open ? { r: +open.dataset.r, c: +open.dataset.c, value: open.value, at: open.selectionStart } : null;
    if (open) open.moved = true;
    const table = document.createElement('table');
    table.className = editable() ? 'sheet editable-sheet' : 'sheet';
    const head = document.createElement('tr');
    const corner = document.createElement('th');
    corner.className = 'idx';
    head.append(corner);
    const byName = Object.fromEntries(ds.columns.map(c => [c.name, c]));
    cols().forEach((name, j) => {
      const th = document.createElement('th');
      th.dataset.c = j;
      th.textContent = name;
      const c = byName[name];
      if (c) {
        const sm = document.createElement('small');
        sm.textContent = c.dtype + (c.missing ? ` · ${c.missing} NaN` : '');
        th.append(sm);
      }
      if (editable()) {
        th.title = t('table.col_hint');
        th.ondblclick = () => renameCol(name);
        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'col-del';
        del.textContent = '✕';
        del.title = t('table.del_col', { name });
        del.onclick = ev => { ev.stopPropagation(); if (confirm(t('table.del_col_confirm', { name }))) send([{ op: 'del_col', col: name }]); };
        th.append(del);
      }
      head.append(th);
    });
    const thead = document.createElement('thead');
    thead.append(head);
    const tbody = document.createElement('tbody');
    const rows = T.page.rows.slice();
    // One empty row at the end of the last page: type there to add a row (as in a spreadsheet).
    const last = T.start + rows.length >= T.page.total;
    if (editable() && last) rows.push(cols().map(() => null));
    rows.forEach((row, i) => {
      const r = T.start + i;
      const tr = document.createElement('tr');
      if (editable() && last && i === rows.length - 1) tr.className = 'new-row';
      else if ((T.page.masked || []).includes(r)) { tr.className = 'masked'; tr.title = t('table.masked_row'); }
      const idx = document.createElement('td');
      idx.className = 'idx' + (T.rows.has(r) ? ' picked' : '');
      idx.textContent = (r + 1).toLocaleString(LOCALE());
      if (editable() && !tr.className) {
        idx.title = t('table.row_hint');
        idx.onclick = ev => pickRow(r, ev);
      }
      tr.append(idx);
      row.forEach((v, j) => {
        const td = document.createElement('td');
        td.dataset.r = r;
        td.dataset.c = j;
        td.textContent = v === null || v === undefined ? '' : (typeof v === 'number' ? String(+v.toPrecision(10)) : v);
        if (typeof v === 'number') td.className = 'num';
        if (T.sel && T.sel.r === r && T.sel.c === j) td.classList.add('sel');
        tr.append(td);
      });
      tbody.append(tr);
    });
    table.append(thead, tbody);
    box.innerHTML = '';
    box.append(toolbar(), table);
    box.scrollTop = keepScroll;
    if (carry && editable()) {
      edit(carry.r, carry.c, carry.value);
      const again = $('#tableBox input.cell-input');
      if (again && carry.at !== null) again.setSelectionRange(carry.at, carry.at);
    }
    if (editable()) {
      table.addEventListener('click', ev => {
        const td = ev.target.closest('td[data-r]');
        if (td) select(+td.dataset.r, +td.dataset.c);
      });
      table.addEventListener('dblclick', ev => {
        const td = ev.target.closest('td[data-r]');
        if (td) edit(+td.dataset.r, +td.dataset.c);
      });
    }
  }

  // ------------------------------------------------------------------ selection and typing
  const cell = (r, c) => $(`#tableBox td[data-r="${r}"][data-c="${c}"]`);

  function select(r, c) {
    $$('#tableBox td.sel').forEach(x => x.classList.remove('sel'));
    T.sel = { r, c };
    const td = cell(r, c);
    if (td) { td.classList.add('sel'); td.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
  }

  function pickRow(r, ev) {
    if (!(ev.shiftKey || ev.metaKey || ev.ctrlKey)) T.rows.clear();
    if (ev.shiftKey && T.lastRow !== undefined) {
      for (let k = Math.min(T.lastRow, r); k <= Math.max(T.lastRow, r); k++) T.rows.add(k);
    } else if (T.rows.has(r)) T.rows.delete(r); else T.rows.add(r);
    T.lastRow = r;
    draw();
  }

  function edit(r, c, initial = null) {
    const td = cell(r, c);
    if (!td || T.busy) return;
    select(r, c);
    const old = td.textContent;
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'cell-input';
    Object.assign(input.dataset, { r, c });
    input.value = initial !== null ? initial : old;
    td.textContent = '';
    td.append(input);
    input.focus();
    if (initial === null) input.select();
    let done = false;
    const finish = async (move) => {
      if (done) return;
      done = true;
      const value = input.value;
      if (value === old) { td.textContent = old; if (move) moveSel(move); return; }
      td.textContent = value;
      const ok = await send([{ op: 'set', row: r, col: cols()[c], value }]);
      if (ok && move) moveSel(move);
    };
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); finish([1, 0]); }
      else if (e.key === 'Tab') { e.preventDefault(); finish([0, e.shiftKey ? -1 : 1]); }
      else if (e.key === 'Escape') { e.preventDefault(); done = true; td.textContent = old; }
      e.stopPropagation();
    });
    input.addEventListener('blur', () => { if (!input.moved) finish(null); });   // not when a redraw moves it
  }

  function moveSel([dr, dc]) {
    if (!T.sel) return;
    const r = Math.max(0, T.sel.r + dr);
    const c = Math.max(0, Math.min(cols().length - 1, T.sel.c + dc));
    if (r >= T.start + PAGE) { load(T.start + PAGE).then(() => select(r, c)); return; }
    if (r < T.start) { load(Math.max(0, T.start - PAGE)).then(() => select(r, c)); return; }
    select(r, c);
  }

  // Keys on the selected cell: arrows move, Enter/F2 edits, a character starts typing, Delete empties it.
  document.addEventListener('keydown', e => {
    if (state.tab !== 'table' || !T.sel || !editable() || typing(e) || $('dialog[open]')) return;
    const moves = { ArrowDown: [1, 0], ArrowUp: [-1, 0], ArrowRight: [0, 1], ArrowLeft: [0, -1] };
    if (moves[e.key]) { e.preventDefault(); moveSel(moves[e.key]); return; }
    if (e.key === 'Enter' || e.key === 'F2') { e.preventDefault(); edit(T.sel.r, T.sel.c); return; }
    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      send([{ op: 'set', row: T.sel.r, col: cols()[T.sel.c], value: '' }]);
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(); return; }
    if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); edit(T.sel.r, T.sel.c, e.key); }
  });

  // Paste a block (tab-separated, as spreadsheets copy it; or ; / , separated text) at the selected cell.
  document.addEventListener('paste', e => {
    if (state.tab !== 'table' || !editable() || typing(e)) return;
    const text = (e.clipboardData || window.clipboardData).getData('text');
    if (!text) return;
    e.preventDefault();
    const lines = text.replace(/\r\n?/g, '\n').replace(/\n$/, '').split('\n');
    const sep = lines.some(l => l.includes('\t')) ? '\t' : (lines.some(l => l.includes(';')) ? ';' : (lines.every(l => !/\d,\d/.test(l)) && lines.some(l => l.includes(',')) ? ',' : null));
    const values = lines.map(l => (sep ? l.split(sep) : [l]).map(v => v.trim()));
    const at = T.sel || { r: 0, c: 0 };
    send([{ op: 'paste', row: at.r, col: cols()[at.c] ?? cols()[0], values }])
      .then(ok => { if (ok) toast(t('table.pasted', { rows: values.length, cols: Math.max(...values.map(v => v.length)) })); });
  });

  // Click points of the figure to exclude them (or bring them back): the nearest point of the drawn columns.
  function excludeOnFigure() {
    if (!editable()) return;
    const ok = startPick({
      owner: 'exclude',
      marks: () => [],
      onPoint: async ({ x, y }) => {
        const g = (state.axesGeom || [])[0];
        if (!g) return;
        try {
          const hit = await api('/api/table/nearest', { dataset_id: state.dataset.dataset_id, x: state.spec.x, ys: state.spec.y, spec: specForServer(),
            px: x, py: y, xlim: g.xlim, ylim: g.ylim, xscale: g.xscale, yscale: g.yscale });
          if (hit.row === undefined || hit.distance > 0.05) { toast(t('table.no_point')); return; }
          if (await send([{ op: 'mask', rows: [hit.row], value: !hit.masked }])) {
            toast(t(hit.masked ? 'table.point_back' : 'table.point_out', { row: hit.row + 1 }));
          }
        } catch (e) {
          handleError(e);
        }
      },
      onStop: () => {},
    });
    if (ok) toast(t('table.exclude_pick_on'));
  }

  // ------------------------------------------------------------------ columns and formulas
  async function renameCol(name) {
    const to = prompt(t('table.rename', { name }), name);
    if (to === null || !to.trim() || to.trim() === name) return;
    renameInSpec(name, to.trim());                 // before the new table comes in, so the figure keeps the column
    if (!(await send([{ op: 'rename', col: name, to: to.trim() }]))) renameInSpec(to.trim(), name);
  }

  function formulaForm() {
    const target = prompt(t('table.formula_col'), T.sel ? cols()[T.sel.c] : '');
    if (target === null || !target.trim()) return;
    const expr = prompt(t('table.formula_expr', { name: target.trim() }), '');
    if (expr === null || !expr.trim()) return;
    send([{ op: 'formula', col: target.trim(), expr: expr.trim() }]);
  }

  // The figure keeps following a renamed column; a deleted one leaves it.
  // The figures that show this table: the one on screen, the original kept aside while a copy is on screen, the copies.
  const tableSpecs = () => [...new Set([state.spec, state.view ? state.mainSpec : null,
    ...state.views.filter(v => !v.dataset).map(v => v.spec)].filter(Boolean))];

  function renameInSpec(from, to) {
    tableSpecs().forEach(s => {
      ['x', 'hue', 'z', 'xerr', 'yerr'].forEach(k => { if (s[k] === from) s[k] = to; });
      ['y', 'y2'].forEach(k => { s[k] = (s[k] || []).map(c => (c === from ? to : c)); });
      if (s.series && s.series[from]) { s.series[to] = s.series[from]; delete s.series[from]; }
    });
  }

  function dropMissing(ds) {
    const names = new Set(ds.columns.map(c => c.name));
    tableSpecs().forEach(s => {
      ['x', 'hue', 'z', 'xerr', 'yerr'].forEach(k => { if (s[k] && !names.has(s[k])) s[k] = null; });
      ['y', 'y2'].forEach(k => { s[k] = (s[k] || []).filter(c => names.has(c)); });
    });
    // A table that had nothing to plot (a new one) gets the usual choice of columns once it has data.
    if (!state.spec.x && !state.spec.y.length && ds.mapping) resetDataSpec(ds.mapping);
  }

  // ------------------------------------------------------------------ sending changes, undo
  async function send(ops) {
    if (!editable() || T.busy || !ops.length) return false;
    T.busy = true;
    const old = state.dataset;
    try {
      const ds = await api('/api/table/edit', { dataset_id: old.dataset_id, ops });
      T.undo.push(old);
      if (T.undo.length > 50) T.undo.shift();
      swapIn(old, ds);
      return true;
    } catch (e) {
      if (e.code === 'table') toast(e.message, true); else handleError(e);
      draw();
      return false;
    } finally {
      T.busy = false;
    }
  }

  async function undo() {
    const prev = T.undo.pop();
    if (!prev || !editable()) return;
    let ds = prev;
    try {
      await api('/api/table/rows', { dataset_id: prev.dataset_id, start: 0, count: 1 });
    } catch (e) {          // the service let it go (or was restarted): rebuild it from its source
      ds = await api('/api/reopen', { source: prev.source });
    }
    swapIn(state.dataset, ds);
  }

  // The new version takes the place of the old one in the list of files, the figure and its copies.
  function swapIn(old, ds) {
    const keepSel = T.sel;
    if (window.Files && Files.list().some(e => e.id === old.dataset_id)) {
      const entry = Files.list().find(e => e.id === old.dataset_id);
      Files.replace(old.dataset_id, ds, entry.info);
    }
    T.dsId = ds.dataset_id;
    T.page = null;
    dropMissing(ds);
    // A copy of the figure on screen keeps the original's data aside (state.mainDataset): it is the same table.
    if (state.view && state.mainDataset && state.mainDataset.dataset_id === old.dataset_id) setState({ mainDataset: ds });
    applyDataset(ds, true);
    T.sel = keepSel;
    load(T.start);
    Bus.emit('dataset:edited', { old, ds });                  // fits and results follow the new data
  }

  // ------------------------------------------------------------------ a new table
  async function newTable() {
    try {
      const ds = await api('/api/table/new', { cols: 2, rows: 10, name: t('table.new_name') });
      if (window.Files) Files.add(ds, null, false);
      showFileControls(null);
      applyDataset(ds);
      T.undo = [];
      setTab('table');
      T.sel = { r: 0, c: 0 };
      draw();
      toast(t('table.new_hint'));
    } catch (e) {
      handleError(e);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const b = $('#btnNewTable');
    if (b) b.onclick = newTable;
  });

  return { render, load, newTable };
})();
