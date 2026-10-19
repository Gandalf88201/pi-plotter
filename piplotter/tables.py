"""Tables the user writes or edits by hand: a blank table, edits as a list of operations, column formulas.

A table is never changed in place. Each edit gives a new data set whose source is the parent's source plus
the list of operations, so the table can be rebuilt after a restart (reopen) and an edit undone by going
back to the previous data set. Operations (dicts, all positions start at 0):

    {'op': 'set', 'row': 3, 'col': 'B', 'value': '1,5'}          one cell ('' = empty)
    {'op': 'paste', 'row': 0, 'col': 'A', 'values': [[…], …]}     a block (e.g. copied from a spreadsheet);
                                                                 rows and columns are added as needed
    {'op': 'add_rows', 'n': 10, 'at': None}                       empty rows (at the end without 'at')
    {'op': 'del_rows', 'rows': [2, 5]}
    {'op': 'add_col', 'name': 'C', 'at': None}                    an empty column
    {'op': 'del_col', 'col': 'C'}
    {'op': 'rename', 'col': 'C', 'to': 'time (s)'}
    {'op': 'formula', 'col': 'D', 'expr': 'sqrt(A) * 2'}          column values from other columns (new or
                                                                 existing column), like "Set column values"
    {'op': 'mask', 'rows': [4, 7], 'value': True}                 exclude rows from analyses and curves (value
                                                                 False brings them back); the data stay

Excluded rows are kept in df.attrs['masked'] (sorted row positions), carried through the edits: rows inserted
or deleted above them move them, deleted rows leave the list.

Typed text becomes a number when it reads as one (a decimal comma is accepted: "1,5"); a column whose
cells are all numbers (or empty) is numeric. Formulas use column names directly when they are valid
names (A, time) and col("name with spaces") otherwise, with numpy functions and the row number i.
"""
import ast
import math
import re

import numpy as np
import pandas as pd

MAX_ROWS = 1_000_000          # rows a table may get by hand (add rows, paste)
MAX_COLS = 1_000
MAX_CELLS = 2_000_000         # cells one operation may write
MAX_OPS = 10_000              # operations kept in a source (a longer history is written as one paste)

OPS = {'set', 'paste', 'add_rows', 'del_rows', 'add_col', 'del_col', 'rename', 'formula', 'mask'}


class TableError(ValueError):
    """An operation that cannot be applied (the message is shown to the user)."""


# ------------------------------------------------------------------ cells
_NUM = re.compile(r'^[+-]?(\d+([.]\d*)?|[.]\d+)([eE][+-]?\d+)?$')
_COMMA = re.compile(r'^[+-]?\d+,\d+([eE][+-]?\d+)?$')


def parse_cell(value):
    """A typed or pasted value: None / '' → empty (NaN), text that reads as a number → float, else text."""
    if value is None:
        return np.nan
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in ('nan', 'na', 'n/a', '-', '—'):
        return np.nan
    if _NUM.match(text):
        return float(text)
    if _COMMA.match(text):
        return float(text.replace(',', '.'))
    if text.lower() in ('inf', '+inf', '-inf'):
        return float(text.lower())
    return text


def _settle(df, cols):
    """Columns written by hand: numeric when every non-empty cell is a number, else text (object)."""
    for c in cols:
        if c not in df.columns:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            continue
        vals = s.map(parse_cell)
        nonempty = vals.notna()
        if not nonempty.any() or vals[nonempty].map(lambda v: isinstance(v, float)).all():
            df[c] = pd.to_numeric(vals, errors='coerce').astype(float)
        else:
            df[c] = vals.astype(object).where(nonempty, None)
    return df


def column_names(n, taken=()):
    """n new column names in spreadsheet order (A, B, …, Z, AA, …) that are not in taken."""
    out, k, taken = [], 0, set(map(str, taken))
    while len(out) < n:
        k += 1
        name, m = '', k
        while m:
            m, r = divmod(m - 1, 26)
            name = chr(65 + r) + name
        if name not in taken:
            out.append(name)
            taken.add(name)
    return out


def blank(cols=2, rows=10, names=None):
    """An empty table: cols numeric columns (A, B, … or names) and rows empty rows."""
    cols, rows = int(cols), int(rows)
    if not 1 <= cols <= MAX_COLS or not 0 <= rows <= MAX_ROWS:
        raise TableError(f'A new table has 1–{MAX_COLS} columns and 0–{MAX_ROWS:,} rows.')
    names = [str(n).strip() for n in (names or []) if str(n).strip()][:cols]
    if len(set(names)) != len(names):
        raise TableError('Column names must be different.')
    names += column_names(cols - len(names), names)
    return pd.DataFrame({n: np.full(rows, np.nan) for n in names})


