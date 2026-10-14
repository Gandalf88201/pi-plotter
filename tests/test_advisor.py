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
        extra = {'my_tool': plugins.validate_meta({'id': 'my_tool', 'description': {'en': 'mine', 'it': 'mio'},
                                                   'suits': {'kinds': ['hist'], 'score': 99}})}
        out = advisor.advise({'kind': 'hist', 'y': ['v']}, smart.profile(df), df, {**self.plugins, **extra})
        self.assertEqual(out['suggestions'][0]['id'], 'my_tool')
        self.assertEqual(out['suggestions'][0]['reason'], {'en': 'mine', 'it': 'mio'})     # the first form: its description
        out = advisor.advise({'kind': 'line', 'y': ['v']}, smart.profile(df), df, {**self.plugins, **extra})
        self.assertNotIn('my_tool', [s['id'] for s in out['suggestions']])
        self.assertEqual(plugins.validate_meta({'id': 'x_y', 'suits': {'kinds': ['hist'], 'x': 'bad', 'score': 300}})['suits'],
                         [{'when': {'kind': ['hist']}, 'score': 100, 'reason': None}])

    def test_suits_with_several_facts_and_reasons(self):
        meta = plugins.validate_meta({'id': 'two_decays', 'suits': [
            {'signal': 'decay', 'many': True, 'score': 97, 'reason': {'en': 'Two decays.', 'it': 'Due decadimenti.'}},
            {'figure': 'groups', 'y_columns': {'min': 2}, 'score': 40, 'reason': 'Groups.'},
            {'figure': 'nonsense', 'colour': 'red', 'score': 'high'}]})
        self.assertEqual(meta['suits'][1], {'when': {'figure': 'groups', 'y_columns': {'min': 2}}, 'score': 40,
                                            'reason': {'en': 'Groups.', 'it': 'Groups.'}})
        self.assertEqual(meta['suits'][2], {'when': {}, 'score': 70, 'reason': None})       # what it cannot read is dropped
        t = np.linspace(0, 50, 200)
        df = pd.DataFrame({'time (s)': t, 'A': 2 * np.exp(-t / 7) + 0.1})
        spec = {'kind': 'scatter', 'x': 'time (s)', 'y': ['A']}
        pl = {**self.plugins, 'two_decays': {**meta, 'suits': meta['suits'][:2]}}
        out = advisor.advise(spec, smart.profile(df), df, pl, n_files=2)
        self.assertEqual(out['suggestions'][0], {'id': 'two_decays', 'score': 97, 'preset': {},
                                                 'reason': {'en': 'Two decays.', 'it': 'Due decadimenti.'}})
        out = advisor.advise(spec, smart.profile(df), df, pl)                    # one curve: not for it
        self.assertNotIn('two_decays', [s['id'] for s in out['suggestions']])

    def test_conditions(self):
        f = {'kind': 'line', 'xkind': 'time', 'y_columns': 3, 'many': True}
        self.assertTrue(advisor.holds({'kind': ['line', 'scatter'], 'many': True}, f))
        self.assertTrue(advisor.holds({'xkind': {'not': ['category', 'free']}, 'y_columns': {'min': 3, 'max': 3}}, f))
        self.assertFalse(advisor.holds({'xkind': {'not': 'time'}}, f))
        self.assertFalse(advisor.holds({'y_columns': {'min': 4}}, f))
        self.assertFalse(advisor.holds({'kind': 'hist'}, f))
        self.assertIsNone(advisor.condition('many', 'yes'))
        self.assertIsNone(advisor.condition('signal', 'sound'))
        self.assertEqual(advisor.condition('x', ['time', 'bad']), ['time'])
        self.assertEqual(advisor.level({'figure': 'xy'}), 0)
        self.assertEqual(advisor.level({'signal': 'time'}), 1)
        self.assertEqual(advisor.level({'signal': 'time', 'many': True}), 2)

    def test_every_builtin_says_what_it_suits(self):
        # Every analysis carries 'suits' (empty when the figure alone does not call for it); nothing in it is dropped
        # on the way, every entry has its reason in both languages, and RULES names analyses that exist.
        for pid, meta in self.plugins.items():
            raw = meta['module'].PLUGIN.get('suits')
            with self.subTest(analysis=pid):
                self.assertIsInstance(raw, list)
                self.assertEqual(len(meta['suits']), len(raw))
                for e, clean in zip(raw, meta['suits']):
                    self.assertEqual(len(clean['when']), len(e) - 2, e)
                    self.assertTrue(clean['reason'] and clean['reason']['en'] and clean['reason']['it'], e)
        for r in advisor.RULES:
            self.assertIn(r['id'], self.plugins)
            self.assertEqual({k: advisor.condition(k, v) for k, v in r['when'].items()}, r['when'])

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
