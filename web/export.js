// π-plotter interface — Exporting the figure and style templates.
// The page is split into classic scripts loaded in order (see index.html); they share one global scope.
'use strict';

// ------------------------------------------------------------------ export & templates
async function exportFigure() {
  if (!state.dataset) return;
  const format = $('#exportFormat').value;
  store.set('pp-export-format', format);
  const need = missingOf(state.meta.export_formats[format].requires);
  if (need.length && !(await ensureModules(need))) return;
  const btn = $('#btnExport');
  btn.disabled = true;
  const label = btn.querySelector('span');
  label.textContent = t('export.busy');
  try {
    const name = $('#exportName').value.trim() || 'figure';
    const res = await api('/api/export', { dataset_id: state.dataset.dataset_id, spec: specForServer(), format,
      dpi: state.spec.figure.dpi, filename: name }, { raw: true });
    const blob = await res.blob();
    const ext = format === 'py' ? 'zip' : format;
    download(blob, `${name}.${ext}`);
    toast(t('export.done', { name: `${name}.${ext}` }));
  } catch (e) {
    handleError(e, exportFigure);
  } finally {
    btn.disabled = false;
    label.textContent = t('export.button');
  }
}

function download(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

function saveTemplate() {
  const tpl = { schema: 'piplotter-template/1', ...styleSnapshot() };
  download(new Blob([JSON.stringify(tpl, null, 2)], { type: 'application/json' }), 'piplotter-style.json');
}

async function loadTemplate(file) {
  try {
    const data = JSON.parse(await file.text());
    if (!/^(piplotter|pyplotter)-template\//.test(String(data.schema || ''))) throw new Error(t('tpl.bad'));
    STYLE_KEYS.forEach(k => { if (data[k]) state.spec[k] = merge(state.spec[k], data[k]); });
    syncControls();
    buildKindOptions();
    updatePalettePreview();
    buildSeries();
    saveStyle();
    updateFigInfo();
    scheduleRender(0);
    toast(t('tpl.loaded'));
  } catch (e) {
    toast(e.message || t('tpl.bad'), true);
  }
}
