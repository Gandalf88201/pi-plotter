"""ANOVA designs beyond one factor (statsmodels):

- two-way: two factors between subjects and their interaction, type II or III sums of squares, partial η², the mean
  of each cell, and the means drawn as an interaction plot;
- repeated measures: the same subjects measured under every condition of one (or two) within-subject factors — rows
  of a long table (subject, condition, value) or one column per condition with one row per subject; for one factor,
  Mauchly's test of sphericity with the Greenhouse–Geisser and Huynh–Feldt corrections;
- mixed model: fixed factors and a random intercept per subject (REML), for unbalanced designs or missing values;
  fixed effects with their tests, the variance between subjects and the intraclass correlation."""
import keyword

import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'anova_models',
    'order': 42,
    'name': {'en': 'ANOVA: two-way, repeated measures, mixed model', 'it': 'ANOVA: due vie, misure ripetute, modello misto'},
    'category': 'stats',
    'description': {'en': 'Two factors with interaction; the same subjects under several conditions (sphericity, '
                          'Greenhouse–Geisser); a linear mixed model with a random intercept per subject.',
                    'it': 'Due fattori con interazione; gli stessi soggetti in più condizioni (sfericità, '
                          'Greenhouse–Geisser); un modello lineare misto con intercetta casuale per soggetto.'},
    'requires': ['statsmodels', 'scipy'],
    'params': [
        {'id': 'design', 'type': 'choice', 'default': 'twoway', 'label': {'en': 'Design', 'it': 'Disegno'},
         'choices': [{'value': 'twoway', 'label': {'en': 'two-way (two factors, different subjects)', 'it': 'due vie (due fattori, soggetti diversi)'}},
                     {'value': 'rm', 'label': {'en': 'repeated measures (same subjects)', 'it': 'misure ripetute (stessi soggetti)'}},
                     {'value': 'mixed', 'label': {'en': 'mixed model (random intercept per subject)', 'it': 'modello misto (intercetta casuale per soggetto)'}}]},
        {'id': 'value', 'type': 'column', 'optional': True, 'default': 'y', 'label': {'en': 'Value', 'it': 'Valore'}},
        {'id': 'a', 'type': 'column', 'optional': True, 'default': 'x',
         'label': {'en': 'Factor A (for repeated measures: the condition)', 'it': 'Fattore A (per le misure ripetute: la condizione)'}},
        {'id': 'b', 'type': 'column', 'optional': True, 'default': 'hue',
         'label': {'en': 'Factor B (optional for repeated measures and mixed model)', 'it': 'Fattore B (facoltativo per misure ripetute e modello misto)'}},
        {'id': 'subject', 'type': 'column', 'optional': True, 'show_if': {'design': ['rm', 'mixed']},
         'label': {'en': 'Subject', 'it': 'Soggetto'}},
        {'id': 'columns', 'type': 'columns', 'optional': True, 'show_if': {'design': ['rm']},
         'label': {'en': 'or one column per condition (one row per subject)', 'it': 'oppure una colonna per condizione (una riga per soggetto)'}},
        {'id': 'typ', 'type': 'choice', 'default': '2', 'show_if': {'design': ['twoway']},
         'label': {'en': 'Sums of squares', 'it': 'Somme dei quadrati'},
         'choices': [{'value': '2', 'label': {'en': 'type II (no interaction assumed in the main effects)', 'it': 'tipo II (effetti principali senza interazione)'}},
                     {'value': '3', 'label': {'en': 'type III (as SPSS, Origin)', 'it': 'tipo III (come SPSS, Origin)'}}]},
        {'id': 'interaction', 'type': 'bool', 'default': True, 'show_if': {'design': ['twoway', 'mixed']},
         'label': {'en': 'Interaction A × B', 'it': 'Interazione A × B'}},
    ],
    'references': [
        'Seabold, S. & Perktold, J. statsmodels: Econometric and statistical modeling with Python. '
        'Proc. 9th Python in Science Conf. 92–96 (2010). doi:10.25080/Majora-92bf1922-011',
        'Maxwell, S. E., Delaney, H. D. & Kelley, K. Designing Experiments and Analyzing Data, 3rd ed. Routledge (2018).',
        'Mauchly, J. W. Significance test for sphericity of a normal n-variate distribution. Ann. Math. Stat. 11, '
        '204–209 (1940). doi:10.1214/aoms/1177731915',
        'Greenhouse, S. W. & Geisser, S. On methods in the analysis of profile data. Psychometrika 24, 95–112 (1959). '
        'doi:10.1007/BF02289823',
        'Huynh, H. & Feldt, L. S. Estimation of the Box correction for degrees of freedom from sample data in randomized '
        'block and split-plot designs. J. Educ. Stat. 1, 69–82 (1976). doi:10.3102/10769986001001069',
        'Laird, N. M. & Ware, J. H. Random-effects models for longitudinal data. Biometrics 38, 963–974 (1982). '
        'doi:10.2307/2529876',
    ],
}


