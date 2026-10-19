"""Tables written or edited by hand (tables.py): blank tables, edits as new data sets, the row under a click, pages
of rows, and a DataFrame of the console made into a table of its own."""
from .common import PREVIEW_COLS, ApiError, json_safe


class TablesArea:
    # -------------------------------------------------------------- tables written or edited by hand
    def blank_table(self, body):
        self.modules.require(self.modules.core_ids())
        from .. import tables
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
        from .. import tables
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
        from .. import tables
        cols = set(map(str, ds['df'].columns))
        x = body.get('x') if body.get('x') in cols else None
        ys = [y for y in body.get('ys') or [] if y in cols]
        try:
            df = ds['df']
            spec = body.get('spec') if isinstance(body.get('spec'), dict) else {}
            if spec:                     # normalised curves: the points as drawn (the excluded rows scaled alike)
                from ..plotting import figure_data
                df = figure_data(tables.kept(df), spec, masked=df)[2]
            hit = tables.nearest(df, x, ys, float(body['px']), float(body['py']), body['xlim'], body['ylim'],
                                 body.get('xscale', 'linear'), body.get('yscale', 'linear'))
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(f'Cannot find the point: {exc}', 422, 'table')
        if hit:
            hit['masked'] = hit['row'] in tables.masked(ds['df'])
        return hit or {}

    def table_rows(self, body):
        ds = self.dataset(body.get('dataset_id'))
        from .. import tables
        page = tables.page(ds['df'], body.get('start', 0), body.get('count', 200), body.get('col_start', 0),
                           body.get('col_count', PREVIEW_COLS))
        page['rows'] = [[json_safe(v) for v in row] for row in page['rows']]
        return page

    def _table_of(self, frame, name):
        """A DataFrame as a table typed in: a blank table and the values pasted into it, so that it is edited,
        saved in projects and reopened like one (dates and other objects become text)."""
        import math
        import pandas as pd
        from .. import tables
        from ..readers import unique_names
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