# ------------------------------------------------------------------ operations
def _col(df, name):
    name = str(name)
    if name not in df.columns:
        raise TableError(f'Column not found: {name}')
    return name


def _row(df, i, allow_end=False):
    try:
        i = int(i)
    except (TypeError, ValueError):
        raise TableError('A row number is needed.')
    if not 0 <= i < len(df) + (1 if allow_end else 0):
        raise TableError(f'Row {i + 1} is outside the table (1–{len(df)}).')
    return i


def _grow(df, rows):
    """df with at least `rows` rows (new rows empty)."""
    if rows > MAX_ROWS:
        raise TableError(f'A table edited by hand has at most {MAX_ROWS:,} rows.')
    if rows <= len(df):
        return df
    extra = pd.DataFrame({c: pd.Series([np.nan] * (rows - len(df)), dtype=df[c].dtype if
                                      pd.api.types.is_numeric_dtype(df[c]) else object) for c in df.columns})
    return pd.concat([df, extra], ignore_index=True)


def _put(df, row, col, value):
    """Write one parsed value, turning a numeric column into text when the value is text."""
    if isinstance(value, str) and pd.api.types.is_numeric_dtype(df[col]):
        df[col] = df[col].astype(object)
    df.iat[row, df.columns.get_loc(col)] = value


def apply_ops(df, ops):
    """A new DataFrame: df with the operations applied in order (df itself is not changed)."""
    if not isinstance(ops, list) or not ops:
        raise TableError('No change to apply.')
    mask = {int(r) for r in df.attrs.get('masked', [])}
    df = df.copy()
    df.index = pd.RangeIndex(len(df))
    touched = set()
    for op in ops:
        if not isinstance(op, dict) or op.get('op') not in OPS:
            raise TableError(f'Unknown table operation: {op!r}')
        kind = op['op']
        if kind == 'set':
            col = _col(df, op.get('col'))
            row = _row(df, op.get('row'), allow_end=True)
            df = _grow(df, row + 1)
            _put(df, row, col, parse_cell(op.get('value')))
            touched.add(col)
        elif kind == 'paste':
            values = op.get('values')
            if not isinstance(values, list) or not values or not all(isinstance(r, list) for r in values):
                raise TableError('Nothing to paste.')
            width = max(len(r) for r in values)
            if len(values) * width > MAX_CELLS:
                raise TableError(f'At most {MAX_CELLS:,} cells can be pasted at once.')
            row = _row(df, op.get('row', 0), allow_end=True) if len(df) else 0
            start = df.columns.get_loc(_col(df, op.get('col'))) if len(df.columns) else 0
            missing = start + width - len(df.columns)
            if missing > 0:
                if len(df.columns) + missing > MAX_COLS:
                    raise TableError(f'A table has at most {MAX_COLS} columns.')
                for name in column_names(missing, df.columns):
                    df[name] = np.nan
            df = _grow(df, row + len(values))
            cols = list(df.columns[start:start + width])
            for j, c in enumerate(cols):
                column = [parse_cell(r[j]) if j < len(r) else np.nan for r in values]
                if any(isinstance(v, str) for v in column) and pd.api.types.is_numeric_dtype(df[c]):
                    df[c] = df[c].astype(object)
                df.iloc[row:row + len(values), df.columns.get_loc(c)] = column
                touched.add(c)
        elif kind == 'add_rows':
            n = int(op.get('n') or 1)
            if not 1 <= n <= MAX_ROWS:
                raise TableError(f'Add 1–{MAX_ROWS:,} rows.')
            at = op.get('at')
            new = _grow(df.iloc[0:0], n)
            if at is None:
                df = _grow(df, len(df) + n)
            else:
                at = _row(df, at, allow_end=True)
                df = pd.concat([df.iloc[:at], new, df.iloc[at:]], ignore_index=True)
                mask = {r + n if r >= at else r for r in mask}
                if len(df) > MAX_ROWS:
                    raise TableError(f'A table edited by hand has at most {MAX_ROWS:,} rows.')
        elif kind == 'del_rows':
            rows = sorted({_row(df, r) for r in (op.get('rows') or [])})
            if not rows:
                raise TableError('Choose the rows to delete.')
            df = df.drop(index=rows).reset_index(drop=True)
            gone = set(rows)
            mask = {r - sum(1 for g in rows if g < r) for r in mask if r not in gone}
        elif kind == 'add_col':
            if len(df.columns) >= MAX_COLS:
                raise TableError(f'A table has at most {MAX_COLS} columns.')
            name = str(op.get('name') or '').strip() or column_names(1, df.columns)[0]
            if name in df.columns:
                raise TableError(f'There is already a column called {name}.')
            at = op.get('at')
            at = len(df.columns) if at is None else max(0, min(int(at), len(df.columns)))
            df.insert(at, name, np.full(len(df), np.nan))
        elif kind == 'del_col':
            col = _col(df, op.get('col'))
            if len(df.columns) == 1:
                raise TableError('A table keeps at least one column.')
            df = df.drop(columns=[col])
            touched.discard(col)
        elif kind == 'rename':
            col = _col(df, op.get('col'))
            to = str(op.get('to') or '').strip()
            if not to:
                raise TableError('A column needs a name.')
            if to != col and to in df.columns:
                raise TableError(f'There is already a column called {to}.')
            df = df.rename(columns={col: to})
            if col in touched:
                touched.discard(col)
                touched.add(to)
        elif kind == 'mask':
            rows = {_row(df, r) for r in (op.get('rows') or [])}
            if not rows:
                raise TableError('Choose the rows to exclude or bring back.')
            mask = (mask | rows) if op.get('value', True) else (mask - rows)
        elif kind == 'formula':
            name = str(op.get('col') or '').strip()
            if not name:
                raise TableError('Name the column that gets the values.')
            values = evaluate(df, str(op.get('expr') or ''))
            if name not in df.columns:
                if len(df.columns) >= MAX_COLS:
                    raise TableError(f'A table has at most {MAX_COLS} columns.')
                df[name] = np.nan
            df[name] = values
    df = _settle(df, touched)
    df.attrs['masked'] = sorted(r for r in mask if 0 <= r < len(df))
    return df


