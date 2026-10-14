"""Statistics of a matrix (an image, a map) or of a region of it clicked on the figure — a rectangle (two opposite
corners) or a polygon of any shape (three or more points; a cell belongs to it when its centre is inside): number of cells, mean, SD,
median, minimum and maximum with where they are, sum, volume (the integral of the values over x and y, each cell
weighted by its area) and centroid (the mean position weighted by the values above the minimum). The values of the
region are given as a histogram; the region is drawn on a copy of the figure."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'matrix_stats',
    'order': 4,
    'name': {'en': 'Matrix: statistics of a region', 'it': 'Matrice: statistiche di una regione'},
    'category': 'matrix',
    'description': {'en': 'Mean, SD, min, max with position, sum, volume and centroid of the matrix or of a rectangle '
                          'clicked on the figure.',
                    'it': 'Media, SD, min, max con posizione, somma, volume e baricentro della matrice o di un '
                          'rettangolo cliccato sul grafico.'},
    'requires': [],
    'params': [
        {'id': 'corners', 'type': 'points', 'optional': True,
         'label': {'en': 'Region: two opposite corners (a rectangle) or three or more points around it (a polygon), '
                         'clicked on the figure; empty = the whole matrix',
                   'it': 'Regione: due angoli opposti (un rettangolo) o tre o più punti attorno (un poligono), '
                         'cliccati sul grafico; vuoto = tutta la matrice'}},
    ],
    'references': [
        'Gonzalez, R. C. & Woods, R. E. Digital Image Processing, 4th ed. Pearson (2018).',
        'Harris, C. R. et al. Array programming with NumPy. Nature 585, 357–362 (2020). doi:10.1038/s41586-020-2649-2',
    ],
}


def cell_widths(v):
    """Width of each cell along an axis: half the distance to each neighbour (the edge cells mirror inward)."""
    v = np.asarray(v, float)
    if v.size < 2:
        return np.ones_like(v)
    edges = np.r_[v[0] - (v[1] - v[0]) / 2, (v[1:] + v[:-1]) / 2, v[-1] + (v[-1] - v[-2]) / 2]
    return np.diff(edges)


def polygon_area(pts):
    """Area of a polygon (shoelace formula), in the units of x times those of y."""
    x, y = np.asarray([q[0] for q in pts], float), np.asarray([q[1] for q in pts], float)
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def region_stats(Z, xs, ys, inside=None):
    """inside: the cells of the region (a polygon), the others ignored; None = every cell."""
    inside = np.ones(Z.shape, bool) if inside is None else inside
    Z = np.where(inside, Z, np.nan)
    ok = np.isfinite(Z)
    vals = Z[ok]
    X, Y = np.meshgrid(xs, ys)
    area = np.outer(cell_widths(ys), cell_widths(xs))
    w = np.where(ok, Z - vals.min(), 0.0)
    total = w.sum()
    i_max, i_min = np.nanargmax(Z), np.nanargmin(Z)
    return {
        'cells': int(inside.sum()), 'empty': int((inside & ~ok).sum()), 'mean': float(vals.mean()),
        'sd': float(vals.std(ddof=1)) if vals.size > 1 else float('nan'), 'median': float(np.median(vals)),
        'min': float(vals.min()), 'min_at': (float(X.flat[i_min]), float(Y.flat[i_min])),
        'max': float(vals.max()), 'max_at': (float(X.flat[i_max]), float(Y.flat[i_max])),
        'sum': float(vals.sum()), 'volume': float(np.sum(np.where(ok, Z, 0.0) * area)),
        'centroid': (float((w * X).sum() / total), float((w * Y).sum() / total)) if total > 0 else (float('nan'),) * 2,
    }


def run(df, p, ctx):
    Z, xs, ys, yname = ctx.matrix(df)
    pts = [q for q in (p.get('corners') or []) if q[1] is not None]
    r = ctx.result()
    rect = poly = inside = None
    if len(pts) >= 3:                                  # a polygon: the cells whose centre is inside
        from matplotlib.path import Path
        poly = [(float(a), float(b)) for a, b in pts]
        px, py = [q[0] for q in poly], [q[1] for q in poly]
        kx, ky = (xs >= min(px)) & (xs <= max(px)), (ys >= min(py)) & (ys <= max(py))
        Z, xs, ys = Z[np.ix_(ky, kx)], xs[kx], ys[ky]
        X, Y = np.meshgrid(xs, ys)
        inside = Path(poly + [poly[0]]).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape) \
            if X.size else np.zeros(X.shape, bool)
        if not inside.any():
            raise ValueError(ctx.tr('The region contains no cell.', 'La regione non contiene celle.'))
        r.value(ctx.tr('region', 'regione'), ctx.tr(f'polygon of {len(poly)} points', f'poligono di {len(poly)} punti'))
        r.value(ctx.tr('area of the polygon', 'area del poligono'), polygon_area(poly), key='area')
    elif pts:
        if len(pts) < 2:
            raise ValueError(ctx.tr('Click two opposite corners of the region (or leave it empty for the whole matrix).',
                                    'Clicca due angoli opposti della regione (o lascia vuoto per tutta la matrice).'))
        (xa, ya), (xb, yb) = pts[-2], pts[-1]
        x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
        kx, ky = (xs >= x0) & (xs <= x1), (ys >= y0) & (ys <= y1)
        if not kx.any() or not ky.any():
            raise ValueError(ctx.tr('The region contains no cell.', 'La regione non contiene celle.'))
        Z, xs, ys = Z[np.ix_(ky, kx)], xs[kx], ys[ky]
        rect = (x0, x1, y0, y1)
        r.value(ctx.tr('region', 'regione'), f'x {x0:.6g} … {x1:.6g}, y {y0:.6g} … {y1:.6g}')
    if not np.isfinite(Z if inside is None else np.where(inside, Z, np.nan)).any():
        raise ValueError(ctx.tr('The region has no values.', 'La regione non ha valori.'))
    s = region_stats(Z, xs, ys, inside)
    r.value(ctx.tr('cells', 'celle'), s['cells'], key='cells')
    if s['empty']:
        r.value(ctx.tr('empty cells', 'celle vuote'), s['empty'])
    r.value(ctx.tr('mean', 'media'), s['mean'], key='mean')
    r.value('SD', s['sd'], key='sd')
    r.value(ctx.tr('median', 'mediana'), s['median'], key='median')
    r.value(ctx.tr('minimum', 'minimo'), s['min'], key='min')
    r.value(ctx.tr('minimum at (x, y)', 'minimo in (x, y)'), f'({s["min_at"][0]:.6g}, {s["min_at"][1]:.6g})')
    r.value(ctx.tr('maximum', 'massimo'), s['max'], key='max')
    r.value(ctx.tr('maximum at (x, y)', 'massimo in (x, y)'), f'({s["max_at"][0]:.6g}, {s["max_at"][1]:.6g})')
    r.value(ctx.tr('sum', 'somma'), s['sum'], key='sum')
    r.value(ctx.tr('volume (∫∫ value dx dy)', 'volume (∫∫ valore dx dy)'), s['volume'], key='volume')
    r.value(ctx.tr('centroid x', 'baricentro x'), s['centroid'][0], key='cx')
    r.value(ctx.tr('centroid y', 'baricentro y'), s['centroid'][1], key='cy')
    if rect:
        x0, x1, y0, y1 = rect
        box = pd.DataFrame({'x': [x0, x1, x1, x0, x0], yname: [y0, y0, y1, y1, y0]})
        r.overlay(box, 'x', yname, label=ctx.tr('region', 'regione'), style={'color': '#ff3b30', 'linewidth': 1.2})
    if poly:
        ring = pd.DataFrame({'x': [q[0] for q in poly] + [poly[0][0]], yname: [q[1] for q in poly] + [poly[0][1]]})
        r.overlay(ring, 'x', yname, label=ctx.tr('region', 'regione'), style={'color': '#ff3b30', 'linewidth': 1.2})
        Z = np.where(inside, Z, np.nan)
    value = ctx.tr('value', 'valore')
    r.data(pd.DataFrame({value: Z[np.isfinite(Z)]}), name=ctx.tr('values of the region', 'valori della regione'),
           plot={'kind': 'hist', 'y': [value]})
    return r
