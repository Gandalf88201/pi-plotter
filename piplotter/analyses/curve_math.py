"""Arithmetic of two curves of the figure (Origin's "Simple Curve Math"): A − B, A + B, A × B, A ÷ B, or A − k·B with
k fitted by least squares (background or solvent subtraction). B is interpolated at the x of A where they overlap,
so the two curves may come from different files with different x."""
import numpy as np
import pandas as pd

from piplotter import signals
from piplotter.analyses import global_fit

PLUGIN = {
    'id': 'curve_math',
    'order': 14,
    'name': {'en': 'Arithmetic of two curves', 'it': 'Operazioni tra due curve'},
    'category': 'signal',
    'description': {'en': 'A − B, A + B, A × B, A ÷ B or A − k·B (k fitted: background subtraction) for two curves of '
                          'the figure, also from different files with different x.',
                    'it': 'A − B, A + B, A × B, A ÷ B o A − k·B (k adattato: sottrazione del fondo) per due curve del '
                          'grafico, anche da file diversi con x diverse.'},
    'suits': [],          # suggested by RULES in piplotter/advisor.py: it needs several facts together
    'requires': ['scipy'],
    'params': [
        {'id': 'op', 'type': 'choice', 'default': 'sub', 'label': {'en': 'Operation', 'it': 'Operazione'},
         'choices': [{'value': 'sub', 'label': 'A − B'}, {'value': 'add', 'label': 'A + B'},
                     {'value': 'mul', 'label': 'A × B'}, {'value': 'div', 'label': 'A ÷ B'},
                     {'value': 'scaled', 'label': {'en': 'A − k·B, k fitted (background)', 'it': 'A − k·B, k adattato (fondo)'}}]},
        {'id': 'a', 'type': 'int', 'default': 1, 'min': 1, 'label': {'en': 'Curve A (number in the figure)', 'it': 'Curva A (numero nel grafico)'}},
        {'id': 'b', 'type': 'int', 'default': 2, 'min': 1, 'label': {'en': 'Curve B', 'it': 'Curva B'}},
        {'id': 'k', 'type': 'float', 'optional': True, 'show_if': {'op': ['scaled']},
         'label': {'en': 'k (empty = fitted)', 'it': 'k (vuoto = adattato)'}},
    ],
    'references': ['Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2'],
}

SYMBOL = {'sub': '−', 'add': '+', 'mul': '×', 'div': '÷'}


def run(df, p, ctx):
    data = global_fit.curves(df, ctx)
    names = ', '.join(f'{i + 1} = {c["label"]}' for i, c in enumerate(data))
    if len(data) < 2:
        raise ValueError(ctx.tr('Two curves are needed: tick a second Y column or another file in the figure.',
                                'Servono due curve: spunta una seconda colonna Y o un altro file nel grafico.'))
    ia, ib = int(p['a']) - 1, int(p['b']) - 1
    if not (0 <= ia < len(data) and 0 <= ib < len(data)) or ia == ib:
        raise ValueError(ctx.tr(f'Choose two different curves among: {names}.', f'Scegli due curve diverse tra: {names}.'))
    A, B = data[ia], data[ib]
    xa, ya = signals.clean(A['x'], A['y'])
    xb, yb = signals.clean(B['x'], B['y'])
    keep = (xa >= xb[0]) & (xa <= xb[-1])
    if keep.sum() < 2:
        raise ValueError(ctx.tr('The two curves do not overlap in x.', 'Le due curve non si sovrappongono in x.'))
    x, a = xa[keep], ya[keep]
    b = np.interp(x, xb, yb)
    r = ctx.result()
    r.text(ctx.tr(f'A = {A["label"]}, B = {B["label"]} (curves of the figure: {names}).',
                  f'A = {A["label"]}, B = {B["label"]} (curve del grafico: {names}).'))
    if (~keep).any():
        r.text(ctx.tr(f'{int((~keep).sum())} points of A outside B are left out.',
                      f'{int((~keep).sum())} punti di A fuori da B sono lasciati fuori.'))
    if p['op'] == 'scaled':
        k = p.get('k')
        if k is None:
            k = float(np.dot(a, b) / np.dot(b, b)) if np.dot(b, b) > 0 else 0.0
            r.value(ctx.tr('k (least squares)', 'k (minimi quadrati)'), k, key='k')
        else:
            r.value('k', k, key='k')
        out, title = a - k * b, f'A − {k:.4g}·B'
    elif p['op'] == 'div':
        with np.errstate(divide='ignore', invalid='ignore'):
            out = np.where(b != 0, a / b, np.nan)
        title = 'A ÷ B'
    else:
        out = {'sub': a - b, 'add': a + b, 'mul': a * b}[p['op']]
        title = f'A {SYMBOL[p["op"]]} B'
    r.value(ctx.tr('points', 'punti'), int(x.size))
    r.value(ctx.tr('mean of the result', 'media del risultato'), float(np.nanmean(out)), key='mean')
    xname = ctx.spec.get('x') or 'x'
    out_df = pd.DataFrame({xname: x, 'A': a, 'B': b, title: out})
    same_units = p['op'] in ('sub', 'add', 'scaled')            # × and ÷ change the units: a figure of their own
    r.overlay(out_df[[xname, title]], xname, title, label=title, style={'linewidth': 1.1}, on_figure=same_units)
    r.data(out_df, name=title, plot={'kind': 'line', 'x': xname, 'y': [title]})
    return r
