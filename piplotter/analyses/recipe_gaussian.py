"""Recipe: is a column Gaussian, and with which mean and width?

Steps (each one is the built-in analysis of the same name, run through ctx.run):
1. histogram of the column (probability density), 2. least-squares Gaussian fit of the histogram
(Curve fitting), 3. normality tests (skewness, kurtosis, Shapiro–Wilk…), 4. block averaging for the
true error of the mean when the values are a time series (MD, Monte Carlo, sensors).
The maximum-likelihood estimates (sample mean and standard deviation) are reported next to the fit,
which depends a little on the number of bins.
"""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'recipe_gaussian',
    'order': 10,
    'name': {'en': 'Gaussian distribution of a column', 'it': 'Distribuzione gaussiana di una colonna'},
    'category': 'recipe',
    'description': {'en': 'Histogram + Gaussian fit, normality check and the true error of the mean: '
                          'mean, σ and FWHM of the values in one go.',
                    'it': 'Istogramma + fit gaussiano, verifica di normalità e vero errore della media: '
                          'media, σ e FWHM dei valori in un colpo solo.'},
    'steps': [
        {'en': 'Histogram of the column (probability density)', 'it': 'Istogramma della colonna (densità di probabilità)'},
        {'en': 'Gaussian least-squares fit of the histogram', 'it': 'Fit gaussiano ai minimi quadrati dell’istogramma'},
        {'en': 'Normality tests (skewness, kurtosis, Shapiro–Wilk…)', 'it': 'Test di normalità (asimmetria, curtosi, Shapiro–Wilk…)'},
        {'en': 'Block averaging: true error of the mean for correlated data',
         'it': 'Block averaging: vero errore della media per dati correlati'},
    ],
    'suits': [                                          # figures it suits (piplotter/advisor.py)
        {'figure': 'distribution', 'score': 95,
         'reason': {'en': 'A distribution of values: its centre, width and mean with the true error.',
                    'it': 'Una distribuzione di valori: centro, larghezza e media con il suo vero errore.'}},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Column', 'it': 'Colonna'}},
        {'id': 'bins', 'type': 'int', 'optional': True, 'min': 5, 'max': 1000,
         'label': {'en': 'Histogram bins (empty = automatic)', 'it': 'Intervalli dell’istogramma (vuoto = automatico)'}},
        {'id': 'series', 'type': 'bool', 'default': True,
         'label': {'en': 'Rows are a time series (correct the error of the mean)',
                   'it': 'Le righe sono una serie temporale (correggi l’errore della media)'}},
        {'id': 'on_figure', 'type': 'bool', 'default': True,
         'label': {'en': 'Draw the fit on the histogram of the figure', 'it': 'Disegna il fit sull’istogramma del grafico'},
         'help': {'en': 'When the figure is a histogram of this column (other files may be in it too), the Gaussian goes '
                        'on a copy of it, over its bars; otherwise, or unticked, on a figure of its own.',
                  'it': 'Quando il grafico è un istogramma di questa colonna (anche con altri file), la gaussiana va su '
                        'una sua copia, sopra le barre; altrimenti, o se tolta la spunta, su un grafico a parte.'}},
        {'id': 'note', 'type': 'bool', 'default': True,
         'label': {'en': 'Write mean, μ, σ and FWHM in the figure', 'it': 'Scrivi media, μ, σ e FWHM nel grafico'}},
    ],
    'references': [
        'Freedman, D. & Diaconis, P. On the histogram as a density estimator: L2 theory. '
        'Z. Wahrscheinlichkeitstheorie verw. Gebiete 57, 453–476 (1981). doi:10.1007/BF01025868',
    ],
}

FWHM = 2 * np.sqrt(2 * np.log(2))     # full width at half maximum of a Gaussian = 2.3548 σ


def plus_minus(value, error):
    """'71.2 ± 0.3': the error with two significant digits and the value to the same decimal place."""
    value = float(value)
    if error is None or not np.isfinite(error) or error <= 0:
        return f'{value:.4g}'
    digits = int(np.clip(1 - np.floor(np.log10(error)), 0, 12))
    return f'{value:.{digits}f} ± {error:.{digits}f}'