def term(name):
    return name if name.isidentifier() and not keyword.iskeyword(name) else 'Q("{}")'.format(name.replace('"', '\\"'))


def helmert(k):
    """k × (k − 1) orthonormal contrasts (Helmert, normalised)."""
    M = np.zeros((k, k - 1))
    for j in range(k - 1):
        M[:j + 1, j] = 1.0
        M[j + 1, j] = -(j + 1)
        M[:, j] /= np.linalg.norm(M[:, j])
    return M


def contrast_test(Z):
    """The repeated-measures F test of one effect from its orthonormal contrasts Z (subjects × p): F, its degrees of
    freedom, partial η², Mauchly's W with its χ² test, and the Greenhouse–Geisser and Huynh–Feldt ε (Maxwell,
    Delaney & Kelley, ch. 11–12). The same F as the univariate sums of squares."""
    from scipy import stats
    n, p = Z.shape
    m = Z.mean(0)
    D = Z - m
    ss_eff = n * float(m @ m)
    ss_err = float(np.sum(D * D))
    F = (ss_eff / p) / (ss_err / (p * (n - 1))) if ss_err > 0 else float('inf')
    T = D.T @ D / (n - 1)
    gg = float(np.trace(T) ** 2 / (p * np.trace(T @ T))) if np.trace(T) > 0 else 1.0
    hf = float(min(1.0, (n * p * gg - 2) / (p * (n - 1 - p * gg)))) if n - 1 - p * gg > 0 else 1.0
    if p > 1 and np.trace(T) > 0:
        W = float(np.linalg.det(T) / (np.trace(T) / p) ** p)
        f = 1 - (2 * p * p + p + 2) / (6 * p * (n - 1))
        chi2 = float(-(n - 1) * f * np.log(W)) if W > 0 else float('inf')
        dfw = p * (p + 1) // 2 - 1
        pw = float(stats.chi2.sf(chi2, dfw))
    else:
        W, chi2, dfw, pw = 1.0, 0.0, 0, 1.0
    d1, d2 = p, p * (n - 1)
    return {'F': F, 'df': d1, 'df_err': d2, 'p': float(stats.f.sf(F, d1, d2)),
            'p_gg': float(stats.f.sf(F, d1 * gg, d2 * gg)), 'p_hf': float(stats.f.sf(F, d1 * hf, d2 * hf)),
            'eta2': ss_eff / (ss_eff + ss_err) if ss_eff + ss_err > 0 else float('nan'),
            'ss': ss_eff, 'ss_err': ss_err, 'W': W, 'chi2': chi2, 'df_w': dfw, 'p_w': pw, 'gg': gg, 'hf': hf}


def sphericity(wide):
    """Mauchly's test and the ε of a subjects × conditions matrix (one within-subject factor)."""
    return contrast_test(np.asarray(wide, float) @ helmert(np.asarray(wide).shape[1]))


