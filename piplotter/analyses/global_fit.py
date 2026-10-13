"""Global fit: one model fitted to every curve of the figure at once, some parameters shared by the curves.

Example: decays measured at several temperatures with the same lifetime τ but their own amplitudes — fitted
together, τ comes from all the data and its error is the smaller for it. A parameter can be shared by all the curves
(`tau`) or by some of them (`tau[1,2], tau[3-5]`: one τ for curves 1–2, another for 3–5), or fixed (`C=0`). With
nothing shared it is a batch fit: each curve on its own, all the results in one report table (one row per curve, as
Origin's fit report).

The curves are those of the figure: each Y column of the analysed file and of the other files drawn with it
(ctx.files), excluded points left out; a file's Y error column weights its points (1/σ²). Least squares on all the
residuals together (scipy.optimize.least_squares, trust-region reflective), standard errors from the Jacobian, R² and
RMSE of each curve.
"""
import re

import numpy as np
import pandas as pd

from piplotter.analyses import fit_curve as fc

PLUGIN = {
    'id': 'global_fit',
    'order': 20,
    'name': {'en': 'Global fit of several curves', 'it': 'Fit globale di più curve'},
    'category': 'fit',
    'description': {'en': 'One model on every curve of the figure at once, with parameters shared by all the curves '
                          'or by some of them (e.g. one τ), fixed ones, and a report table, one row per curve.',
                    'it': 'Un modello su tutte le curve del grafico insieme, con parametri condivisi da tutte o da '
                          'alcune (es. un solo τ), parametri fissi, e una tabella di riepilogo, una riga per curva.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'model', 'type': 'choice', 'default': 'exp_decay', 'label': {'en': 'Model', 'it': 'Modello'},
         'choices': [{'value': k, 'label': v[0]} for k, v in fc.MODELS.items()] +
                    [{'value': 'custom', 'label': {'en': 'Custom formula…', 'it': 'Formula personalizzata…'}}]},
        {'id': 'formula', 'type': 'text', 'default': 'a*exp(-x/tau) + c', 'show_if': {'model': ['custom']},
         'label': {'en': 'Custom formula in x', 'it': 'Formula personalizzata in x'}},
        {'id': 'shared', 'type': 'text', 'default': '',
         'label': {'en': 'Shared parameters (e.g. tau)', 'it': 'Parametri condivisi (es. tau)'},
         'help': {'en': 'tau = one τ for all the curves; tau[1,2], tau[3-5] = one τ for curves 1–2 and another for '
                        '3–5 (numbers as in the report table). Empty = every curve fitted on its own (batch fit).',
                  'it': 'tau = un solo τ per tutte le curve; tau[1,2], tau[3-5] = un τ per le curve 1–2 e un altro '
                        'per le 3–5 (numeri come nella tabella di riepilogo). Vuoto = ogni curva adattata da sola '
                        '(fit in serie).'}},
        {'id': 'fixed', 'type': 'text', 'default': '',
         'label': {'en': 'Fixed parameters (e.g. C=0)', 'it': 'Parametri fissi (es. C=0)'},
         'help': {'en': 'Parameters kept at the given value for every curve, not fitted.',
                  'it': 'Parametri tenuti al valore dato per ogni curva, non adattati.'}},
        {'id': 'weights', 'type': 'choice', 'default': 'auto', 'label': {'en': 'Weights', 'it': 'Pesi'},
         'choices': [{'value': 'auto', 'label': {'en': 'from the Y error columns of the figure (1/σ²), if every curve '
                                                       'has one', 'it': 'dalle colonne di errore Y del grafico '
                                                       '(1/σ²), se ogni curva ne ha una'}},
                     {'value': 'none', 'label': {'en': 'none (all points equal)', 'it': 'nessuno (punti uguali)'}}]},
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
    """[{label, x, y, sigma}] of the figure's curves: each Y column of each file (ctx.files), NaN rows dropped; sigma
    from the file's Y error column when it has one Y column (else None)."""
    files = ctx.files
    if not files:       # no figure (a recipe, a test): its Y columns, or every numeric column against the first
        x, ys = ctx.spec.get('x'), [c for c in ctx.spec.get('y') or [] if c in df.columns]
        if not ys:
            numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            x = x if x in df.columns else (numeric[0] if numeric else None)
            ys = [c for c in numeric if c != x]
        yerr = ctx.spec.get('yerr') if ctx.spec.get('yerr') in df.columns else None
        files = [{'name': '', 'df': df, 'x': x, 'y': ys, 'yerr': yerr, 'main': True}]
    many_files = len(files) > 1
    out = []
    for f in files:
        frame = f['df']
        err = f.get('yerr') if len(f['y']) == 1 and f.get('yerr') in frame.columns else None
        for y in f['y']:
            ys = ctx.numeric(frame, y, dropna=False)
            xs = (ctx.numeric(frame, f['x'], dropna=False) if f['x']
                  else pd.Series(np.arange(len(frame), dtype=float), index=frame.index))
            es = ctx.numeric(frame, err, dropna=False) if err else None
            ok = xs.notna() & ys.notna()
            if es is not None:
                ok &= es.notna() & (es > 0)
            if not ok.any():
                continue
            name = f['name'].split('›')[-1].strip()
            label = f'{name} · {y}' if many_files and len(f['y']) > 1 else (name if many_files else str(y))
            out.append({'label': label, 'x': xs[ok].to_numpy(float), 'y': ys[ok].to_numpy(float),
                        'sigma': es[ok].to_numpy(float) if es is not None else None})
    return out


def parse_shared(text, names, n_curves, tr):
    """[(name, [curve indices])] from 'tau, A[1,2], A[3-5]' (curves numbered from 1; no list = all the curves)."""
    groups, taken = [], {}
    text = str(text or '').replace(';', ',')
    for name, idx in re.findall(r'([A-Za-z_]\w*)\s*(?:\[([^\]]*)\])?', text):
        if name not in names:
            raise ValueError(tr(f'Not a parameter of the model: {name} (the parameters are {", ".join(names)}).',
                                f'Non è un parametro del modello: {name} (i parametri sono {", ".join(names)}).'))
        members = set()
        for part in (idx.split(',') if idx else []):
            part = part.strip()
            m = re.fullmatch(r'(\d+)\s*-\s*(\d+)', part)
            nums = range(int(m.group(1)), int(m.group(2)) + 1) if m else ([int(part)] if part.isdigit() else None)
            if nums is None:
                raise ValueError(tr(f'Curves of {name}: write numbers or ranges, e.g. {name}[1,2] or {name}[3-5].',
                                    f'Curve di {name}: scrivi numeri o intervalli, es. {name}[1,2] o {name}[3-5].'))
            for k in nums:
                if not 1 <= k <= n_curves:
                    raise ValueError(tr(f'There is no curve {k} (the figure has {n_curves}).',
                                        f'Non c’è la curva {k} (il grafico ne ha {n_curves}).'))
                members.add(k - 1)
        members = sorted(members) if idx else list(range(n_curves))
        if taken.setdefault(name, set()) & set(members):
            raise ValueError(tr(f'A curve is in two groups of {name}.', f'Una curva è in due gruppi di {name}.'))
        taken[name] |= set(members)
        groups.append((name, members))
    return groups


def parse_fixed(text, names, tr):
    """{name: value} from 'C=0, tau=5'."""
    out = {}
    for part in str(text or '').replace(';', ',').split(','):
        if not part.strip():
            continue
        k, _, v = (t.strip() for t in part.partition('='))
        if k not in names:
            raise ValueError(tr(f'Not a parameter of the model: {k} (the parameters are {", ".join(names)}).',
                                f'Non è un parametro del modello: {k} (i parametri sono {", ".join(names)}).'))
        try:
            out[k] = float(v)
        except ValueError:
            raise ValueError(tr(f'Fixed parameters: write name=value, e.g. {k}=0.', f'Parametri fissi: scrivi nome=valore, es. {k}=0.'))
    return out


def curve_list(members, n):
    """'all' or '1–3, 5' for the curves of a group."""
    if len(members) == n:
        return None
    runs, start = [], None
    for k in members + [None]:
        if start is None:
            start = prev = k
        elif k == prev + 1:
            prev = k
        else:
            runs.append(f'{start + 1}' if start == prev else f'{start + 1}–{prev + 1}')
            start = prev = k
    return ', '.join(runs)


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
    n_curves = len(data)
    fixed = parse_fixed(p.get('fixed'), names, ctx.tr)
    groups = parse_shared(p['shared'], names, n_curves, ctx.tr)
    both = sorted({g for g, _ in groups} & set(fixed))
    if both:
        raise ValueError(ctx.tr(f'{", ".join(both)}: either shared or fixed, not both.',
                                f'{", ".join(both)}: o condiviso o fisso, non entrambi.'))
    if len(fixed) == len(names):
        raise ValueError(ctx.tr('Every parameter is fixed: nothing to fit.', 'Tutti i parametri sono fissi: niente da adattare.'))

    # The fitted numbers (theta): one per group, then one per curve for each parameter neither shared nor fixed.
    slots, index = [], {}                     # slots[k] = (name, [curves]); index[(curve, name)] = k
    for name, members in groups:
        for i in members:
            index[(i, name)] = len(slots)
        slots.append((name, members))
    for i in range(n_curves):
        for name in names:
            if name not in fixed and (i, name) not in index:
                index[(i, name)] = len(slots)
                slots.append((name, [i]))
    pooled = any(len(m) > 1 for _, m in slots)          # some number comes from several curves

    def params_of(theta, i):
        return [fixed[n] if n in fixed else theta[index[(i, n)]] for n in names]

    # Starting values: the model's own guess on each curve (a group's averaged over its curves), then the user's.
    guesses = []
    for c in data:
        g = fc.initial_guess(p['model'], c['x'], c['y']) if p['model'] != 'custom' else None
        guesses.append(fc.parse_p0(p['p0'], names, g))
    guesses = np.array(guesses, float)
    theta0 = np.array([float(np.mean(guesses[m, names.index(n)])) for n, m in slots])
    limits = fc.parse_bounds(p.get('bounds'), names)
    lo_one, hi_one = limits if limits is not None else (np.full(len(names), -np.inf), np.full(len(names), np.inf))
    lo = np.array([lo_one[names.index(n)] for n, _ in slots])
    hi = np.array([hi_one[names.index(n)] for n, _ in slots])
    theta0 = np.clip(theta0, lo + 1e-12, hi - 1e-12)

    weighted = p.get('weights', 'auto') != 'none' and all(c['sigma'] is not None for c in data)
    partly = p.get('weights', 'auto') != 'none' and not weighted and any(c['sigma'] is not None for c in data)

    def residuals(theta):
        with np.errstate(all='ignore'):
            r = np.concatenate([(f(c['x'], *params_of(theta, i)) - c['y']) / (c['sigma'] if weighted else 1.0)
                                for i, c in enumerate(data)])
        return np.where(np.isfinite(r), r, 1e30)

    sol = optimize.least_squares(residuals, theta0, bounds=(lo, hi), x_scale='jac', max_nfev=20000 * len(theta0))
    if not sol.success:
        raise ValueError(ctx.tr(f'The fit did not converge: {sol.message}', f'Il fit non converge: {sol.message}'))
    n_total, k = sum(c['x'].size for c in data), len(sol.x)
    dof = max(1, n_total - k)
    s2 = float(np.sum(sol.fun ** 2)) / dof          # reduced χ² when weighted
    jac = np.asarray(sol.jac.todense() if hasattr(sol.jac, 'todense') else sol.jac)
    try:
        if pooled:      # one noise level (or one χ² scale) for all the data: the global-analysis assumption
            err = np.sqrt(np.clip(np.diag(np.linalg.pinv(jac.T @ jac) * s2), 0, None))
        else:           # independent curves: each its own residual variance, as a fit of that curve alone
            err, row = np.empty(k), 0
            for i, c in enumerate(data):
                cols = [index[(i, n)] for n in names if n not in fixed]
                rows = slice(row, row + c['x'].size)
                s2_i = float(np.sum(sol.fun[rows] ** 2)) / max(1, c['x'].size - len(cols))
                block = jac[rows][:, cols]
                err[cols] = np.sqrt(np.clip(np.diag(np.linalg.pinv(block.T @ block) * s2_i), 0, None))
                row += c['x'].size
    except np.linalg.LinAlgError:
        err = np.full(k, np.nan)

    r = ctx.result()
    r.text(equation)
    shared_slots = [(j, n, m) for j, (n, m) in enumerate(slots) if len(m) > 1]
    r.text(ctx.tr(f'{n_curves} curves, {n_total} points, {k} fitted numbers.',
                  f'{n_curves} curve, {n_total} punti, {k} numeri adattati.'))
    if not shared_slots:
        r.text(ctx.tr('No shared parameter: each curve fitted on its own.',
                      'Nessun parametro condiviso: ogni curva adattata da sola.'))
    if fixed:
        r.text(ctx.tr('Fixed: ', 'Fissi: ') + ', '.join(f'{fc.SYMBOLS.get(n, n)} = {v:g}' for n, v in fixed.items()))
    if weighted:
        r.text(ctx.tr('Weighted by the Y errors (1/σ²); χ²_red = ', 'Pesato con gli errori Y (1/σ²); χ²_red = ')
               + f'{s2:.3g}')
    elif partly:
        r.text(ctx.tr('Not weighted: only some curves have a Y error column.',
                      'Non pesato: solo alcune curve hanno una colonna di errore Y.'))
    note_lines, keyed = [], set()
    for j, n, m in shared_slots:
        who = curve_list(m, n_curves)
        label = (f'{fc.SYMBOLS.get(n, n)} ({ctx.tr("shared", "condiviso")})' if who is None
                 else f'{fc.SYMBOLS.get(n, n)} ({ctx.tr("curves", "curve")} {who})')
        key = n if n not in keyed else f'{n}_{j}'
        keyed.add(n)
        r.value(label, sol.x[j], err[j], key=key)
        note_lines.append(f'{fc.SYMBOLS.get(n, n)}{"" if who is None else f" ({who})"} = {fc.plus_minus(sol.x[j], err[j])}')
    report, overlay_ids = [], []
    for i, c in enumerate(data):
        vals = params_of(sol.x, i)
        fit_y = f(c['x'], *vals)
        ss_res = float(np.sum((c['y'] - fit_y) ** 2))
        ss_tot = float(np.sum((c['y'] - c['y'].mean()) ** 2))
        row = {'#': i + 1, ctx.tr('curve', 'curva'): c['label'], 'N': int(c['x'].size)}
        for n, v in zip(names, vals):
            row[n] = float(v)
            row[f'σ({n})'] = np.nan if n in fixed else float(err[index[(i, n)]])
        row['R²'] = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
        row['RMSE'] = float(np.sqrt(ss_res / c['x'].size))
        report.append(row)
        grid = np.linspace(c['x'].min(), c['x'].max(), 400)
        overlay_ids.append(r.overlay(pd.DataFrame({'x': grid, 'fit': f(grid, *vals)}), 'x', 'fit',
                                     label=ctx.tr('global fit', 'fit globale') + f' · {c["label"]}'))
    report = pd.DataFrame(report)
    r.table(ctx.tr('Fit report (one row per curve)', 'Riepilogo dei fit (una riga per curva)'), report)
    r.value(ctx.tr('curves', 'curve'), n_curves)
    r.value('RMSE', float(np.sqrt(np.sum((sol.fun * (np.concatenate([c['sigma'] for c in data]) if weighted else 1)) ** 2)
                                  / n_total)), key='rmse')
    r.value(ctx.tr('lowest R² of a curve', 'R² più basso di una curva'), float(report['R²'].min()), key='r2_min')
    if weighted:
        r.value('χ²_red', s2, key='chi2_red')
    if p['note'] and note_lines:
        r.overlays[overlay_ids[0]]['note'] = '\n'.join(
            note_lines + [ctx.tr(f'{n_curves} curves, global fit', f'{n_curves} curve, fit globale')])
    # The report as data: each parameter against the curve number (plot the trend, export it).
    own = [n for n in names if n not in fixed and all(len(m) == 1 for nn, m in slots if nn == n)]
    first = own[0] if own else next(n for n in names if n not in fixed)
    r.data(report, name=ctx.tr('global fit report', 'riepilogo fit globale'),
           plot={'kind': 'errorbar', 'x': '#', 'y': [first], 'yerr': f'σ({first})', 'style': {'marker': 'o'}})
    r.cite('Moré, J. J. The Levenberg–Marquardt algorithm: implementation and theory. In Numerical Analysis, '
           'Lecture Notes in Mathematics 630, 105–116 (1978). doi:10.1007/BFb0067700')
    return r