def masked(df):
    """Positions of the rows excluded from analyses and curves (see the 'mask' operation)."""
    return [int(r) for r in df.attrs.get('masked', []) if 0 <= int(r) < len(df)]


def kept(df):
    """df without its excluded rows (the original index is kept, so columns stay aligned)."""
    rows = masked(df)
    return df.drop(index=df.index[rows]) if rows else df


def nearest(df, x, ys, px, py, xlim, ylim, xscale='linear', yscale='linear'):
    """The row whose point (x, y) of one of the ys columns is nearest to the click (px, py), distances measured as
    fractions of the axes (so x and y in different units weigh the same); x None = row number. None if no point.
    {'row', 'distance', 'col': that y column, 'x', 'y': the point's values}."""
    def scaled(v, lim, scale):
        v = np.asarray(v, float)
        lo, hi = (float(lim[0]), float(lim[1]))
        if scale == 'log':
            with np.errstate(all='ignore'):
                v, lo, hi = np.log10(v), np.log10(lo), np.log10(hi)
        elif isinstance(scale, dict) and scale.get('cuts'):          # an axis with breaks: as drawn, gaps closed up
            from .plotting import break_functions, knot_functions
            fwd = (knot_functions(*scale['knots']) if scale.get('knots')
                   else break_functions(scale['cuts'], float(scale['gap'])))[0]
            v, lo, hi = fwd(v), float(fwd([lo])[0]), float(fwd([hi])[0])
        return (v - lo) / ((hi - lo) or 1.0)
    xv = pd.to_numeric(df[x], errors='coerce').to_numpy(float) if x else np.arange(len(df), dtype=float)
    best, where, col, yval = np.inf, None, None, None
    for y in ys:
        if y not in df.columns:
            continue
        yv = pd.to_numeric(df[y], errors='coerce').to_numpy(float)
        d = np.hypot(scaled(xv, xlim, xscale) - scaled([px], xlim, xscale)[0],
                     scaled(yv, ylim, yscale) - scaled([py], ylim, yscale)[0])
        d[~np.isfinite(d)] = np.inf
        i = int(np.argmin(d)) if d.size else -1
        if i >= 0 and d[i] < best:
            best, where, col, yval = float(d[i]), i, str(y), float(yv[i])
    if where is None:
        return None
    return {'row': where, 'distance': best, 'col': col, 'x': float(xv[where]), 'y': yval}


def squash(ops):
    """A list of operations short enough to keep in a source (the oldest ones are kept as they are)."""
    return ops if len(ops) <= MAX_OPS else ops[-MAX_OPS:]


# ------------------------------------------------------------------ column formulas
FUNCS = {'abs', 'sqrt', 'exp', 'log', 'log10', 'log2', 'sin', 'cos', 'tan', 'arcsin', 'arccos', 'arctan', 'arctan2',
         'sinh', 'cosh', 'tanh', 'floor', 'ceil', 'round', 'sign', 'radians', 'degrees', 'hypot', 'minimum',
         'maximum', 'where', 'isnan', 'cumsum', 'diff', 'mean', 'std', 'min', 'max', 'sum', 'median', 'gradient'}
CONSTS = {'pi': math.pi, 'e': math.e, 'nan': np.nan, 'inf': np.inf}


