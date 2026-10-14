"""Reshape and convert a matrix (an image, a map, a 2D spectrum): transpose, flip, rotate by 90°, crop to a range,
bin blocks of cells, resample on a new grid, or turn it into X, Y, Z columns. From X, Y, Z columns it makes the
matrix: their own grid, or scattered points interpolated on a regular one (Delaunay triangulation)."""
import numpy as np

from piplotter import matrices

PLUGIN = {
    'id': 'matrix_transform',
    'order': 1,
    'name': {'en': 'Matrix: reshape & convert', 'it': 'Matrice: trasforma e converti'},
    'category': 'matrix',
    'description': {'en': 'Transpose, flip, rotate, crop, bin or resample a matrix; matrix ↔ X, Y, Z columns '
                          '(scattered points gridded).',
                    'it': 'Trasposta, ribalta, ruota, ritaglia, raggruppa o ricampiona una matrice; matrice ↔ colonne '
                          'X, Y, Z (punti sparsi su griglia).'},
    'suits': [                                          # figures it suits (piplotter/advisor.py)
        {'figure': 'matrix', 'score': 70,
         'reason': {'en': 'Crop, bin, rotate or resample it; turn it into X, Y, Z columns.',
                    'it': 'Ritagliala, raggruppa, ruota o ricampiona; trasformala in colonne X, Y, Z.'}},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'operation', 'type': 'choice', 'default': 'grid', 'label': {'en': 'Operation', 'it': 'Operazione'},
         'choices': [{'value': 'grid', 'label': {'en': 'matrix of the figure (from X, Y, Z: gridded)', 'it': 'matrice del grafico (da X, Y, Z: su griglia)'}},
                     {'value': 'crop', 'label': {'en': 'crop to a range', 'it': 'ritaglia a un intervallo'}},
                     {'value': 'bin', 'label': {'en': 'bin blocks of cells (mean)', 'it': 'raggruppa blocchi di celle (media)'}},
                     {'value': 'resample', 'label': {'en': 'resample on a new grid', 'it': 'ricampiona su una nuova griglia'}},
                     {'value': 'transpose', 'label': {'en': 'transpose (swap x and y)', 'it': 'trasposta (scambia x e y)'}},
                     {'value': 'flip_x', 'label': {'en': 'flip left ↔ right', 'it': 'ribalta sinistra ↔ destra'}},
                     {'value': 'flip_y', 'label': {'en': 'flip top ↔ bottom', 'it': 'ribalta alto ↔ basso'}},
                     {'value': 'rotate', 'label': {'en': 'rotate 90° anticlockwise', 'it': 'ruota di 90° in senso antiorario'}},
                     {'value': 'to_xyz', 'label': {'en': 'to X, Y, Z columns', 'it': 'in colonne X, Y, Z'}}]},
        {'id': 'xmin', 'type': 'float', 'optional': True, 'show_if': {'operation': ['crop']}, 'label': {'en': 'X from', 'it': 'X da'}},
        {'id': 'xmax', 'type': 'float', 'optional': True, 'show_if': {'operation': ['crop']}, 'label': {'en': 'X to', 'it': 'X a'}},
        {'id': 'ymin', 'type': 'float', 'optional': True, 'show_if': {'operation': ['crop']}, 'label': {'en': 'Y from', 'it': 'Y da'}},
        {'id': 'ymax', 'type': 'float', 'optional': True, 'show_if': {'operation': ['crop']}, 'label': {'en': 'Y to', 'it': 'Y a'}},
        {'id': 'factor', 'type': 'int', 'default': 2, 'min': 2, 'max': 64, 'show_if': {'operation': ['bin']},
         'label': {'en': 'Cells per block (each side)', 'it': 'Celle per blocco (per lato)'}},
        {'id': 'nx', 'type': 'int', 'optional': True, 'min': 2, 'max': 4096, 'show_if': {'operation': ['resample', 'grid']},
         'label': {'en': 'Columns of the new grid (empty = automatic)', 'it': 'Colonne della nuova griglia (vuoto = automatico)'}},
        {'id': 'ny', 'type': 'int', 'optional': True, 'min': 2, 'max': 4096, 'show_if': {'operation': ['resample', 'grid']},
         'label': {'en': 'Rows of the new grid (empty = automatic)', 'it': 'Righe della nuova griglia (vuoto = automatico)'}},
        {'id': 'method', 'type': 'choice', 'default': 'linear', 'show_if': {'operation': ['resample', 'grid']},
         'label': {'en': 'Interpolation', 'it': 'Interpolazione'},
         'choices': [{'value': 'linear', 'label': {'en': 'linear', 'it': 'lineare'}},
                     {'value': 'nearest', 'label': {'en': 'nearest', 'it': 'più vicino'}},
                     {'value': 'cubic', 'label': {'en': 'cubic', 'it': 'cubica'}}]},
    ],
    'references': [
        'Delaunay, B. Sur la sphère vide. Bull. Acad. Sci. URSS 6, 793–800 (1934).',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def resample(Z, xs, ys, nx, ny, method):
    """Z on an even nx × ny grid over the same range (linear, nearest or cubic on the rectilinear grid)."""
    from scipy.interpolate import RegularGridInterpolator
    gx, gy = np.linspace(xs[0], xs[-1], nx), np.linspace(ys[0], ys[-1], ny)
    f = RegularGridInterpolator((ys, xs), Z, method=method if len(xs) > 3 and len(ys) > 3 else 'linear',
                                bounds_error=False)
    Y, X = np.meshgrid(gy, gx, indexing='ij')
    return f(np.stack([Y, X], -1)), gx, gy


def run(df, p, ctx):
    spec = ctx.spec or {}
    op = p['operation']
    r = ctx.result()
    xyz = bool(spec.get('z') and spec.get('z') in df.columns)
    if op == 'grid' and xyz and (p.get('nx') or p.get('ny')):       # scattered points on a grid of a chosen size
        n = max(p.get('nx') or 0, p.get('ny') or 0)
        Z, xs, ys = matrices.from_xyz(df, spec['x'], spec['y'][0], spec['z'], size=n, method=p['method'])
        yname = spec['y'][0]
    else:
        Z, xs, ys, yname = ctx.matrix(df)
    if op == 'crop':
        lo_x, hi_x = p.get('xmin'), p.get('xmax')
        lo_y, hi_y = p.get('ymin'), p.get('ymax')
        kx = (xs >= (lo_x if lo_x is not None else -np.inf)) & (xs <= (hi_x if hi_x is not None else np.inf))
        ky = (ys >= (lo_y if lo_y is not None else -np.inf)) & (ys <= (hi_y if hi_y is not None else np.inf))
        if kx.sum() < 2 or ky.sum() < 2:
            raise ValueError(ctx.tr('The range keeps fewer than two rows or columns.',
                                    'L’intervallo tiene meno di due righe o colonne.'))
        Z, xs, ys = Z[np.ix_(ky, kx)], xs[kx], ys[ky]
    elif op == 'bin':
        k = int(p['factor'])
        Z = matrices.bin_matrix(Z, k)
        xs = xs[:Z.shape[1] * k].reshape(-1, k).mean(1)
        ys = ys[:Z.shape[0] * k].reshape(-1, k).mean(1)
    elif op == 'resample' or (op == 'grid' and (p.get('nx') or p.get('ny'))):
        nx, ny = int(p.get('nx') or len(xs)), int(p.get('ny') or len(ys))
        Z, xs, ys = resample(Z, xs, ys, nx, ny, p['method'])
    elif op == 'transpose':
        Z, xs, ys = Z.T, ys, xs
    elif op == 'flip_x':
        Z = Z[:, ::-1]
    elif op == 'flip_y':
        Z = Z[::-1, :]
    elif op == 'rotate':                        # (x, y) → (−y, x), placed back on the range y had
        Z, xs, ys = Z.T[:, ::-1], (ys.min() + ys.max()) - ys[::-1], xs
    r.value(ctx.tr('columns', 'colonne'), int(Z.shape[1]), key='nx')
    r.value(ctx.tr('rows', 'righe'), int(Z.shape[0]), key='ny')
    r.value(ctx.tr('x from … to', 'x da … a'), f'{xs[0]:.6g} … {xs[-1]:.6g}')
    r.value(ctx.tr('y from … to', 'y da … a'), f'{ys[0]:.6g} … {ys[-1]:.6g}')
    missing = int(np.isnan(Z).sum())
    if missing:
        r.text(ctx.tr(f'{missing:,} cells have no value (outside the measured points or the image).',
                      f'{missing:,} celle non hanno valore (fuori dai punti misurati o dall’immagine).'))
    name = {'grid': ctx.tr('matrix', 'matrice'), 'to_xyz': 'x, y, z'}.get(op, ctx.tr('matrix', 'matrice') + f' ({op})')
    if op == 'to_xyz':
        value = ctx.tr('value', 'valore')
        out = matrices.to_xyz(Z, xs, ys, ('x', yname, value))
        r.data(out, name=name, plot={'kind': 'heatmap', 'x': 'x', 'y': [yname], 'z': value})
    else:
        r.data(matrices.to_frame(Z, xs, ys, yname), name=name, plot={'kind': 'heatmap', 'x': yname, 'y': []})
    return r
