"""Which analyses suit the figure on screen: the "suggested for this figure" list of the Analysis panel.

The figure says a lot about the question behind it (as in LabPlot's and Origin's context menus, where the
analyses offered depend on the plot): a histogram asks about a distribution, a spectrum about its baseline and
peaks, a decaying signal about its rate, boxes per group about differences between groups. advise() reads the
figure's specification and a light profile of the data, and returns analyses ranked by a score, each with the
reason in plain words and, when useful, starting parameters (e.g. Curve fitting of the histogram with a Gaussian).

Plugins can join in with PLUGIN['suits'] = {'kinds': ['line', 'scatter'], 'x': 'spectrum' | 'time' | 'ordered',
'score': 70} (all optional): they are offered for those figures, with their own description as the reason.
"""
import re

import numpy as np
import pandas as pd

LINE_KINDS = {'line', 'scatter', 'step', 'area', 'errorbar', 'stem'}
DIST_KINDS = {'hist', 'kde', 'ecdf'}
GROUP_KINDS = {'box', 'violin', 'strip', 'swarm', 'bar', 'barh'}
MATRIX_KINDS = {'corr', 'pairplot'}
SURFACE_KINDS = {'heatmap', 'contour', 'surface3d'}      # a matrix (an image, a map) or z(x, y)

SPECTRUM_X = re.compile(r'(wave ?length|wave ?number|lambda|λ|\bnm\b|cm-1|cm⁻¹|1/cm|energy|\bev\b|ppm|2 ?theta|2θ|'
                        r'frequen|raman|shift|m/z|retention|binding)', re.I)
WAVENUMBER_X = re.compile(r'(wave ?number|cm-1|cm⁻¹|1/cm)', re.I)
TIME_X = re.compile(r'(^t$|^time|tempo|\btime\b|\(s\)|\(min\)|\(h\)|\bps\b|\bns\b|\bfs\b|frame|step|epoch|date|'
                    r'^iter|cycle)', re.I)

MAX_SUGGESTIONS = 6


def _tr(en, it):
    return {'en': en, 'it': it}


def _numeric(df, col):
    if not col or col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors='coerce') if not pd.api.types.is_datetime64_any_dtype(df[col]) else None
    return None if s is None else s.dropna().to_numpy(float)


