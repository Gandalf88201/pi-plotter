"""Files and data sets: uploads kept in the session folder, tables read from them, samples, and every data set
rebuilt from its source (a file, a sample, a blank table, a list of edits, an analysis, a batch)."""
import json
from pathlib import Path
import secrets
import shutil

from .. import catalog
from ..modules import MissingModules
from .common import CHUNK, MAX_DATASET_BYTES, MAX_DATASETS, PREVIEW_COLS, PREVIEW_ROWS, ApiError, json_safe, safe_name


class FilesArea:
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
            from .. import readers
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
        from .. import readers
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

    def sample(self, which):
        self.modules.require(self.modules.core_ids())
        from .. import samples
        df = samples.make(which)
        return self._register(df, f'sample: {which}', {'sample': which}, {})

    def _register(self, df, name, source, used, references=()):
        from .. import smart
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
