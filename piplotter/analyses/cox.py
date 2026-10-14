"""Cox proportional-hazards regression (statsmodels PHReg): how covariates — a treatment, a dose, an age — change the
hazard of the event, as hazard ratios with 95 % intervals and p-values (Wald), with Efron's handling of tied times.
Harrell's concordance index says how well the model orders the subjects; the proportional-hazards assumption is
checked per covariate by the correlation of its Schoenfeld residuals with the rank of the event times
(Grambsch & Therneau)."""
import keyword

import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'cox',
    'order': 46,
    'name': {'en': 'Cox regression (hazard ratios)', 'it': 'Regressione di Cox (hazard ratio)'},
    'category': 'stats',
    'description': {'en': 'Proportional-hazards model of the time to an event: hazard ratio of each covariate with its '
                          'interval and p, concordance, check of proportional hazards.',
                    'it': 'Modello a rischi proporzionali del tempo a un evento: hazard ratio di ogni covariata con '
                          'intervallo e p, concordanza, verifica dei rischi proporzionali.'},
    'requires': ['statsmodels', 'scipy'],
    'params': [
        {'id': 'time', 'type': 'column', 'default': 'x', 'label': {'en': 'Time', 'it': 'Tempo'}},
        {'id': 'event', 'type': 'column', 'optional': True,
         'label': {'en': 'Event (1 = happened, 0 = censored; empty = all events)',
                   'it': 'Evento (1 = avvenuto, 0 = censurato; vuoto = tutti eventi)'}},
        {'id': 'covariates', 'type': 'columns', 'default': 'xs',
         'label': {'en': 'Covariates (text columns become categories)', 'it': 'Covariate (le colonne di testo diventano categorie)'}},
    ],
    'references': [
        'Cox, D. R. Regression models and life-tables. J. R. Stat. Soc. B 34, 187–220 (1972). '
        'doi:10.1111/j.2517-6161.1972.tb00899.x',
        'Efron, B. The efficiency of Cox’s likelihood function for censored data. J. Am. Stat. Assoc. 72, 557–565 '
        '(1977). doi:10.1080/01621459.1977.10480613',
        'Harrell, F. E., Califf, R. M., Pryor, D. B., Lee, K. L. & Rosati, R. A. Evaluating the yield of medical tests. '
        'JAMA 247, 2543–2546 (1982). doi:10.1001/jama.1982.03320430047030',
        'Grambsch, P. M. & Therneau, T. M. Proportional hazards tests and diagnostics based on weighted residuals. '
        'Biometrika 81, 515–526 (1994). doi:10.1093/biomet/81.3.515',
        'Seabold, S. & Perktold, J. statsmodels: Econometric and statistical modeling with Python. '
        'Proc. 9th Python in Science Conf. 92–96 (2010). doi:10.25080/Majora-92bf1922-011',
    ],
}


def term(name):
    return name if name.isidentifier() and not keyword.iskeyword(name) else 'Q("{}")'.format(name.replace('"', '\\"'))


def concordance(t, e, risk):
    """Harrell's C: of the pairs where the earlier time is an event, the share where that subject has the higher
    risk (ties in risk count one half). O(n²) in blocks."""
    order = np.argsort(t, kind='stable')
    t, e, risk = t[order], e[order], risk[order]
    agree = ties = total = 0.0
    for i in np.flatnonzero(e == 1):
        later = t > t[i]
        if not later.any():
            continue
        total += later.sum()
        agree += np.sum(risk[i] > risk[later])
        ties += np.sum(risk[i] == risk[later])
    return (agree + 0.5 * ties) / total if total else float('nan')


