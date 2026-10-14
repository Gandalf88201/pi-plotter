"""Local HTTP service for the π-plotter web interface.

Listens on loopback only. Every /api call must carry the per-session token embedded in the page
and a loopback Host header. Uploaded files live in a private session directory that is removed
when π-plotter stops. The server starts with the standard library alone; NumPy, pandas and
Matplotlib are imported on first use, after the interface has installed them.
"""
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import numbers
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import threading
import time
import traceback
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import AUTHOR, NAME, __version__, catalog, manual
from .modules import MissingModules, MissingUserModules, ModuleManager, canonical, clean_appledouble

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
MAX_JSON = 32 * 1024 * 1024
MAX_BATCH_FILES = 500           # files in one batch analysis
MAX_DATASETS = 200                # kept in memory, least recently used dropped first …
MAX_DATASET_BYTES = 2 * 1024 ** 3  # … also when together they take more than this
PREVIEW_ROWS = 200
PREVIEW_COLS = 100      # the table shows the first columns: a wide table would be millions of cells
CHUNK = 1 << 20
DOWNLOAD_TTL = 600            # seconds a one-off download link stays valid
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.json': 'application/json'}


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


class ApiError(Exception):
    def __init__(self, message, status=400, code='error', **extra):
        super().__init__(message)
        self.status, self.code, self.extra = status, code, extra


def safe_name(name, fallback='data'):
    name = re.sub(r'[^\w.\-]+', '_', Path(str(name)).name, flags=re.UNICODE).strip('._')
    return name[:120] or fallback


def content_disposition(fname):
    """Header value for a download name; HTTP headers are Latin-1, so non-ASCII names go in filename*."""
    ascii_name = fname.encode('ascii', 'replace').decode('ascii').replace('?', '_').replace('"', '_')
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(fname, safe="")}'


def json_safe(v):
    """Make pandas/numpy cell values JSON-serialisable."""
    if v is None:
        return None
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, (str, bool, int)):
        return v
    if hasattr(v, 'isoformat'):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if hasattr(v, 'item'):
        try:
            return json_safe(v.item())
        except Exception:
            pass
    s = str(v)
    return None if s in ('NaT', 'nan', '<NA>') else s


def build_id():
    """Fingerprint of the program files: pages from another version ask to reload."""
    import hashlib
    h = hashlib.sha1(__version__.encode())
    for folder, pattern in ((WEB, '*'), (Path(__file__).parent, '*.py')):
        for f in sorted(folder.glob(pattern)):
            if f.is_file() and not f.name.startswith('.'):
                h.update(f.name.encode())
                h.update(f.read_bytes())
    return h.hexdigest()[:12]