def run(df, p, ctx):
    v = ctx.numeric(df, p['y']).to_numpy(float)
    v = v[np.isfinite(v)]
    if v.size < 20:
        raise ValueError(ctx.tr('At least 20 values are needed.', 'Servono almeno 20 valori.'))
    step = ctx.tr('Step', 'Passo')

    # 1–2. Histogram and Gaussian fit (Curve fitting on the histogram of the column). With a histogram of this
    # column on screen and no bins of its own, the figure's bins and scale (density or counts) are used, so the
    # curve can be drawn over the figure's bars.
    fit = ctx.run('fit_curve', df, source='hist', y=p['y'], bins=p['bins'] or None, model='gaussian',
                  band='confidence', note=False)
    hist = fit.frame.iloc[:, :2]                          # bin centres, density or counts
    xname, dname = hist.columns
    bins = fit.get('bins')
    mu, mu_err = fit.get('mu'), fit.error('mu')
    sig, sig_err = abs(fit.get('sigma')), fit.error('sigma')

    # 3. normality
    norm = ctx.run('normality', pd.DataFrame({xname: v}), y=xname)

    # 4. error of the mean (block averaging) for time series
    block = ctx.run('block_average', pd.DataFrame({xname: v}), y=xname, x=None) if p['series'] and v.size >= 16 else None

    r = ctx.result()
    r.value('N', v.size)
    if block is not None:
        r.value(ctx.tr('mean (with block-averaging error)', 'media (con errore da block averaging)'),
                block.get('mean'), block.get('sem'), key='mean')
    else:
        r.value(ctx.tr('mean ± standard error', 'media ± errore standard'), v.mean(), v.std(ddof=1) / np.sqrt(v.size),
                key='mean')
    r.value(ctx.tr('standard deviation σ (of the values)', 'deviazione standard σ (dei valori)'), v.std(ddof=1), key='sd')
    r.value(ctx.tr('Gaussian fit: centre μ', 'fit gaussiano: centro μ'), mu, mu_err, key='mu')
    r.value(ctx.tr('Gaussian fit: width σ', 'fit gaussiano: larghezza σ'), sig, sig_err, key='sigma')
    r.value('FWHM = 2.3548 σ', FWHM * sig, FWHM * sig_err if sig_err is not None else None, key='fwhm')
    r.value(ctx.tr('Gaussian fit: R²', 'fit gaussiano: R²'), fit.get('r2'), key='r2')
    r.value(ctx.tr('skewness (0 for a Gaussian)', 'asimmetria (0 per una gaussiana)'), norm.get('skew'), key='skew')
    r.value(ctx.tr('excess kurtosis (0 for a Gaussian)', 'curtosi in eccesso (0 per una gaussiana)'),
            norm.get('kurtosis'), key='kurtosis')
    if block is not None:
        r.value(ctx.tr('statistical inefficiency g (1 = independent values)',
                       'inefficienza statistica g (1 = valori indipendenti)'), block.get('g'), key='g')
    r.value(ctx.tr('histogram bins', 'intervalli dell’istogramma'), bins)

    # Plain-language verdict
    skew, kurt, r2 = norm.get('skew'), norm.get('kurtosis'), fit.get('r2')
    good = r2 is not None and r2 > 0.95 and abs(skew) < 0.5 and abs(kurt) < 1
    if good:
        r.text(ctx.tr(f'The values are well described by a Gaussian (R² = {r2:.3f}, skewness {skew:+.2f}, '
                      f'excess kurtosis {kurt:+.2f}).',
                      f'I valori sono ben descritti da una gaussiana (R² = {r2:.3f}, asimmetria {skew:+.2f}, '
                      f'curtosi in eccesso {kurt:+.2f}).'))
    else:
        r.text(ctx.tr(f'The values depart from a Gaussian (R² = {r2:.3f}, skewness {skew:+.2f}, excess kurtosis '
                      f'{kurt:+.2f}): look at the figure; consider Distribution fitting for other shapes.',
                      f'I valori si discostano da una gaussiana (R² = {r2:.3f}, asimmetria {skew:+.2f}, curtosi in '
                      f'eccesso {kurt:+.2f}): guarda la figura; per altre forme usa «Fit di distribuzioni».'))
    if v.size > 5000 and not norm.get('normal'):
        r.text(ctx.tr('With this many values the normality tests reject even tiny deviations: judge from skewness, '
                      'kurtosis and the figure.',
                      'Con così tanti valori i test di normalità respingono anche scostamenti minimi: giudica da '
                      'asimmetria, curtosi e figura.'))
    if block is not None and block.get('g') and block.get('g') > 2:
        r.text(ctx.tr(f'The rows are correlated (g = {block.get("g"):.0f}): the error of the mean uses block averaging; '
                      'the fit error on μ is too small for these data.',
                      f'Le righe sono correlate (g = {block.get("g"):.0f}): l’errore della media usa il block averaging; '
                      'l’errore del fit su μ è troppo piccolo per questi dati.'))

    # Steps in detail
    first = r.include(fit, f'{step} 1–2 · ' + ctx.tr('histogram and Gaussian fit', 'istogramma e fit gaussiano'),
                      overlays=True)
    layer = r.overlays[first]
    layer['on_figure'] = bool(layer['on_figure'] and p['on_figure'])   # the figure's own bins and scale only
    if p['note']:
        mean, mean_err = r.get('mean'), r.error('mean')
        layer['note'] = '\n'.join([
            ctx.tr('mean', 'media') + f' = {plus_minus(mean, mean_err)}',
            f'μ = {plus_minus(mu, mu_err)}', f'σ = {plus_minus(sig, sig_err)}',
            f'FWHM = {plus_minus(FWHM * sig, FWHM * sig_err if sig_err is not None else None)}',
            f'R² = {fit.get("r2"):.4f}'])
    r.include(norm, f'{step} 3 · ' + ctx.tr('normality', 'normalità'))
    if block is not None:
        r.include(block, f'{step} 4 · block averaging')

    r.data(hist, name=ctx.tr('histogram + Gaussian', 'istogramma + gaussiana') + f' · {p["y"]}', plot={
        'kind': 'step', 'x': xname, 'y': [dname], 'overlays': [{'ref': first}],
        'series': {dname: {'label': ctx.tr('histogram', 'istogramma'), 'linewidth': 1.2}},
        'text': {'xlabel': p['y'], 'ylabel': dname}})
    return r