def run(df, p, ctx):
    from scipy import stats
    from statsmodels.duration.hazard_regression import PHReg
    covs = [c for c in (p['covariates'] or []) if c not in (p['time'], p['event'])]
    if not covs:
        raise ValueError(ctx.tr('Choose at least one covariate.', 'Scegli almeno una covariata.'))
    data = pd.DataFrame({'_t': pd.to_numeric(df[p['time']], errors='coerce')})
    data['_e'] = (pd.to_numeric(df[p['event']], errors='coerce') if p['event'] else 1.0)
    rhs = []
    for c in covs:
        numeric = pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 2
        data[c] = pd.to_numeric(df[c], errors='coerce') if numeric else df[c].astype(str)
        rhs.append(term(c) if numeric else f'C({term(c)})')
    data = data.dropna()
    data = data[data['_t'] >= 0]
    if not set(np.unique(data['_e'])) <= {0.0, 1.0}:
        raise ValueError(ctx.tr('The event column must hold 1 (event) or 0 (censored).',
                                'La colonna evento deve contenere 1 (evento) o 0 (censurato).'))
    events = int(data['_e'].sum())
    if events < 2:
        raise ValueError(ctx.tr('Fewer than two events: nothing to estimate.', 'Meno di due eventi: niente da stimare.'))
    model = PHReg.from_formula('_t ~ ' + ' + '.join(rhs), data, status=data['_e'].to_numpy(), ties='efron')
    fit = model.fit()
    names = model.exog_names
    b, se = np.asarray(fit.params), np.asarray(fit.bse)
    nice = [n.replace('C(', '').replace(')[T.', ' = ').replace('Q("', '').replace('")', '').rstrip(']') for n in names]
    table = pd.DataFrame({'HR': np.exp(b), 'HR 95% low': np.exp(b - 1.96 * se), 'HR 95% high': np.exp(b + 1.96 * se),
                          'coef (log HR)': b, ctx.tr('std. error', 'errore std.'): se, 'z': b / se,
                          'p': 2 * stats.norm.sf(np.abs(b / se))}, index=nice)
    r = ctx.result()
    r.text(ctx.tr(f'Cox proportional hazards, Efron ties: {len(data)} subjects, {events} events.',
                  f'Cox a rischi proporzionali, pareggi di Efron: {len(data)} soggetti, {events} eventi.'))
    r.table(ctx.tr('Hazard ratios', 'Hazard ratio'), table, index=True)
    for k, name in enumerate(nice):
        r.value(f'HR ({name})', float(np.exp(b[k])), float(np.exp(b[k]) * se[k]), key=f'hr_{k}')
        r.value(f'p ({name})', float(table['p'].iloc[k]), key=f'p_{k}')
    # Likelihood-ratio test of the whole model against no covariates.
    null = PHReg(data['_t'].to_numpy(), np.zeros((len(data), 0)), status=data['_e'].to_numpy(), ties='efron')
    ll0 = float(null.loglike(np.zeros(0)))
    lr = 2 * (float(fit.llf) - ll0)
    r.value(ctx.tr('likelihood-ratio χ²', 'χ² del rapporto di verosimiglianza'), lr, key='lr')
    r.value(ctx.tr('likelihood-ratio p', 'p del rapporto di verosimiglianza'), float(stats.chi2.sf(lr, len(names))),
            key='lr_p')
    risk = model.exog @ b
    if len(data) <= 5000:
        r.value(ctx.tr("concordance (Harrell's C)", "concordanza (C di Harrell)"),
                concordance(data['_t'].to_numpy(), data['_e'].to_numpy(), risk), key='c_index')
    # Proportional hazards: Schoenfeld residuals of each covariate against the rank of the event times.
    sch = np.asarray(fit.schoenfeld_residuals)
    ev = data['_e'].to_numpy() == 1
    times = stats.rankdata(data['_t'].to_numpy()[ev])
    rows = []
    for k, name in enumerate(nice):
        res = sch[ev, k]
        ok = np.isfinite(res)
        if ok.sum() > 2 and np.std(res[ok]) > 0:
            rho, pv = stats.pearsonr(times[ok], res[ok])
            rows.append((name, float(rho), float(pv)))
    if rows:
        ph = pd.DataFrame([x[1:] for x in rows], index=[x[0] for x in rows],
                          columns=[ctx.tr('correlation with time', 'correlazione con il tempo'), 'p'])
        r.table(ctx.tr('Proportional hazards (Schoenfeld residuals)', 'Rischi proporzionali (residui di Schoenfeld)'),
                ph, index=True)
        bad = [x[0] for x in rows if x[2] < 0.05]
        r.text(ctx.tr(f'The effect of {", ".join(bad)} seems to change with time: the hazard ratio is an average.'
                      if bad else 'No sign that the hazard ratios change with time.',
                      f'L’effetto di {", ".join(bad)} sembra cambiare nel tempo: l’hazard ratio è una media.'
                      if bad else 'Nessun segno che gli hazard ratio cambino nel tempo.'))
    forest = pd.DataFrame({ctx.tr('covariate', 'covariata'): nice, 'HR': np.exp(b),
                           'log HR ± 1.96 SE': 1.96 * se, 'log₁₀ HR': b / np.log(10)})
    r.data(forest, name=ctx.tr('hazard ratios', 'hazard ratio'),
           plot={'kind': 'bar', 'x': forest.columns[0], 'y': ['log₁₀ HR']})
    return r
