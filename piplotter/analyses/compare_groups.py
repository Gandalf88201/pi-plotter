"""Compare groups or columns: t-tests, Mann–Whitney, Wilcoxon, ANOVA, Kruskal–Wallis, Friedman, effect sizes; post-hoc
Tukey HSD (ANOVA), Games–Howell (unequal variances), Dunn (Kruskal–Wallis), Wilcoxon (Friedman), Holm-corrected."""
import itertools

import numpy as np
import pandas as pd

TESTS = {
    'auto': {'en': 'Automatic (by normality and number of groups)', 'it': 'Automatico (normalità e numero di gruppi)'},
    'welch': {'en': 'Welch t-test (2 groups)', 'it': 't-test di Welch (2 gruppi)'},
    'student': {'en': 'Student t-test, equal variances (2 groups)', 'it': 't-test di Student, varianze uguali (2 gruppi)'},
    'paired': {'en': 'Paired t-test (2 columns)', 'it': 't-test appaiato (2 colonne)'},
    'mannwhitney': {'en': 'Mann–Whitney U (2 groups, non-parametric)', 'it': 'Mann–Whitney U (2 gruppi, non parametrico)'},
    'wilcoxon': {'en': 'Wilcoxon signed-rank (2 paired columns)', 'it': 'Wilcoxon dei ranghi con segno (2 colonne appaiate)'},
    'anova': {'en': 'One-way ANOVA + Tukey HSD', 'it': 'ANOVA a una via + Tukey HSD'},
    'welch_anova': {'en': 'Alexander–Govern (ANOVA, unequal variances)', 'it': 'Alexander–Govern (ANOVA, varianze diverse)'},
    'kruskal': {'en': 'Kruskal–Wallis (non-parametric ANOVA)', 'it': 'Kruskal–Wallis (ANOVA non parametrica)'},
    'friedman': {'en': 'Friedman (3 or more paired columns, repeated measures)',
                 'it': 'Friedman (3 o più colonne appaiate, misure ripetute)'},
}

