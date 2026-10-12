"""Analyses suggested for the figure on screen (piplotter/advisor.py)."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from piplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from piplotter import advisor, plugins, samples, smart  # noqa: E402


class TestAdvisor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugins = plugins.PluginManager(user_dir=ROOT / 'no-user-plugins').plugins

    def ask(self, df, spec, n_files=1):
        out = advisor.advise(spec, smart.profile(df), df, self.plugins, n_files=n_files)
        return [s['id'] for s in out['suggestions']], out

    def test_histogram(self):
        df = pd.DataFrame({'angle': np.random.default_rng(1).normal(71, 10, 2000)})
        ids, out = self.ask(df, {'kind': 'hist', 'y': ['angle']})
        self.assertEqual(ids[0], 'recipe_gaussian')
        self.assertIn('distribution_fit', ids)
        fit = next(s for s in out['suggestions'] if s['id'] == 'fit_curve')
        self.assertEqual(fit['preset'], {'source': 'hist', 'model': 'gaussian'})
        self.assertTrue(all(s['reason']['it'] and s['reason']['en'] for s in out['suggestions']))

    def test_spectrum(self):
        df = samples.make('ir')
        x = df.columns[0]
        ids, out = self.ask(df, {'kind': 'line', 'x': x, 'y': [df.columns[1]]})
        self.assertEqual(out['facts']['xkind'], 'spectrum', x)
        self.assertEqual(ids[:2], ['baseline', 'peaks'])
        self.assertIn('ir_assign', ids)

    def test_decay(self):
        t = np.linspace(0, 50, 200)
        df = pd.DataFrame({'time (s)': t, 'A': 2 * np.exp(-t / 7) + 0.1})
        ids, out = self.ask(df, {'kind': 'scatter', 'x': 'time (s)', 'y': ['A']})
        self.assertTrue(out['facts']['decays'])
        self.assertEqual(ids[0], 'recipe_kinetics')
        fit = next(s for s in out['suggestions'] if s['id'] == 'fit_curve')
        self.assertEqual(fit['preset'], {'model': 'exp_decay'})

    def test_time_series(self):
        df = pd.DataFrame({'Frame': np.arange(5000), 'angle': np.random.default_rng(2).normal(0, 1, 5000)})
        ids, _ = self.ask(df, {'kind': 'line', 'x': 'Frame', 'y': ['angle']})
        self.assertEqual(ids[0], 'recipe_series_mean')
        self.assertIn('recipe_equilibration', ids)

    def test_groups(self):
        df = samples.make('groups')
        cat = next(c['name'] for c in smart.profile(df) if c['kind'] == 'category')
        num = next(c['name'] for c in smart.profile(df) if c['kind'] == 'numeric')
        ids, _ = self.ask(df, {'kind': 'box', 'x': cat, 'y': [num]})
        self.assertEqual(ids[0], 'recipe_compare_groups')

    def test_xy_cloud(self):
        rng = np.random.default_rng(3)
        x = rng.normal(0, 1, 300)
        df = pd.DataFrame({'height': x, 'weight': 2 * x + rng.normal(0, 1, 300)})
        ids, _ = self.ask(df, {'kind': 'scatter', 'x': 'height', 'y': ['weight']})
        self.assertEqual(ids[0], 'recipe_xy_relation')

    def test_plugins_can_say_what_they_suit(self):
        df = pd.DataFrame({'v': np.arange(10.0)})
        extra = {'my_tool': {'description': {'en': 'mine', 'it': 'mio'}, 'suits': {'kinds': ['hist'], 'score': 99}}}
        out = advisor.advise({'kind': 'hist', 'y': ['v']}, smart.profile(df), df, {**self.plugins, **extra})
        self.assertEqual(out['suggestions'][0]['id'], 'my_tool')
        out = advisor.advise({'kind': 'line', 'y': ['v']}, smart.profile(df), df, {**self.plugins, **extra})
        self.assertNotIn('my_tool', [s['id'] for s in out['suggestions']])
        self.assertEqual(plugins.validate_meta({'id': 'x_y', 'suits': {'kinds': ['hist'], 'x': 'bad', 'score': 300}})['suits'],
                         {'kinds': ['hist'], 'score': 100})

    def test_several_curves_global_fit(self):
        t = np.linspace(0, 50, 200)
        df = pd.DataFrame({'time (s)': t, 'A': 2 * np.exp(-t / 7) + 0.1})
        ids, out = self.ask(df, {'kind': 'scatter', 'x': 'time (s)', 'y': ['A']}, n_files=3)
        fit = next(s for s in out['suggestions'] if s['id'] == 'global_fit')
        self.assertEqual(fit['preset'], {'model': 'exp_decay', 'shared': 'tau'})
        ids, _ = self.ask(df, {'kind': 'scatter', 'x': 'time (s)', 'y': ['A']})
        self.assertNotIn('global_fit', ids)                                  # one curve: nothing to share

    def test_decays(self):
        t = np.linspace(0, 10, 100)
        self.assertTrue(advisor.decays(np.exp(-t)))
        self.assertFalse(advisor.decays(np.sin(t)))
        self.assertFalse(advisor.decays(t))


if __name__ == '__main__':
    unittest.main()
