"""Profile of a matrix (an image, a map): its values along a row (at a y), a column (at an x) or a straight segment
between two points clicked on the figure, read by bilinear interpolation and, if asked, averaged over a strip a few
cells wide. Gives the curve, its extremes and mean, and draws the path on a copy of the figure."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'matrix_profile',
    'order': 3,
    'name': {'en': 'Matrix: profile along a line', 'it': 'Matrice: profilo lungo una linea'},
    'category': 'matrix',
    'description': {'en': 'The values along a row, a column or a segment clicked on the figure (optionally averaged '
                          'over a strip) as a curve.',
                    'it': 'I valori lungo una riga, una colonna o un segmento cliccato sul grafico (anche mediati su '
                          'una striscia) come curva.'},
    'suits': [                                          # figures it suits (piplotter/advisor.py)
        {'figure': 'matrix', 'score': 92,
         'reason': {'en': 'A matrix: its values along a line clicked on the figure (or a row, a column).',
                    'it': 'Una matrice: i suoi valori lungo una linea cliccata sul grafico (o una riga, una colonna).'}},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'along', 'type': 'choice', 'default': 'line', 'label': {'en': 'Along', 'it': 'Lungo'},
         'choices': [{'value': 'line', 'label': {'en': 'a segment (two points)', 'it': 'un segmento (due punti)'}},
                     {'value': 'row', 'label': {'en': 'a row (at a y)', 'it': 'una riga (a una y)'}},
                     {'value': 'column', 'label': {'en': 'a column (at an x)', 'it': 'una colonna (a una x)'}}]},
        {'id': 'points', 'type': 'points', 'optional': True, 'show_if': {'along': ['line']},
         'label': {'en': 'Ends of the segment: click two points on the figure', 'it': 'Estremi del segmento: clicca due punti sul grafico'}},
        {'id': 'at', 'type': 'float', 'optional': True, 'show_if': {'along': ['row', 'column']},
         'label': {'en': 'At (y of the row, x of the column; empty = the middle)', 'it': 'A (y della riga, x della colonna; vuoto = a metà)'}},
        {'id': 'width', 'type': 'int', 'default': 1, 'min': 1, 'max': 101,
         'label': {'en': 'Width of the strip averaged (cells)', 'it': 'Larghezza della striscia mediata (celle)'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}

MAX_SAMPLES = 5000


def sample(Z, xs, ys, x0, y0, x1, y1, width=1):
    """(t, x, y, values): n points from (x0, y0) to (x1, y1), each the bilinear value averaged over `width`
    parallel lines one cell apart (in cell units, so x and y may have different units); t the distance along
    the segment in cells."""
    from scipy import ndimage
    ix = lambda v: np.interp(v, xs, np.arange(len(xs), dtype=float))                       # noqa: E731
    iy = lambda v: np.interp(v, ys, np.arange(len(ys), dtype=float))                       # noqa: E731
    c0, r0, c1, r1 = ix(x0), iy(y0), ix(x1), iy(y1)
    length = float(np.hypot(c1 - c0, r1 - r0))
    n = int(min(MAX_SAMPLES, max(2, np.ceil(length) + 1)))
    s = np.linspace(0, 1, n)
    cols, rows = c0 + s * (c1 - c0), r0 + s * (r1 - r0)
    if length > 0:
        nc, nr = -(r1 - r0) / length, (c1 - c0) / length                 # unit normal, in cells
    else:
        nc, nr = 0.0, 0.0
    offsets = np.arange(width) - (width - 1) / 2
    vals = np.mean([ndimage.map_coordinates(Z, [rows + o * nr, cols + o * nc], order=1, mode='nearest', cval=np.nan)
                    for o in offsets], axis=0)
    xv = np.interp(cols, np.arange(len(xs)), xs)
    yv = np.interp(rows, np.arange(len(ys)), ys)
    return s * length, xv, yv, vals


def run(df, p, ctx):
    Z, xs, ys, yname = ctx.matrix(df)
    along = p['along']
    w = int(p['width'])
    value = ctx.tr('value', 'valore')
    r = ctx.result()
    if along == 'line':
        pts = [q for q in (p.get('points') or []) if q[1] is not None]
        if len(pts) < 2:
            raise ValueError(ctx.tr('Click the two ends of the segment on the figure (or write “x y” on two lines).',
                                    'Clicca i due estremi del segmento sul grafico (o scrivi “x y” su due righe).'))
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        t, xv, yv, vals = sample(Z, xs, ys, x0, y0, x1, y1, w)
        dist = np.hypot(xv - xv[0], yv - yv[0])                         # along the segment, in the data's units
        abscissa = ctx.tr('distance', 'distanza')
        out = pd.DataFrame({abscissa: dist, 'x': xv, yname: yv, value: vals})
        r.value(ctx.tr('from', 'da'), f'({x0:.6g}, {y0:.6g})')
        r.value(ctx.tr('to', 'a'), f'({x1:.6g}, {y1:.6g})')
        r.value(ctx.tr('length', 'lunghezza'), float(dist[-1]), key='length')
    else:
        mid = (ys if along == 'row' else xs)
        at = p.get('at')
        at = float(np.median(mid)) if at is None else float(at)
        if not mid[0] <= at <= mid[-1]:
            raise ValueError(ctx.tr(f'{at:g} is outside the matrix ({mid[0]:g} … {mid[-1]:g}).',
                                    f'{at:g} è fuori dalla matrice ({mid[0]:g} … {mid[-1]:g}).'))
        if along == 'row':
            t, xv, yv, vals = sample(Z, xs, ys, xs[0], at, xs[-1], at, w)
            abscissa = 'x'
            out = pd.DataFrame({'x': xv, value: vals})
        else:
            t, xv, yv, vals = sample(Z, xs, ys, at, ys[0], at, ys[-1], w)
            abscissa = yname
            out = pd.DataFrame({yname: yv, value: vals})
        r.value(ctx.tr('at', 'a'), at, key='at')
    ok = np.isfinite(vals)
    if not ok.any():
        raise ValueError(ctx.tr('The path crosses no cell with a value.', 'Il percorso non attraversa celle con un valore.'))
    i_max, i_min = int(np.nanargmax(vals)), int(np.nanargmin(vals))
    pos = out[abscissa].to_numpy(float)
    r.value(ctx.tr('points', 'punti'), int(ok.sum()))
    r.value(ctx.tr('mean', 'media'), float(np.nanmean(vals)), key='mean')
    r.value(ctx.tr('maximum', 'massimo'), float(vals[i_max]), key='max')
    r.value(ctx.tr('at (maximum)', 'a (massimo)'), float(pos[i_max]), key='at_max')
    if along == 'line':
        r.value(ctx.tr('maximum at (x, y)', 'massimo in (x, y)'), f'({xv[i_max]:.6g}, {yv[i_max]:.6g})')
    r.value(ctx.tr('minimum', 'minimo'), float(vals[i_min]), key='min')
    if w > 1:
        r.text(ctx.tr(f'Each point is the mean of {w} parallel lines one cell apart.',
                      f'Ogni punto è la media di {w} linee parallele distanti una cella.'))
    path = pd.DataFrame({'x': xv, yname: yv})
    r.overlay(path, 'x', yname, label=ctx.tr('profile', 'profilo'), style={'color': '#ff3b30', 'linewidth': 1.4})
    r.data(out, name=ctx.tr('profile', 'profilo'), plot={'kind': 'line', 'x': abscissa, 'y': [value]})
    return r