def _numbers(df, col, ctx):
    v = pd.to_numeric(df[col], errors='coerce')
    if v.notna().sum() < 3:
        raise ValueError(ctx.tr(f'“{col}” has too few numbers.', f'«{col}» ha troppo pochi numeri.'))
    return v


def two_way(df, p, ctx, r):
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    y, a, b = p['value'], p['a'], p['b']
    if not (y and a and b):
        raise ValueError(ctx.tr('Choose the value and the two factors A and B.', 'Scegli il valore e i due fattori A e B.'))
    data = pd.DataFrame({'y': _numbers(df, y, ctx), 'A': df[a].astype(str), 'B': df[b].astype(str)}).dropna()
    typ = int(p.get('typ') or 2)
    code = (lambda f: f'C({f}, Sum)') if typ == 3 else (lambda f: f'C({f})')
    rhs = f'{code("A")} * {code("B")}' if p['interaction'] else f'{code("A")} + {code("B")}'
    fit = smf.ols(f'y ~ {rhs}', data=data).fit()
    table = sm.stats.anova_lm(fit, typ=typ)
    table = table.drop(index=[i for i in table.index if i == 'Intercept'])
    names = {code('A'): a, code('B'): b, f'{code("A")}:{code("B")}': f'{a} × {b}', 'Residual': ctx.tr('residual', 'residuo')}
    table.index = [names.get(i, i) for i in table.index]
    ss_res = float(table.loc[names['Residual'], 'sum_sq'])
    table['partial η²'] = [s / (s + ss_res) if i != names['Residual'] else np.nan
                           for i, s in zip(table.index, table['sum_sq'])]
    table = table.rename(columns={'sum_sq': ctx.tr('sum of squares', 'somma dei quadrati'), 'df': 'df', 'PR(>F)': 'p'})
    r.text(ctx.tr(f'Two-way ANOVA, type {"II" if typ == 2 else "III"} sums of squares; N = {len(data)}.',
                  f'ANOVA a due vie, somme dei quadrati di tipo {"II" if typ == 2 else "III"}; N = {len(data)}.'))
    r.table(ctx.tr('ANOVA', 'ANOVA'), table, index=True)
    for key, name in (('A', a), ('B', b), ('AB', f'{a} × {b}')):
        if name in table.index:
            r.value(f'p ({name})', float(table.loc[name, 'p']), key=f'p_{key}')
            r.value(f'F ({name})', float(table.loc[name, 'F']), key=f'F_{key}')
    cells = data.groupby(['A', 'B'])['y'].agg(['mean', 'std', 'count']).reset_index()
    cells['SE'] = cells['std'] / np.sqrt(cells['count'])
    if (cells['count'] < 2).any():
        r.text(ctx.tr('Some cells have a single value: their spread is unknown.',
                      'Alcune celle hanno un solo valore: la loro dispersione è ignota.'))
    shown = cells.rename(columns={'A': a, 'B': b, 'mean': ctx.tr('mean', 'media'), 'std': ctx.tr('SD', 'DS'), 'count': 'n'})
    r.table(ctx.tr('Mean of each cell', 'Media di ogni cella'), shown)
    # The mean of each cell as grouped bars: A along x, one colour per level of B.
    plot = pd.DataFrame({a: cells['A'], b: cells['B'], 'mean': cells['mean'], 'SE': cells['SE']})
    r.data(plot, name=ctx.tr('cell means', 'medie delle celle'), plot={'kind': 'bar', 'x': a, 'y': ['mean'], 'hue': b})


