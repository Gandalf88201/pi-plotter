"""Analyses and plugins: the list, the advice, one run, the same run on many files (batch), the plugin editor."""
import math
import numbers
import secrets
import traceback

from ..modules import canonical
from .common import MAX_BATCH_FILES, ApiError


def _same_columns(plugin, params, df):
    """A result computed again on a new version of its table (strict): the columns it was made from must still be
    there — an analysis quietly falling back to another column would give numbers that look current but are not."""
    for prm in plugin.get('params', []):
        if prm.get('type') not in ('column', 'columns'):
            continue
        v = params.get(prm['id'])
        gone = [c for c in (v if isinstance(v, list) else [v]) if isinstance(c, str) and c and c not in df.columns]
        if gone:
            raise ApiError('The table no longer has the column ' + ', '.join(f'“{c}”' for c in gone)
                           + ' this result was made from.', 422, 'column_gone')


def _keyed_values(res):
    """[{key, value, error}] of the numbers an analysis keeps under fixed names (fitted parameters, R²…), offered
    for a box of values in the figure."""
    num = lambda v: isinstance(v, numbers.Real) and not isinstance(v, bool) and math.isfinite(v)   # noqa: E731
    return [{'key': k, 'value': float(v), 'error': float(e) if num(e) else None}
            for k, (v, e) in res.out.items() if num(v)]


def _batch_numbers(res, limit=200):
    """The numbers of one result for its row of a batch: the values it keeps for recipes (fitted parameters with
    their errors, R²…, under fixed names), else its summary, else its first table (one row as it is, more rows
    flattened as "row · column")."""
    def number(v):
        return isinstance(v, numbers.Real) and not isinstance(v, bool) and math.isfinite(v)   # numpy too
    out = {}
    for key, (value, error) in res.out.items():
        if number(value):
            out[key] = float(value)
            if number(error):
                out[f'σ({key})'] = float(error)
    if not out:
        for entry in res.summary:
            label = entry['label'] + (f' ({entry["unit"]})' if entry['unit'] else '')
            out[label] = entry['value']
            if entry['error'] is not None:
                out[f'σ({label})'] = entry['error']
    if not out and res.tables:
        tb = res.tables[0]
        for r in tb['rows'][:limit]:
            for col, v in zip(tb['columns'], r):
                if number(v):
                    out[col if len(tb['rows']) == 1 else f'{r[0]} · {col}'] = v
    return dict(list(out.items())[:limit])


def _follow_columns(params, given, main, f):
    """Parameters of a batch for one file: a column chosen as the figure's X, one of its Y or its Y error becomes
    the file's own (the same place in its list of Y); other values are kept."""
    mx, my, me, fy = main.get('x'), list(main.get('y') or []), main.get('yerr'), list(f.get('y') or [])

    def follow(v):
        if not isinstance(v, str) or not v:
            return v
        if v == mx and f.get('x'):
            return f['x']
        if v == me and f.get('yerr'):
            return f['yerr']
        if v in my and fy:
            i = my.index(v)
            return fy[i] if i < len(fy) else fy[0]
        return v
    out = dict(given)
    for prm in params:
        v = out.get(prm['id'])
        if prm['type'] == 'column':
            out[prm['id']] = follow(v)
        elif prm['type'] == 'columns' and isinstance(v, list):
            out[prm['id']] = list(dict.fromkeys(follow(c) for c in v))
    return out


def _plugin_message(exc, plugin):
    """Error text for a failed analysis; for user plugins include the failing line of their file."""
    msg = f'{exc.__class__.__name__}: {exc}' if not str(exc).startswith(exc.__class__.__name__) else str(exc)
    if isinstance(exc, (ValueError,)) and exc.__class__.__name__ in ('ValueError', 'PluginError'):
        msg = str(exc)
    tb = traceback.extract_tb(exc.__traceback__)
    lines = [f for f in tb if f.filename == plugin.get('path')]
    if lines and plugin.get('source') == 'user':
        msg += f' ({plugin["file"]}, line {lines[-1].lineno})'
    return msg


