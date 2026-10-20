// ---------------------------------------------------------------- reading a picture of a graph back into data
// The "reverse plot" (piplotter/digitize.py): a picture of a graph is calibrated with two points on each axis, its
// curves are read — by their colour (a line, or the markers of a scatter plot) or point by point — and become a table
// like any other (plotted, analysed, saved in projects, made again from its source) that can be saved as CSV or Excel.
// The picture is shown in a dialog: the wheel zooms, dragging with the hand tool (or the middle button, or space)
// moves it, and a magnifier follows the pointer so points land on the right pixel.

// A table of the service as a file to save: CSV, TSV or Excel (.xlsx); the rows the user excluded are left out.
async function downloadTable(datasetId, format, name) {
  try {
    const res = await api('/api/table/export', { dataset_id: datasetId, format, filename: name || 'data' }, { raw: true });
    const ext = format === 'xlsx' ? 'xlsx' : format;
    download(await res.blob(), `${String(name || 'data').replace(/[^\w.\- ]+/g, '_')}.${ext}`);
  } catch (e) {
    handleError(e);
  }
}

window.Digitizer = (() => {
  const AXES = [['x', 0], ['x', 1], ['y', 0], ['y', 1]];
  const LOUPE = 9;                      // magnification of the magnifier
  const D = {
    fileId: null, name: '', img: null, pixels: null, w: 0, h: 0,
    axes: null, series: [], cur: 0, tool: null, preview: null, made: null, replaces: null,
    view: { scale: 1, ox: 0, oy: 0 }, drag: null, mouse: null, space: false, timer: null, busy: false,
  };
  const dlg = () => $('#digitizeDialog');
  const canvas = () => $('#digCanvas');

  function freshAxes() {
    return { x: [{ px: null, value: '' }, { px: null, value: '' }], y: [{ px: null, value: '' }, { px: null, value: '' }],
      xlog: false, ylog: false };
  }
  function newSeries(k) {
    return { name: `${t('dig.curve')} ${k + 1}`, mode: 'line', colour: null, tolerance: 12, region: null, points: [], min_size: 4 };
  }

  // ------------------------------------------------------------ opening
  // The picture of the file on screen, or the one a digitised table was read from (to change how it was read).
  async function open() {
    const src = state.dataset && state.dataset.source && state.dataset.source.digitize;
    const fileId = src ? src.file_id : state.file && state.file.format === 'image' ? state.file.file_id : null;
    if (!fileId) return;
    try {
      const res = await api('/api/digitize/picture', { file_id: fileId }, { raw: true });
      const meta = JSON.parse(res.headers.get('X-Picture') || '{}');
      const url = URL.createObjectURL(await res.blob());
      const img = new Image();
      await new Promise((ok, fail) => { img.onload = ok; img.onerror = () => fail(new Error(t('dig.no_picture'))); img.src = url; });
      const off = document.createElement('canvas');
      off.width = img.naturalWidth;
      off.height = img.naturalHeight;
      off.getContext('2d').drawImage(img, 0, 0);
      Object.assign(D, { fileId, name: meta.name || (state.file && state.file.name) || 'picture', img, w: img.naturalWidth,
        h: img.naturalHeight, pixels: off.getContext('2d').getImageData(0, 0, off.width, off.height), preview: null,
        made: null, tool: 'x0', replaces: src ? state.dataset.dataset_id : null });
      D.axes = src && src.axes ? clone(src.axes) : freshAxes();
      D.series = src && src.series && src.series.length ? clone(src.series) : [newSeries(0)];
      D.cur = 0;
      $('#digXName').value = (src && src.xname) || 'x';
      $('#digYName').value = (src && src.yname) || 'y';
      if (src) D.tool = null;
      dlg().showModal();
      fit();
      renderSide();
      schedulePreview(0);
    } catch (e) {
      handleError(e);
    }
  }

  function close() {
    dlg().close();
    if (D.img) URL.revokeObjectURL(D.img.src);
    Object.assign(D, { img: null, pixels: null, preview: null, tool: null });
  }

  // ------------------------------------------------------------ the picture on screen
  // The canvas keeps the size the page lays it out at, in device pixels: a bitmap of another shape would be drawn
  // stretched, and the points clicked would land elsewhere than the pointer (higher, the lower the click).
  function sizeCanvas() {
    const c = canvas();
    const r = c.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(r.width * ratio)), h = Math.max(1, Math.round(r.height * ratio));
    if (c.width === w && c.height === h) return false;
    c.width = w;
    c.height = h;
    return true;
  }
  function fit() {
    const c = canvas();
    sizeCanvas();
    const s = Math.min(c.width / D.w, c.height / D.h) * 0.96;
    D.view = { scale: s, ox: (c.width - D.w * s) / 2, oy: (c.height - D.h * s) / 2 };
    draw();
  }
  // Pixel coordinates: the centre of the pixel in column u, row v is (u, v), as the service reads the picture.
  const toPx = (cx, cy) => [(cx - D.view.ox) / D.view.scale - 0.5, (cy - D.view.oy) / D.view.scale - 0.5];
  const toCanvas = (u, v) => [D.view.ox + (u + 0.5) * D.view.scale, D.view.oy + (v + 0.5) * D.view.scale];
  function eventPx(ev) {
    const c = canvas(), r = c.getBoundingClientRect();
    const cx = (ev.clientX - r.left) * c.width / r.width, cy = (ev.clientY - r.top) * c.height / r.height;
    return { cx, cy, px: toPx(cx, cy) };
  }

  function draw() {
    const c = canvas();
    if (!c || !D.img) return;
    const g = c.getContext('2d');
    const ratio = window.devicePixelRatio || 1;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = getComputedStyle(document.body).getPropertyValue('--panel-2') || '#f8fafb';
    g.fillRect(0, 0, c.width, c.height);
    g.imageSmoothingEnabled = D.view.scale < 2;
    g.drawImage(D.img, D.view.ox, D.view.oy, D.w * D.view.scale, D.h * D.view.scale);
    const r = 5 * ratio;
    // The curves read: every point, small, in a colour that stands out on the picture.
    (D.preview || []).forEach((cv, k) => {
      g.fillStyle = g.strokeStyle = k === D.cur ? '#ff00c8' : '#ff8a00';
      g.globalAlpha = k === D.cur ? 1 : 0.45;               // the other curves: seen, without hiding the picture
      g.lineWidth = 2 * ratio;
      cv.px.forEach(([u, v]) => {
        const [x, y] = toCanvas(u, v);
        if (cv.mode === 'line') g.fillRect(x - 1.5 * ratio, y - 1.5 * ratio, 3 * ratio, 3 * ratio);
        else { g.beginPath(); g.arc(x, y, 1.6 * r, 0, 2 * Math.PI); g.stroke(); }     // a marker found, or a point clicked
      });
    });
    g.globalAlpha = 1;
    const s = D.series[D.cur];
    if (s && s.region) {
      const [x0, y0] = toCanvas(s.region[0], s.region[1]), [x1, y1] = toCanvas(s.region[2], s.region[3]);
      g.setLineDash([6 * ratio, 4 * ratio]);
      g.strokeStyle = '#ff00c8';
      g.lineWidth = 1.5 * ratio;
      g.strokeRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
      g.setLineDash([]);
    }
    if (s && s.mode === 'points') {
      g.strokeStyle = '#ff00c8';
      g.lineWidth = 1.5 * ratio;
      s.points.forEach(([u, v]) => { const [x, y] = toCanvas(u, v); g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); g.stroke(); });
    }
    // The calibration: X points in red, Y points in blue. Through each point, dashed, the line of the picture where
    // the axis has the value of that point (upright for X, level for Y): the two Y lines on one row show at once
    // that the Y points were clicked side by side.
    g.save();
    g.beginPath();
    g.rect(D.view.ox, D.view.oy, D.w * D.view.scale, D.h * D.view.scale);
    g.clip();
    const far = (D.w + D.h) * D.view.scale;
    AXES.forEach(([a, i]) => {
      const p = D.axes[a][i].px;
      if (!p) return;
      const [x, y] = toCanvas(p[0], p[1]);
      const [dx, dy] = isoLine(a);
      g.setLineDash([5 * ratio, 4 * ratio]);
      g.strokeStyle = a === 'x' ? '#d6336c' : '#1c7ed6';
      g.globalAlpha = 0.7;
      g.lineWidth = ratio;
      g.beginPath(); g.moveTo(x - dx * far, y - dy * far); g.lineTo(x + dx * far, y + dy * far); g.stroke();
    });
    g.restore();
    AXES.forEach(([a, i]) => {
      const p = D.axes[a][i].px;
      if (!p) return;
      const [x, y] = toCanvas(p[0], p[1]);
      g.strokeStyle = a === 'x' ? '#d6336c' : '#1c7ed6';
      g.lineWidth = 2 * ratio;
      g.beginPath(); g.moveTo(x - 3 * r, y); g.lineTo(x + 3 * r, y); g.moveTo(x, y - 3 * r); g.lineTo(x, y + 3 * r); g.stroke();
      g.font = `600 ${12 * ratio}px system-ui, sans-serif`;
      g.fillStyle = g.strokeStyle;
      g.fillText(`${a.toUpperCase()}${i + 1}`, x + 4 * ratio, y - 4 * ratio);
    });
    if (D.drag && D.drag.kind === 'region') {
      const { x0, y0, x1, y1 } = D.drag;
      g.strokeStyle = '#ff00c8';
      g.lineWidth = 1.5 * ratio;
      g.strokeRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
    }
    drawLoupe();
  }

  // The magnifier: the pixels around the pointer, enlarged, with the place a click would take.
  function drawLoupe() {
    const l = $('#digLoupe');
    const g = l.getContext('2d');
    g.clearRect(0, 0, l.width, l.height);
    if (!D.mouse) { l.hidden = true; return; }
    l.hidden = false;
    const [u, v] = D.mouse;
    const n = l.width / LOUPE;
    g.imageSmoothingEnabled = false;
    g.drawImage(D.img, Math.round(u) - n / 2 + 0.5, Math.round(v) - n / 2 + 0.5, n, n, 0, 0, l.width, l.height);
    g.strokeStyle = '#ff00c8';
    g.lineWidth = 1;
    const m = l.width / 2;
    g.beginPath(); g.moveTo(m, 0); g.lineTo(m, l.height); g.moveTo(0, m); g.lineTo(l.width, m); g.stroke();
    const at = toData(u, v);
    const num = q => Number(q.toPrecision(4)).toLocaleString(LOCALE());
    $('#digCoords').textContent = (at ? `x = ${num(at[0])}   y = ${num(at[1])}   ·   ` : '') + `${Math.round(u)}, ${Math.round(v)} px`;
  }

  // ------------------------------------------------------------ the calibration, as the service reads it
  // A value is read along its axis: the projection of the pixel on the line through the two points of that axis.
  function axisLine(a) {
    const [p, q] = D.axes[a].map(e => e.px);
    if (!p || !q) return null;
    const d = [q[0] - p[0], q[1] - p[1]], n = d[0] * d[0] + d[1] * d[1];
    return n < 4 ? null : { p, d, n };
  }
  // The direction (unit, in the canvas) of the lines of equal value of an axis: across it; upright for X and level
  // for Y while its second point is not clicked.
  function isoLine(a) {
    const l = axisLine(a);
    if (!l) return a === 'x' ? [0, 1] : [1, 0];
    const k = Math.sqrt(l.n);
    return [-l.d[1] / k, l.d[0] / k];
  }
  function toData(u, v) {
    const out = [];
    for (const a of ['x', 'y']) {
      const l = axisLine(a);
      const vals = D.axes[a].map(e => Number(e.value));
      if (!l || D.axes[a].some(e => e.value === '') || !vals.every(Number.isFinite) || vals[0] === vals[1]) return null;
      const log = D.axes[`${a}log`];
      if (log && Math.min(...vals) <= 0) return null;
      const [v0, v1] = log ? vals.map(Math.log10) : vals;
      const tt = ((u - l.p[0]) * l.d[0] + (v - l.p[1]) * l.d[1]) / l.n;
      const r = v0 + tt * (v1 - v0);
      out.push(log ? 10 ** r : r);
    }
    return out;
  }

  // ------------------------------------------------------------ clicks on the picture
  function colourAt(u, v) {
    // The pixel clicked, or the one around it (3 px) with the most ink: a thin line is picked even a little off.
    const P = D.pixels;
    let best = null, ink = -1;
    for (let dv = -3; dv <= 3; dv++) {
      for (let du = -3; du <= 3; du++) {
        const x = Math.round(u) + du, y = Math.round(v) + dv;
        if (x < 0 || y < 0 || x >= P.width || y >= P.height) continue;
        const i = (y * P.width + x) * 4;
        const rgb = [P.data[i], P.data[i + 1], P.data[i + 2]];
        const sat = Math.max(...rgb) - Math.min(...rgb), dark = 255 - (rgb[0] + rgb[1] + rgb[2]) / 3;
        const score = sat + dark - (du * du + dv * dv);
        if (score > ink) { ink = score; best = rgb; }
      }
    }
    return '#' + best.map(c => c.toString(16).padStart(2, '0')).join('');
  }

  function onDown(ev) {
    if (!D.img) return;
    const { cx, cy, px } = eventPx(ev);
    if (ev.button === 1 || D.space || D.tool === 'pan' || !D.tool) {
      D.drag = { kind: 'pan', cx, cy, ox: D.view.ox, oy: D.view.oy };
      return;
    }
    if (D.tool === 'region') {
      D.drag = { kind: 'region', x0: cx, y0: cy, x1: cx, y1: cy };
      return;
    }
    const [u, v] = px;
    if (u < -0.5 || v < -0.5 || u > D.w - 0.5 || v > D.h - 0.5) return;
    const s = D.series[D.cur];
    if (/^[xy][01]$/.test(D.tool)) {
      const a = D.tool[0], i = Number(D.tool[1]);
      D.axes[a][i].px = [round2(u), round2(v)];
      const next = AXES.map(([b, j]) => b + j).find(k => !D.axes[k[0]][Number(k[1])].px);
      D.tool = next || null;
      renderSide();
      const box = $(`#digAxes [data-axis="${a}${i}"] input[type=number]`);
      if (box && box.value === '') box.focus();
    } else if (D.tool === 'colour' && s) {
      s.colour = colourAt(u, v);
      if (s.mode === 'points') s.mode = 'line';
      D.tool = null;
      renderSide();
    } else if (D.tool === 'points' && s) {
      const near = s.points.findIndex(([a, b]) => Math.hypot(a - u, b - v) * D.view.scale < 8 * (window.devicePixelRatio || 1));
      if (near >= 0) s.points.splice(near, 1);             // a click on a point takes it away
      else s.points.push([round2(u), round2(v)]);
      renderSide(false);
    }
    draw();
    schedulePreview();
  }
  const round2 = v => Math.round(v * 100) / 100;

  function onMove(ev) {
    if (!D.img) return;
    const { cx, cy, px } = eventPx(ev);
    D.mouse = px;
    if (D.drag && D.drag.kind === 'pan') {
      D.view.ox = D.drag.ox + cx - D.drag.cx;
      D.view.oy = D.drag.oy + cy - D.drag.cy;
    } else if (D.drag && D.drag.kind === 'region') {
      Object.assign(D.drag, { x1: cx, y1: cy });
    }
    draw();
  }

  function onUp() {
    if (D.drag && D.drag.kind === 'region') {
      const { x0, y0, x1, y1 } = D.drag;
      const [u0, v0] = toPx(x0, y0), [u1, v1] = toPx(x1, y1);
      const s = D.series[D.cur];
      if (s && Math.abs(u1 - u0) > 3 && Math.abs(v1 - v0) > 3) {
        s.region = [round2(Math.max(0, Math.min(u0, u1))), round2(Math.max(0, Math.min(v0, v1))),
          round2(Math.min(D.w - 1, Math.max(u0, u1))), round2(Math.min(D.h - 1, Math.max(v0, v1)))];
        D.tool = null;
        renderSide();
        schedulePreview();
      }
    }
    D.drag = null;
    draw();
  }

  function onWheel(ev) {
    if (!D.img) return;
    ev.preventDefault();
    const { cx, cy } = eventPx(ev);
    const k = Math.exp(-ev.deltaY * 0.0015);
    const s = Math.max(0.05, Math.min(40, D.view.scale * k));
    D.view.ox = cx - (cx - D.view.ox) * s / D.view.scale;
    D.view.oy = cy - (cy - D.view.oy) * s / D.view.scale;
    D.view.scale = s;
    draw();
  }

  // ------------------------------------------------------------ the side panel
  function renderSide(full = true) {
    const ax = $('#digAxes');
    if (full) {
      ax.innerHTML = '';
      AXES.forEach(([a, i]) => {
        const e = D.axes[a][i];
        const row = document.createElement('div');
        row.className = 'dig-axis' + (D.tool === `${a}${i}` ? ' active' : '');
        row.dataset.axis = `${a}${i}`;
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn small' + (D.tool === `${a}${i}` ? ' primary' : '');
        b.textContent = `${e.px ? '✓' : '＋'} ${a.toUpperCase()}${i + 1}`;
        b.title = t('dig.axis_hint', { axis: a.toUpperCase() });
        b.onclick = () => { D.tool = `${a}${i}`; renderSide(); draw(); };
        const inp = document.createElement('input');
        inp.type = 'number';
        inp.step = 'any';
        inp.value = e.value;
        inp.placeholder = `${t('dig.value')} ${a.toUpperCase()}${i + 1}`;
        inp.oninput = () => { e.value = inp.value; schedulePreview(); };
        row.append(b, inp);
        ax.append(row);
      });
      $('#digXLog').checked = !!D.axes.xlog;
      $('#digYLog').checked = !!D.axes.ylog;
    }
    const list = $('#digSeries');
    list.innerHTML = '';
    D.series.forEach((s, k) => {
      const row = document.createElement('div');
      row.className = 'dig-series' + (k === D.cur ? ' active' : '');
      const pick = document.createElement('input');
      pick.type = 'radio';
      pick.name = 'digCur';
      pick.checked = k === D.cur;
      pick.onchange = () => { D.cur = k; D.tool = null; renderSide(); draw(); };
      const sw = document.createElement('span');
      sw.className = 'dig-swatch';
      sw.style.background = s.colour || 'transparent';
      const name = document.createElement('input');
      name.type = 'text';
      name.value = s.name;
      name.oninput = () => { s.name = name.value; };
      const n = document.createElement('span');
      n.className = 'tiny muted';
      const pv = (D.preview || [])[k];
      n.textContent = pv ? t('dig.n_points', { n: pv.n.toLocaleString(LOCALE()) }) : '';
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'btn ghost icon small';
      del.textContent = '×';
      del.title = t('dig.remove_curve');
      del.disabled = D.series.length < 2;
      del.onclick = () => { D.series.splice(k, 1); D.cur = Math.min(D.cur, D.series.length - 1); renderSide(); schedulePreview(); };
      row.append(pick, sw, name, n, del);
      list.append(row);
    });
    const s = D.series[D.cur];
    $('#digMode').value = s.mode;
    $('#digTol').value = s.tolerance;
    $('#digTolText').textContent = `${s.tolerance} %`;
    $('#digColourRow').hidden = s.mode === 'points';
    $('#digPointsRow').hidden = s.mode !== 'points';
    $('#digSwatch').style.background = s.colour || 'transparent';
    $('#digSwatch').title = s.colour || '';
    $('#digPickColour').classList.toggle('primary', D.tool === 'colour');
    $('#digRegion').classList.toggle('primary', D.tool === 'region');
    $('#digClickPoints').classList.toggle('primary', D.tool === 'points');
    $('#digRegionClear').hidden = !s.region;
    $('#digPan').classList.toggle('primary', D.tool === 'pan');
    $('#digHint').textContent = t(`dig.hint_${D.tool || 'none'}`);   // each axis point says where it goes
    $('#digMake').disabled = D.busy;
    $('#digCsv').disabled = $('#digXlsx').disabled = D.busy;
  }

  // ------------------------------------------------------------ the service
  const calibrated = () => AXES.every(([a, i]) => D.axes[a][i].px && D.axes[a][i].value !== '');
  const body = () => ({ file_id: D.fileId, axes: D.axes, series: D.series.filter(usable), xname: $('#digXName').value,
    yname: $('#digYName').value });
  const usable = s => (s.mode === 'points' ? s.points.length : !!s.colour);

  function schedulePreview(delay = 350) {
    clearTimeout(D.timer);
    D.timer = setTimeout(preview, delay);
  }

  async function preview() {
    D.made = null;
    const msg = $('#digMessage');
    msg.classList.remove('error');
    if (!calibrated()) { D.preview = null; msg.textContent = t('dig.need_axes'); renderSide(false); draw(); return; }
    if (!D.series.some(usable)) { D.preview = null; msg.textContent = t('dig.need_curve'); renderSide(false); draw(); return; }
    try {
      const out = await api('/api/digitize/preview', body());
      // Back in the order of the list (curves not usable yet have no points).
      let k = 0;
      D.preview = D.series.map(s => (usable(s) ? out.curves[k++] : null)).map(c => c || { px: [], n: 0 });
      msg.textContent = '';
    } catch (e) {
      D.preview = null;
      msg.textContent = specMessage(e);
      msg.classList.add('error');
      if (e.code === 'missing_modules') handleError(e);
    }
    renderSide(false);
    draw();
  }

  // The table: added to the loaded files (or in place of the one it was read before), drawn at once.
  async function make() {
    if (D.made) return D.made;
    D.busy = true;
    renderSide(false);
    try {
      const ds = await api('/api/digitize', { ...body(), name: `${D.name} › ${t('dig.digitised')}` });
      const info = { file_id: D.fileId, name: ds.name, format: 'digitize', tables: ['data'] };
      if (D.replaces && Files.list().some(e => e.id === D.replaces)) Files.replace(D.replaces, ds, info);
      else Files.add(ds, info, false);
      Files.render();
      Files.activate(ds.dataset_id);
      if (state.dataset && state.dataset.dataset_id !== ds.dataset_id) { showFileControls(info); applyDataset(ds); }
      const cols = ds.columns.map(c => c.name);
      const several = cols[0] === 'curve';
      const s = state.spec;
      s.x = cols[several ? 1 : 0];
      s.y = [cols[several ? 2 : 1]];
      s.hue = several ? 'curve' : null;
      const read = D.series.filter(usable);
      s.kind = read.every(c => c.mode !== 'line') ? 'scatter' : 'line';
      // On lines, the curves read as markers or clicked point by point are drawn as markers.
      s.series = s.series || {};
      if (s.kind === 'line') {
        read.filter(c => c.mode !== 'line').forEach(c => {
          const key = several ? `${s.y[0]}::${c.name}` : s.y[0];
          s.series[key] = { ...(s.series[key] || {}), linestyle: 'none', marker: 'o' };
        });
      }
      ['xscale', 'yscale'].forEach((k, i) => { s.axes[k] = D.axes[i ? 'ylog' : 'xlog'] ? 'log' : 'linear'; });
      refreshSpecUI();
      scheduleRender(0);
      D.made = ds;
      D.replaces = ds.dataset_id;
      toast(t('dig.made', { rows: ds.rows.toLocaleString(LOCALE()) }));
      return ds;
    } catch (e) {
      if (e.code === 'digitize') toast(specMessage(e), true);
      else handleError(e);
      return null;
    } finally {
      D.busy = false;
      renderSide(false);
    }
  }

  async function save(format) {
    const ds = await make();
    if (ds) downloadTable(ds.dataset_id, format, `${D.name.replace(/\.[^.]+$/, '')} digitised`);
  }

  // ------------------------------------------------------------ wiring
  function init() {
    const c = canvas();
    c.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', ev => { if (dlg().open) onMove(ev); });
    window.addEventListener('mouseup', () => { if (dlg().open) onUp(); });
    c.addEventListener('mouseleave', () => { D.mouse = null; draw(); });
    c.addEventListener('wheel', onWheel, { passive: false });
    c.addEventListener('contextmenu', ev => ev.preventDefault());
    window.addEventListener('keydown', ev => { if (dlg().open && ev.code === 'Space' && ev.target.tagName !== 'INPUT') { D.space = true; ev.preventDefault(); } });
    window.addEventListener('keyup', ev => { if (ev.code === 'Space') D.space = false; });
    // The dialog laid out anew (a window resized, the side panel growing): the same view, on a bitmap of the new size.
    new ResizeObserver(() => { if (dlg().open && D.img && sizeCanvas()) draw(); }).observe(c);
    $('#digXLog').onchange = () => { D.axes.xlog = $('#digXLog').checked; schedulePreview(); };
    $('#digYLog').onchange = () => { D.axes.ylog = $('#digYLog').checked; schedulePreview(); };
    $('#digAddCurve').onclick = () => { D.series.push(newSeries(D.series.length)); D.cur = D.series.length - 1; D.tool = 'colour'; renderSide(); draw(); };
    $('#digMode').onchange = () => {
      const s = D.series[D.cur];
      s.mode = $('#digMode').value;
      D.tool = s.mode === 'points' ? 'points' : s.colour ? null : 'colour';
      renderSide();
      draw();
      schedulePreview();
    };
    $('#digTol').oninput = () => { D.series[D.cur].tolerance = Number($('#digTol').value); renderSide(false); schedulePreview(); };
    $('#digPickColour').onclick = () => { D.tool = D.tool === 'colour' ? null : 'colour'; renderSide(); };
    $('#digRegion').onclick = () => { D.tool = D.tool === 'region' ? null : 'region'; renderSide(); };
    $('#digRegionClear').onclick = () => { D.series[D.cur].region = null; renderSide(); draw(); schedulePreview(); };
    $('#digClickPoints').onclick = () => { D.tool = D.tool === 'points' ? null : 'points'; renderSide(); };
    $('#digClearPoints').onclick = () => { D.series[D.cur].points = []; renderSide(); draw(); schedulePreview(); };
    $('#digPan').onclick = () => { D.tool = D.tool === 'pan' ? null : 'pan'; renderSide(); };
    $('#digFit').onclick = fit;
    $('#digXName').oninput = $('#digYName').oninput = () => { D.made = null; };
    $('#digMake').onclick = () => make().then(ds => { if (ds) close(); });
    $('#digCsv').onclick = () => save('csv');
    $('#digXlsx').onclick = () => save('xlsx');
    $('#digClose').onclick = close;
    $('#btnDigitize').onclick = open;
  }

  // The button shows for a picture, and for a table read from one (to change how it was read).
  function update() {
    const src = state.dataset && state.dataset.source;
    const show = !!(state.file && state.file.format === 'image') || !!(src && src.digitize);
    $('#digitizeBox').hidden = !show;
  }

  Bus.on('ready', init);
  Bus.on('dataset:shown', update);
  return { open, close, update, state: D };
})();