def decays(y):
    """A signal that falls from a high start to a level (relaxation, kinetics): the first tenth is well above
    the last tenth, and most of the way down is already done in the first half."""
    if y is None or y.size < 8 or not np.isfinite(y).all():
        return False
    k = max(2, y.size // 10)
    start, end, half = np.median(y[:k]), np.median(y[-k:]), np.median(y[y.size // 2 - k // 2: y.size // 2 + k // 2 + 1])
    drop = start - end
    spread = np.ptp(y)
    if spread <= 0 or drop <= 0.5 * spread:
        return False
    return (start - half) > 0.6 * drop


def describe(spec, columns, df, n_files=1):
    """The facts about the figure the rules use."""
    by = {c['name']: c for c in columns}
    kind = spec.get('kind') or ''
    x = spec.get('x') if spec.get('x') in by else None
    ys = [c for c in (spec.get('y') or []) if c in by]
    xi = by.get(x, {})
    ordered = bool(x and xi.get('kind') in ('numeric', 'datetime') and xi.get('monotonic'))
    xname = str(x or '')
    xkind = ('spectrum' if ordered and SPECTRUM_X.search(xname) else
             'time' if (ordered and (TIME_X.search(xname) or xi.get('kind') == 'datetime')) or (not x and kind in LINE_KINDS) else
             'ordered' if ordered else ('category' if x and xi.get('kind') == 'category' else 'free'))
    y0 = _numeric(df, ys[0]) if ys and df is not None else None
    return {'kind': kind, 'x': x, 'ys': ys, 'xkind': xkind, 'wavenumber': bool(x and WAVENUMBER_X.search(xname)),
            'decays': bool(xkind in ('time', 'ordered') and decays(y0)), 'curves': len(ys) + max(0, n_files - 1),
            'files': n_files, 'hue': bool(spec.get('hue')), 'rows': int(len(df)) if df is not None else 0,
            'matrix': kind in SURFACE_KINDS and (bool(spec.get('z')) or _matrix_table(columns)),
            'long': bool(df is not None and len(df) >= 1000)}


def _matrix_table(columns):
    from .smart import find_matrix
    return find_matrix(columns)[0]


def rules(f):
    """[(analysis id, score 0–100, reason, starting parameters)] for the facts f."""
    out = []

    def add(pid, score, en, it, preset=None):
        out.append((pid, score, _tr(en, it), preset or {}))

    k, xk, many = f['kind'], f['xkind'], f['curves'] > 1
    if f.get('matrix'):
        add('matrix_profile', 92, 'A matrix: its values along a line clicked on the figure (or a row, a column).',
            'Una matrice: i suoi valori lungo una linea cliccata sul grafico (o una riga, una colonna).')
        add('matrix_stats', 88, 'Mean, extremes, volume and centroid of the matrix or of a region of it.',
            'Media, estremi, volume e baricentro della matrice o di una sua regione.')
        add('matrix_filter', 80, 'Smooth it, remove a background plane, or see its 2D spectrum (FFT).',
            'Smussala, togli un piano di fondo o guarda il suo spettro 2D (FFT).')
        add('matrix_transform', 70, 'Crop, bin, rotate or resample it; turn it into X, Y, Z columns.',
            'Ritagliala, raggruppa, ruota o ricampiona; trasformala in colonne X, Y, Z.')
    elif k in DIST_KINDS:
        add('recipe_gaussian', 95, 'A distribution of values: its centre, width and mean with the true error.',
            'Una distribuzione di valori: centro, larghezza e media con il suo vero errore.')
        add('distribution_fit', 82, 'Which distribution describes the values best (normal, log-normal, gamma…).',
            'Quale distribuzione descrive meglio i valori (normale, log-normale, gamma…).')
        add('descriptive', 78, 'Mean, SD, median, quartiles of the values.', 'Media, DS, mediana, quartili dei valori.')
        add('normality', 70, 'Is the distribution normal? (Shapiro–Wilk, D’Agostino…)',
            'La distribuzione è normale? (Shapiro–Wilk, D’Agostino…)')
        add('fit_curve', 62, 'Fit a peak shape to the histogram (Gaussian, Lorentzian, your formula).',
            'Adatta una forma di picco all’istogramma (gaussiana, lorentziana, formula tua).',
            {'source': 'hist', 'model': 'gaussian'})
        if len(f['ys']) > 1 or f['hue']:
            add('recipe_compare_groups', 88, 'Several distributions: are they different?',
                'Più distribuzioni: sono diverse tra loro?')
    elif k in GROUP_KINDS or (k in LINE_KINDS and xk == 'category'):
        add('recipe_compare_groups', 95, 'Values per group: are the groups different? (test chosen for you)',
            'Valori per gruppo: i gruppi sono diversi? (test scelto per te)')
        add('compare_groups', 85, 'Choose the test yourself: t, Welch, ANOVA, Mann–Whitney, Kruskal–Wallis…',
            'Scegli tu il test: t, Welch, ANOVA, Mann–Whitney, Kruskal–Wallis…')
        add('descriptive', 80, 'Mean, SD and confidence interval of each group.',
            'Media, DS e intervallo di confidenza di ogni gruppo.')
        add('normality', 60, 'Are the values of each group normal?', 'I valori di ogni gruppo sono normali?')
    elif k in MATRIX_KINDS or (k == 'heatmap' and len(f['ys']) > 2):
        add('correlation', 95, 'Correlations between the columns (Pearson, Spearman) with p-values.',
            'Correlazioni tra le colonne (Pearson, Spearman) con i p-value.')
        add('descriptive', 70, 'Mean, SD, range of each column.', 'Media, DS, intervallo di ogni colonna.')
        add('pca', 82, 'Many columns: the few combinations that carry most of the variation (PCA).',
            'Molte colonne: le poche combinazioni che portano più variazione (PCA).')
        add('clustering', 64, 'Groups of rows that resemble each other (k-means, Ward).',
            'Gruppi di righe che si somigliano (k-means, Ward).')
    elif k == 'regression' or (k == 'scatter' and xk in ('free', 'ordered') and not f['decays']):
        add('recipe_xy_relation', 93, 'How Y depends on X: straight line, correlation and residuals.',
            'Come Y dipende da X: retta, correlazione e residui.')
        add('regression', 88, 'Linear or polynomial regression with confidence band.',
            'Regressione lineare o polinomiale con banda di confidenza.')
        add('correlation', 75, 'How strongly X and Y go together (Pearson, Spearman).',
            'Quanto X e Y vanno insieme (Pearson, Spearman).')
        add('fit_curve', 72, 'A model of your choice through the points.', 'Un modello a scelta sui punti.')
    if k in LINE_KINDS or k == 'regression':
        if xk == 'spectrum':
            add('baseline', 92, 'A spectrum: remove its baseline first.', 'Uno spettro: prima togli la linea di base.')
            add('peaks', 90, 'Find the peaks: position, height, width, area.', 'Trova i picchi: posizione, altezza, larghezza, area.')
            add('recipe_peak_fit', 86, 'Fit all the peaks together (Gaussian or Lorentzian shapes).',
                'Adatta tutti i picchi insieme (forme gaussiane o lorentziane).')
            if f['wavenumber']:
                add('ir_assign', 84, 'An IR spectrum: which groups the peaks belong to.',
                    'Uno spettro IR: a quali gruppi appartengono i picchi.')
            add('integrate', 68, 'Area under the signal (or of a band).', 'Area sotto il segnale (o di una banda).')
            add('smoothing', 58, 'Smooth the noise, or take the derivative.', 'Togli il rumore, o calcola la derivata.')
            add('convolution', 46, 'Broaden with a line shape, or remove a known broadening (deconvolution).',
                'Allarga con una forma di riga, o togli un allargamento noto (deconvoluzione).')
        elif f['decays']:
            add('recipe_kinetics', 94, 'A signal that decays: rate constant, half-life, order.',
                'Un segnale che decade: costante di velocità, tempo di dimezzamento, ordine.')
            add('fit_curve', 88, 'Fit an exponential decay (single, double, stretched).',
                'Adatta un decadimento esponenziale (singolo, doppio, stretched).', {'model': 'exp_decay'})
            add('integrate', 55, 'Area under the curve.', 'Area sotto la curva.')
        elif xk == 'time':
            add('recipe_series_mean', 88, 'A series in time: its mean with the true error (correlated values).',
                'Una serie nel tempo: la sua media con il vero errore (valori correlati).')
            if f['long']:
                add('recipe_equilibration', 82, 'A long run: when is it equilibrated, and the mean after that.',
                    'Una corsa lunga: quando è all’equilibrio, e la media da lì in poi.')
            add('autocorrelation', 72, 'How long the series remembers itself (ACF, correlation time).',
                'Per quanto la serie "ricorda" se stessa (ACF, tempo di correlazione).')
            add('block_average', 66, 'Error of the mean by block averaging.', 'Errore della media con il block averaging.')
            add('smoothing', 60, 'Smooth the noise, or take the derivative.', 'Togli il rumore, o calcola la derivata.')
            add('spectrum', 56, 'Frequencies in the signal (power spectrum).', 'Frequenze nel segnale (spettro di potenza).')
            add('descriptive', 52, 'Mean, SD, median of the values.', 'Media, DS, mediana dei valori.')
        elif xk == 'ordered':
            add('fit_curve', 85, 'Fit a model to Y against X.', 'Adatta un modello a Y in funzione di X.')
            add('peaks', 66, 'Find peaks or minima.', 'Trova picchi o minimi.')
            add('integrate', 64, 'Area under the curve.', 'Area sotto la curva.')
            add('smoothing', 60, 'Smooth the noise, or take the derivative.', 'Togli il rumore, o calcola la derivata.')
            add('descriptive', 50, 'Mean, SD, median of the values.', 'Media, DS, mediana dei valori.')
        if many and xk != 'category':
            if f['decays']:
                add('global_fit', 90, 'Several decays: fit them together with one shared τ.',
                    'Più decadimenti: adattali insieme con un solo τ condiviso.', {'model': 'exp_decay', 'shared': 'tau'})
            else:
                add('global_fit', 80, 'Several curves: one model on all of them, parameters shared or one by one, '
                    'with a report table.', 'Più curve: un modello su tutte, parametri condivisi o curva per curva, '
                    'con una tabella di riepilogo.')
        if xk in ('time', 'ordered', 'spectrum'):
            add('frequency_filter', 50, 'Remove noise, drift or a frequency (low-, high-, band-pass).',
                'Togli rumore, deriva o una frequenza (passa-basso, passa-alto, banda).')
            add('interpolate', 42, 'The curve on a new x grid (even spacing, another file’s x).',
                'La curva su una nuova griglia di x (passo regolare, le x di un altro file).')
        if many and xk != 'category':
            add('curve_math', 70, 'Two curves: their difference or ratio, or a background subtracted (A − k·B).',
                'Due curve: differenza o rapporto, o un fondo sottratto (A − k·B).')
        if many and xk in ('time', 'ordered', 'spectrum'):
            add('cross_correlation', 58, 'Two signals: is one a delayed copy of the other?',
                'Due segnali: uno è una copia ritardata dell’altro?')
        if len(f['ys']) > 2:
            add('correlation', 62, 'Several columns: how they go together.', 'Più colonne: come vanno insieme.')
            if xk in ('free', 'ordered'):
                add('pca', 56, 'Several columns: reduce them to a few principal components.',
                    'Più colonne: riducile a poche componenti principali.')
    return out


def advise(spec, columns, df, plugins, n_files=1, limit=MAX_SUGGESTIONS):
    """[{id, score, reason: {en, it}, preset: {param: value}}] for the analyses in plugins ({id: meta}), best first."""
    f = describe(spec or {}, columns, df, n_files)
    return {'facts': f, 'suggestions': rank(f, plugins, limit)}


def rank(f, plugins, limit=MAX_SUGGESTIONS):
    """The suggestions for the facts f, best first (all of them when limit is None)."""
    best = {}
    for pid, score, reason, preset in rules(f):
        if pid in plugins and score > best.get(pid, (0,))[0]:
            best[pid] = (score, reason, preset)
    for pid, meta in plugins.items():                 # plugins that say which figures they suit
        suits = meta.get('suits') or {}
        if not suits or pid in best:
            continue
        kinds = suits.get('kinds')
        if kinds and f['kind'] not in kinds:
            continue
        if suits.get('x') and suits['x'] != f['xkind']:
            continue
        best[pid] = (int(suits.get('score', 70)), meta.get('description') or _tr('', ''), {})
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])[:limit]
    return [{'id': pid, 'score': s, 'reason': r, 'preset': p} for pid, (s, r, p) in ranked]
