"""Files and data sets: uploads kept in the session folder, tables read from them, samples, and every data set
rebuilt from its source (sources.py: a file, a sample, a blank table, a list of edits, an analysis, a batch). A data
set made from the same source as one still loaded is not made again (a project with many copies of one analysis)."""
import json
from pathlib import Path
import secrets
import shutil

from .. import catalog, sources
from ..modules import MissingModules
from .common import CHUNK, MAX_DATASET_BYTES, MAX_DATASETS, MAX_MADE, PREVIEW_COLS, PREVIEW_ROWS, ApiError, json_safe, safe_name


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
            self._trim()
        head = df.iloc[:PREVIEW_ROWS, :PREVIEW_COLS]
        out = {'dataset_id': did, 'name': name, 'rows': int(len(df)), 'columns': cols, 'mapping': mapping,
                'options': {k: v for k, v in used.items() if k != 'names'}, 'source': source,
                'recommend': smart.recommend(cols, mapping, len(df)),
                'preview': [[json_safe(v) for v in row] for row in head.itertuples(index=False, name=None)],
                'preview_cols': int(head.shape[1]), 'masked': len(df.attrs.get('masked', []))}
        self._remember(source, out)
        return out

    def _trim(self):
        # Least recently used first (dataset() marks use): the file being plotted is never the one
        # dropped, however many analyses register their results and layers.
        total = sum(d.get('bytes', 0) for d in self.datasets.values())
        while len(self.datasets) > 1 and (len(self.datasets) > MAX_DATASETS or total > MAX_DATASET_BYTES):
            _, old = self.datasets.popitem(last=False)
            total -= old.get('bytes', 0)

    # -------------------------------------------------------------- made once per source
    def _generation(self):
        """Changes when the analyses are loaded again (an edited plugin): their results are made anew."""
        return getattr(self._plugins, 'generation', 0)

    def _remember(self, source, out):
        try:
            k = sources.key(source)
            gen = self._generation() if sources.computed(source) else None
        except (TypeError, ValueError):
            return
        with self.lock:
            self.made[k] = (out['dataset_id'], out, gen)
            self.made.move_to_end(k)
            while len(self.made) > MAX_MADE:
                self.made.popitem(last=False)

    def _made_before(self, source):
        """The data set already made from this source, under a new id (each user of it gets its own), or None."""
        try:
            k = sources.key(source)
        except (TypeError, ValueError):
            return None
        with self.lock:
            entry = self.made.get(k)
            if not entry or (entry[2] is not None and entry[2] != self._generation()):
                return None
            ds = self.datasets.get(entry[0])
            if ds is None:
                return None
            did = secrets.token_hex(6)
            self.datasets[did] = dict(ds)                     # the same data, read only: shared
            self._trim()
        return {**entry[1], 'dataset_id': did}

    def dataset(self, did):
        with self.lock:
            ds = self.datasets.get(str(did))
            if ds is not None:
                self.datasets.move_to_end(str(did))          # recently used: dropped last
        if ds is None:
            raise ApiError('The data set is no longer loaded; open the file again.', 404, 'dataset_gone')
        return ds

    def reopen(self, source, depth=0):
        """The data set of a source (sources.py), made again — or the one already made from it, when still loaded."""
        try:
            if depth == 0:
                sources.check(source)
            return self._made_before(source) or sources.make(self, source, depth)
        except sources.SourceError as exc:
            raise ApiError(str(exc), 400, 'source')