PLUGIN = {
    'id': 'compare_groups',
    'order': 30,
    'name': {'en': 'Compare groups (t-test, ANOVA…)', 'it': 'Confronto tra gruppi (t-test, ANOVA…)'},
    'category': 'stats',
    'description': {'en': 'Hypothesis tests between groups of one column, or between columns; with post-hoc tests and effect sizes.',
                    'it': 'Test d’ipotesi tra gruppi di una colonna o tra colonne; con test post-hoc ed effect size.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'value', 'type': 'column', 'optional': True, 'default': 'y',
         'label': {'en': 'Values (with a group column)', 'it': 'Valori (con colonna dei gruppi)'}},
        {'id': 'group', 'type': 'column', 'optional': True, 'default': 'x',
         'label': {'en': 'Group column', 'it': 'Colonna dei gruppi'}},
        {'id': 'columns', 'type': 'columns', 'optional': True,
         'label': {'en': '…or compare these columns', 'it': '…oppure confronta queste colonne'}},
        {'id': 'test', 'type': 'choice', 'default': 'auto', 'label': {'en': 'Test', 'it': 'Test'},
         'choices': [{'value': k, 'label': v} for k, v in TESTS.items()]},
        {'id': 'alpha', 'type': 'float', 'default': 0.05, 'min': 0.001, 'max': 0.5,
         'label': {'en': 'Significance level α', 'it': 'Livello di significatività α'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
        'Welch, B. L. The generalization of “Student’s” problem when several different population variances are '
        'involved. Biometrika 34, 28–35 (1947). doi:10.1093/biomet/34.1-2.28',
        'Mann, H. B. & Whitney, D. R. On a test of whether one of two random variables is stochastically larger '
        'than the other. Ann. Math. Stat. 18, 50–60 (1947). doi:10.1214/aoms/1177730491',
        'Kruskal, W. H. & Wallis, W. A. Use of ranks in one-criterion variance analysis. J. Am. Stat. Assoc. 47, '
        '583–621 (1952). doi:10.1080/01621459.1952.10483441',
        'Tukey, J. W. Comparing individual means in the analysis of variance. Biometrics 5, 99–114 (1949). '
        'doi:10.2307/3001913',
        'Cohen, J. Statistical Power Analysis for the Behavioral Sciences, 2nd ed. Lawrence Erlbaum (1988).',
        'Games, P. A. & Howell, J. F. Pairwise multiple comparison procedures with unequal n’s and/or variances. '
        'J. Educ. Stat. 1, 113–125 (1976). doi:10.3102/10769986001002113',
        'Dunn, O. J. Multiple comparisons using rank sums. Technometrics 6, 241–252 (1964). '
        'doi:10.1080/00401706.1964.10490181',
        'Holm, S. A simple sequentially rejective multiple test procedure. Scand. J. Stat. 6, 65–70 (1979).',
        'Friedman, M. The use of ranks to avoid the assumption of normality implicit in the analysis of variance. '
        'J. Am. Stat. Assoc. 32, 675–701 (1937). doi:10.1080/01621459.1937.10503522',
    ],
}


def cohens_d(a, b):
    na, nb = len(a), len(b)
    sp = np.sqrt(((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1)) / (na + nb - 2))
    return (np.mean(a) - np.mean(b)) / sp if sp > 0 else np.nan


def holm(pvalues):
    """Holm-adjusted p-values (step-down, monotone), in the order given."""
    p = np.asarray(pvalues, float)
    m = p.size
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj


def games_howell(samples, names, alpha, tr):
    """Pairwise Games–Howell: Welch t per pair, p and CI from the studentized range with Welch's df."""
    from scipy import stats
    k = len(samples)
    rows = []
    for i, j in itertools.combinations(range(k), 2):
        a, b = samples[i], samples[j]
        va, vb = a.var(ddof=1) / a.size, b.var(ddof=1) / b.size
        se = np.sqrt(va + vb)
        dof = (va + vb) ** 2 / (va ** 2 / (a.size - 1) + vb ** 2 / (b.size - 1))
        diff = a.mean() - b.mean()
        q = abs(diff) / se * np.sqrt(2)
        half = stats.studentized_range.ppf(1 - alpha, k, dof) / np.sqrt(2) * se
        rows.append({'A': names[i], 'B': names[j], tr('difference', 'differenza'): diff,
                     'CI low': diff - half, 'CI high': diff + half, 'p (Games–Howell)': stats.studentized_range.sf(q, k, dof)})
    return rows


def dunn(samples, names, tr):
    """Dunn's test on the ranks of all the values (ties corrected), Holm-adjusted."""
    from scipy import stats
    allv = np.concatenate(samples)
    ranks = stats.rankdata(allv)
    n = allv.size
    _, counts = np.unique(allv, return_counts=True)
    ties = np.sum(counts ** 3 - counts) / (12 * (n - 1))
    bounds = np.cumsum([0] + [s.size for s in samples])
    means = [ranks[bounds[i]:bounds[i + 1]].mean() for i in range(len(samples))]
    rows = []
    for i, j in itertools.combinations(range(len(samples)), 2):
        se = np.sqrt((n * (n + 1) / 12 - ties) * (1 / samples[i].size + 1 / samples[j].size))
        z = (means[i] - means[j]) / se
        rows.append({'A': names[i], 'B': names[j], tr('mean rank A', 'rango medio A'): means[i],
                     tr('mean rank B', 'rango medio B'): means[j], 'z': z, 'p': 2 * stats.norm.sf(abs(z))})
    for row, adj in zip(rows, holm([r['p'] for r in rows])):
        row['p (Holm)'] = adj
    return rows


def run(df, p, ctx):
    from scipy import stats

    paired_possible = False
    if p['columns'] and len(p['columns']) >= 2:
        names = list(p['columns'])
        if p['test'] in ('paired', 'wilcoxon', 'friedman'):
            block = df[names].apply(lambda s: ctx.numeric(df, s.name, dropna=False)).dropna()
            samples = [block[c].to_numpy(float) for c in names]
        else:
            samples = [ctx.numeric(df, c).to_numpy(float) for c in names]
        paired_possible = True
    elif p['value'] and p['group']:
        v = ctx.numeric(df, p['value'], dropna=False)
        groups = [(str(g), sub.dropna().to_numpy(float)) for g, sub in v.groupby(df[p['group']], sort=True)]
        groups = [(g, s) for g, s in groups if s.size]
        names, samples = [g for g, _ in groups], [s for _, s in groups]
    else:
        raise ValueError(ctx.tr('Choose a value column and a group column, or at least two columns.',
                                'Scegli una colonna di valori e una dei gruppi, oppure almeno due colonne.'))
    if len(samples) < 2 or any(s.size < 2 for s in samples):
        raise ValueError(ctx.tr('Each group needs at least two values.', 'Ogni gruppo deve avere almeno due valori.'))

    k = len(samples)
    test = p['test']
    normal = all(stats.shapiro(s)[1] >= p['alpha'] for s in samples if 3 <= s.size <= 5000)
    if test == 'auto':
        test = ('welch' if normal else 'mannwhitney') if k == 2 else ('anova' if normal else 'kruskal')
    if test in ('welch', 'student', 'paired', 'mannwhitney', 'wilcoxon') and k != 2:
        raise ValueError(ctx.tr('This test compares exactly two groups.', 'Questo test confronta esattamente due gruppi.'))
    if test == 'friedman' and k < 3:
        raise ValueError(ctx.tr('Friedman compares three or more paired columns (two: paired t-test or Wilcoxon).',
                                'Friedman confronta tre o più colonne appaiate (due: t-test appaiato o Wilcoxon).'))
    if test in ('paired', 'wilcoxon', 'friedman') and (not paired_possible or len({s.size for s in samples}) != 1):
        raise ValueError(ctx.tr('Paired tests need two columns with values in the same rows.',
                                'I test appaiati richiedono due colonne con valori nelle stesse righe.'))

    a = p['alpha']
    r = ctx.result()
    summary = pd.DataFrame({ctx.tr('group', 'gruppo'): names, 'N': [s.size for s in samples],
                            ctx.tr('mean', 'media'): [s.mean() for s in samples],
                            ctx.tr('SD', 'DS'): [s.std(ddof=1) for s in samples],
                            ctx.tr('median', 'mediana'): [np.median(s) for s in samples]})
    r.table(ctx.tr('Groups', 'Gruppi'), summary)
    levene = stats.levene(*samples)
    r.value(ctx.tr('normality (Shapiro–Wilk, all groups)', 'normalità (Shapiro–Wilk, tutti i gruppi)'),
            ctx.tr('yes', 'sì') if normal else 'no')
    r.value(ctx.tr('Levene test for equal variances, p', 'test di Levene varianze uguali, p'), levene.pvalue)

    if test in ('welch', 'student'):
        res = stats.ttest_ind(samples[0], samples[1], equal_var=test == 'student')
        stat_name, effect = 't', ('Cohen d', cohens_d(*samples))
    elif test == 'paired':
        res = stats.ttest_rel(samples[0], samples[1])
        diff = samples[0] - samples[1]
        stat_name, effect = 't', ('Cohen d_z', diff.mean() / diff.std(ddof=1))
    elif test == 'mannwhitney':
        res = stats.mannwhitneyu(samples[0], samples[1], alternative='two-sided')
        n1, n2 = samples[0].size, samples[1].size
        stat_name, effect = 'U', ('rank-biserial r', 1 - 2 * res.statistic / (n1 * n2))
    elif test == 'wilcoxon':
        res = stats.wilcoxon(samples[0], samples[1])
        stat_name, effect = 'W', None
    elif test == 'anova':
        res = stats.f_oneway(*samples)
        allv = np.concatenate(samples)
        ss_b = sum(s.size * (s.mean() - allv.mean()) ** 2 for s in samples)
        ss_t = np.sum((allv - allv.mean()) ** 2)
        stat_name, effect = 'F', ('η²', ss_b / ss_t if ss_t else np.nan)
    elif test == 'welch_anova':
        res = stats.alexandergovern(*samples)
        stat_name, effect = 'A', None
    elif test == 'friedman':
        res = stats.friedmanchisquare(*samples)
        stat_name, effect = 'χ²', ("Kendall's W", res.statistic / (samples[0].size * (k - 1)))
    else:
        res = stats.kruskal(*samples)
        allv = np.concatenate(samples)
        stat_name, effect = 'H', ('ε²', (res.statistic - k + 1) / (allv.size - k))
    r.value(ctx.tr('test', 'test'), TESTS[test][ctx.lang], key='test')
    r.value(stat_name, res.statistic, key='statistic')
    r.value('p', res.pvalue, key='p')
    if effect:
        r.value(effect[0], effect[1], key='effect')
        r.keep('effect_name', effect[0])
    r.keep('groups_normal', normal)
    r.keep('significant', bool(res.pvalue < a))
    r.keep('k', k)
    r.value(ctx.tr('conclusion', 'conclusione'),
            ctx.tr(f'significant difference (p < {a:g})', f'differenza significativa (p < {a:g})') if res.pvalue < a
            else ctx.tr(f'no significant difference (p ≥ {a:g})', f'nessuna differenza significativa (p ≥ {a:g})'))

    if k > 2:
        rows = []
        if test == 'welch_anova':                 # unequal variances: Tukey's pooled variance would be wrong
            rows, title = games_howell(samples, names, a, ctx.tr), 'Games–Howell'
        elif test == 'friedman':
            pairs = list(itertools.combinations(range(k), 2))
            for i, j in pairs:
                w = stats.wilcoxon(samples[i], samples[j])
                rows.append({'A': names[i], 'B': names[j], 'W': w.statistic, 'p': w.pvalue})
            for row, adj in zip(rows, holm([row['p'] for row in rows])):
                row['p (Holm)'] = adj
            title = ctx.tr('Pairwise Wilcoxon signed-rank (Holm)', 'Wilcoxon a coppie (Holm)')
        elif test == 'anova':
            tk = stats.tukey_hsd(*samples)
            ci = tk.confidence_interval(1 - a)
            for i, j in itertools.combinations(range(k), 2):
                rows.append({'A': names[i], 'B': names[j], ctx.tr('difference', 'differenza'): tk.statistic[i, j],
                             'CI low': ci.low[i, j], 'CI high': ci.high[i, j], 'p (Tukey)': tk.pvalue[i, j]})
            title = 'Tukey HSD'
        else:
            rows, title = dunn(samples, names, ctx.tr), ctx.tr("Dunn's test (Holm)", 'Test di Dunn (Holm)')
        r.table(title, rows)

    long = pd.DataFrame({ctx.tr('group', 'gruppo'): np.concatenate([[n] * s.size for n, s in zip(names, samples)]),
                         ctx.tr('value', 'valore'): np.concatenate(samples)})
    r.data(long, name=ctx.tr('groups', 'gruppi'), plot={'kind': 'box', 'x': long.columns[0], 'y': [long.columns[1]]})
    return r