def _long_rm(df, p, ctx):
    """(data with columns S, A[, B], y; names) for repeated measures, from a long table or from one column per
    condition."""
    cols = [c for c in (p.get('columns') or []) if c in df.columns]
    if len(cols) >= 2:
        wide = df[cols].apply(pd.to_numeric, errors='coerce')
        wide.insert(0, 'S', [f'#{i + 1}' for i in range(len(wide))])
        data = wide.melt(id_vars='S', var_name='A', value_name='y')
        return data, {'A': ctx.tr('condition', 'condizione'), 'B': None}
    y, a, s, b = p['value'], p['a'], p['subject'], p['b']
    if not (y and a and s):
        raise ValueError(ctx.tr('Choose the value, the condition and the subject (or one column per condition).',
                                'Scegli il valore, la condizione e il soggetto (oppure una colonna per condizione).'))
    data = pd.DataFrame({'S': df[s].astype(str), 'A': df[a].astype(str), 'y': _numbers(df, y, ctx)})
    if b and b not in (a, s):
        data['B'] = df[b].astype(str)
    return data, {'A': a, 'B': b if 'B' in data else None}


def repeated(df, p, ctx, r):
    data, names = _long_rm(df, p, ctx)
    within = ['A'] + (['B'] if names['B'] else [])
    data = data.dropna(subset=['y'])
    # Every subject needs a value in every condition (the others are left out); repeated values are averaged.
    cells = data.groupby(within).ngroups
    full = data.drop_duplicates(['S'] + within).groupby('S').size() == cells
    dropped = int((~full).sum())
    data = data[data['S'].isin(full.index[full])]
    n = data['S'].nunique()
    if n < 3:
        raise ValueError(ctx.tr('Fewer than three subjects have a value in every condition.',
                                'Meno di tre soggetti hanno un valore in ogni condizione.'))
    wide = data.pivot_table(index='S', columns=within, values='y', aggfunc='mean').sort_index(axis=1)
    la = list(dict.fromkeys(wide.columns.get_level_values(0) if names['B'] else wide.columns))
    a = len(la)
    b = wide.shape[1] // a
    if a < 2 or (names['B'] and b < 2):
        raise ValueError(ctx.tr('Each within-subject factor needs at least two conditions.',
                                'Ogni fattore entro i soggetti richiede almeno due condizioni.'))
    Y = wide.to_numpy(float)                                       # subjects × (a·b), B varying fastest
    one = lambda k: np.ones((k, 1)) / np.sqrt(k)                   # noqa: E731
    effects = [(names['A'], 'A', np.kron(helmert(a), one(b)) if names['B'] else helmert(a))]
    if names['B']:
        effects += [(names['B'], 'B', np.kron(one(a), helmert(b))),
                    (f'{names["A"]} × {names["B"]}', 'AB', np.kron(helmert(a), helmert(b)))]
    rows = {}
    for label, key, M in effects:
        t = contrast_test(Y @ M)
        rows[label] = t
        r.value(f'F ({label})' if names['B'] else 'F', t['F'], key=f'F_{key}' if names['B'] else 'F')
        r.value(f'p ({label})' if names['B'] else 'p', t['p'], key=f'p_{key}' if names['B'] else 'p')
        r.value(f'p, Greenhouse–Geisser ({label})' if names['B'] else 'p, Greenhouse–Geisser', t['p_gg'],
                key=f'p_gg_{key}' if names['B'] else 'p_gg')
    table = pd.DataFrame({ctx.tr('sum of squares', 'somma dei quadrati'): [t['ss'] for t in rows.values()],
                          'df': [t['df'] for t in rows.values()], ctx.tr('df error', 'df errore'): [t['df_err'] for t in rows.values()],
                          'F': [t['F'] for t in rows.values()], 'p': [t['p'] for t in rows.values()],
                          'ε GG': [t['gg'] for t in rows.values()], 'p (GG)': [t['p_gg'] for t in rows.values()],
                          'ε HF': [t['hf'] for t in rows.values()], 'p (HF)': [t['p_hf'] for t in rows.values()],
                          'partial η²': [t['eta2'] for t in rows.values()]}, index=list(rows))
    r.text(ctx.tr(f'Repeated-measures ANOVA: {n} subjects, each in every condition.',
                  f'ANOVA per misure ripetute: {n} soggetti, ciascuno in ogni condizione.'))
    if dropped:
        r.text(ctx.tr(f'{dropped} subjects without a value in every condition are left out.',
                      f'{dropped} soggetti senza un valore in ogni condizione sono esclusi.'))
    r.table(ctx.tr('ANOVA', 'ANOVA'), table, index=True)
    sph = pd.DataFrame({"Mauchly W": [t['W'] for t in rows.values()], 'χ²': [t['chi2'] for t in rows.values()],
                        'df': [t['df_w'] for t in rows.values()], 'p': [t['p_w'] for t in rows.values()]},
                       index=list(rows))
    sph = sph[[t['df'] > 1 for t in rows.values()]]
    if len(sph):
        r.table(ctx.tr("Sphericity (Mauchly's test)", 'Sfericità (test di Mauchly)'), sph, index=True)
        first = next(t for t in rows.values() if t['df'] > 1)
        if not names['B']:
            r.value(ctx.tr("Mauchly's W", 'W di Mauchly'), first['W'], key='mauchly_w')
            r.value(ctx.tr("Mauchly's test, p", 'test di Mauchly, p'), first['p_w'], key='mauchly_p')
            r.value('ε (Greenhouse–Geisser)', first['gg'], key='eps_gg')
            r.value('ε (Huynh–Feldt)', first['hf'], key='eps_hf')
        doubtful = (sph['p'] < 0.05).any()
        r.text(ctx.tr('Sphericity is doubtful (Mauchly p < 0.05): read the Greenhouse–Geisser p.' if doubtful
                      else 'Sphericity holds (Mauchly p ≥ 0.05): the plain p can be read.',
                      'La sfericità è dubbia (Mauchly p < 0,05): leggi il p di Greenhouse–Geisser.' if doubtful
                      else 'La sfericità regge (Mauchly p ≥ 0,05): si può leggere il p semplice.'))
    means = data.groupby(within)['y'].agg(['mean', 'std', 'count']).reset_index()
    means['SE'] = means['std'] / np.sqrt(means['count'])
    plot = pd.DataFrame({names['A']: means['A'], 'mean': means['mean'], 'SE': means['SE']})
    spec = {'kind': 'bar', 'x': names['A'], 'y': ['mean'], 'yerr': 'SE'}
    if names['B']:
        plot[names['B']] = means['B']
        spec = {'kind': 'bar', 'x': names['A'], 'y': ['mean'], 'hue': names['B']}
    r.table(ctx.tr('Mean of each condition', 'Media di ogni condizione'), plot)
    r.data(plot, name=ctx.tr('condition means', 'medie delle condizioni'), plot=spec)


