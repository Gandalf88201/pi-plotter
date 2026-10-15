"""Survival analysis: Kaplan–Meier curves (with Greenwood's 95 % band) for each group, median survival time, and
the log-rank test of whether the groups differ. Time to the event (or to the end of follow-up) in one column; a second
column says whether the event happened (1) or the case was censored (0)."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'survival',
    'order': 45,
    'name': {'en': 'Survival (Kaplan–Meier, log-rank)', 'it': 'Sopravvivenza (Kaplan–Meier, log-rank)'},
    'category': 'stats',
    'description': {'en': 'Kaplan–Meier curves per group with confidence bands, median survival and the log-rank test.',
                    'it': 'Curve di Kaplan–Meier per gruppo con bande di confidenza, sopravvivenza mediana e test log-rank.'},
    'suits': [                                          # figures it suits (piplotter/advisor.py)
        {'events': True, 'xkind': {'not': 'category'}, 'score': 96,
         'reason': {'en': 'Times and events (0/1): Kaplan–Meier curves, median survival, log-rank test.',
                    'it': 'Tempi ed eventi (0/1): curve di Kaplan–Meier, sopravvivenza mediana, test log-rank.'}},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'time', 'type': 'column', 'default': 'x', 'label': {'en': 'Time', 'it': 'Tempo'}},
        {'id': 'event', 'type': 'column', 'optional': True, 'default': 'y',
         'label': {'en': 'Event (1 = happened, 0 = censored; empty = all events)',
                   'it': 'Evento (1 = avvenuto, 0 = censurato; vuoto = tutti eventi)'}},
        {'id': 'group', 'type': 'column', 'optional': True, 'default': 'hue',
         'label': {'en': 'Groups (optional)', 'it': 'Gruppi (facoltativa)'}},
    ],
    'references': [
        'Kaplan, E. L. & Meier, P. Nonparametric estimation from incomplete observations. J. Am. Stat. Assoc. 53, '
        '457–481 (1958). doi:10.1080/01621459.1958.10501452',
        'Greenwood, M. The natural duration of cancer. Rep. Public Health Med. Subj. 33, 1–26 (1926).',
        'Mantel, N. Evaluation of survival data and two new rank order statistics arising in its consideration. '
        'Cancer Chemother. Rep. 50, 163–170 (1966).',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def kaplan_meier(t, e):
    """(times, S, low, high) at each distinct event time, starting at (0, 1); Greenwood band on log(−log S)."""
    times = np.unique(t[e == 1])
    S, var_sum, out = 1.0, 0.0, [(0.0, 1.0, 1.0, 1.0)]
    for ti in times:
        n = np.sum(t >= ti)
        d = np.sum((t == ti) & (e == 1))
        S *= 1 - d / n
        if n > d:
            var_sum += d / (n * (n - d))
        if 0 < S < 1:
            se = np.sqrt(var_sum) / abs(np.log(S))
            lo, hi = S ** np.exp(1.96 * se), S ** np.exp(-1.96 * se)
        else:
            lo = hi = S
        out.append((float(ti), S, lo, hi))
    return np.array(out)


def median_time(km):
    below = np.where(km[:, 1] <= 0.5)[0]
    return float(km[below[0], 0]) if below.size else float('nan')


def logrank(t, e, g):
    """χ² and p of the log-rank test for k groups (k − 1 degrees of freedom)."""
    from scipy import stats
    groups = list(dict.fromkeys(g))
    k = len(groups)
    O = np.zeros(k)
    E = np.zeros(k)
    V = np.zeros((k, k))
    for ti in np.unique(t[e == 1]):
        at_risk = np.array([np.sum((t >= ti) & (g == gr)) for gr in groups], float)
        died = np.array([np.sum((t == ti) & (e == 1) & (g == gr)) for gr in groups], float)
        n, d = at_risk.sum(), died.sum()
        O += died
        E += d * at_risk / n
        if n > 1:
            f = d * (n - d) / (n * n * (n - 1))
            V += f * (np.diag(at_risk * n) - np.outer(at_risk, at_risk))
    diff = (O - E)[:-1]
    chi2 = float(diff @ np.linalg.pinv(V[:-1, :-1]) @ diff)
    return chi2, k - 1, float(stats.chi2.sf(chi2, k - 1)), O, E


def run(df, p, ctx):
    t = ctx.numeric(df, p['time'], dropna=False)
    e = ctx.numeric(df, p['event'], dropna=False) if p.get('event') else pd.Series(1.0, index=df.index)
    g = df[p['group']].astype(str) if p.get('group') else pd.Series(ctx.tr('all', 'tutti'), index=df.index)
    ok = t.notna() & e.notna() & (t >= 0)
    t, e, g = t[ok].to_numpy(float), (e[ok].to_numpy(float) > 0).astype(int), g[ok].to_numpy()
    if t.size < 3 or e.sum() == 0:
        raise ValueError(ctx.tr('At least three cases and one event are needed.', 'Servono almeno tre casi e un evento.'))
    r = ctx.result()
    rows, curves = [], {}
    for gr in dict.fromkeys(g):
        sel = g == gr
        km = kaplan_meier(t[sel], e[sel])
        curves[gr] = km
        rows.append({ctx.tr('group', 'gruppo'): gr, 'N': int(sel.sum()), ctx.tr('events', 'eventi'): int(e[sel].sum()),
                     ctx.tr('censored', 'censurati'): int((1 - e[sel]).sum()),
                     ctx.tr('median survival', 'sopravvivenza mediana'): median_time(km)})
    r.table(ctx.tr('Groups', 'Gruppi'), rows)
    if len(curves) > 1:
        chi2, dof, pval, O, E = logrank(t, e, g)
        r.value(ctx.tr('log-rank χ²', 'χ² log-rank'), chi2, key='chi2')
        r.value(ctx.tr('degrees of freedom', 'gradi di libertà'), dof)
        r.value('p', pval, key='p')
        r.table(ctx.tr('Events observed and expected', 'Eventi osservati e attesi'),
                {ctx.tr('group', 'gruppo'): list(curves), ctx.tr('observed', 'osservati'): O,
                 ctx.tr('expected', 'attesi'): E})
    else:
        r.value(ctx.tr('median survival', 'sopravvivenza mediana'), rows[0][ctx.tr('median survival', 'sopravvivenza mediana')],
                key='median')
    # Step curves on the union of the times (each group's survival carried forward), with its band as layers.
    tname = p['time']
    grid = np.unique(np.concatenate([[0.0], t]))
    out = pd.DataFrame({tname: grid})
    for gr, km in curves.items():
        idx = np.searchsorted(km[:, 0], grid, side='right') - 1
        out[gr] = km[idx, 1]
        lo, hi = km[idx, 2], km[idx, 3]
        r.overlay(pd.DataFrame({tname: grid, gr: km[idx, 1], 'lo': lo, 'hi': hi}), tname, gr, lo='lo', hi='hi',
                  label=f'{gr}', band_label='95% CI', on_figure=False,
                  style={'linestyle': 'none', 'band_alpha': 0.15, 'band_step': 'post', 'color_of': gr})
    r.data(out, name=ctx.tr('Kaplan–Meier', 'Kaplan–Meier'),
           plot={'kind': 'step', 'x': tname, 'y': list(curves), 'overlays': [{'ref': i} for i in range(len(curves))],
                 'style': {'step_where': 'post'},           # the survival drops at each event and stays until the next
                 'text': {'ylabel': ctx.tr('survival probability', 'probabilità di sopravvivenza')}})
    return r