class App:
    def __init__(self, token, session_dir, modules, max_upload_bytes):
        self.token = token
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.modules = modules
        self.max_upload = max_upload_bytes
        self.datasets = OrderedDict()
        self.render_lock = threading.Lock()
        self.lock = threading.Lock()
        self.files = self._load_files()
        self.restart_hook = None
        self.shutdown_hook = None
        self.started = time.time()
        self.build = build_id()
        self._plugins = None
        self.views3d = OrderedDict()      # id -> view3d of a recent 3D render (the rotatable preview)
        self._overlay_alias = {}
        self._console = None              # the Python console's process (console.py), started on first use
        self._autosaved = False           # this session has written its autosave (autosave.py)
        self.downloads = {}               # one-off links to files written on disk (a project): id -> path, name
        self._extra_refs = []

    # -------------------------------------------------------------- uploaded files
    def _files_index(self):
        return self.session_dir / 'files.json'

    def _load_files(self):
        try:
            return json.loads(self._files_index().read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _save_files(self):
        self._files_index().write_text(json.dumps(self.files), encoding='utf-8')

    def file(self, fid):
        info = self.files.get(str(fid))
        if not info or not Path(info['path']).is_file():
            raise ApiError('The file is no longer available; open it again.', 404, 'file_gone')
        return info

    def add_upload(self, name, stream, length):
        if length <= 0:
            raise ApiError('Empty upload.')
        if length > self.max_upload:
            raise ApiError(f'File larger than the limit ({self.max_upload / 1024 ** 3:.0f} GB).', 413)
        fmt, compression = catalog.detect_format(name)
        if fmt is None:
            raise ApiError('Unsupported file type: ' + (Path(name).suffix or name), 415, 'unsupported',
                           extensions=catalog.all_extensions())
        fid = secrets.token_hex(8)
        folder = self.session_dir / fid
        folder.mkdir()
        path = folder / safe_name(name)
        remaining = length
        with open(path, 'wb') as out:
            while remaining > 0:
                chunk = stream.read(min(CHUNK, remaining))
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
        if remaining:
            shutil.rmtree(folder, ignore_errors=True)
            raise ApiError('Upload interrupted.')
        info = {'id': fid, 'name': name, 'path': str(path), 'format': fmt, 'compression': compression, 'size': length}
        with self.lock:
            self.files[fid] = info
            self._save_files()
        return info

    def describe_file(self, info):
        need = self.modules.missing(catalog.FILE_FORMATS[info['format']]['requires'] + self.modules.core_ids())
        out = {'file_id': info['id'], 'name': info['name'], 'format': info['format'], 'size': info['size'],
               'missing': need, 'tables': []}
        if not need:
            from . import readers
            try:
                out['tables'] = readers.list_tables(info['path'], info['format'])
            except MissingModules:
                raise
            except ImportError as exc:
                raise ApiError(f'A module needed for this file is missing: {exc}', 409, 'import_error')
            except Exception as exc:
                raise ApiError(f'Cannot read {info["name"]}: {exc}', 422, 'read_error')
            if not out['tables']:
                raise ApiError('No table or dataset found in the file.', 422, 'read_error')
        return out

    # -------------------------------------------------------------- datasets
    def open_table(self, body):
        info = self.file(body.get('file_id'))
        self.modules.require(catalog.FILE_FORMATS[info['format']]['requires'] + self.modules.core_ids())
        from . import readers, smart
        table = body.get('table') or None
        options = body.get('options') or {}
        try:
            df, used = readers.read_table(info['path'], info['format'], table, options, info.get('compression'))
        except (MissingModules, ApiError):
            raise
        except ImportError as exc:
            raise ApiError(f'A module needed for this file is missing: {exc}', 409, 'import_error')
        except Exception as exc:
            raise ApiError(f'Cannot read {info["name"]}: {exc}', 422, 'read_error')
        if df.empty or not len(df.columns):
            raise ApiError('The table is empty.', 422, 'read_error')
        name = info['name'] + (f' › {table}' if table and table != 'data' else '')
        return self._register(df, name, {'file_id': info['id'], 'table': table, 'options': options}, used)

    # -------------------------------------------------------------- project files (.piplot)
    def save_project(self, body):
        """The project archive (bytes): the page's description of the work + the data files it uses."""
        from . import projects
        project = body.get('project')
        try:
            with self.lock:
                files = dict(self.files)
            return projects.to_bytes(project, files)
        except projects.ProjectError as exc:
            raise ApiError(str(exc), 422, 'project')

    def save_project_file(self, body):
        """Write the project archive to a file of the session and give a one-off link to download it: the data
        files are copied from disk to disk and sent in pieces, so a project of many GB never sits in memory (neither
        here nor in the page)."""
        from . import projects
        project = body.get('project')
        name = safe_name(body.get('filename') or 'project', 'project') + projects.EXTENSION
        with self.lock:
            files = dict(self.files)
        did = secrets.token_hex(16)
        path = self.session_dir / f'_save_{did}{projects.EXTENSION}'
        try:
            with open(path, 'wb') as out:
                projects.pack(project, files, out)
        except projects.ProjectError as exc:
            path.unlink(missing_ok=True)
            raise ApiError(str(exc), 422, 'project')
        except OSError as exc:
            path.unlink(missing_ok=True)
            raise ApiError(f'The project could not be written: {exc}', 500, 'project')
        with self.lock:
            self._expire_downloads()
            self.downloads[did] = {'path': path, 'name': name, 'until': time.time() + DOWNLOAD_TTL}
        return {'url': f'/download/{did}', 'name': name, 'size': path.stat().st_size}

    def take_download(self, did):
        """The file behind a one-off link (the link is used up)."""
        with self.lock:
            self._expire_downloads()
            d = self.downloads.pop(str(did), None)
        if d is None or not d['path'].is_file():
            raise ApiError('This download link has expired; save again.', 404, 'not_found')
        return d

    def _expire_downloads(self):
        now = time.time()
        for did in [k for k, d in self.downloads.items() if d['until'] < now]:
            self.downloads.pop(did)['path'].unlink(missing_ok=True)

    def open_project(self, name, stream, length):
        """Read an uploaded project: its data files go back into the session (new ids), and the project comes
        back with the file ids replaced, for the page to rebuild every data set from its source."""
        from . import projects
        if length <= 0:
            raise ApiError('Empty upload.')
        if length > self.max_upload:
            raise ApiError(f'File larger than the limit ({self.max_upload / 1024 ** 3:.0f} GB).', 413)
        tmp = self.session_dir / f'_project_{secrets.token_hex(6)}{projects.EXTENSION}'
        try:
            remaining = length
            with open(tmp, 'wb') as out:
                while remaining > 0:
                    chunk = stream.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
            if remaining:
                raise ApiError('Upload interrupted.')
            try:
                doc, entries = projects.read(tmp, self.max_upload)
            except projects.ProjectError as exc:
                raise ApiError(str(exc), 422, 'project')
            mapping = {}
            for old, fname, entry in entries:
                z, f, size = projects.open_entry(tmp, entry)
                try:
                    mapping[old] = self.add_upload(fname, f, size)['id']
                finally:
                    f.close()
                    z.close()
        finally:
            tmp.unlink(missing_ok=True)
        return {'project': projects.remap(doc, mapping), 'name': Path(name).stem}

    # -------------------------------------------------------------- tables written or edited by hand
    def blank_table(self, body):
        self.modules.require(self.modules.core_ids())
        from . import tables
        spec = {'cols': body.get('cols', 2), 'rows': body.get('rows', 10), 'names': body.get('names') or []}
        try:
            df = tables.blank(spec['cols'], spec['rows'], spec['names'])
        except (TypeError, ValueError) as exc:
            raise ApiError(str(exc), 422, 'table')
        name = str(body.get('name') or '').strip()[:120] or 'new table'
        return self._register(df, name, {'blank': spec, 'name': name}, {})

    def edit_table(self, body):
        """A new data set: the table with the user's operations applied (see tables.py); the old one stays,
        so going back to it undoes the edit. The source keeps every operation since the file or blank table."""
        ds = self.dataset(body.get('dataset_id'))
        from . import tables
        ops = body.get('ops')
        try:
            df = tables.apply_ops(ds['df'], ops)
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            raise ApiError(str(exc), 422, 'table')
        src = ds['source'] or {}
        if src.get('edit') is not None:
            source = {'edit': src['edit'], 'ops': tables.squash(list(src.get('ops') or []) + list(ops))}
        else:
            source = {'edit': src, 'ops': tables.squash(list(ops))}
        out = self._register(df, ds['name'], source, {}, references=ds.get('references', []))
        out['replaces'] = str(body.get('dataset_id'))
        return out

    def table_nearest(self, body):
        """The row of the point nearest to a click on the figure (to exclude it or bring it back)."""
        ds = self.dataset(body.get('dataset_id'))
        from . import tables
        cols = set(map(str, ds['df'].columns))
        x = body.get('x') if body.get('x') in cols else None
        ys = [y for y in body.get('ys') or [] if y in cols]
        try:
            hit = tables.nearest(ds['df'], x, ys, float(body['px']), float(body['py']), body['xlim'], body['ylim'],
                                 body.get('xscale', 'linear'), body.get('yscale', 'linear'))
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(f'Cannot find the point: {exc}', 422, 'table')
        if hit:
            hit['masked'] = hit['row'] in tables.masked(ds['df'])
        return hit or {}

    def table_rows(self, body):
        ds = self.dataset(body.get('dataset_id'))
        from . import tables
        page = tables.page(ds['df'], body.get('start', 0), body.get('count', 200), body.get('col_start', 0),
                           body.get('col_count', PREVIEW_COLS))
        page['rows'] = [[json_safe(v) for v in row] for row in page['rows']]
        return page

    def sample(self, which):
        self.modules.require(self.modules.core_ids())
        from . import samples
        df = samples.make(which)
        return self._register(df, f'sample: {which}', {'sample': which}, {})

    def _register(self, df, name, source, used, references=()):
        from . import smart
        cols = smart.profile(df)
        mapping = smart.default_mapping(cols, len(df))
        did = secrets.token_hex(6)
        try:
            size = int(df.memory_usage(index=True, deep=False).sum())
        except Exception:
            size = 0
        with self.lock:
            self.datasets[did] = {'df': df, 'name': name, 'source': source, 'columns': cols,
                                  'references': list(references), 'bytes': size}
            # Least recently used first (dataset() marks use): the file being plotted is never the one
            # dropped, however many analyses register their results and layers.
            total = sum(d.get('bytes', 0) for d in self.datasets.values())
            while len(self.datasets) > 1 and (len(self.datasets) > MAX_DATASETS or total > MAX_DATASET_BYTES):
                _, old = self.datasets.popitem(last=False)
                total -= old.get('bytes', 0)
        head = df.iloc[:PREVIEW_ROWS, :PREVIEW_COLS]
        return {'dataset_id': did, 'name': name, 'rows': int(len(df)), 'columns': cols, 'mapping': mapping,
                'options': {k: v for k, v in used.items() if k != 'names'}, 'source': source,
                'recommend': smart.recommend(cols, mapping, len(df)),
                'preview': [[json_safe(v) for v in row] for row in head.itertuples(index=False, name=None)],
                'preview_cols': int(head.shape[1]), 'masked': len(df.attrs.get('masked', []))}

    def dataset(self, did):
        with self.lock:
            ds = self.datasets.get(str(did))
            if ds is not None:
                self.datasets.move_to_end(str(did))          # recently used: dropped last
        if ds is None:
            raise ApiError('The data set is no longer loaded; open the file again.', 404, 'dataset_gone')
        return ds

    def reopen(self, source, depth=0):
        """Rebuild a data set from its source: file, sample, or analysis of another data set."""
        if not isinstance(source, dict) or depth > 10:
            raise ApiError('Unknown data source.', 400)
        if source.get('sample'):
            return self.sample(str(source['sample']))
        if source.get('blank') is not None:
            return self.blank_table({**(source['blank'] or {}), 'name': source.get('name')})
        if source.get('edit') is not None:
            parent = self.reopen(source['edit'], depth + 1)
            return self.edit_table({'dataset_id': parent['dataset_id'], 'ops': source.get('ops') or []})
        if source.get('batch'):
            return self.batch_analysis({'id': source['batch'], 'params': source.get('params') or {},
                                        'main': source.get('main') or {}, 'files': source.get('files') or [],
                                        'spec': source.get('spec') or {}, 'lang': source.get('lang', 'en')})['dataset']
        if source.get('analysis'):
            parent = self.reopen(source.get('parent'), depth + 1)
            out = self.run_analysis({'dataset_id': parent['dataset_id'], 'id': source['analysis'],
                                     'params': source.get('params') or {}, 'spec': source.get('spec') or {},
                                     'lang': source.get('lang', 'en')})
            if source.get('overlay') is not None:
                return out['overlays'][int(source['overlay'])]['dataset']
            return out['dataset']
        return self.open_table(source)

    # -------------------------------------------------------------- autosave (autosave.py)
    def autosave_write(self, body):
        """Keep the work on screen on disk (the page sends it when it changes)."""
        from . import autosave
        project = body.get('project')
        if not isinstance(project, dict) or not project.get('files') and not project.get('main'):
            return {'saved': None}
        with self.lock:
            files = dict(self.files)
            first = not self._autosaved
            self._autosaved = True
        try:
            autosave.save(project, files, first, self.build)
        except OSError as exc:
            raise ApiError(f'Autosave failed: {exc}', 500, 'autosave')
        return {'saved': time.time()}

    def autosave_info(self):
        """The work that can be recovered (not this session's own copy)."""
        from . import autosave
        return {'items': autosave.info(skip_current=self._autosaved)}

    def autosave_recover(self, body):
        from . import autosave

        def add_file(name, path):
            with open(path, 'rb') as f:
                return self.add_upload(name, f, path.stat().st_size)['id']
        try:
            project, missing = autosave.recover(str(body.get('slot') or 'current'), add_file)
        except FileNotFoundError as exc:
            raise ApiError(str(exc), 404, 'autosave')
        return {'project': project, 'missing': missing}

    def autosave_discard(self, body):
        from . import autosave
        autosave.discard(str(body.get('slot') or ''))
        return {'ok': True}

    # -------------------------------------------------------------- the Python console
    def console_run(self, body):
        """Run code in the console (console.py) with df = the data of the figure and files = the open files; the
        tables it makes with new_table() become tables of their own, kept in projects like a table typed in."""
        self.modules.require(self.modules.core_ids())
        from .console import Console
        if self._console is None:
            self._console = Console()
        df, df_id = None, body.get('dataset_id')
        if df_id:
            try:
                df = self.dataset(df_id)['df']
            except ApiError:
                df_id = None
        files, ids = {}, []
        for f in body.get('files') or []:
            try:
                d = self.dataset(f.get('dataset_id'))
            except ApiError:
                continue
            files[str(f.get('name') or d['name'])] = d['df']
            ids.append(str(f.get('dataset_id')))
        try:
            out = self._console.run(str(body.get('code') or ''), df, df_id if df is not None else None, files,
                                    tuple(ids), body.get('spec') or {}, body.get('lang') or 'en')
        except RuntimeError as exc:
            raise ApiError(str(exc), 500, 'console')
        made = []
        for name, frame in out.pop('tables', []):
            try:
                made.append(self._table_of(frame, name))
            except (ValueError, TypeError) as exc:
                out['outputs'].append({'type': 'error', 'text': f'new_table({name!r}): {exc}'})
        out['tables'] = made
        return out

    def console_stop(self):
        if self._console is not None:
            self._console.stop()
        return {'ok': True}

    def console_reset(self):
        if self._console is not None:
            self._console.reset()
        return {'ok': True}

    def _table_of(self, frame, name):
        """A DataFrame as a table typed in: a blank table and the values pasted into it, so that it is edited,
        saved in projects and reopened like one (dates and other objects become text)."""
        import math
        import pandas as pd
        from . import tables
        from .readers import unique_names
        if frame.index.name is not None or not isinstance(frame.index, pd.RangeIndex):
            frame = frame.reset_index() if frame.index.name is not None else frame.reset_index(drop=True)
        names = unique_names([str(c).strip() or 'column' for c in frame.columns])
        if not names:
            raise ValueError('the table has no columns')
        if len(names) > tables.MAX_COLS or len(frame) > tables.MAX_ROWS:
            raise ValueError(f'too large for a table ({len(frame):,} rows × {len(names):,} columns; at most '
                             f'{tables.MAX_ROWS:,} × {tables.MAX_COLS:,}) — save it with frame.to_csv(…) instead')

        def cell(v):
            if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
                return None
            if isinstance(v, float):
                return repr(v)
            return v.isoformat() if hasattr(v, 'isoformat') else str(v)
        rows = [[cell(v) for v in row] for row in frame.itertuples(index=False, name=None)]
        spec = {'cols': len(names), 'rows': 0, 'names': names}
        step = max(1, tables.MAX_CELLS // len(names))
        ops = [{'op': 'paste', 'row': i, 'col': names[0], 'values': rows[i:i + step]} for i in range(0, len(rows), step)]
        df = tables.apply_ops(tables.blank(**spec), ops)
        name = str(name).strip()[:120] or 'console'
        return self._register(df, name, {'edit': {'blank': spec, 'name': name}, 'ops': ops}, {})

    # -------------------------------------------------------------- analyses & plugins
    def plugin_manager(self):
        self.modules.require(self.modules.core_ids())
        if self._plugins is None:
            from .plugins import PluginManager
            self._plugins = PluginManager()
        return self._plugins

    def analyses(self):
        return self.plugin_manager().describe(missing=self.modules.missing, blocked=self.modules.unusable)

    def figure_files(self, ds, spec):
        """The files of the figure for ctx.files: the analysed one first, then the other enabled files in the order
        of the list, each with its x and y columns (excluded rows left out)."""
        from .tables import kept
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
        from . import advisor
        spec = body.get('spec') or {}
        files = 1 + sum(1 for e in spec.get('extra') or [] if isinstance(e, dict) and e.get('enabled', True))
        out = advisor.advise(spec, ds['columns'], ds['df'], self.plugin_manager().plugins, n_files=files)
        out['facts'] = {k: v for k, v in out['facts'].items() if k in ('kind', 'xkind', 'decays', 'curves')}
        return out

    def run_analysis(self, body):
        from .plugins import PluginError
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
            from .tables import kept                          # rows the user excluded stay out of every analysis
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
        from .readers import tidy
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

    def _frames(self, items):
        """{item id: DataFrame} for overlay / extra-file entries of a spec ({'id', 'dataset_id', 'source'});
        data sets that are gone (e.g. after a restart) are rebuilt from their source when possible."""
        data = {}
        for o in items or []:
            if not isinstance(o, dict) or not o.get('dataset_id'):
                continue
            did = self._overlay_alias.get(o['dataset_id'], o['dataset_id'])
            with self.lock:
                ds = self.datasets.get(did)
                if ds is not None:
                    self.datasets.move_to_end(did)
            if ds is None and o.get('source'):
                try:
                    ds_new = self.reopen(o['source'])
                    self._overlay_alias[o['dataset_id']] = ds_new['dataset_id']
                    ds = self.datasets.get(ds_new['dataset_id'])
                except Exception:
                    ds = None
            if ds is not None:
                from .tables import kept
                data[o.get('id')] = kept(ds['df'])           # another file's excluded rows stay out too
                for r in ds.get('references', []):
                    if r not in self._extra_refs:
                        self._extra_refs.append(r)
        return data

    def overlay_data(self, spec):
        return self._frames(spec.get('overlays'))

    def batch_analysis(self, body):
        """The same analysis on many files (Origin's Batch Processing): one row per file with the numbers of its
        summary, value and error; files where it fails are listed apart instead of stopping the others.

        Column parameters follow each file: a column chosen as the figure's X (one of its Y, its Y error) becomes
        that file's own X (Y, Y error), as the figure draws it; other names are used as they are. The table is a
        data set rebuilt from its source like any other (projects), so it can be plotted and exported."""
        from .plugins import PluginError, _cell
        from .readers import tidy
        from .tables import kept
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

    def extra_data(self, spec):
        return self._frames(spec.get('extra'))

    def plugin_action(self, action, body):
        from .plugins import PluginError
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

    # -------------------------------------------------------------- figures
    def check_spec(self, spec, export=None):
        st = spec.get('style') or {}
        need = catalog.requirements_for(spec.get('kind'), st.get('base'), st.get('cmap'), export)
        self.modules.require(self.modules.core_ids() + need)

    def render(self, body, export=None, info=None):
        ds = self.dataset(body.get('dataset_id'))
        spec = body.get('spec') or {}
        self.check_spec(spec, export)
        from . import plotting, exporters
        from .tables import kept, masked
        fmt = export or 'png'
        df = kept(ds['df'])                       # excluded rows: out of the curves, drawn apart as crosses
        hidden = ds['df'].iloc[masked(ds['df'])] if masked(ds['df']) else None
        compose = [p for p in spec.get('compose') or [] if isinstance(p, dict)]
        if compose and fmt in ('html', 'py'):
            raise ApiError('A layout of several figures exports as an image, PDF, SVG or EPS.', 422, 'layout')
        try:
            with self.render_lock:
                self._extra_refs = []
                panels = [self._panel(p) for p in compose[:plotting.MAX_PANELS]] or None
                overlays = self.overlay_data(spec)
                extras = self.extra_data(spec)
                if fmt == 'html':
                    return exporters.plotly_html(df, spec, overlays, extras), catalog.EXPORT_FORMATS['html']['mime']
                if fmt == 'py':
                    data = exporters.script_bundle(df, spec, 'figure', self.modules.modules,
                                                   extra_refs=ds.get('references', []) + self._extra_refs,
                                                   source=ds['source'], overlay_data=overlays, extra_data=extras)
                    return data, catalog.EXPORT_FORMATS['py']['mime']
                dpi = body.get('dpi') if not export else (body.get('dpi') or None)
                return (plotting.render(df, spec, fmt, dpi, overlays, extras, info=info, masked=hidden, panels=panels),
                        catalog.EXPORT_FORMATS[fmt]['mime'])
        except plotting.SpecError as exc:
            raise ApiError(str(exc), 422, 'spec', key=exc.key, values=exc.values)
        except (MissingModules, ApiError):
            raise
        except ImportError as exc:
            raise ApiError(f'A module is missing: {exc}', 409, 'import_error')
        except Exception as exc:
            traceback.print_exc()
            raise ApiError(f'The figure could not be drawn: {exc}', 422, 'render')

    def _panel(self, p):
        """One figure of a layout: its data (loaded, or rebuilt from its source), spec, layers and other files."""
        from .tables import kept, masked
        pspec = p.get('spec') if isinstance(p.get('spec'), dict) else {}
        self.check_spec(pspec)
        try:
            ds = self.dataset(p.get('dataset_id'))
        except ApiError:
            if not p.get('source'):
                raise
            ds = self.dataset(self.reopen(p['source'])['dataset_id'])
        rows = masked(ds['df'])
        return {'df': kept(ds['df']), 'spec': pspec, 'overlay_data': self.overlay_data(pspec),
                'extra_data': self.extra_data(pspec), 'masked': ds['df'].iloc[rows] if rows else None}

    def recommend(self, body):
        ds = self.dataset(body.get('dataset_id'))
        from . import smart
        mapping = body.get('mapping') or {}
        return {'recommend': smart.recommend(ds['columns'], mapping, len(ds['df'])),
                'warnings': smart.warnings_for(mapping, body.get('kind'), len(ds['df']))}

    def meta(self):
        fonts, default_spec, previews = [], None, {}
        if not self.modules.missing(self.modules.core_ids()):
            from .plotting import DEFAULT_SPEC, palette_previews
            default_spec = DEFAULT_SPEC
            previews = palette_previews()
            try:
                from matplotlib import font_manager
                fonts = sorted({f.name for f in font_manager.fontManager.ttflist})
            except Exception:
                fonts = []
        return {'version': __version__, 'kinds': catalog.KINDS, 'twin_kinds': sorted(catalog.TWIN_KINDS),
                'styles': catalog.STYLES, 'palettes': catalog.PALETTES, 'colormaps': catalog.COLORMAPS,
                'export_formats': catalog.EXPORT_FORMATS, 'size_presets': catalog.SIZE_PRESETS,
                'file_formats': catalog.FILE_FORMATS, 'extensions': catalog.all_extensions(), 'fonts': fonts,
                'default_spec': default_spec, 'palette_previews': previews}


def make_handler(app, port):
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}

    class Handler(BaseHTTPRequestHandler):
        server_version = f'piplotter/{__version__}'
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):   # quiet; errors are printed explicitly
            pass

        # ------------------------------------------------ responses
        def _send(self, status, body, ctype, extra=None):
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path, ctype, extra=None):
            """A file in pieces (any size), removed once sent or abandoned."""
            try:
                size = path.stat().st_size
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(size))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                with open(path, 'rb') as f:
                    while chunk := f.read(CHUNK):
                        self.wfile.write(chunk)
            finally:
                path.unlink(missing_ok=True)

        def _json(self, data, status=200):
            self._send(status, json.dumps(data, allow_nan=False, default=json_safe).encode('utf-8'),
                       'application/json; charset=utf-8')

        def _log_error(self, status, message):
            if status in (404,) and 'gone' not in message:
                return
            print(f'[π-plotter {time.strftime("%H:%M:%S")}] {status} {self.command} {urlsplit(self.path).path} — {message}',
                  file=sys.stderr, flush=True)

        def _error(self, exc):
            if isinstance(exc, ConnectionError):
                return      # the page cancelled the request (e.g. a newer render replaced it): nothing to answer
            if isinstance(exc, MissingModules):
                return self._json({'error': str(exc), 'code': 'missing_modules', 'modules': exc.ids}, 409)
            if isinstance(exc, MissingUserModules):
                return self._json({'error': str(exc), 'code': 'missing_user_modules', 'modules': exc.names}, 409)
            if isinstance(exc, ApiError):
                self._log_error(exc.status, f'{exc.code}: {exc}')
                return self._json({'error': str(exc), 'code': exc.code, **exc.extra}, exc.status)
            self._log_error(500, f'{exc.__class__.__name__}: {exc}')
            traceback.print_exc()
            return self._json({'error': f'Internal error: {exc}', 'code': 'internal'}, 500)

        def _body(self):
            length = int(self.headers.get('Content-Length') or 0)
            if length > MAX_JSON:
                raise ApiError('Request too large.', 413)
            raw = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(raw or b'{}')
            except json.JSONDecodeError:
                raise ApiError('Invalid JSON.')
            if not isinstance(data, dict):
                raise ApiError('Invalid request.')
            return data

        def _guard(self):
            if self.headers.get('Host', '') not in allowed_hosts:
                raise ApiError('Forbidden host.', 403, 'forbidden')
            if self.path.startswith('/api/') and not secrets.compare_digest(self.headers.get('X-Token', ''), app.token):
                raise ApiError('Invalid session token; reload the page.', 403, 'token')

        # ------------------------------------------------ GET
        def do_GET(self):
            try:
                self._guard()
                path = urlsplit(self.path).path
                if path in ('/', '/index.html'):
                    html = (WEB / 'index.html').read_text(encoding='utf-8').replace('{{TOKEN}}', app.token) \
                        .replace('{{BUILD}}', app.build)
                    return self._send(200, html.encode('utf-8'), MIME['.html'],
                                      {'Content-Security-Policy': "default-src 'self'; img-src 'self' blob: data:; "
                                       "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
                                       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
                if path in ('/manual', '/manual/'):
                    query = parse_qs(urlsplit(self.path).query)
                    page = manual.render_page(lang=(query.get('lang') or [''])[0], explicit='lang' in query)
                    return self._send(200, page.encode('utf-8'), MIME['.html'],
                                      {'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                       "script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
                if path.startswith('/manual/img/'):
                    image = manual.image_path(unquote(path[len('/manual/img/'):]))
                    if image is None:
                        raise ApiError('Not found', 404, 'not_found')
                    return self._send(200, image.read_bytes(), MIME[image.suffix])
                if path.startswith('/static/'):
                    name = unquote(path[len('/static/'):])
                    target = (WEB / name).resolve()
                    if WEB.resolve() not in target.parents or not target.is_file() or target.suffix not in MIME:
                        raise ApiError('Not found', 404, 'not_found')
                    return self._send(200, target.read_bytes(), MIME[target.suffix])
                if path.startswith('/download/'):     # a one-off link: the id is the permission
                    d = app.take_download(path.rsplit('/', 1)[-1])
                    return self._send_file(d['path'], 'application/zip', {'Content-Disposition': content_disposition(d['name'])})
                if path == '/api/status':
                    return self._json({**app.modules.status(), 'build': app.build, 'started': app.started})
                if path == '/api/meta':
                    return self._json(app.meta())
                if path.startswith('/api/view3d/'):
                    view = app.views3d.get(path.rsplit('/', 1)[-1])
                    if view is None:
                        raise ApiError('Not found', 404, 'not_found')
                    return self._json(view)
                if path.startswith('/api/jobs/'):
                    job = app.modules.job(path.rsplit('/', 1)[-1])
                    if not job:
                        raise ApiError('Unknown job.', 404)
                    return self._json(job.to_dict())
                raise ApiError('Not found', 404, 'not_found')
            except Exception as exc:
                self._error(exc)

        # ------------------------------------------------ POST
        def do_POST(self):
            try:
                self._guard()
                path = urlsplit(self.path).path
                if path == '/api/project/open':
                    name = unquote(self.headers.get('X-Filename', '')) or 'project.piplot'
                    return self._json(app.open_project(name, self.rfile, int(self.headers.get('Content-Length') or 0)))
                if path == '/api/project/prepare':
                    return self._json(app.save_project_file(self._body()))
                if path == '/api/project/save':
                    body = self._body()
                    data = app.save_project(body)
                    fname = safe_name(body.get('filename') or 'project', 'project') + '.piplot'
                    return self._send(200, data, 'application/zip', {'Content-Disposition': content_disposition(fname)})
                if path == '/api/upload':
                    name = unquote(self.headers.get('X-Filename', '')) or 'data.csv'
                    info = app.add_upload(name, self.rfile, int(self.headers.get('Content-Length') or 0))
                    return self._json(app.describe_file(info))
                body = self._body()
                if path == '/api/file':
                    return self._json(app.describe_file(app.file(body.get('file_id'))))
                if path == '/api/open':
                    return self._json(app.open_table(body))
                if path == '/api/table/new':
                    return self._json(app.blank_table(body))
                if path == '/api/table/edit':
                    return self._json(app.edit_table(body))
                if path == '/api/table/nearest':
                    return self._json(app.table_nearest(body))
                if path == '/api/table/rows':
                    return self._json(app.table_rows(body))
                if path == '/api/sample':
                    return self._json(app.sample(str(body.get('name') or 'spectra')))
                if path == '/api/analyses':
                    return self._json(app.analyses())
                if path == '/api/analyses/suggest':
                    return self._json(app.suggest_analyses(body))
                if path == '/api/analyses/run':
                    return self._json(app.run_analysis(body))
                if path == '/api/analyses/batch':
                    return self._json(app.batch_analysis(body))
                if path == '/api/autosave':
                    return self._json(app.autosave_write(body))
                if path == '/api/autosave/info':
                    return self._json(app.autosave_info())
                if path == '/api/autosave/recover':
                    return self._json(app.autosave_recover(body))
                if path == '/api/autosave/discard':
                    return self._json(app.autosave_discard(body))
                if path == '/api/console/run':
                    return self._json(app.console_run(body))
                if path == '/api/console/stop':
                    return self._json(app.console_stop())
                if path == '/api/console/reset':
                    return self._json(app.console_reset())
                if path == '/api/reopen':
                    return self._json(app.reopen(body.get('source')))
                if path.startswith('/api/plugins/'):
                    return self._json(app.plugin_action(path.rsplit('/', 1)[-1], body))
                if path == '/api/recommend':
                    return self._json(app.recommend(body))
                if path == '/api/render':
                    info = {}
                    data, mime = app.render(body, info=info)
                    # The colour each series really got, for the Series panel (JSON, URL-encoded).
                    series = quote(json.dumps(info.get('series', []), ensure_ascii=False, default=json_safe))
                    axes = quote(json.dumps(info.get('axes', []), default=json_safe))
                    # The texts that can be dragged and rewritten on the preview, and the polar / 3D axes the wheel zooms.
                    movable = quote(json.dumps({'items': info.get('movables', []), 'face': info.get('face'), 'zoom': info.get('zoom', [])},
                                               default=json_safe))
                    headers = {'X-Series': series, 'X-Axes': axes, 'X-Movables': movable}
                    if info.get('view3d'):          # fetched by the page only when the user starts rotating
                        vid = secrets.token_hex(8)
                        app.views3d[vid] = info['view3d']
                        while len(app.views3d) > 8:
                            app.views3d.popitem(last=False)
                        headers['X-View3D'] = vid
                    return self._send(200, data, mime, headers)
                if path == '/api/export':
                    fmt = str(body.get('format') or 'png').lower()
                    if fmt not in catalog.EXPORT_FORMATS:
                        raise ApiError('Unknown export format.')
                    data, mime = app.render(body, export=fmt)
                    ext = 'zip' if fmt == 'py' else fmt
                    fname = safe_name(body.get('filename') or 'figure', 'figure') + '.' + ext
                    return self._send(200, data, mime, {'Content-Disposition': content_disposition(fname)})
                if path == '/api/modules/refresh':
                    app.modules.refresh_async()
                    return self._json(app.modules.status())
                if path == '/api/modules/verify':
                    app.modules.verify_async(force=True)
                    return self._json(app.modules.status())
                if path == '/api/modules/install':
                    ids = body.get('ids') or []
                    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                        raise ApiError('ids must be a list of module ids.')
                    unknown = [i for i in ids if i not in app.modules.by_id]
                    if unknown:
                        raise ApiError('Unknown module: ' + ', '.join(unknown))
                    job = app.modules.start_install(ids, upgrade=bool(body.get('upgrade')),
                                                    reinstall=bool(body.get('reinstall')))
                    return self._json(job.to_dict())
                if path.startswith('/api/modules/user/'):
                    return self._json(user_module_action(app.modules, path.rsplit('/', 1)[-1], body))
                if path.startswith('/api/jobs/') and path.endswith('/cancel'):
                    job = app.modules.job(path.split('/')[3])
                    if job:
                        job.cancel()
                    return self._json(job.to_dict() if job else {})
                if path == '/api/shutdown':      # a newer π-plotter is starting: give it the port
                    self._json({'ok': True})
                    if app.shutdown_hook:
                        threading.Timer(0.2, app.shutdown_hook).start()
                    return
                if path == '/api/restart':
                    if not app.restart_hook:
                        raise ApiError('Restart is not available.')
                    self._json({'ok': True})
                    threading.Timer(0.4, app.restart_hook).start()
                    return
                raise ApiError('Not found', 404, 'not_found')
            except Exception as exc:
                self._error(exc)

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # A browser that closes a connection early (cancelled render, closed tab) is not an error.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


def serve(port, token, session_dir, open_browser=True, max_upload_gb=20, online=True, quiet=False):
    clean_appledouble()          # exFAT drives on macOS: see modules.clean_appledouble
    modules = ModuleManager(online=online)
    app = App(token, session_dir, modules, int(max_upload_gb * 1024 ** 3))
    httpd = Server(('127.0.0.1', port), make_handler(app, port))
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(app, port)
    url = f'http://127.0.0.1:{port}/'
    modules.refresh_async()      # latest versions from PyPI, at every start
    modules.verify_async()       # installed modules really import (separate Python, in the background)
    if not quiet:
        status = modules.status()
        print(f'{NAME} {__version__} — {url}')
        print(AUTHOR)
        print(f'Python {status["python"]} ({sys.executable})')
        if not status['core_ready']:
            print('First start: the browser page will install NumPy, pandas and Matplotlib.')
        print('Keep this window open; press Ctrl+C to stop.')
    if open_browser:
        threading.Timer(0.6, lambda: _open(url)).start()
    return httpd, app, url


def _open(url):
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass


def user_module_action(modules, action, body):
    """Modules the user adds from PyPI: inspect (licences first), install, uninstall, cite."""
    try:
        if action == 'inspect':
            return modules.start_inspect(body.get('name')).to_dict()
        if action == 'install':
            return modules.start_user_install(body.get('inspection'), accept=body.get('accept') is True).to_dict()
        if action == 'uninstall':
            return modules.start_uninstall(body.get('name')).to_dict()
        if action == 'cite':
            modules.set_user_cite(body.get('name'), body.get('cite'))
            return modules.status()
    except ValueError as exc:
        raise ApiError(str(exc), 400, 'user_module')
    raise ApiError('Not found', 404, 'not_found')


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