class AnalysesArea:
    # -------------------------------------------------------------- analyses & plugins
    def plugin_manager(self):
        self.modules.require(self.modules.core_ids())
        if self._plugins is None:
            from ..plugins import PluginManager
            self._plugins = PluginManager()
        return self._plugins

    def analyses(self):
        return self.plugin_manager().describe(missing=self.modules.missing, blocked=self.modules.unusable)

    def figure_files(self, ds, spec):
        """The files of the figure for ctx.files: the analysed one first, then the other enabled files in the order
        of the list, each with its x and y columns (excluded rows left out)."""
        from ..tables import kept
        out = [{'name': ds['name'], 'df': kept(ds['df']), 'x': spec.get('x') or None,
                'y': [c for c in spec.get('y') or [] if c in ds['df'].columns], 'main': True,
                'yerr': spec.get('yerr') if spec.get('yerr') in ds['df'].columns else None}]
        extras = [e for e in spec.get('extra') or [] if isinstance(e, dict) and e.get('enabled', True)]
        try:
            frames = self.extra_data(spec) if extras else {}
        except Exception:
            frames = {}
        for e in sorted(extras, key=lambda e: e.get('pos') or 0):
            frame = frames.get(e.get('id'))
            if frame is not None:
                out.append({'name': str(e.get('name') or e.get('id')), 'df': frame, 'x': e.get('x') or None,
                            'y': [c for c in e.get('y') or [] if c in frame.columns], 'main': False,
                            'yerr': e.get('yerr') if e.get('yerr') in frame.columns else None})
        return out

    def suggest_analyses(self, body):
        """Analyses that suit the figure on screen (advisor.py), best first, with the reason and starting values."""
        ds = self.dataset(body.get('dataset_id'))
        from .. import advisor
        spec = body.get('spec') or {}
        files = 1 + sum(1 for e in spec.get('extra') or [] if isinstance(e, dict) and e.get('enabled', True))
        out = advisor.advise(spec, ds['columns'], ds['df'], self.plugin_manager().plugins, n_files=files)
        out['facts'] = {k: v for k, v in out['facts'].items() if k in ('kind', 'xkind', 'decays', 'curves')}
        return out

    def run_analysis(self, body):
        from ..plugins import PluginError
        ds = self.dataset(body.get('dataset_id'))
        pm = self.plugin_manager()
        try:
            plugin = pm.get(str(body.get('id')))
        except PluginError as exc:
            raise ApiError(str(exc), 404, 'plugin')
        self.modules.require(self.modules.core_ids() + plugin['requires'])
        blocked = self.modules.unusable(plugin['requires'], plugin['imports'])
        if blocked:
            raise ApiError('This analysis needs modules that do not import: '
                           + '; '.join(f'{name} ({error})' for name, error in blocked), 409, 'blocked_module')
        lang = body.get('lang') if body.get('lang') in ('en', 'it') else 'en'
        spec = body.get('spec') or {}
        if body.get('strict'):
            _same_columns(plugin, body.get('params') or {}, ds['df'])
        try:
            from ..tables import kept                          # rows the user excluded stay out of every analysis
            plugin, values, res = pm.run(plugin['id'], kept(ds['df']), body.get('params') or {}, lang, spec,
                                         files=self.figure_files(ds, spec))
        except (PluginError, ValueError, KeyError, TypeError, ZeroDivisionError, RuntimeError, ArithmeticError) as exc:
            raise ApiError(_plugin_message(exc, plugin), 422, 'analysis')
        except ImportError as exc:
            raise ApiError(f'A module is missing: {exc}', 409, 'import_error')
        except Exception as exc:
            traceback.print_exc()
            raise ApiError(_plugin_message(exc, plugin), 422, 'analysis')
        out = {'plugin': {'id': plugin['id'], 'name': plugin['name'], 'source': plugin['source'], 'file': plugin['file']},
               'params': values, 'summary': res.summary, 'tables': res.tables, 'texts': res.texts,
               'references': list(dict.fromkeys(res.refs + self.modules.user_citations(plugin['requires']))),
               'dataset': None, 'plot': res.plot, 'values': _keyed_values(res)}
        from ..readers import tidy
        source = {'analysis': plugin['id'], 'params': values, 'parent': ds['source'], 'spec': spec, 'lang': lang}
        refs = ds.get('references', []) + out['references']
        title = res.name or plugin['name'][lang]
        out['overlays'] = []
        for k, ov in enumerate(res.overlays):
            reg = self._register(ov['frame'], f'{ds["name"]} › {title} · {ov["label"]}', {**source, 'overlay': k}, {},
                                 references=refs)
            reg.pop('preview', None)
            out['overlays'].append({
                'dataset': reg, 'source': {**source, 'overlay': k}, 'dataset_id': reg['dataset_id'],
                'x': ov['x'], 'y': ov['y'], 'lo': ov['lo'], 'hi': ov['hi'], 'label': ov['label'],
                'band_label': ov['band_label'], 'style': ov['style'], 'band': bool(ov['lo'] and ov['hi']),
                'on_figure': ov.get('on_figure', True), 'text': ov.get('text'), 'note': ov.get('note'),
                'id': secrets.token_hex(5), 'references': out['references']})
        out['analysed_dataset'] = str(body.get('dataset_id'))
        out['source'] = source                              # how to compute it again (on a new version of the table)
        if res.frame is not None and len(res.frame.columns):
            name = f'{ds["name"]} › {title}'
            out['dataset'] = self._register(tidy(res.frame.copy()), name, source, {}, references=refs)
            plot = dict(res.plot or {})
            if plot.get('overlays'):         # {'ref': k} → the k-th overlay of this result
                resolved = []
                for o in plot['overlays']:
                    if isinstance(o, dict) and 'ref' in o and int(o['ref']) < len(out['overlays']):
                        base = {k: v for k, v in out['overlays'][int(o['ref'])].items() if k != 'dataset'}
                        resolved.append({**base, **{k: v for k, v in o.items() if k != 'ref'}})
                plot['overlays'] = resolved
            out['plot'] = plot
        return out

    def batch_analysis(self, body):
        """The same analysis on many files (Origin's Batch Processing): one row per file with the numbers of its
        summary, value and error; files where it fails are listed apart instead of stopping the others.

        Column parameters follow each file: a column chosen as the figure's X (one of its Y, its Y error) becomes
        that file's own X (Y, Y error), as the figure draws it; other names are used as they are. The table is a
        data set rebuilt from its source like any other (projects), so it can be plotted and exported."""
        from ..plugins import PluginError, _cell
        from ..readers import tidy
        from ..tables import kept
        import pandas as pd
        pm = self.plugin_manager()
        try:
            plugin = pm.get(str(body.get('id')))
        except PluginError as exc:
            raise ApiError(str(exc), 404, 'plugin')
        self.modules.require(self.modules.core_ids() + plugin['requires'])
        blocked = self.modules.unusable(plugin['requires'], plugin['imports'])
        if blocked:
            raise ApiError('This analysis needs modules that do not import: '
                           + '; '.join(f'{name} ({error})' for name, error in blocked), 409, 'blocked_module')
        lang = body.get('lang') if body.get('lang') in ('en', 'it') else 'en'
        tr = lambda en, it: it if lang == 'it' else en          # noqa: E731
        spec = body.get('spec') or {}
        main = body.get('main') or {'x': spec.get('x'), 'y': spec.get('y') or [], 'yerr': spec.get('yerr')}
        files = [f for f in body.get('files') or [] if isinstance(f, dict)]
        if not files:
            raise ApiError(tr('No files to analyse.', 'Nessun file da analizzare.'), 400, 'batch')
        if len(files) > MAX_BATCH_FILES:
            raise ApiError(tr(f'At most {MAX_BATCH_FILES} files in one batch.',
                              f'Al massimo {MAX_BATCH_FILES} file in una serie.'), 400, 'batch')
        params = body.get('params') or {}
        name_col, rows, failed, refs, used = tr('file', 'file'), [], [], [], []
        for k, f in enumerate(files, 1):
            name = str(f.get('name') or f'#{k}')
            fspec = {**spec, 'x': f.get('x') or None, 'y': list(f.get('y') or []), 'yerr': f.get('yerr') or None,
                     'extra': [], 'overlays': []}
            temp = None
            try:
                ds, temp = self._batch_dataset(f)
                df = kept(ds['df'])
                one = [{'name': ds['name'], 'df': df, 'x': fspec['x'],
                        'y': [c for c in fspec['y'] if c in df.columns], 'main': True,
                        'yerr': fspec['yerr'] if fspec['yerr'] in df.columns else None}]
                _, _, res = pm.run(plugin['id'], df, _follow_columns(plugin['params'], params, main, f), lang, fspec,
                                   files=one)
            except ImportError as exc:
                raise ApiError(f'A module is missing: {exc}', 409, 'import_error')
            except ApiError as exc:
                failed.append([name, str(exc)])
                continue
            except Exception as exc:              # one file that does not fit the analysis does not stop the rest
                failed.append([name, _plugin_message(exc, plugin)])
                continue
            finally:
                if temp:                          # read only for this batch (a file of a folder): not kept
                    with self.lock:
                        self.datasets.pop(temp, None)
            row = {'#': k, name_col: name, **_batch_numbers(res)}
            rows.append(row)
            refs.extend(r for r in res.refs if r not in refs)
            used.append({'source': ds['source'], 'name': name, 'x': fspec['x'], 'y': fspec['y'], 'yerr': fspec['yerr']})
        if not rows:
            raise ApiError(tr('The analysis failed on every file: ', 'L’analisi non riesce su nessun file: ')
                           + '; '.join(f'{n}: {m}' for n, m in failed), 422, 'analysis')
        frame = pd.DataFrame(rows)
        title = plugin['name'][lang]
        out = {'plugin': {'id': plugin['id'], 'name': plugin['name'], 'source': plugin['source'], 'file': plugin['file']},
               'params': params, 'summary': [], 'overlays': [], 'analysed_dataset': f'batch:{plugin["id"]}',
               'texts': [tr(f'{title}: {len(rows)} of {len(files)} files.', f'{title}: {len(rows)} file su {len(files)}.')],
               'tables': [{'title': tr('One row per file', 'Una riga per file'), 'columns': [str(c) for c in frame.columns],
                           'rows': [[_cell(v) for v in r] for r in frame.itertuples(index=False, name=None)]}],
               'references': list(dict.fromkeys(refs + self.modules.user_citations(plugin['requires'])))}
        if failed:
            out['tables'].append({'title': tr('Files where it failed', 'File su cui non riesce'),
                                  'columns': [name_col, tr('reason', 'motivo')], 'rows': failed})
        source = {'batch': plugin['id'], 'params': params, 'main': main, 'files': used, 'spec': spec, 'lang': lang}
        out['dataset'] = self._register(tidy(frame.copy()), tr(f'{title} · batch of {len(rows)} files',
                                                               f'{title} · serie di {len(rows)} file'),
                                        source, {}, references=out['references'])
        # Plotted: the first number of the summary against the file number, with its error when it has one.
        first = next((c for c in frame.columns[2:] if not str(c).startswith('σ(')
                      and pd.api.types.is_numeric_dtype(frame[c])), None)
        if first is not None:
            err = f'σ({first})' if f'σ({first})' in frame.columns else None
            out['plot'] = {'kind': 'errorbar' if err else 'scatter', 'x': '#', 'y': [first], 'yerr': err,
                           'style': {'marker': 'o'}}
        else:
            out['plot'] = {}
        return out

    def _batch_dataset(self, f):
        """A file of a batch: loaded, or rebuilt from its source (after a restart, in a project); a file never
        opened (one of a folder) is read only for the batch. Second item: the id of a data set made only for the
        batch, to drop after it."""
        if f.get('dataset_id'):
            try:
                return self.dataset(f.get('dataset_id')), None
            except ApiError:
                if not f.get('source'):
                    raise
            return self.dataset(self.reopen(f['source'])['dataset_id']), None
        if not f.get('source'):
            raise ApiError('Unknown data source.', 400)
        did = self.reopen(f['source'])['dataset_id']
        return self.dataset(did), did

    def plugin_action(self, action, body):
        from ..plugins import PluginError
        pm = self.plugin_manager()
        try:
            if action == 'read':
                return pm.read(body.get('file'), body.get('id'))
            if action == 'save':
                code = str(body.get('code') or '')
                if len(code) > 2_000_000:
                    raise PluginError('The plugin file is too large.')
                return pm.save(body.get('file'), code)
            if action == 'new':
                return pm.create(body.get('name'))
            if action == 'customize':
                return pm.customize(str(body.get('id')))
            if action == 'integration':          # the first analysis using one of the user's modules
                rec = self.modules.user.get(canonical(str(body.get('name') or '')))
                if not rec:
                    raise PluginError('Not one of your modules.')
                return pm.create_integration(rec['pip'], (rec.get('imports') or [''])[0])
            if action == 'disable':
                return pm.disable(body.get('file'))
            if action == 'folder':
                return pm.open_folder()
            if action == 'reload':
                pm.reload()
                return self.analyses()
        except (PluginError, OSError) as exc:
            raise ApiError(str(exc), 422, 'plugin')
        raise ApiError('Unknown plugin action.', 404)
