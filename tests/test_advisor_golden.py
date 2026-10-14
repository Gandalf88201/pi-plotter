"""The advisor's suggestions, recorded: a change of what it proposes is deliberate.

tests/golden/advisor.json keeps, for a set of reference figures (every family of figure, x as spectrum / time /
category, several curves, a decay, a matrix), the full ranked list: analysis, score, starting parameters and reason.
It also keeps a fingerprint of the suggestions for every combination of the facts the rules read (kind of figure,
kind of x, decay, curves, columns, groups, length, wavenumbers, matrix), so a change anywhere shows up.

After a deliberate change of the rules or of a `suits`, write the file again:

    .venv/bin/python tests/test_advisor_golden.py --update
"""
from pathlib import Path
import hashlib
import itertools
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from piplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from piplotter import advisor, plugins, samples, smart  # noqa: E402

GOLDEN = ROOT / 'tests' / 'golden' / 'advisor.json'


def _normal(n, seed):
    return np.random.default_rng(seed).normal(0, 1, n)


def _decay(n_cols=1):
    t = np.linspace(0, 50, 200)
    return pd.DataFrame({'time (s)': t, **{f'A{i + 1}': (2 + i) * np.exp(-t / (7 + 3 * i)) + 0.1 for i in range(n_cols)}})


def _columns():
    rng = np.random.default_rng(5)
    a = rng.normal(0, 1, 120)
    return pd.DataFrame({'a': a, 'b': a + rng.normal(0, 0.5, 120), 'c': rng.normal(0, 1, 120),
                         'd': -a + rng.normal(0, 0.3, 120)})


def _ordered():
    T = np.linspace(280, 360, 80)
    return pd.DataFrame({'temperature (K)': T, 'cp': 2 + 0.01 * T + 0.3 * np.exp(-((T - 320) / 6) ** 2),
                         'h': 0.02 * T ** 1.1, 'g': -0.01 * T})


def _series(n):
    return pd.DataFrame({'Frame': np.arange(n), 'angle': _normal(n, 2), 'dist': 3 + 0.1 * _normal(n, 3)})


def _groups():
    return samples.make('groups')


def _cloud():
    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, 300)
    return pd.DataFrame({'height': x, 'weight': 2 * x + rng.normal(0, 1, 300)})


def _hist():
    return pd.DataFrame({'angle': 71 + 10 * _normal(2000, 1), 'other': 60 + 8 * _normal(2000, 4),
                         'group': np.repeat(['a', 'b'], 1000)})