def evaluate(df, expr):
    """Values of a column formula over the rows of df (numpy arrays; only arithmetic, comparisons and FUNCS)."""
    expr = expr.strip()
    if not expr:
        raise TableError('Write a formula, e.g. sqrt(A) * 2 or col("time (s)") / 60.')
    try:
        tree = ast.parse(expr.replace('^', '**'), mode='eval')
    except SyntaxError:
        raise TableError(f'Not a formula: {expr}')
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.IfExp, ast.Call, ast.Name,
               ast.Constant, ast.Load, ast.operator, ast.unaryop, ast.cmpop, ast.boolop)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise TableError(f'Not allowed in a formula: {node.__class__.__name__}')
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or (node.func.id not in FUNCS and node.func.id != 'col'):
                raise TableError('Functions: col("name"), ' + ', '.join(sorted(FUNCS)))
            if node.keywords:
                raise TableError('Write the arguments of a function without names.')
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str)):
            raise TableError('Only numbers and column names in quotes.')

    n = len(df)

    def column(name):
        name = str(name)
        if name not in df.columns:
            raise TableError(f'Column not found: {name}')
        return pd.to_numeric(df[name], errors='coerce').to_numpy(float)

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == 'i':
                return np.arange(n, dtype=float)
            if node.id in CONSTS:
                return CONSTS[node.id]
            if node.id in df.columns:
                return column(node.id)
            raise TableError(f'Unknown name: {node.id} (a column with spaces is written col("its name"))')
        if isinstance(node, ast.Call):
            args = [ev(a) for a in node.args]
            if node.func.id == 'col':
                if len(args) != 1 or not isinstance(args[0], str):
                    raise TableError('col needs a column name in quotes: col("time (s)").')
                return column(args[0])
            name = {'min': 'nanmin', 'max': 'nanmax', 'mean': 'nanmean', 'std': 'nanstd', 'sum': 'nansum',
                    'median': 'nanmedian'}.get(node.func.id, node.func.id)
            fn = getattr(np, name)
            if node.func.id == 'diff':                  # same length as the table: first value empty
                return np.concatenate([[np.nan], np.diff(np.asarray(args[0], float))])
            if node.func.id == 'std':
                return fn(*args, ddof=1)
            return fn(*args)
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            return {ast.USub: lambda a: -a, ast.UAdd: lambda a: +a, ast.Not: np.logical_not}[type(node.op)](v)
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            ops = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.true_divide,
                   ast.Pow: np.power, ast.Mod: np.mod, ast.FloorDiv: np.floor_divide}
            if type(node.op) not in ops:
                raise TableError('Operators: + - * / ** % //')
            return ops[type(node.op)](a, b)
        if isinstance(node, ast.Compare):
            cmp = {ast.Lt: np.less, ast.LtE: np.less_equal, ast.Gt: np.greater, ast.GtE: np.greater_equal,
                   ast.Eq: np.equal, ast.NotEq: np.not_equal}
            left, out = ev(node.left), True
            for op, right in zip(node.ops, node.comparators):
                if type(op) not in cmp:
                    raise TableError('Comparisons: < <= > >= == !=')
                r = ev(right)
                out = np.logical_and(out, cmp[type(op)](left, r))
                left = r
            return out
        if isinstance(node, ast.BoolOp):
            vals = [ev(v) for v in node.values]
            fn = np.logical_and if isinstance(node.op, ast.And) else np.logical_or
            out = vals[0]
            for v in vals[1:]:
                out = fn(out, v)
            return out
        if isinstance(node, ast.IfExp):
            return np.where(ev(node.test), ev(node.body), ev(node.orelse))
        raise TableError(f'Not allowed in a formula: {node.__class__.__name__}')

    with np.errstate(all='ignore'):
        try:
            out = ev(tree)
        except TableError:
            raise
        except Exception as exc:                       # numpy argument errors and the like
            raise TableError(f'The formula cannot be computed: {exc}')
    out = np.asarray(out, dtype=float) if not isinstance(out, str) else None
    if out is None:
        raise TableError('A formula must give numbers.')
    if out.ndim == 0:
        out = np.full(n, float(out))
    if out.shape != (n,):
        raise TableError(f'The formula gives {out.size} values for {n} rows.')
    return out


# ------------------------------------------------------------------ pages for the table on screen
def page(df, start=0, count=200, col_start=0, col_count=100):
    """Rows start…start+count of columns col_start…col_start+col_count, as lists of plain values."""
    start = max(0, min(int(start), max(0, len(df) - 1)))
    count = max(1, min(int(count), 2000))
    col_start = max(0, min(int(col_start), max(0, len(df.columns) - 1)))
    col_count = max(1, min(int(col_count), 200))
    part = df.iloc[start:start + count, col_start:col_start + col_count]
    return {'start': start, 'total': int(len(df)), 'col_start': col_start, 'columns': [str(c) for c in part.columns],
            'rows': [list(r) for r in part.itertuples(index=False, name=None)],
            'masked': [r for r in masked(df) if start <= r < start + count]}
