"""Interpolation and resampling of a curve (scipy.interpolate): a new x grid — evenly spaced (number of points or
step), the x of another file of the figure (to put curves on a common grid), or values written — and y there by
linear, cubic spline, PCHIP, Akima or smoothing spline. Outside the data nothing is invented (no extrapolation)."""
import re

import numpy as np
import pandas as pd

from piplotter import signals

PLUGIN = {
    'id': 'interpolate',
    'order': 12,
    'name': {'en': 'Interpolation & resampling', 'it': 'Interpolazione e ricampionamento'},
    'category': 'signal',
    'description': {'en': 'The curve on a new x grid (even, a step, another file’s x or values written): linear, '
                          'spline, PCHIP, Akima or smoothing spline.',
                    'it': 'La curva su una nuova griglia di x (regolare, un passo, le x di un altro file o valori '
                          'scritti): lineare, spline, PCHIP, Akima o spline di smoothing.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        {'id': 'method', 'type': 'choice', 'default': 'pchip', 'label': {'en': 'Method', 'it': 'Metodo'},
         'choices': [{'value': 'linear', 'label': {'en': 'linear', 'it': 'lineare'}},
                     {'value': 'cubic', 'label': {'en': 'cubic spline', 'it': 'spline cubica'}},
                     {'value': 'pchip', 'label': {'en': 'PCHIP (shape-preserving, no overshoot)', 'it': 'PCHIP (conserva la forma, senza oscillazioni)'}},
                     {'value': 'akima', 'label': 'Akima'},
                     {'value': 'smooth', 'label': {'en': 'smoothing spline (through the noise)', 'it': 'spline di smoothing (attraverso il rumore)'}},
                     {'value': 'nearest', 'label': {'en': 'nearest point', 'it': 'punto più vicino'}}]},
        {'id': 'grid', 'type': 'choice', 'default': 'n', 'label': {'en': 'New x', 'it': 'Nuove x'},
         'choices': [{'value': 'n', 'label': {'en': 'evenly spaced: number of points', 'it': 'regolari: numero di punti'}},
                     {'value': 'step', 'label': {'en': 'evenly spaced: step', 'it': 'regolari: passo'}},
                     {'value': 'file', 'label': {'en': 'the x of another file in the figure', 'it': 'le x di un altro file del grafico'}},
                     {'value': 'values', 'label': {'en': 'values written', 'it': 'valori scritti'}}]},
        {'id': 'n', 'type': 'int', 'default': 500, 'min': 2, 'max': 1000000, 'show_if': {'grid': ['n']},
         'label': {'en': 'Number of points', 'it': 'Numero di punti'}},
        {'id': 'step', 'type': 'float', 'optional': True, 'min': 0, 'show_if': {'grid': ['step']},
         'label': {'en': 'Step (x units)', 'it': 'Passo (unità di x)'}},
        {'id': 'values', 'type': 'text', 'default': '', 'show_if': {'grid': ['values']},
         'label': {'en': 'x values (separated by spaces, commas or lines)', 'it': 'valori di x (separati da spazi, virgole o righe)'}},
        {'id': 'xmin', 'type': 'float', 'optional': True, 'show_if': {'grid': ['n', 'step']}, 'label': {'en': 'From x =', 'it': 'Da x ='}},
        {'id': 'xmax', 'type': 'float', 'optional': True, 'show_if': {'grid': ['n', 'step']}, 'label': {'en': 'To x =', 'it': 'A x ='}},
        {'id': 'smooth', 'type': 'float', 'optional': True, 'min': 0, 'show_if': {'method': ['smooth']},
         'label': {'en': 'Smoothing (empty = from the noise)', 'it': 'Smoothing (vuoto = dal rumore)'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
        'Fritsch, F. N. & Carlson, R. E. Monotone piecewise cubic interpolation. SIAM J. Numer. Anal. 17, 238–246 '
        '(1980). doi:10.1137/0717021',
        'Akima, H. A new method of interpolation and smooth curve fitting based on local procedures. J. ACM 17, '
        '589–602 (1970). doi:10.1145/321607.321609',
    ],
}


def interpolator(method, x, y, smooth=None):
    from scipy import interpolate
    if method == 'linear':
        return lambda g: np.interp(g, x, y)
    if method == 'nearest':
        return interpolate.interp1d(x, y, kind='nearest', assume_sorted=True)
    if x.size < 4 and method != 'linear':
        raise ValueError('At least four points are needed for this method.')
    if method == 'cubic':
        return interpolate.CubicSpline(x, y, bc_type='natural', extrapolate=False)
    if method == 'pchip':
        return interpolate.PchipInterpolator(x, y, extrapolate=False)
    if method == 'akima':
        return interpolate.Akima1DInterpolator(x, y)
    # Smoothing spline: s = n·σ² (Reinsch's criterion), σ the noise from the second differences (robust MAD; a
    # smooth curve's slope and gentle curvature hardly count), unless given.
    if smooth is None:
        d2 = np.diff(y, 2)
        sigma = 1.4826 * np.median(np.abs(d2 - np.median(d2))) / np.sqrt(6) if d2.size else 0.0
        smooth = x.size * sigma ** 2
    return interpolate.UnivariateSpline(x, y, s=smooth)


def parse_values(text):
    """Numbers separated by spaces, semicolons, lines or commas ("1, 2.5, 4" or "1 2,5 4": a comma between two
    digits is a decimal comma, unless the values are written only with commas, "1,2,3")."""
    text = str(text or '').strip()
    if not re.search(r'[\s;]', text) and text.count(',') > 1:      # "1,2,3": commas separate the values
        tokens = text.split(',')
    else:
        tokens = re.split(r'[\s;]+|,(?=\s)', text)
    return [float(t.strip().replace(',', '.')) for t in tokens if t.strip()]


def new_grid(p, x, ctx):
    lo = x[0] if p.get('xmin') is None else max(x[0], p['xmin'])
    hi = x[-1] if p.get('xmax') is None else min(x[-1], p['xmax'])
    if p['grid'] == 'values':
        vals = parse_values(p['values'])
        if not vals:
            raise ValueError(ctx.tr('Write the x values.', 'Scrivi i valori di x.'))
        return np.array(sorted(vals)), ctx.tr('values written', 'valori scritti')
    if p['grid'] == 'file':
        other = next((f for f in ctx.files if not f.get('main')), None)
        if other is None:
            raise ValueError(ctx.tr('No other file in the figure: tick one in Loaded files.',
                                    'Nessun altro file nel grafico: spuntane uno in File caricati.'))
        xs = ctx.numeric(other['df'], other['x']).to_numpy(float) if other['x'] else np.arange(len(other['df']), dtype=float)
        return np.unique(xs[np.isfinite(xs)]), ctx.tr(f'the x of {other["name"]}', f'le x di {other["name"]}')
    if not hi > lo:
        raise ValueError(ctx.tr('The range of x is empty.', 'L’intervallo di x è vuoto.'))
    if p['grid'] == 'step':
        if not p.get('step'):
            raise ValueError(ctx.tr('Write the step.', 'Scrivi il passo.'))
        return lo + p['step'] * np.arange(int(np.floor((hi - lo) / p['step'] + 1e-9)) + 1), \
            ctx.tr(f'step {p["step"]:g}', f'passo {p["step"]:g}')
    return np.linspace(lo, hi, int(p['n'])), ctx.tr(f'{int(p["n"])} points', f'{int(p["n"])} punti')


def run(df, p, ctx):
    x, y = signals.clean(*ctx.signal(df, p['x'], p['y']))
    if x.size < 2:
        raise ValueError(ctx.tr('At least two points are needed.', 'Servono almeno due punti.'))
    grid, how = new_grid(p, x, ctx)
    inside = (grid >= x[0]) & (grid <= x[-1])
    f = interpolator(p['method'], x, y, p.get('smooth'))
    yi = np.full(grid.size, np.nan)
    with np.errstate(all='ignore'):
        yi[inside] = np.asarray(f(grid[inside]), dtype=float)
    xname, yname = ctx.signal_names(p['x'], p['y'])
    label = f'{yname} ({ctx.tr("interpolated", "interpolata")})'
    out = pd.DataFrame({xname: grid, label: yi})
    r = ctx.result()
    method = next(c['label'] for c in PLUGIN['params'][2]['choices'] if c['value'] == p['method'])
    r.value(ctx.tr('method', 'metodo'), method if isinstance(method, str) else method[ctx.lang])
    r.value(ctx.tr('new x', 'nuove x'), how)
    r.value(ctx.tr('points: original → new', 'punti: originali → nuovi'), f'{x.size} → {grid.size}')
    if (~inside).any():
        r.text(ctx.tr(f'{int((~inside).sum())} new x outside the data are left empty (no extrapolation).',
                      f'{int((~inside).sum())} nuove x fuori dai dati restano vuote (nessuna estrapolazione).'))
    if grid.size > 1 and np.allclose(np.diff(grid), np.diff(grid)[0]):
        r.value(ctx.tr('step of the new x', 'passo delle nuove x'), float(np.diff(grid)[0]), key='step')
    r.overlay(out.dropna(), xname, label, label=label, style={'linewidth': 1.0})
    r.data(out, name=label, plot={'kind': 'line', 'x': xname, 'y': [label]})
    return r
