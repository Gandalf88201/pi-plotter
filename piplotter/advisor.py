"""Which analyses suit the figure on screen: the "suggested for this figure" list of the Analysis panel.

The figure says a lot about the question behind it (as in LabPlot's and Origin's context menus, where the
analyses offered depend on the plot): a histogram asks about a distribution, a spectrum about its baseline and
peaks, a decaying signal about its rate, boxes per group about differences between groups. advise() reads the
figure's specification and a light profile of the data, and returns analyses ranked by a score, each with the
reason in plain words and, when useful, starting parameters (e.g. Curve fitting of the histogram with a Gaussian).

The rules are data. Every analysis says which figures it suits in PLUGIN['suits'], a list of entries
{conditions…, 'score': 0–100, 'reason': {'en', 'it'}}; the conditions are facts of FACTS (all must hold), e.g.
{'figure': 'distribution', 'score': 78, 'reason': …}. RULES below keeps only what depends on several facts at once
or brings starting parameters. Of the entries that hold, each analysis keeps its best score; ties go to the broader
fact (what the figure is, then what its signal is, then the rest), then to the name.

The older form {'kinds': ['line', 'scatter'], 'x': 'spectrum', 'score': 70} still works: one entry, with the
plugin's description as the reason.
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


FIGURES = ('matrix', 'distribution', 'groups', 'columns', 'xy', '')
SIGNALS = ('spectrum', 'decay', 'time', 'ordered', '')
XKINDS = ('spectrum', 'time', 'ordered', 'category', 'free')

# What a rule can ask about: fact → its values (a tuple), bool, int (a count) or str (any text).
FACTS = {
    'kind': str,            # the figure's kind: 'line', 'hist', 'box'…
    'xkind': XKINDS,        # what x is: a spectral axis, time, another ordered quantity, categories, free values
    'figure': FIGURES,      # what the figure is: a matrix, a distribution, values per group, columns side by side,
                            # y against x — or none of these
    'signal': SIGNALS,      # for curves (line, scatter…): a spectrum, a decay, a series in time, y of an ordered x
    'line': bool,           # curves: line, scatter, step, area, error bars, stems, regression
    'many': bool,           # more than one curve (columns or files)
    'decays': bool,         # the first curve falls from a high start to a level
    'hue': bool,            # coloured by a column
    'long': bool,           # 1000 rows or more
    'wavenumber': bool,     # x in cm⁻¹
    'matrix': bool,         # a heatmap, contour or surface of a matrix
    'y_columns': int,       # how many y columns
    'files': int,           # how many files in the figure
}
LEVELS = {'kind': 0, 'figure': 0, 'xkind': 1, 'signal': 1}     # ties: what the figure is, its signal, the rest
LEGACY = {'kinds': 'kind', 'x': 'xkind'}                        # the first form of PLUGIN['suits']


def _rule(pid, score, en, it, preset=None, **when):
    return {'id': pid, 'when': when, 'score': score, 'reason': _tr(en, it), 'preset': preset or {}}


ANY_SIGNAL = ['spectrum', 'decay', 'time', 'ordered']

# Suggestions that need several facts together, or that come with starting parameters; the rest is in the
# 'suits' of each analysis (piplotter/analyses/*.py).
RULES = [
    _rule('fit_curve', 62, 'Fit a peak shape to the histogram (Gaussian, Lorentzian, your formula).',
          'Adatta una forma di picco all’istogramma (gaussiana, lorentziana, formula tua).',
          {'source': 'hist', 'model': 'gaussian'}, figure='distribution'),
    _rule('recipe_compare_groups', 88, 'Several distributions: are they different?',
          'Più distribuzioni: sono diverse tra loro?', figure='distribution', y_columns={'min': 2}),
    _rule('recipe_compare_groups', 88, 'Several distributions: are they different?',
          'Più distribuzioni: sono diverse tra loro?', figure='distribution', hue=True),
    _rule('ir_assign', 84, 'An IR spectrum: which groups the peaks belong to.',
          'Uno spettro IR: a quali gruppi appartengono i picchi.', signal='spectrum', wavenumber=True),
    _rule('fit_curve', 88, 'Fit an exponential decay (single, double, stretched).',
          'Adatta un decadimento esponenziale (singolo, doppio, stretched).', {'model': 'exp_decay'}, signal='decay'),
    _rule('recipe_equilibration', 82, 'A long run: when is it equilibrated, and the mean after that.',
          'Una corsa lunga: quando è all’equilibrio, e la media da lì in poi.', signal='time', long=True),
    _rule('global_fit', 90, 'Several decays: fit them together with one shared τ.',
          'Più decadimenti: adattali insieme con un solo τ condiviso.', {'model': 'exp_decay', 'shared': 'tau'},
          line=True, many=True, decays=True, xkind={'not': 'category'}),
    _rule('global_fit', 80, 'Several curves: one model on all of them, parameters shared or one by one, '
          'with a report table.', 'Più curve: un modello su tutte, parametri condivisi o curva per curva, '
          'con una tabella di riepilogo.', line=True, many=True, xkind={'not': 'category'}),
    _rule('curve_math', 70, 'Two curves: their difference or ratio, or a background subtracted (A − k·B).',
          'Due curve: differenza o rapporto, o un fondo sottratto (A − k·B).', line=True, many=True,
          xkind={'not': 'category'}),
    _rule('cross_correlation', 58, 'Two signals: is one a delayed copy of the other?',
          'Due segnali: uno è una copia ritardata dell’altro?', signal=ANY_SIGNAL, many=True),
    _rule('correlation', 62, 'Several columns: how they go together.', 'Più colonne: come vanno insieme.',
          line=True, y_columns={'min': 3}),
    _rule('pca', 56, 'Several columns: reduce them to a few principal components.',
          'Più colonne: riducile a poche componenti principali.', line=True, y_columns={'min': 3},
          xkind=['free', 'ordered']),
]


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
    return derive({'kind': kind, 'x': x, 'ys': ys, 'xkind': xkind, 'wavenumber': bool(x and WAVENUMBER_X.search(xname)),
                   'decays': bool(xkind in ('time', 'ordered') and decays(y0)), 'curves': len(ys) + max(0, n_files - 1),
                   'files': n_files, 'hue': bool(spec.get('hue')), 'rows': int(len(df)) if df is not None else 0,
                   'matrix': kind in SURFACE_KINDS and (bool(spec.get('z')) or _matrix_table(columns)),
                   'long': bool(df is not None and len(df) >= 1000)})


def derive(f):
    """The facts read off the others: what the figure is, what its signal is, how many curves and columns."""
    k, xk = f['kind'], f['xkind']
    line = k in LINE_KINDS or k == 'regression'
    figure = ('matrix' if f.get('matrix') else
              'distribution' if k in DIST_KINDS else
              'groups' if k in GROUP_KINDS or (k in LINE_KINDS and xk == 'category') else
              'columns' if k in MATRIX_KINDS or (k == 'heatmap' and len(f['ys']) > 2) else
              'xy' if k == 'regression' or (k == 'scatter' and xk in ('free', 'ordered') and not f['decays']) else '')
    signal = ('' if not line else 'spectrum' if xk == 'spectrum' else 'decay' if f['decays'] else
              'time' if xk == 'time' else 'ordered' if xk == 'ordered' else '')
    return {**f, 'figure': figure, 'signal': signal, 'line': line, 'many': f['curves'] > 1, 'y_columns': len(f['ys'])}


def _matrix_table(columns):
    from .smart import find_matrix
    return find_matrix(columns)[0]


# ------------------------------------------------------------------ conditions
def _value_ok(fact, v):
    kind = FACTS[fact]
    if kind is bool:
        return isinstance(v, bool)
    if kind is int:
        return isinstance(v, int) and not isinstance(v, bool)
    if kind is str:
        return isinstance(v, str)
    return v in kind


def condition(fact, want):
    """The condition on one fact, cleaned: a value, a list of values (any of them), {'not': value or list},
    or for counts {'min': n, 'max': n}; None when it does not fit the fact."""
    fact = LEGACY.get(fact, fact)
    if fact not in FACTS:
        return None
    if isinstance(want, dict):
        out = {}
        if 'not' in want:
            vals = want['not'] if isinstance(want['not'], (list, tuple)) else [want['not']]
            if vals and all(_value_ok(fact, v) for v in vals):
                out['not'] = list(vals) if isinstance(want['not'], (list, tuple)) else want['not']
        if FACTS[fact] is int:
            for b in ('min', 'max'):
                if _value_ok(fact, want.get(b)):
                    out[b] = want[b]
        return out or None
    if isinstance(want, (list, tuple)):
        vals = [v for v in want if _value_ok(fact, v)]
        return vals or None
    return want if _value_ok(fact, want) else None


def suits(v):
    """PLUGIN['suits'] cleaned: [{'when': {fact: condition}, 'score': 0–100, 'reason': {'en', 'it'} or None}].
    A dict is one entry; conditions on unknown facts or with values a fact cannot take are dropped."""
    entries = [v] if isinstance(v, dict) else v if isinstance(v, (list, tuple)) else []
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        when = {}
        for k, want in e.items():
            if k in ('score', 'reason'):
                continue
            c = condition(k, want)
            if c is not None:
                when[LEGACY.get(k, k)] = c
        score = e.get('score', 70)
        score = max(0, min(100, int(score))) if isinstance(score, (int, float)) and not isinstance(score, bool) else 70
        out.append({'when': when, 'score': score, 'reason': _reason(e.get('reason'))})
    return out


def _reason(v):
    if isinstance(v, dict) and (v.get('en') or v.get('it')):
        return {'en': str(v.get('en') or v['it']), 'it': str(v.get('it') or v['en'])}
    return _tr(v, v) if isinstance(v, str) and v else None


def holds(when, f):
    """Whether every condition of when holds for the facts f."""
    for fact, want in when.items():
        have = f.get(fact)
        if isinstance(want, dict):
            no = want.get('not')
            if no is not None and (have in no if isinstance(no, list) else have == no):
                return False
            if 'min' in want and not (have is not None and have >= want['min']):
                return False
            if 'max' in want and not (have is not None and have <= want['max']):
                return False
        elif isinstance(want, list):
            if have not in want:
                return False
        elif have != want:
            return False
    return True


def level(when):
    """How broad the facts of a rule are, for ties: 0 the figure, 1 its signal, 2 anything else."""
    return max((LEVELS.get(k, 2) for k in when), default=2)


def rules(f):
    """[(analysis id, score 0–100, reason, starting parameters, level)] of the RULES that hold for the facts f."""
    return [(r['id'], r['score'], r['reason'], r['preset'], level(r['when'])) for r in RULES if holds(r['when'], f)]


def advise(spec, columns, df, plugins, n_files=1, limit=MAX_SUGGESTIONS):
    """{facts, suggestions: [{id, score, reason: {en, it}, preset: {param: value}}]} for the analyses in plugins
    ({id: meta}), best first."""
    f = describe(spec or {}, columns, df, n_files)
    return {'facts': f, 'suggestions': rank(f, plugins, limit)}


def rank(f, plugins, limit=MAX_SUGGESTIONS):
    """The suggestions for the facts f, best first (all of them when limit is None): the RULES, then the
    'suits' of every analysis; each analysis keeps its best score."""
    f = derive(f)
    best = {}

    def offer(pid, score, reason, preset, lvl):
        if pid in plugins and score > best.get(pid, (0,))[0]:
            best[pid] = (score, lvl, reason, preset)

    for pid, score, reason, preset, lvl in rules(f):
        offer(pid, score, reason, preset, lvl)
    for pid, meta in plugins.items():
        for s in meta.get('suits') or []:
            if holds(s['when'], f):
                offer(pid, s['score'], s['reason'] or meta.get('description') or _tr('', ''), {}, level(s['when']))
    ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[0]))[:limit]
    return [{'id': pid, 'score': s, 'reason': r, 'preset': p} for pid, (s, _, r, p) in ranked]