def mixed(df, p, ctx, r):
    import statsmodels.formula.api as smf
    y, a, b, s = p['value'], p['a'], p['b'], p['subject']
    if not (y and a and s):
        raise ValueError(ctx.tr('Choose the value, factor A and the subject.', 'Scegli il valore, il fattore A e il soggetto.'))
    data = pd.DataFrame({'y': _numbers(df, y, ctx), 'S': df[s].astype(str)})
    numeric = lambda c: pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 10    # noqa: E731
    data['A'] = pd.to_numeric(df[a], errors='coerce') if numeric(a) else df[a].astype(str)
    fixed = ['A' if numeric(a) else 'C(A)']
    if b and b not in (a, s):
        data['B'] = pd.to_numeric(df[b], errors='coerce') if numeric(b) else df[b].astype(str)
        fixed.append('B' if numeric(b) else 'C(B)')
    data = data.dropna()
    rhs = ' * '.join(fixed) if p['interaction'] and len(fixed) == 2 else ' + '.join(fixed)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')                       # convergence notes: judged below from the fit itself
        fit = smf.mixedlm(f'y ~ {rhs}', data, groups=data['S']).fit(reml=True)
    def rename(t):                       # 'C(A)[T.x]:B' → 'factor[x] × other', in the user's names
        out = []
        for part in t.split(':'):
            part = a if part == 'A' else (b if part == 'B' else part)
            out.append(part.replace('C(A)', a).replace('C(B)', b or '').replace('[T.', '['))
        return ' × '.join(out)
    fe = fit.fe_params.index
    ci = fit.conf_int().loc[fe]
    coef = pd.DataFrame({ctx.tr('estimate', 'stima'): fit.fe_params, ctx.tr('std. error', 'errore std.'): fit.bse[fe],
                         'z': fit.tvalues[fe], 'p': fit.pvalues[fe], 'CI 95% low': ci[0], 'CI 95% high': ci[1]})
    coef.index = [rename(i) for i in coef.index]
    var_u = float(fit.cov_re.iloc[0, 0])
    var_e = float(fit.scale)
    n, groups = int(fit.nobs), data['S'].nunique()
    r.text(ctx.tr(f'Linear mixed model (REML): y ~ {rhs.replace("C(A)", a).replace("C(B)", b or "")} + '
                  f'(1 | {s}); {n} values from {groups} subjects.',
                  f'Modello lineare misto (REML): y ~ {rhs.replace("C(A)", a).replace("C(B)", b or "")} + '
                  f'(1 | {s}); {n} valori da {groups} soggetti.'))
    r.table(ctx.tr('Fixed effects', 'Effetti fissi'), coef, index=True)
    # One Wald χ² test per factor: all its coefficients zero together (b' V⁻¹ b, as many df as coefficients).
    from scipy import stats
    V = fit.cov_params().loc[fe, fe]
    terms = {}
    for name in fe:
        if name == 'Intercept':
            continue
        key = ':'.join(part.split('[')[0] for part in name.split(':'))
        terms.setdefault(key, []).append(name)
    rows = []
    for key, names in terms.items():
        bvec = fit.fe_params[names].to_numpy()
        chi2 = float(bvec @ np.linalg.solve(V.loc[names, names].to_numpy(), bvec))
        rows.append((rename(key), chi2, len(names), float(stats.chi2.sf(chi2, len(names)))))
    tests = pd.DataFrame([r_[1:] for r_ in rows], index=[r_[0] for r_ in rows], columns=['χ²', 'df', 'p'])
    r.table(ctx.tr('Tests of the factors (Wald)', 'Test dei fattori (Wald)'), tests, index=True)
    for (label, _, _, pv), key in zip(rows, ('A', 'B', 'AB')):
        r.value(f'p ({label})', pv, key=f'p_{key}')
    r.value(ctx.tr(f'variance between subjects ({s})', f'varianza tra i soggetti ({s})'), var_u, key='var_subject')
    r.value(ctx.tr('residual variance', 'varianza residua'), var_e, key='var_residual')
    r.value(ctx.tr('intraclass correlation (ICC)', 'correlazione intraclasse (ICC)'),
            var_u / (var_u + var_e) if var_u + var_e > 0 else float('nan'), key='icc')
    r.value(ctx.tr('log-likelihood (REML)', 'log-verosimiglianza (REML)'), float(fit.llf))
    if not fit.converged:
        r.text(ctx.tr('The fit did not fully converge: read the numbers with care.',
                      'Il fit non è arrivato a convergenza piena: leggi i numeri con cautela.'))
    if var_u < 1e-10 * max(var_e, 1e-300):
        r.text(ctx.tr('The variance between subjects is about zero: the subjects do not differ beyond the noise.',
                      'La varianza tra i soggetti è circa zero: i soggetti non differiscono oltre il rumore.'))
    out = pd.DataFrame({ctx.tr('fitted', 'valori stimati'): fit.fittedvalues, ctx.tr('residual', 'residuo'): fit.resid})
    cols = list(out.columns)
    r.data(out, name=ctx.tr('mixed model', 'modello misto'), plot={'kind': 'scatter', 'x': cols[0], 'y': [cols[1]]})


def run(df, p, ctx):
    r = ctx.result()
    {'twoway': two_way, 'rm': repeated, 'mixed': mixed}[p['design']](df, p, ctx, r)
    return r