def _category_line():
    return pd.DataFrame({'month': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'], 'sales': [3.0, 4, 2, 5, 6, 4]})


def _first(df, kind):
    return next(c['name'] for c in smart.profile(df) if c['kind'] == kind)


def reference_figures():
    """name → (data, figure description, number of files)."""
    ir, uv, groups, hist, cols = samples.make('ir'), samples.make('spectra'), _groups(), _hist(), _columns()
    surface, cloud = samples.make('surface'), _cloud()
    ordered, short, long = _ordered(), _series(300), _series(5000)
    return {
        'hist': (hist, {'kind': 'hist', 'y': ['angle']}, 1),
        'hist_two_columns': (hist, {'kind': 'hist', 'y': ['angle', 'other']}, 1),
        'hist_by_group': (hist, {'kind': 'hist', 'y': ['angle'], 'hue': 'group'}, 1),
        'kde': (hist, {'kind': 'kde', 'y': ['angle']}, 1),
        'ecdf': (hist, {'kind': 'ecdf', 'y': ['angle']}, 1),
        'box_groups': (groups, {'kind': 'box', 'x': _first(groups, 'category'), 'y': [_first(groups, 'numeric')]}, 1),
        'violin_groups': (groups, {'kind': 'violin', 'x': _first(groups, 'category'),
                                   'y': [_first(groups, 'numeric')]}, 1),
        'bar_groups': (groups, {'kind': 'bar', 'x': _first(groups, 'category'), 'y': [_first(groups, 'numeric')]}, 1),
        'line_category_x': (_category_line(), {'kind': 'line', 'x': 'month', 'y': ['sales']}, 1),
        'corr': (cols, {'kind': 'corr', 'y': list(cols.columns)}, 1),
        'pairplot': (cols, {'kind': 'pairplot', 'y': list(cols.columns)}, 1),
        'heatmap_columns': (cols, {'kind': 'heatmap', 'y': list(cols.columns)}, 1),
        'heatmap_matrix': (surface, {'kind': 'heatmap', 'x': surface.columns[0], 'y': [surface.columns[1]],
                                     'z': surface.columns[2]}, 1),
        'contour_matrix': (surface, {'kind': 'contour', 'x': surface.columns[0], 'y': [surface.columns[1]],
                                     'z': surface.columns[2]}, 1),
        'scatter_cloud': (cloud, {'kind': 'scatter', 'x': 'height', 'y': ['weight']}, 1),
        'regression_cloud': (cloud, {'kind': 'regression', 'x': 'height', 'y': ['weight']}, 1),
        'ir_spectrum': (ir, {'kind': 'line', 'x': ir.columns[0], 'y': [ir.columns[1]]}, 1),
        'uv_spectra_three': (uv, {'kind': 'line', 'x': uv.columns[0], 'y': list(uv.columns[1:4])}, 1),
        'uv_spectrum_two_files': (uv, {'kind': 'line', 'x': uv.columns[0], 'y': [uv.columns[1]]}, 2),
        'decay_scatter': (_decay(), {'kind': 'scatter', 'x': 'time (s)', 'y': ['A1']}, 1),
        'decay_three_files': (_decay(), {'kind': 'scatter', 'x': 'time (s)', 'y': ['A1']}, 3),
        'decay_two_columns': (_decay(2), {'kind': 'line', 'x': 'time (s)', 'y': ['A1', 'A2']}, 1),
        'time_series_short': (short, {'kind': 'line', 'x': 'Frame', 'y': ['angle']}, 1),
        'time_series_long': (long, {'kind': 'line', 'x': 'Frame', 'y': ['angle']}, 1),
        'time_series_two': (long, {'kind': 'line', 'x': 'Frame', 'y': ['angle', 'dist']}, 1),
        'line_no_x': (short, {'kind': 'line', 'y': ['angle']}, 1),
        'ordered_x': (ordered, {'kind': 'line', 'x': 'temperature (K)', 'y': ['cp']}, 1),
        'ordered_x_three': (ordered, {'kind': 'scatter', 'x': 'temperature (K)', 'y': ['cp', 'h', 'g']}, 1),
        'step_ordered': (ordered, {'kind': 'step', 'x': 'temperature (K)', 'y': ['cp']}, 1),
        'stem_ordered': (ordered, {'kind': 'stem', 'x': 'temperature (K)', 'y': ['cp']}, 1),
        'area_spectrum': (uv, {'kind': 'area', 'x': uv.columns[0], 'y': [uv.columns[1]]}, 1),
        'errorbar_time': (short, {'kind': 'errorbar', 'x': 'Frame', 'y': ['angle']}, 1),
        'pie': (_category_line(), {'kind': 'pie', 'x': 'month', 'y': ['sales']}, 1),
    }


# Every value of every fact the rules read; matrix only comes with surface kinds, decay only with an x that runs.
GRID_KINDS = sorted(advisor.LINE_KINDS | advisor.DIST_KINDS | advisor.GROUP_KINDS | advisor.MATRIX_KINDS
                    | advisor.SURFACE_KINDS | {'regression', 'pie', 'polar', 'hexbin', ''})
GRID_XKINDS = ('spectrum', 'time', 'ordered', 'category', 'free')


def grid():
    for kind, xkind, ys, files, decays, hue, long, wavenumber, matrix in itertools.product(
            GRID_KINDS, GRID_XKINDS, (1, 2, 3), (1, 2), (False, True), (False, True), (False, True),
            (False, True), (False, True)):
        if matrix and kind not in advisor.SURFACE_KINDS:
            continue
        if decays and xkind not in ('time', 'ordered'):
            continue
        if wavenumber and xkind in ('time', 'ordered'):
            continue
        yield {'kind': kind, 'x': 'x', 'ys': [f'y{i}' for i in range(ys)], 'xkind': xkind, 'wavenumber': wavenumber,
               'decays': decays, 'curves': ys + files - 1, 'files': files, 'hue': hue, 'rows': 100, 'matrix': matrix,
               'long': long}


def _row(s):
    return [s['id'], s['score'], s['preset'], s['reason']['en'], s['reason']['it']]


def figure_suggestions(builtins):
    out = {}
    for name, (df, spec, n_files) in reference_figures().items():
        res = advisor.advise(spec, smart.profile(df), df, builtins, n_files=n_files, limit=None)
        f = res['facts']
        out[name] = {'facts': {k: f[k] for k in ('kind', 'xkind', 'decays', 'curves', 'matrix', 'wavenumber')},
                     'suggestions': [_row(s) for s in res['suggestions']]}
    return out


def grid_fingerprint(builtins):
    """(number of cases, sha256 of every case's ranked suggestions)."""
    h, n = hashlib.sha256(), 0
    for facts in grid():
        ranked = advisor.rank(facts, builtins, limit=None)
        h.update(json.dumps([facts, [_row(s) for s in ranked]], sort_keys=True, ensure_ascii=False).encode())
        n += 1
    return n, h.hexdigest()


def made(builtins):
    n, sha = grid_fingerprint(builtins)
    return {'figures': figure_suggestions(builtins), 'grid': {'cases': n, 'sha256': sha}}


def builtin_plugins():
    return plugins.PluginManager(user_dir=ROOT / 'no-user-plugins').plugins


class TestAdvisorGolden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builtins = builtin_plugins()
        cls.stored = json.loads(GOLDEN.read_text(encoding='utf-8'))

    def test_reference_figures(self):
        now = figure_suggestions(self.builtins)
        self.assertEqual(sorted(now), sorted(self.stored['figures']))
        for name, want in self.stored['figures'].items():
            with self.subTest(figure=name):
                self.assertEqual(now[name]['facts'], want['facts'])
                self.assertEqual(now[name]['suggestions'], want['suggestions'])

    def test_the_first_six_are_what_the_panel_shows(self):
        df, spec, n_files = reference_figures()['ir_spectrum']
        shown = advisor.advise(spec, smart.profile(df), df, self.builtins, n_files=n_files)['suggestions']
        self.assertEqual([_row(s) for s in shown], self.stored['figures']['ir_spectrum']['suggestions'][:6])

    def test_every_combination_of_facts(self):
        n, sha = grid_fingerprint(self.builtins)
        self.assertEqual(n, self.stored['grid']['cases'])
        self.assertEqual(sha, self.stored['grid']['sha256'],
                         'the suggestions changed for some figure: if deliberate, run '
                         'tests/test_advisor_golden.py --update')


if __name__ == '__main__':
    if '--update' in sys.argv:
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(made(builtin_plugins()), indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'written {GOLDEN.relative_to(ROOT)}')
    else:
        unittest.main()
