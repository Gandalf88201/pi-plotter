"""Decimation of a very long signal to a few thousand points that keep its look — peaks, dips and spikes included —
for a lighter table, a faster figure or an export: Largest-Triangle-Three-Buckets (LTTB), or the first, last, lowest
and highest point of equal slices of x (M4, exact for a line drawn one slice per pixel column). Block averages
(less noise, peaks flattened) and every k-th point (fast, peaks can be lost) are offered for comparison."""
import numpy as np
import pandas as pd

from piplotter import signals

PLUGIN = {
    'id': 'decimate',
    'order': 13,
    'name': {'en': 'Decimation (keep the peaks)', 'it': 'Decimazione (conserva i picchi)'},
    'category': 'signal',
    'description': {'en': 'A very long signal reduced to a few thousand points that keep its shape and its peaks '
                          '(LTTB, min/max per slice), or block averages.',
                    'it': 'Un segnale molto lungo ridotto a poche migliaia di punti che ne conservano la forma e i '
                          'picchi (LTTB, min/max per intervallo), o medie a blocchi.'},
    'suits': [],          # not suggested from the figure alone
    'requires': [],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        {'id': 'method', 'type': 'choice', 'default': 'lttb', 'label': {'en': 'Method', 'it': 'Metodo'},
         'choices': [{'value': 'lttb', 'label': {'en': 'LTTB: the shape, peaks kept', 'it': 'LTTB: la forma, picchi conservati'}},
                     {'value': 'minmax', 'label': {'en': 'min / max of each slice (M4): every extreme kept', 'it': 'min / max di ogni intervallo (M4): ogni estremo conservato'}},
                     {'value': 'mean', 'label': {'en': 'block averages (less noise, peaks flattened)', 'it': 'medie a blocchi (meno rumore, picchi appiattiti)'}},
                     {'value': 'every', 'label': {'en': 'every k-th point (peaks can be lost)', 'it': 'un punto ogni k (i picchi si possono perdere)'}}]},
        {'id': 'n', 'type': 'int', 'default': 2000, 'min': 10, 'max': 1000000,
         'label': {'en': 'Points to keep (about)', 'it': 'Punti da tenere (circa)'}},
    ],
    'references': [
        'Steinarsson, S. Downsampling time series for visual representation. MSc thesis, University of Iceland (2013). '
        'http://hdl.handle.net/1946/15343',
        'Jugel, U., Jerzak, Z., Hackenbroich, G. & Markl, V. M4: a visualization-oriented time series data '
        'aggregation. Proc. VLDB Endow. 7, 797–808 (2014). doi:10.14778/2732951.2732953',
    ],
}


def run(df, p, ctx):
    x, y = signals.clean(*ctx.signal(df, p['x'], p['y']))
    n = int(p['n'])
    if x.size < 3:
        raise ValueError(ctx.tr('At least three points are needed.', 'Servono almeno tre punti.'))
    kind = p['method']
    if x.size <= n:
        xs, ys = x, y
    elif kind == 'lttb':
        idx = signals.lttb_indices(x, y, n)
        xs, ys = x[idx], y[idx]
    elif kind == 'minmax':
        idx = signals.m4_indices(x, y, max(1, n // 4))
        xs, ys = x[idx], y[idx]
    elif kind == 'mean':
        k = int(np.ceil(x.size / n))
        m = x.size // k * k
        xs = x[:m].reshape(-1, k).mean(1)
        ys = y[:m].reshape(-1, k).mean(1)
        if m < x.size:                                       # the last, shorter block
            xs, ys = np.r_[xs, x[m:].mean()], np.r_[ys, y[m:].mean()]
    else:
        k = int(np.ceil(x.size / n))
        xs, ys = x[::k], y[::k]
    xname, yname = ctx.signal_names(p['x'], p['y'])
    label = f'{yname} ({ctx.tr("decimated", "decimata")})'
    out = pd.DataFrame({xname: xs, label: ys})
    r = ctx.result()
    r.value(ctx.tr('points: original → kept', 'punti: originali → tenuti'), f'{x.size:,} → {xs.size:,}')
    r.value(ctx.tr('kept points', 'punti tenuti'), int(xs.size), key='n')
    r.value(ctx.tr('highest value: original / kept', 'valore più alto: originale / tenuto'),
            f'{np.max(y):.6g} / {np.max(ys):.6g}')
    r.value(ctx.tr('lowest value: original / kept', 'valore più basso: originale / tenuto'),
            f'{np.min(y):.6g} / {np.min(ys):.6g}')
    if x.size <= n:
        r.text(ctx.tr('The signal has no more points than asked: kept as it is.',
                      'Il segnale non ha più punti di quanti richiesti: tenuto com’è.'))
    r.overlay(out, xname, label, label=label, style={'linewidth': 1.0})
    r.data(out, name=label, plot={'kind': 'line', 'x': xname, 'y': [label]})
    return r
