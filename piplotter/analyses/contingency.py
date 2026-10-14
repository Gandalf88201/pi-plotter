"""Contingency tables: is one category related to another? χ² test of independence (Pearson, with Yates' correction
for 2×2), Fisher's exact test and odds ratio for 2×2, Cramér's V, expected counts and standardised residuals. The
table comes from two category columns (one row per observation) or from columns of counts already tallied."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'contingency',
    'order': 34,
    'name': {'en': 'Contingency table (χ², Fisher)', 'it': 'Tabella di contingenza (χ², Fisher)'},
    'category': 'stats',
    'description': {'en': 'Are two categories related? χ² of independence, Fisher’s exact test and odds ratio (2×2), '
                          'Cramér’s V, residuals.',
                    'it': 'Due categorie sono legate? χ² di indipendenza, test esatto di Fisher e odds ratio (2×2), '
                          'V di Cramér, residui.'},
    'suits': [],          # not suggested from the figure alone
    'requires': ['scipy'],
    'params': [
        {'id': 'source', 'type': 'choice', 'default': 'columns', 'label': {'en': 'Data', 'it': 'Dati'},
         'choices': [{'value': 'columns', 'label': {'en': 'two category columns (one row per case)', 'it': 'due colonne di categorie (una riga per caso)'}},
                     {'value': 'counts', 'label': {'en': 'counts already tallied (one column per category)', 'it': 'conteggi già contati (una colonna per categoria)'}}]},
        {'id': 'row', 'type': 'column', 'default': 'x',
         'label': {'en': 'Rows: category (or labels of the rows of counts)', 'it': 'Righe: categoria (o etichette delle righe di conteggi)'}},
        {'id': 'col', 'type': 'column', 'optional': True, 'default': 'hue', 'show_if': {'source': ['columns']},
         'label': {'en': 'Columns: category', 'it': 'Colonne: categoria'}},
        {'id': 'counts', 'type': 'columns', 'optional': True, 'show_if': {'source': ['counts']},
         'label': {'en': 'Columns of counts', 'it': 'Colonne di conteggi'}},
        {'id': 'alpha', 'type': 'float', 'default': 0.05, 'min': 0.001, 'max': 0.5,
         'label': {'en': 'Significance level α', 'it': 'Livello di significatività α'}},
    ],
    'references': [
        'Pearson, K. On the criterion that a given system of deviations from the probable… Philos. Mag. 50, 157–175 '
        '(1900). doi:10.1080/14786440009463897',
        'Fisher, R. A. On the interpretation of χ² from contingency tables, and the calculation of P. J. R. Stat. Soc. '
        '85, 87–94 (1922). doi:10.2307/2340521',
        'Yates, F. Contingency tables involving small numbers and the χ² test. Suppl. J. R. Stat. Soc. 1, 217–235 '
        '(1934). doi:10.2307/2983604',
        'Cramér, H. Mathematical Methods of Statistics. Princeton University Press (1946).',
        'Agresti, A. Categorical Data Analysis, 3rd ed. Wiley (2013).',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def table_of(df, p, ctx):
    if p['source'] == 'counts':
        cols = list(p['counts'] or [])
        if len(cols) < 2:
            raise ValueError(ctx.tr('Choose at least two columns of counts.', 'Scegli almeno due colonne di conteggi.'))
        t = df[[p['row'], *cols]].dropna(subset=[p['row']])
        t = t.groupby(t[p['row']].astype(str), sort=False)[cols].sum()
        t = t.apply(pd.to_numeric, errors='coerce').fillna(0)
        if (t.to_numpy() < 0).any():
            raise ValueError(ctx.tr('Counts cannot be negative.', 'I conteggi non possono essere negativi.'))
        return t
    if not p.get('col') or p['col'] == p['row']:
        raise ValueError(ctx.tr('Choose a second category column.', 'Scegli una seconda colonna di categorie.'))
    sub = df[[p['row'], p['col']]].dropna().astype(str)
    return pd.crosstab(sub[p['row']], sub[p['col']])


def run(df, p, ctx):
    from scipy import stats
    obs = table_of(df, p, ctx)
    obs = obs.loc[obs.sum(axis=1) > 0, obs.sum(axis=0) > 0]
    if obs.shape[0] < 2 or obs.shape[1] < 2:
        raise ValueError(ctx.tr('The table needs at least two rows and two columns with counts.',
                                'La tabella richiede almeno due righe e due colonne con conteggi.'))
    if obs.shape[0] * obs.shape[1] > 2500:
        raise ValueError(ctx.tr('Too many categories for a contingency table (more than 2500 cells).',
                                'Troppe categorie per una tabella di contingenza (oltre 2500 celle).'))
    O = obs.to_numpy(float)
    n = O.sum()
    two = O.shape == (2, 2)
    chi2, pval, dof, E = stats.chi2_contingency(O, correction=two)
    small = float(np.mean(E < 5))
    v = np.sqrt(stats.chi2_contingency(O, correction=False)[0] / (n * (min(O.shape) - 1)))
    resid = (O - E) / np.sqrt(E * np.outer(1 - O.sum(1) / n, 1 - O.sum(0) / n))     # adjusted standardised residuals
    r = ctx.result()
    total = ctx.tr('total', 'totale')
    shown = obs.copy()
    shown[total] = shown.sum(axis=1)
    shown.loc[total] = shown.sum(axis=0)
    r.table(ctx.tr('Observed counts', 'Conteggi osservati'), shown.astype(int), index=True)
    r.table(ctx.tr('Expected counts (if independent)', 'Conteggi attesi (se indipendenti)'),
            pd.DataFrame(E, index=obs.index, columns=obs.columns).round(2), index=True)
    r.table(ctx.tr('Adjusted residuals (|r| > 2: a cell far from independence)',
                   'Residui standardizzati corretti (|r| > 2: cella lontana dall’indipendenza)'),
            pd.DataFrame(resid, index=obs.index, columns=obs.columns).round(2), index=True)
    r.value('N', int(n), key='n')
    r.value(ctx.tr('χ² (Yates)' if two else 'χ²', 'χ² (Yates)' if two else 'χ²'), chi2, key='chi2')
    r.value(ctx.tr('degrees of freedom', 'gradi di libertà'), int(dof))
    r.value('p (χ²)', pval, key='p')
    r.value("Cramér's V", v, key='cramer_v')
    p_main = pval
    if two:
        fisher = stats.fisher_exact(O)
        r.value(ctx.tr('p (Fisher exact)', 'p (Fisher esatto)'), fisher.pvalue, key='p_fisher')
        ratio = stats.contingency.odds_ratio(O.astype(int), kind='sample')      # (a·d)/(b·c), Woolf's interval
        ci = ratio.confidence_interval(1 - p['alpha'])
        r.value(ctx.tr('odds ratio', 'odds ratio'), ratio.statistic, key='odds_ratio')
        r.value(ctx.tr(f'odds ratio, {100 * (1 - p["alpha"]):g}% CI', f'odds ratio, IC {100 * (1 - p["alpha"]):g}%'),
                f'{ci.low:.4g} … {ci.high:.4g}')
        if small > 0:
            p_main = fisher.pvalue
            r.text(ctx.tr('Some expected counts are below 5: the conclusion uses Fisher’s exact test.',
                          'Alcuni conteggi attesi sono sotto 5: la conclusione usa il test esatto di Fisher.'))
    elif small > 0.2:
        r.text(ctx.tr(f'{100 * small:.0f}% of the expected counts are below 5: the χ² p-value is approximate '
                      f'(merge rare categories).',
                      f'Il {100 * small:.0f}% dei conteggi attesi è sotto 5: il p del χ² è approssimato '
                      f'(unisci le categorie rare).'))
    a = p['alpha']
    r.value(ctx.tr('conclusion', 'conclusione'),
            ctx.tr(f'the categories are related (p < {a:g})', f'le categorie sono legate (p < {a:g})') if p_main < a
            else ctx.tr(f'no evidence of a relation (p ≥ {a:g})', f'nessuna evidenza di legame (p ≥ {a:g})'))
    rname, cname = str(obs.index.name or p['row']), str(obs.columns.name or ctx.tr('category', 'categoria'))
    count = ctx.tr('count', 'conteggio')
    long = obs.reset_index().melt(id_vars=obs.index.name or 'index', var_name=cname, value_name=count)
    long.columns = [rname, cname, count]
    r.data(long, name=ctx.tr('contingency table', 'tabella di contingenza'),
           plot={'kind': 'bar', 'x': rname, 'y': [count], 'hue': cname})
    return r
