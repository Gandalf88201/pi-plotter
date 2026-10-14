"""The Python console (console.py): code run on the data of the figure, or once per open file."""
from .common import ApiError


class ConsoleArea:
    # -------------------------------------------------------------- the Python console
    def console_run(self, body):
        """Run code in the console (console.py) with df = the data of the figure and files = the open files; the
        tables it makes with new_table() become tables of their own, kept in projects like a table typed in."""
        self.modules.require(self.modules.core_ids())
        from ..console import Console
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

    def console_complete(self, body):
        from ..console import Console
        if self._console is None:
            self._console = Console()
        return self._console.complete(str(body.get('text') or ''))

    def console_each(self, body):
        """The code once per open file, df = that file (and name = its name): the value of each last line becomes a
        row of one table (a table typed in, kept in projects); the outputs of each run come back under its name."""
        self.modules.require(self.modules.core_ids())
        from ..console import Console
        import pandas as pd
        if self._console is None:
            self._console = Console()
        files = [f for f in body.get('files') or [] if isinstance(f, dict)]
        if not files:
            raise ApiError('No files open.', 400, 'console')
        lang = body.get('lang') or 'en'
        tr = lambda en, it: it if lang == 'it' else en            # noqa: E731
        runs, rows = [], []
        for k, f in enumerate(files, 1):
            name = str(f.get('name') or f'#{k}')
            try:
                d = self.dataset(f.get('dataset_id'))
            except ApiError:
                runs.append({'name': name, 'outputs': [{'type': 'error', 'text': tr('Not open any more.', 'Non è più aperto.')}]})
                continue
            out = self._console.run(str(body.get('code') or ''), d['df'], None, None, None, body.get('spec') or {},
                                    lang, name=name)
            out.pop('tables', None)
            runs.append({'name': name, 'outputs': out.get('outputs', []), 'restarted': out.get('restarted')})
            if out.get('value'):
                rows.append({tr('file', 'file'): name, **out['value']})
            if out.get('restarted'):                               # stopped, timed out or crashed: stop here
                break
        table = None
        if rows:
            table = self._table_of(pd.DataFrame(rows), tr('console · every file', 'console · ogni file'))
        return {'runs': runs, 'table': table, 'rows': len(rows)}

    def console_stop(self):
        if self._console is not None:
            self._console.stop()
        return {'ok': True}

    def console_reset(self):
        if self._console is not None:
            self._console.reset()
        return {'ok': True}
