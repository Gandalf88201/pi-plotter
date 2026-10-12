"""Global fit: one model fitted to every curve of the figure at once, some parameters shared by all the curves.

Example: decays measured at several temperatures with the same lifetime τ but their own amplitudes — fitted
together, τ comes from all the data and its error is the smaller for it. With no shared parameter it is a batch
fit: each curve on its own, all the results in one report table (one row per curve, as Origin's fit report).

The curves are those of the figure: each Y column of the analysed file and of the other files drawn with it
(ctx.files), excluded points left out. Least squares on all the residuals together (scipy.optimize.least_squares,
trust-region reflective), standard errors from the Jacobian, R² and RMSE of each curve.
"""
import numpy as np
import pandas as pd

from piplotter.analyses import fit_curve as fc

PLUGIN = {
    'id': 'global_fit',
    'order': 20,
    'name': {'en': 'Global fit of several curves', 'it': 'Fit globale di più curve'},
    'category': 'fit',
    'description': {'en': 'One model on every curve of the figure at once, with parameters shared by all the curves '
                          '(e.g. one τ) and a report table, one row per curve.',
                    'it': 'Un modello su tutte le curve del grafico insieme, con parametri condivisi da tutte (es. un '
                          'solo τ) e una tabella di riepilogo, una riga per curva.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'model', 'type': 'choice', 'default': 'exp_decay', 'label': {'en': 'Model', 'it': 'Modello'},
         'choices': [{'value': k, 'label': v[0]} for k, v in fc.MODELS.items()] +
                    [{'value': 'custom', 'label': {'en': 'Custom formula…', 'it': 'Formula personalizzata…'}}]},
        {'id': 'formula', 'type': 'text', 'default': 'a*exp(-x/tau) + c', 'show_if': {'model': ['custom']},
         'label': {'en': 'Custom formula in x', 'it': 'Formula personalizzata in x'}},
        {'id': 'shared', 'type': 'text', 'default': '',
         'label': {'en': 'Shared parameters (e.g. tau)', 'it': 'Parametri condivisi (es. tau)'},
         'help': {'en': 'Names of the parameters with one value for all the curves, separated by commas; empty = '
                        'every curve fitted on its own (batch fit).',
                  'it': 'Nomi dei parametri con un solo valore per tutte le curve, separati da virgole; vuoto = ogni '
                        'curva adattata da sola (fit in serie).'}},
        {'id': 'p0', 'type': 'text', 'default': '',
         'label': {'en': 'Starting values (e.g. tau=10)', 'it': 'Valori iniziali (es. tau=10)'}},
        {'id': 'bounds', 'type': 'text', 'default': '',
         'label': {'en': 'Limits (e.g. tau=0..inf)', 'it': 'Limiti (es. tau=0..inf)'}},
        {'id': 'note', 'type': 'bool', 'default': True,
         'label': {'en': 'Write the shared values in the figure', 'it': 'Scrivi i valori condivisi nel grafico'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
        'Beechem, J. M. Global analysis of biochemical and biophysical data. Methods Enzymol. 210, 37–54 (1992). '
        'doi:10.1016/0076-6879(92)10004-W',
    ],
}


def curves(df, ctx):
    """[(label, x, y)] of the figure's curves: each Y column of each file (ctx.files), NaN rows dropped."""
    files = ctx.files
    if not files:       # no figure (a recipe, a test): its Y columns, or every numeric column against the first
        x, ys = ctx.spec.get('x'), [c for c in ctx.spec.get('y') or [] if c in df.columns]
        if not ys:
            numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            x = x if x in df.columns else (numeric[0] if numeric else None)
            ys = [c for c in numeric if c != x]
        files = [{'name': '', 'df': df, 'x': x, 'y': ys, 'main': True}]
    many_files = len(files) > 1
    out = []
    for f in files:
        for y in f['y']:
            x_arr, y_arr = ctx.xy(f['df'], f['x'], y)
            if x_arr.size:
                name = f['name'].split('›')[-1].strip()
                label = f'{name} · {y}' if many_files and len(f['y']) > 1 else (name if many_files else str(y))
                out.append((label, x_arr, y_arr))
    return out


def run(df, p, ctx):
    from scipy import optimize

    data = curves(df, ctx)
    if not data:
        raise ValueError(ctx.tr('No curve to fit: choose Y columns (and other files) in the figure.',
                                'Nessuna curva da adattare: scegli colonne Y (e altri file) nel grafico.'))
    if p['model'] == 'custom':
        f, names = fc.compile_formula(p['formula'])
        equation = 'y = ' + p['formula']
    else:
        f = fc.model_function(p['model'])
        equation, names = fc.MODELS[p['model']]
    shared = [s.strip() for s in str(p['shared'] or '').replace(';', ',').split(',') if s.strip()]
    unknown = [s for s in shared if s not in names]
    if unknown:
        raise ValueError(ctx.tr(f'Not a parameter of the model: {", ".join(unknown)} (the parameters are {", ".join(names)}).',
                                f'Non è un parametro del modello: {", ".join(unknown)} (i parametri sono {", ".join(names)}).'))
    local = [n for n in names if n not in shared]
    n_curves = len(data)

    # Starting values: the model's own guess on each curve (the shared ones averaged), then the user's.
    guesses = []
    for _, x, y in data:
        g = fc.initial_guess(p['model'], x, y) if p['model'] != 'custom' else None
        guesses.append(fc.parse_p0(p['p0'], names, g))
    guesses = np.array(guesses, float)
    theta0 = [float(np.mean(guesses[:, names.index(n)])) for n in shared]
    for g in guesses:
        theta0 += [float(g[names.index(n)]) for n in local]
    limits = fc.parse_bounds(p.get('bounds'), names)
    lo_one, hi_one = limits if limits is not None else (np.full(len(names), -np.inf), np.full(len(names), np.inf))
    lo = [lo_one[names.index(n)] for n in shared] + [lo_one[names.index(n)] for _ in data for n in local]
    hi = [hi_one[names.index(n)] for n in shared] + [hi_one[names.index(n)] for _ in data for n in local]
    theta0 = np.clip(theta0, np.array(lo) + 1e-12, np.array(hi) - 1e-12)

    def params_of(theta, i):
        vals = dict(zip(shared, theta[:len(shared)]))
        start = len(shared) + i * len(local)
        vals.update(zip(local, theta[start:start + len(local)]))
        return [vals[n] for n in names]

    def residuals(theta):
        with np.errstate(all='ignore'):
            r = np.concatenate([f(x, *params_of(theta, i)) - y for i, (_, x, y) in enumerate(data)])
        return np.where(np.isfinite(r), r, 1e30)

    sol = optimize.least_squares(residuals, theta0, bounds=(lo, hi), x_scale='jac', max_nfev=20000 * len(theta0))
    if not sol.success:
        raise ValueError(ctx.tr(f'The fit did not converge: {sol.message}', f'Il fit non converge: {sol.message}'))
    n_total, k = sum(len(x) for _, x, _ in data), len(sol.x)
    dof = max(1, n_total - k)
    s2 = float(np.sum(sol.fun ** 2)) / dof
    jac = np.asarray(sol.jac.todense() if hasattr(sol.jac, 'todense') else sol.jac)
    try:
        if shared:      # one noise level for all the data (the global-analysis assumption)
            err = np.sqrt(np.clip(np.diag(np.linalg.pinv(jac.T @ jac) * s2), 0, None))
        else:           # independent curves: each its own residual variance, as a fit of that curve alone
            err, row = np.empty(k), 0
            for i, (_, x, _) in enumerate(data):
                cols = slice(i * len(local), (i + 1) * len(local))
                rows = slice(row, row + x.size)
                s2_i = float(np.sum(sol.fun[rows] ** 2)) / max(1, x.size - len(local))
                block = jac[rows, cols]
                err[cols] = np.sqrt(np.clip(np.diag(np.linalg.pinv(block.T @ block) * s2_i), 0, None))
                row += x.size
    except np.linalg.LinAlgError:
        err = np.full(k, np.nan)

    r = ctx.result()
    r.text(equation)
    r.text(ctx.tr(f'{n_curves} curves, {n_total} points, {k} parameters'
                  + (f'; shared: {", ".join(shared)}.' if shared else '; no shared parameter: each curve fitted on its own.'),
                  f'{n_curves} curve, {n_total} punti, {k} parametri'
                  + (f'; condivisi: {", ".join(shared)}.' if shared else '; nessun parametro condiviso: ogni curva adattata da sola.')))
    for j, n in enumerate(shared):
        r.value(f'{fc.SYMBOLS.get(n, n)} ({ctx.tr("shared", "condiviso")})', sol.x[j], err[j], key=n)
    report, overlay_ids = [], []
    for i, (label, x, y) in enumerate(data):
        vals = params_of(sol.x, i)
        start = len(shared) + i * len(local)
        errs = {n: err[shared.index(n)] for n in shared}
        errs.update({n: err[start + m] for m, n in enumerate(local)})
        fit_y = f(x, *vals)
        ss_res = float(np.sum((y - fit_y) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        row = {ctx.tr('curve', 'curva'): label, 'N': int(x.size)}
        for n, v in zip(names, vals):
            row[n] = float(v)
            row[f'σ({n})'] = float(errs[n])
        row['R²'] = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
        row['RMSE'] = float(np.sqrt(ss_res / x.size))
        report.append(row)
        grid = np.linspace(x.min(), x.max(), 400)
        overlay_ids.append(r.overlay(pd.DataFrame({'x': grid, 'fit': f(grid, *vals)}), 'x', 'fit',
                                     label=ctx.tr('global fit', 'fit globale') + f' · {label}'))
    report = pd.DataFrame(report)
    r.table(ctx.tr('Fit report (one row per curve)', 'Riepilogo dei fit (una riga per curva)'), report)
    r.value(ctx.tr('curves', 'curve'), n_curves)
    r.value('RMSE', float(np.sqrt(np.sum(sol.fun ** 2) / n_total)), key='rmse')
    r.value(ctx.tr('lowest R² of a curve', 'R² più basso di una curva'), float(report['R²'].min()), key='r2_min')
    if p['note'] and shared:
        r.overlays[overlay_ids[0]]['note'] = '\n'.join(
            [f'{fc.SYMBOLS.get(n, n)} = {fc.plus_minus(sol.x[j], err[j])}' for j, n in enumerate(shared)]
            + [ctx.tr(f'{n_curves} curves, shared', f'{n_curves} curve, condiviso')])
    # The report as data: each parameter against the curve number (plot the trend, export it).
    trend = report.copy()
    trend.insert(0, '#', np.arange(1, len(trend) + 1))
    first_local = local[0] if local else names[0]
    r.data(trend, name=ctx.tr('global fit report', 'riepilogo fit globale'),
           plot={'kind': 'errorbar', 'x': '#', 'y': [first_local], 'yerr': f'σ({first_local})', 'style': {'marker': 'o'}})
    r.cite('Moré, J. J. The Levenberg–Marquardt algorithm: implementation and theory. In Numerical Analysis, '
           'Lecture Notes in Mathematics 630, 105–116 (1978). doi:10.1007/BFb0067700')
    return r
