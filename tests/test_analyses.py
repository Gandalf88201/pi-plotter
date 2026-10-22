"""Analysis plugins: built-ins run on sample data, user plugins load, override and report errors."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from piplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

from piplotter import plotting, plugins, samples  # noqa: E402


def has(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


@unittest.skipUnless(has('scipy') and has('statsmodels'), 'scipy and statsmodels needed')
class TestBuiltins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pm = plugins.PluginManager(user_dir=cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    CASES = [
        ('fit_curve', 'kinetics', {'x': 'Time (min)', 'y': 'Concentration (mM)', 'sigma': 'Std. dev. (mM)', 'model': 'exp_decay'}),
        ('fit_curve', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A', 'model': 'gaussian', 'xmin': 400, 'xmax': 490}),
        ('fit_curve', 'kinetics', {'x': 'Time (min)', 'y': 'Concentration (mM)', 'model': 'custom',
                                   'formula': 'a*exp(-x/tau) + c', 'p0': 'tau=10'}),
        ('autocorrelation', 'spectra', {'y': 'Sample A', 'partial': True}),
        ('block_average', 'cloud', {'y': 'x'}),
        ('cross_correlation', 'spectra', {'a': 'Sample A', 'b': 'Sample B'}),
        ('descriptive', 'groups', {'columns': ['Response (a.u.)'], 'group': 'Group'}),
        ('normality', 'cloud', {'y': 'x'}),
        ('compare_groups', 'groups', {'value': 'Response (a.u.)', 'group': 'Group'}),
        ('correlation', 'cloud', {'columns': ['x', 'y', 'z']}),
        ('regression', 'cloud', {'y': 'y', 'predictors': ['x', 'class']}),
        ('distribution_fit', 'cloud', {'y': 'w'}),
        ('smoothing', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A'}),
        ('spectrum', 'spectra', {'y': 'Sample A'}),
        ('peaks', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample C'}),
        ('ir_assign', 'ir', {'x': 'Wavenumber (cm⁻¹)', 'y': 'Transmittance (%)'}),
        ('integrate', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A'}),
        ('baseline', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample C', 'baseline': 'arpls'}),
        ('recipe_gaussian', 'cloud', {'y': 'w'}),
        ('recipe_series_mean', 'kinetics', {'y': 'Concentration (mM)', 'x': 'Time (min)'}),
        ('recipe_compare_groups', 'groups', {'value': 'Response (a.u.)', 'group': 'Group'}),
        ('recipe_xy_relation', 'cloud', {'x': 'x', 'y': 'y'}),
        ('recipe_peak_fit', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample C'}),
        ('recipe_kinetics', 'kinetics', {'x': 'Time (min)', 'y': 'Concentration (mM)', 'sigma': 'Std. dev. (mM)'}),
        ('recipe_equilibration', 'cloud', {'y': 'x'}),
        ('global_fit', 'spectra', {'model': 'gaussian', 'shared': 'sigma'}),
        ('interpolate', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A', 'method': 'pchip', 'n': 300}),
        ('frequency_filter', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A', 'kind': 'lowpass'}),
        ('convolution', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A', 'mode': 'convolve', 'width': 10}),
        ('curve_math', 'spectra', {'op': 'sub', 'a': 2, 'b': 3}),
        ('contingency', 'groups', {'source': 'columns', 'row': 'Group', 'col': 'Batch'}),
        ('pca', 'cloud', {'columns': ['x', 'y', 'z', 'w'], 'group': 'class'}),
        ('clustering', 'cloud', {'columns': ['x', 'y'], 'method': 'kmeans', 'k': 3}),
        ('survival', 'kinetics', {'time': 'Time (min)'}),
        ('matrix_transform', 'map', {'operation': 'bin', 'factor': 2}),
        ('matrix_filter', 'map', {'filter': 'gaussian', 'size': 1.5}),
        ('decimate', 'spectra', {'method': 'lttb', 'n': 100}),
        ('anova_models', 'groups', {'design': 'twoway', 'value': 'Response (a.u.)', 'a': 'Group', 'b': 'Batch'}),
        ('cox', 'kinetics', {'time': 'Time (min)', 'covariates': ['Temperature (°C)']}),
        ('matrix_profile', 'map', {'along': 'row', 'at': 3}),
        ('matrix_stats', 'map', {'corners': '500 0\n540 5'}),
        ('matrix_spots', 'map', {'method': 'otsu'}),
    ]

    def test_all_builtins_loaded(self):
        self.assertFalse(self.pm.errors)
        self.assertEqual({c[0] for c in self.CASES}, set(self.pm.plugins))
        for p in self.pm.plugins.values():
            self.assertTrue(p['references'], p['id'])

    def test_each_runs_and_plots(self):
        for pid, sample, params in self.CASES:
            with self.subTest(pid=pid, params=params):
                _, _, res = self.pm.run(pid, samples.make(sample), params, lang='it')
                self.assertTrue(res.summary or res.tables)
                if res.frame is not None:
                    png = plotting.render(res.frame, res.plot, 'png', dpi=40)
                    self.assertTrue(png.startswith(b'\x89PNG'))

    def test_fit_recovers_parameters(self):
        import numpy as np
        import pandas as pd
        x = np.linspace(0, 50, 200)
        df = pd.DataFrame({'t': x, 's': 3.0 * np.exp(-x / 7.0) + 0.5})
        _, _, res = self.pm.run('fit_curve', df, {'x': 't', 'y': 's', 'model': 'exp_decay'})
        params = {row[0]: row[1] for row in res.tables[0]['rows']}
        self.assertAlmostEqual(params['tau'], 7.0, places=4)
        self.assertAlmostEqual(params['A'], 3.0, places=4)

    def test_recipe_gaussian_recovers_parameters(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({'v': np.random.default_rng(3).normal(108, 11, 20000)})
        _, _, res = self.pm.run('recipe_gaussian', df, {'y': 'v', 'series': False})
        self.assertAlmostEqual(res.get('mu'), 108, delta=0.5)
        self.assertAlmostEqual(res.get('sigma'), 11, delta=0.5)
        self.assertAlmostEqual(res.get('fwhm'), 2 * np.sqrt(2 * np.log(2)) * res.get('sigma'), places=9)
        self.assertGreater(res.get('r2'), 0.98)
        self.assertFalse(res.overlays[0]['on_figure'])          # the curve belongs to the histogram plot
        self.assertEqual(res.plot['overlays'], [{'ref': 0}])

    def test_gaussian_of_a_broad_distribution(self):
        """A peak that fills most of the histogram (MD dihedrals): the median of the heights sat on the peak and the
        fit started from, and kept, an upside-down Gaussian at the edge. Now: a real peak, C ≥ 0, on the figure."""
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(8)
        df = pd.DataFrame({'d': np.clip(rng.normal(71, 10.7, 20000), 44, 101)})
        hist_fig = {'kind': 'hist', 'y': ['d'], 'style': {'bins': 30, 'density': True},
                    'extra': [{'id': 'e1', 'name': 'other.csv', 'y': ['d']}]}     # another file in the figure
        _, _, res = self.pm.run('recipe_gaussian', df, {'y': 'd'}, spec=hist_fig)
        self.assertAlmostEqual(res.get('mu'), 71, delta=1)
        self.assertAlmostEqual(res.get('sigma'), 10.7, delta=1.5)
        self.assertGreater(res.get('r2'), 0.95)
        layer = res.overlays[0]
        self.assertTrue(layer['on_figure'])                      # over the bars of the figure
        self.assertIn('μ = ', layer['note'])
        self.assertIn('FWHM = ', layer['note'])
        _, _, res = self.pm.run('recipe_gaussian', df, {'y': 'd', 'on_figure': False, 'note': False}, spec=hist_fig)
        self.assertFalse(res.overlays[0]['on_figure'])
        self.assertIsNone(res.overlays[0]['note'])
        # Curve fitting writes its values too, with errors to two significant digits.
        _, _, res = self.pm.run('fit_curve', df, {'y': 'd', 'model': 'gaussian'}, spec=hist_fig)
        self.assertGreaterEqual(res.get('C'), 0)
        self.assertRegex(res.overlays[0]['note'], r'μ = 7\d\.\d+ ± 0\.\d+')

    def test_customised_copy_says_when_the_builtin_is_newer(self):
        from pathlib import Path
        code = "PLUGIN = {'id': 'tiny', 'name': 'Tiny', 'params': []}\ndef run(df, p, ctx):\n    return ctx.result()\n"
        with tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as u:
            Path(b, 'tiny.py').write_text(code, encoding='utf-8')
            pm = plugins.PluginManager(builtin_dir=b, user_dir=u)
            pm.customize('tiny')
            self.assertIn('# Built-in version: ', Path(u, 'tiny.py').read_text(encoding='utf-8'))
            self.assertFalse(pm.describe()['plugins'][0]['outdated'])
            Path(b, 'tiny.py').write_text(code + '# improved\n', encoding='utf-8')     # the built-in changes
            pm.reload()
            info = pm.describe()['plugins'][0]
            self.assertTrue(info['overrides'] and info['outdated'])
            # a copy made before fingerprints: outdated only when it differs from the built-in
            old = '# Customised copy of the built-in analysis "tiny" (π-plotter tiny).\n# It replaces…\n\n'
            Path(u, 'tiny.py').write_text(old + code + '# improved\n', encoding='utf-8')
            pm.reload()
            self.assertFalse(pm.describe()['plugins'][0]['outdated'])
            Path(u, 'tiny.py').write_text(old + code, encoding='utf-8')
            pm.reload()
            self.assertTrue(pm.describe()['plugins'][0]['outdated'])

    def test_recipes_use_builtin_steps(self):
        """A customised copy of an analysis must not change what a recipe computes."""
        import numpy as np
        import pandas as pd
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'fit_curve.py').write_text(
                "PLUGIN = {'id': 'fit_curve', 'name': 'broken fit', 'params': []}\n"
                "def run(df, p, ctx):\n    raise RuntimeError('user copy used')\n", encoding='utf-8')
            pm = plugins.PluginManager(user_dir=tmp)
            self.assertTrue(pm.plugins['fit_curve']['overrides'])
            df = pd.DataFrame({'v': np.random.default_rng(4).normal(0, 1, 2000)})
            _, _, res = pm.run('recipe_gaussian', df, {'y': 'v', 'series': False})
            self.assertAlmostEqual(res.get('mu'), 0, delta=0.2)

    def test_fit_histogram_mode(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({'v': np.random.default_rng(5).normal(5, 2, 5000)})
        hist_fig = {'kind': 'hist', 'y': ['v'], 'style': {'bins': 30, 'density': False}}
        _, vals, res = self.pm.run('fit_curve', df, {'y': 'v', 'model': 'gaussian'}, spec=hist_fig)
        self.assertEqual(vals['source'], 'auto')
        self.assertTrue(res.overlays[0]['on_figure'])           # same bins and counts as the figure
        width = np.ptp(df['v']) / 30
        self.assertAlmostEqual(res.get('A'), 5000 * width / (2 * np.sqrt(2 * np.pi)), delta=15)
        self.assertAlmostEqual(res.get('sigma'), 2, delta=0.1)
        # other bins than the figure: the curve stays on the result's own plot
        _, _, res = self.pm.run('fit_curve', df, {'y': 'v', 'model': 'gaussian', 'bins': 50}, spec=hist_fig)
        self.assertFalse(res.overlays[0]['on_figure'])
        # a line figure: Y against X as before
        _, _, res = self.pm.run('fit_curve', df.assign(t=np.arange(5000)), {'x': 't', 'y': 'v', 'model': 'linear'},
                                spec={'kind': 'line'})
        self.assertIsNone(res.get('bins'))

    def test_recipe_peak_fit_recovers_peaks(self):
        import numpy as np
        import pandas as pd
        x = np.linspace(300, 550, 600)
        g = lambda a, m, f: a * np.exp(-(x - m) ** 2 / (2 * (f / 2.3548) ** 2))
        y = g(1.0, 400, 20) + g(0.6, 430, 30) + 0.1 + 0.0004 * (x - 300) + np.random.default_rng(0).normal(0, 0.01, x.size)
        _, _, res = self.pm.run('recipe_peak_fit', pd.DataFrame({'nm': x, 'A': y}), {'x': 'nm', 'y': 'A'})
        self.assertEqual(res.get('n_peaks'), 2)
        self.assertAlmostEqual(res.get('centre1'), 400, delta=0.3)
        self.assertAlmostEqual(res.get('centre2'), 430, delta=0.5)
        labels = res.overlays[-1]
        self.assertEqual(labels['text'], 'text')
        self.assertEqual([float(t) for t in labels['frame']['text']],          # the centres, 4 significant digits
                         [float(f'{res.get(k):.4g}') for k in ('centre1', 'centre2')])

    @staticmethod
    def ir(bands, unit='cm-1'):
        """A synthetic mid-IR absorbance spectrum from Lorentzian bands (centre cm⁻¹, FWHM, height)."""
        import numpy as np
        import pandas as pd
        nu = np.arange(4000.0, 399.0, -2.0)
        a = 0.02 + sum(h / (1 + ((nu - c) / (w / 2)) ** 2) for c, w, h in bands)
        a = a + np.random.default_rng(1).normal(0, 0.002, nu.size)
        x, name = (nu, 'Wavenumber (cm-1)') if unit == 'cm-1' else (1e4 / nu, 'Wavelength (µm)')
        return pd.DataFrame({name: x, 'Absorbance': a}), name

    @staticmethod
    def best(res):
        """{rounded position: (best family, confidence)} of an IR assignment."""
        return {round(a['position'] / 10) * 10: (a['candidates'][0]['family'], a['candidates'][0]['confidence'])
                for a in res.get('assignments') if a['candidates']}

    def test_ir_assignment_of_the_example(self):
        df = samples.make('ir')
        _, _, res = self.pm.run('ir_assign', df, {'x': 'Wavenumber (cm⁻¹)', 'y': 'Transmittance (%)'}, lang='en')
        best = self.best(res)
        self.assertEqual(best[1740], ('ester', 'high'))                        # C=O of a saturated ester
        self.assertEqual(best[3450][0], 'alcohol')                              # broad hydrogen-bonded O–H
        self.assertEqual(best[1370][0], 'alkane')                               # CH₃ umbrella
        self.assertEqual(res.summary[1]['value'], 'transmittance, turned into absorbance A = −log₁₀ T')
        groups = next(t for t in res.tables if t['title'].startswith('Groups'))
        self.assertIn('ester', [r[0] for r in groups['rows']])
        labels = res.overlays[-1]
        self.assertEqual(labels['text'], 'assignment')
        self.assertIn('1738 C=O', list(labels['frame']['assignment']))
        self.assertTrue(labels['style']['text_below'])                          # transmittance: bands point down
        # the marks sit on the spectrum, at its minima
        self.assertTrue(all(df['Transmittance (%)'].min() <= y < 100 for y in labels['frame']['peaks']))

    def test_ir_assignment_needs_companion_bands(self):
        # Hexanoic-acid-like: acid C=O, C–O and O–H bends; no O–H stretch above 3200.
        df, x = self.ir([(3000, 500, 0.35), (2958, 25, 0.5), (2933, 25, 0.6), (2872, 20, 0.3), (1710, 30, 1.0),
                         (1465, 20, 0.2), (1413, 25, 0.3), (1285, 35, 0.45), (1230, 30, 0.35), (935, 60, 0.3)])
        _, _, res = self.pm.run('ir_assign', df, {'x': x, 'y': 'Absorbance'}, lang='en')
        best = self.best(res)
        for pos in (1710, 1410, 1280, 1230, 930):
            self.assertEqual(best[pos][0], 'acid', pos)
        self.assertTrue(any('No band at 3650–3200' in t for t in res.texts))
        # Calcite and gypsum: inorganic bands, no organic group without C–H bands.
        df, x = self.ir([(3545, 60, 0.3), (3405, 120, 0.35), (1685, 25, 0.15), (1621, 25, 0.2), (1425, 90, 1.0),
                         (1120, 70, 0.9), (875, 12, 0.35), (712, 8, 0.15), (669, 12, 0.3), (602, 12, 0.3)])
        _, _, res = self.pm.run('ir_assign', df, {'x': x, 'y': 'Absorbance'}, lang='en')
        best = self.best(res)
        self.assertEqual({best[p][0] for p in (1420, 870, 710)}, {"carbonate"})
        self.assertEqual({best[p][0] for p in (1120, 670, 600)}, {'sulfate'})
        self.assertEqual({best[p][0] for p in (1680, 1620, 3400)}, {'water'})
        # Aromatic: ring bands, not alkene; and wavelengths in µm are read as such.
        df, x = self.ir([(3082, 10, 0.15), (3060, 10, 0.25), (3026, 10, 0.3), (2923, 20, 0.6), (2850, 15, 0.3),
                         (1601, 8, 0.2), (1493, 10, 0.4), (1452, 12, 0.4), (757, 12, 0.6), (698, 12, 1.0)], unit='um')
        _, _, res = self.pm.run('ir_assign', df, {'x': x, 'y': 'Absorbance'}, lang='en')
        best = self.best(res)
        self.assertEqual(res.summary[2]['value'], 'µm')
        self.assertEqual({best[p][0] for p in (3060, 3030, 1600, 1490, 760, 700)}, {'aromatic'})
        self.assertTrue(any('No strong band at 1850–1650' in t for t in res.texts))

    def test_ir_assignment_editable_by_the_user(self):
        import json
        df = samples.make('ir')
        base = {'x': 'Wavenumber (cm⁻¹)', 'y': 'Transmittance (%)'}
        _, _, auto = self.pm.run('ir_assign', df, base, lang='en')
        self.assertEqual(auto.tables[0]['edit']['entries'], [])
        cols = auto.tables[0]['columns']
        self.assertEqual(sorted(auto.tables[0]['edit']['fields']), ['group', 'label', 'note', 'vibration'])
        self.assertTrue(all(c in cols for c in auto.tables[0]['edit']['fields'].values()))
        pos = next(r[0] for r in auto.tables[0]['rows'] if 1735 < r[0] < 1745)
        manual = [{'position': pos, 'label': 'C=O lac', 'group': 'ester', 'vibration': 'C=O of a γ-lactone'},
                  {'position': 3452, 'note': 'wet sample'},                       # a note only: the table's assignment stays
                  {'position': 2200, 'added': True, 'label': 'C≡C', 'group': 'alkyne'},
                  {'position': 1374, 'remove': True}]
        _, _, res = self.pm.run('ir_assign', df, {**base, 'manual': json.dumps(manual)}, lang='en')
        table = res.tables[0]
        row = {r[0]: dict(zip(cols, r)) for r in table['rows']}
        self.assertNotIn(1374.0, row)                                           # removed
        self.assertEqual(row[pos]['label'], 'C=O lac')
        self.assertEqual(row[pos]['confidence'], '')                            # the user's, not a score
        self.assertEqual(row[pos]['assigned by'], 'you')
        self.assertEqual(row[2200.0]['assigned by'], 'you (added)')
        self.assertEqual(row[2200.0]['group'], 'alkyne')
        self.assertEqual(row[3454.0]['note'], 'wet sample')
        self.assertEqual(row[3454.0]['group'], 'alcohol')                       # untouched
        self.assertEqual(row[1454.0]['assigned by'], 'table')
        marks = list(res.overlays[-1]['frame']['assignment'])
        self.assertIn('1738 C=O lac', marks)
        self.assertIn('2200 C≡C', marks)
        self.assertFalse(any(m.startswith('1374') for m in marks))
        groups = next(t for t in res.tables if t['title'].startswith('Groups'))
        self.assertIn('alkyne', [r[0] for r in groups['rows']])
        # the lines come back as the table needs them, and feed the next run unchanged
        entries = table['edit']['entries']
        self.assertEqual({(e['position'], e['added'], e['remove']) for e in entries},
                         {(1738.0, False, False), (3454.0, False, False), (2200.0, True, False), (1374.0, False, True)})
        _, _, again = self.pm.run('ir_assign', df, {**base, 'manual': json.dumps(entries)}, lang='en')
        self.assertEqual(again.tables[0]['rows'], table['rows'])
        # Italian: a group typed in English is shown by the Italian name of the table's family
        _, _, it = self.pm.run('ir_assign', df, {**base, 'manual': json.dumps(manual)}, lang='it')
        self.assertIn('alchino', [r[5] for r in it.tables[0]['rows']])
        # nothing of this belongs to a recipe: a table included from another run is not editable
        outer = plugins.Result('en')
        outer.include(res, 'step')
        self.assertTrue(outer.tables and all('edit' not in tb for tb in outer.tables))
        with self.assertRaises(ValueError):
            self.pm.run('ir_assign', df, {**base, 'manual': 'not json'})
        with self.assertRaises(ValueError):                                     # outside the spectrum
            self.pm.run('ir_assign', df, {**base, 'manual': json.dumps([{'position': 100, 'label': 'x'}])})

    def test_ir_assignment_options(self):
        from piplotter.analyses import ir_assign
        everything, chon = ir_assign.bands('all', 'all'), ir_assign.bands('all', 'chon')
        self.assertGreater(len(everything), len(chon))
        self.assertFalse({b['family'] for b in chon} & ir_assign.HETEROATOM)
        self.assertTrue(all(ir_assign.FAMILIES[b['family']][1] != 'o' for b in ir_assign.bands('inorganic')))
        self.assertTrue(ir_assign.is_transmittance([90, 95, 40, 96, 97, 94, 60, 95], 'signal'))
        self.assertFalse(ir_assign.is_transmittance([0.02, 0.01, 0.6, 0.02, 0.03, 0.4, 0.01], 'signal'))
        self.assertEqual(ir_assign.x_unit([400, 4000], 'Wavelength (nm)'), 'nm')
        with self.assertRaises(ValueError):                                     # a UV-Vis spectrum is not mid-IR
            self.pm.run('ir_assign', samples.make('spectra'), {'x': 'Wavelength (nm)', 'y': 'Sample A'})

    @staticmethod
    def gas():
        """A gas spectrum at high resolution (transmittance 0–1, 0.05 cm⁻¹ apart): each band a comb of narrow
        rotational lines, P and R branches either side of a Q branch (centre cm⁻¹, absorbance of the strongest
        line); the Q branch at 1070 saturates (T below 0) and one point is a spike of 105."""
        import numpy as np
        import pandas as pd
        nu = np.arange(600.0, 3200.0, 0.05)
        a = np.zeros_like(nu)
        for c, h in ((760, 0.6), (1070, 1.0), (2950, 0.4)):
            for j in range(1, 40):
                w = h * j * np.exp(-j * j / 150) / 5.25          # thermal envelope of the lines, highest ≈ h
                for pos in (c - 0.8 * j, c + 0.8 * j):
                    a += w / (1 + ((nu - pos) / 0.08) ** 2)
            a += 2 * h / (1 + ((nu - c) / 0.3) ** 2)
        t = 10 ** -a + np.random.default_rng(3).normal(0, 0.002, nu.size)
        t[np.abs(nu - 1070) < 0.1] = -0.02
        t[5] = 105.0
        return pd.DataFrame({'Wavenumber (cm-1)': nu, 'Transmittance': t})

    def test_ir_gas_lines_grouped_into_bands(self):
        """Rotational lines are recognised and grouped: one band per vibration instead of dozens of peaks; a spike
        is left out (and does not make the spectrum read as %), a saturated band is flagged."""
        df = self.gas()
        p = {'x': 'Wavenumber (cm-1)', 'y': 'Transmittance', 'signal': 'transmittance'}
        _, _, res = self.pm.run('ir_assign', df, p, lang='en')
        summary = {s['label']: s['value'] for s in res.summary}
        self.assertEqual(summary['band resolution'], '8 cm⁻¹ (rotational lines recognised)')
        self.assertEqual(summary['points left out (transmittance above 150 %)'], 1)
        found = res.get('assignments')
        self.assertLessEqual(len(found), 6)
        for c in (760, 1070, 2950):
            near = [a for a in found if abs(a['position'] - c) < 15]
            self.assertTrue(near, (c, [a['position'] for a in found]))
            self.assertGreater(sum(a['lines'] for a in near), 20)                # the lines of the band, counted
        self.assertTrue(any(a['saturated'] for a in found if abs(a['position'] - 1070) < 15))
        self.assertFalse(any(a['saturated'] for a in found if abs(a['position'] - 2950) < 15))
        self.assertTrue(any(t.startswith('Saturated (transmittance near 0) at') for t in res.texts))
        names = [o['label'] for o in res.overlays]
        self.assertIn('band contour (8 cm⁻¹)', names)
        contour = res.overlays[names.index('band contour (8 cm⁻¹)')]['frame']['band contour']
        self.assertTrue(((contour > 0) & (contour <= 1.01)).all())              # drawn as a transmittance
        each = self.pm.run('ir_assign', df, {**p, 'resolution': 0}, lang='en')[2]
        self.assertGreater(len(each.get('assignments')), 40)                    # 0: every line is a peak
        self.assertEqual({s['label']: s['value'] for s in each.summary}['band resolution'], 'none: each peak as found')
        self.assertTrue(any('the figure labels at most 15' in t for t in each.texts))
        labels = each.overlays[-1]
        self.assertEqual((labels['text_max'], labels['text_vertical']), (15, 'auto'))  # upright if more fit so
        self.assertEqual(len(labels['frame'][labels['text_rank']]), len(labels['frame']))
        # a condensed-phase spectrum is not grouped; the direction of the labels can be chosen
        df2, x = self.ir([(1740, 20, 1.0), (2920, 30, 0.6), (1460, 15, 0.3)])
        _, _, res2 = self.pm.run('ir_assign', df2, {'x': x, 'y': 'Absorbance'}, lang='en')
        self.assertEqual({s['label']: s['value'] for s in res2.summary}['band resolution'], 'none: each peak as found')
        for choice, value in (('vertical', True), ('horizontal', False)):
            _, _, up = self.pm.run('ir_assign', df2, {'x': x, 'y': 'Absorbance', 'label_dir': choice}, lang='en')
            self.assertIs(up.overlays[-1]['text_vertical'], value)
        _, _, none = self.pm.run('ir_assign', df2, {'x': x, 'y': 'Absorbance', 'labels': 'none'}, lang='en')
        self.assertIsNone(none.overlays[-1]['text_max'])

    @staticmethod
    def spectrum():
        """Three Gaussian peaks (areas known) on a curved background, with a little noise."""
        import numpy as np
        x = np.linspace(0, 1000, 1001)
        background = 0.4 + 0.0004 * x + 0.3 * np.exp(-x / 300)
        peaks = [(1.0, 250, 12), (0.6, 520, 20), (0.8, 780, 15)]                  # height, centre, sigma
        y = background + sum(a * np.exp(-(x - m) ** 2 / (2 * s ** 2)) for a, m, s in peaks)
        return x, y + np.random.default_rng(1).normal(0, 0.003, x.size), background, peaks

    def test_baseline_methods_follow_the_background(self):
        import numpy as np
        from piplotter import baselines
        x, y, background, peaks = self.spectrum()
        anchors = '\n'.join(str(v) for v in (0, 120, 380, 650, 900, 1000))
        for p, tol in [({'baseline': 'arpls', 'bl_stiffness': 6}, 0.03), ({'baseline': 'asls', 'bl_stiffness': 6}, 0.05),
                       ({'baseline': 'snip', 'bl_width': 150}, 0.05),
                       ({'baseline': 'points', 'bl_points': plugins.parse_points(anchors), 'bl_curve': 'smooth'}, 0.02)]:
            with self.subTest(method=p['baseline']):
                b = baselines.estimate(x, y, p)
                self.assertLess(np.max(np.abs(b.values - background)), tol)
                self.assertTrue(b.refs)
        line = 0.2 + 0.001 * x                                    # rubber band: exact under a straight background
        b = baselines.estimate(x, line + (y - background), {'baseline': 'rubberband'})
        self.assertLess(np.max(np.abs(b.values - line)), 0.02)
        shuffled = np.random.default_rng(2).permutation(x.size)  # any order of x: values follow the points
        b2 = baselines.estimate(x[shuffled], y[shuffled], {'baseline': 'arpls'})
        np.testing.assert_allclose(b2.values, baselines.estimate(x, y, {'baseline': 'arpls'}).values[shuffled])
        self.assertIsNone(baselines.estimate(x, y, {'baseline': 'none'}))
        with self.assertRaises(ValueError):
            baselines.estimate(x, y, {'baseline': 'points', 'bl_points': []})

    def test_baseline_of_a_long_signal(self):
        """arPLS and AsLS on 100 001 points follow the background as on 1001 (fitted on a share of the points: with
        λ ~ 1e14 the solve on every point is numerically singular and the curve lands far from the signal)."""
        import numpy as np
        from piplotter import baselines
        x = np.linspace(0, 1000, 100_001)
        background = 0.4 + 0.0004 * x + 0.3 * np.exp(-x / 300)
        y = background + sum(a * np.exp(-(x - m) ** 2 / (2 * s ** 2)) for a, m, s in ((1.0, 250, 12), (0.6, 520, 20)))
        y = y + np.random.default_rng(1).normal(0, 0.003, x.size)
        for method, tol in (('arpls', 0.03), ('asls', 0.05)):
            with self.subTest(method=method):
                b = baselines.estimate(x, y, {'baseline': method, 'bl_stiffness': 6})
                self.assertLess(np.max(np.abs(b.values - background)), tol)
                self.assertIn(' of the 100001 points', b.label)

    def test_straight_baseline_under_peaks(self):
        """The default baseline is a straight line under the peaks: flat where the signal is flat."""
        import numpy as np
        from piplotter import baselines, samples
        x = np.linspace(0, 100, 2001)
        line = 2 + 0.03 * x
        y = line + 3 * np.exp(-(x - 30) ** 2 / 8) + 2 * np.exp(-(x - 60) ** 2 / 50) + np.random.default_rng(4).normal(0, 0.01, x.size)
        b = baselines.estimate(x, y, {'baseline': 'poly'})
        self.assertLess(np.max(np.abs(b.values - line)), 0.02)
        self.assertFalse(b.down)
        flat = baselines.estimate(x, y - 0.03 * x, {'baseline': 'poly', 'bl_degree': 0})
        self.assertLess(np.ptp(flat.values), 1e-9)                               # degree 0: a constant
        self.assertAlmostEqual(flat.values[0], 2, delta=0.02)
        df = samples.make('spectra')
        for col in ('Sample A', 'Sample B', 'Sample C'):                         # true baseline: 0
            b = baselines.estimate(df.iloc[:, 0], df[col], {'baseline': 'poly'})
            self.assertLess(np.max(np.abs(b.values)), 0.01, col)

    def test_baseline_of_dips_lies_above_them(self):
        """Transmittance (peaks pointing down): every automatic method puts the baseline on top, near 100·10^-0.02."""
        import numpy as np
        from piplotter import baselines, samples
        df = samples.make('ir')
        x, y = df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()
        self.assertTrue(baselines.peaks_point_down(y))
        self.assertFalse(baselines.peaks_point_down(-y))
        top = 100 * 10 ** -0.02
        for method, tol in (('poly', 3.5), ('arpls', 5), ('rubberband', 4), ('snip', 5.5)):
            with self.subTest(method=method):
                b = baselines.estimate(x, y, {'baseline': method})
                self.assertTrue(b.down)
                self.assertLess(np.max(np.abs(b.values - top)), tol)
                self.assertLess(b.below, 0.02)                                   # hardly any point above it
        up = baselines.estimate(x, y, {'baseline': 'poly', 'bl_peaks': 'up'})    # forced the other way: under the dips
        self.assertLess(up.values.min(), 60)

    def test_baseline_correction_divides_transmittance(self):
        """Transmittance is divided by its baseline (stays in %, flat at 100); other signals are subtracted (flat at 0).
        The corrected spectrum is drawn alone unless the spectrum before the correction is asked for."""
        import numpy as np
        from piplotter import samples
        df = samples.make('ir')
        p = {'x': df.columns[0], 'y': df.columns[1]}
        _, _, r = self.pm.run('baseline', df, p, lang='en')
        corr = r.frame['Transmittance (%) (baseline-corrected)']
        self.assertAlmostEqual(float(np.percentile(corr, 90)), 100, delta=2)       # between the bands: 100 %
        self.assertLess(corr.min(), 20)                                             # the C=O band stays deep
        self.assertEqual(r.plot['y'], ['Transmittance (%) (baseline-corrected)'])
        self.assertFalse([o for o in r.overlays if o.get('on_figure', True)])     # nothing over the original
        _, _, both = self.pm.run('baseline', df, {**p, 'show_original': True}, lang='en')
        self.assertEqual(both.plot['y'], ['Transmittance (%)', 'Transmittance (%) (baseline-corrected)'])
        self.assertEqual(len([o for o in both.overlays if o.get('on_figure', True)]), 2)   # baseline + corrected
        _, _, sub = self.pm.run('baseline', df, {**p, 'correction': 'subtract'}, lang='en')
        self.assertAlmostEqual(float(np.percentile(sub.frame['Transmittance (%) (baseline-corrected)'], 90)), 0, delta=2)
        sp = samples.make('spectra')
        _, _, a = self.pm.run('baseline', sp, {'x': sp.columns[0], 'y': 'Sample A'}, lang='en')
        self.assertAlmostEqual(float(np.median(a.frame['Sample A (baseline-corrected)'])), 0, delta=0.02)

    def test_clicked_points_keep_their_height(self):
        """A clicked point (x and y) stays where it was clicked, even where the signal has a spike."""
        import numpy as np
        from piplotter import baselines
        x = np.linspace(60, 6000, 3000)
        y = 0.03 + 0.6 * np.exp(-(x - 60) / 30) + 0.2 * np.exp(-(x - 600) ** 2 / 800)
        b = baselines.estimate(x, y, {'baseline': 'points', 'bl_points': [(-1.0, 0.03), (6010.0, 0.03)]})
        np.testing.assert_allclose(b.values, 0.03)
        np.testing.assert_allclose(b.anchors, [[-1, 0.03], [6010, 0.03]])
        old = baselines.estimate(x, y, {'baseline': 'points', 'bl_anchor': 'signal',          # a setting of older
                                        'bl_points': [(-1.0, 0.03), (6010.0, 0.03)]})            # versions: ignored
        np.testing.assert_allclose(old.values, 0.03)

    def test_anchor_points_text(self):
        self.assertEqual(plugins.parse_points('100\n200 0.5; 300,5\n\n -4e-3  7'),
                         [(100.0, None), (200.0, 0.5), (300.5, None), (-0.004, 7.0)])
        for bad in ('100, 200', '1 2 3', 'abc', '1,000.5'):
            with self.subTest(text=bad), self.assertRaises(plugins.PluginError):
                plugins.parse_points(bad)
        from piplotter import baselines
        import numpy as np
        x = np.linspace(0, 10, 101)
        b = baselines.estimate(x, x * 0 + 5, {'baseline': 'points', 'bl_anchor': 'given',
                                              'bl_points': [(2.0, 1.0), (8.0, 3.0), (5.0, None)]})
        np.testing.assert_allclose(b.anchors, [[2, 1], [5, 5], [8, 3]])  # no y given: read on the signal
        self.assertAlmostEqual(b.values[0], 1.0)                         # level beyond the first point

    def test_peaks_measured_above_the_baseline(self):
        import numpy as np
        import pandas as pd
        x, y, background, peaks = self.spectrum()
        df = pd.DataFrame({'x': x, 'y': y})
        anchors = '0\n120\n380\n650\n900\n1000'
        _, _, res = self.pm.run('peaks', df, {'x': 'x', 'y': 'y', 'baseline': 'points', 'bl_points': anchors,
                                               'bl_curve': 'smooth', 'prominence': 0.2})
        found = res.get('peaks')
        self.assertEqual(len(found), 3)
        for q, (a, m, s) in zip(found, peaks):
            self.assertAlmostEqual(q['position'], m, delta=2)
            self.assertAlmostEqual(q['height'], a, delta=0.03)
            self.assertAlmostEqual(q['fwhm'], 2.3548 * s, delta=1.5)
            self.assertAlmostEqual(q['area'], a * s * np.sqrt(2 * np.pi), delta=0.04 * a * s * np.sqrt(2 * np.pi))
        _, _, raw = self.pm.run('peaks', df, {'x': 'x', 'y': 'y', 'baseline': 'none', 'prominence': 0.2})
        self.assertGreater(raw.get('peaks')[0]['area'], found[0]['area'] * 1.5)   # background counted in
        _, _, part = self.pm.run('peaks', df, {'x': 'x', 'y': 'y', 'baseline': 'arpls', 'xmin': 400, 'xmax': 1000})
        self.assertEqual([round(q['position'] / 10) for q in part.get('peaks')], [52, 78])

    def test_recipe_peak_fit_with_baseline(self):
        import pandas as pd
        x, y, background, peaks = self.spectrum()
        _, _, res = self.pm.run('recipe_peak_fit', pd.DataFrame({'x': x, 'y': y}),
                                {'x': 'x', 'y': 'y', 'baseline': 'arpls', 'bl_stiffness': 6}, lang='en')
        self.assertEqual(res.get('n_peaks'), 3)
        self.assertGreater(res.get('r2'), 0.995)
        for i, (a, m, s) in enumerate(peaks, 1):
            self.assertAlmostEqual(res.get(f'centre{i}'), m, delta=0.5)
        base = res.overlays[0]
        self.assertEqual(base['label'], 'baseline')
        fit = res.overlays[1]                                     # the fit sits on the spectrum, not on zero
        top = fit['frame'][fit['y']].max()
        self.assertAlmostEqual(top, max(y), delta=0.05)

    def test_fit_limits(self):
        import numpy as np
        import pandas as pd
        x = np.linspace(0, 10, 100)
        df = pd.DataFrame({'t': x, 's': 2.0 * np.exp(-x / 3.0)})
        _, _, res = self.pm.run('fit_curve', df, {'x': 't', 'y': 's', 'model': 'custom', 'formula': 'a*exp(-x/tau)',
                                                   'p0': 'a=1, tau=1', 'bounds': 'tau=0.5..2'}, lang='en')
        self.assertAlmostEqual(res.get('tau'), 2.0, places=6)     # the true value is outside: stops at the limit
        self.assertTrue(any('At a limit: tau' in t for t in res.texts))
        for bad in ('tau=2..1', 'nope=0..1', 'tau=3'):
            with self.subTest(bounds=bad), self.assertRaises(Exception):
                self.pm.run('fit_curve', df, {'x': 't', 'y': 's', 'model': 'custom', 'formula': 'a*exp(-x/tau)',
                                              'bounds': bad})

    def test_integral_with_baseline(self):
        import numpy as np
        import pandas as pd
        x, y, background, peaks = self.spectrum()
        df = pd.DataFrame({'x': x, 'y': y})
        a, m, s = peaks[1]
        _, _, res = self.pm.run('integrate', df, {'x': 'x', 'y': 'y', 'xmin': 440, 'xmax': 600, 'baseline': 'ends'}, lang='en')
        area = {v['label']: v['value'] for v in res.summary}['area (trapezoid)']
        self.assertAlmostEqual(area, a * s * np.sqrt(2 * np.pi), delta=0.5)
        _, _, res = self.pm.run('integrate', df, {'x': 'x', 'y': 'y', 'xmin': 440, 'xmax': 600, 'baseline': 'arpls',
                                                  'bl_stiffness': 6}, lang='en')
        area = {v['label']: v['value'] for v in res.summary}['area (trapezoid)']
        self.assertAlmostEqual(area, a * s * np.sqrt(2 * np.pi), delta=0.5)

    def test_recipe_kinetics_finds_order(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(0)
        t = np.linspace(0, 30, 25)
        first = pd.DataFrame({'t': t, 'c': 2.0 * np.exp(-0.15 * t) + 0.1 + rng.normal(0, 0.02, t.size)})
        _, _, res = self.pm.run('recipe_kinetics', first, {'x': 't', 'y': 'c'}, lang='en')
        self.assertTrue(res.get('order').startswith('first'))
        self.assertAlmostEqual(res.get('k'), 0.15, delta=0.01)
        self.assertAlmostEqual(res.get('t_half'), np.log(2) / res.get('k'), places=9)
        second = pd.DataFrame({'t': t, 'c': 2.0 / (1 + 2.0 * 0.05 * t) + rng.normal(0, 0.005, t.size)})
        _, _, res = self.pm.run('recipe_kinetics', second, {'x': 't', 'y': 'c'}, lang='en')
        self.assertTrue(res.get('order').startswith('second'))
        self.assertAlmostEqual(res.get('k'), 0.05, delta=0.004)

    def test_recipe_equilibration(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(1)
        n = 6000
        e = np.zeros(n)
        for i in range(1, n):
            e[i] = 0.9 * e[i - 1] + rng.normal(0, 1)
        y = -50 + 30 * np.exp(-np.arange(n) / 300) + e
        _, _, res = self.pm.run('recipe_equilibration', pd.DataFrame({'E': y}), {'y': 'E'})
        self.assertTrue(500 < res.get('t0') < 2000, res.get('t0'))
        self.assertAlmostEqual(res.get('mean'), -50, delta=4 * res.error('mean') + 0.2)
        # a column that is not a time axis is not used as time
        shuffled = pd.DataFrame({'E': y, 'noise': np.random.default_rng(2).normal(size=n)})
        _, _, res = self.pm.run('recipe_equilibration', shuffled, {'y': 'E', 'x': 'noise'}, lang='en')
        self.assertTrue(any('not used as time' in t for t in res.texts))
        self.assertTrue(500 < res.get('t0') < 2000)
        self.assertFalse(any(o['on_figure'] for o in res.overlays))

    def test_recipe_kinetics_any_time_origin(self):
        """Data recorded from t = 100 give the same k as data from t = 0; growth gives a positive k."""
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(0)
        t = np.linspace(100, 160, 25)
        first = 2.0 * np.exp(-0.1 * (t - 100)) + 0.1 + rng.normal(0, 0.01, t.size)
        _, _, res = self.pm.run('recipe_kinetics', pd.DataFrame({'t': t, 'c': first}), {'x': 't', 'y': 'c'}, lang='en')
        self.assertTrue(res.get('order').startswith('first'), res.get('order'))
        self.assertAlmostEqual(res.get('k'), 0.1, delta=0.005)
        zero = 5 - 0.05 * (t - 100) + rng.normal(0, 0.005, t.size)
        _, _, res = self.pm.run('recipe_kinetics', pd.DataFrame({'t': t, 'c': zero}),
                                {'x': 't', 'y': 'c', 'order': '0'}, lang='en')
        self.assertAlmostEqual(res.get('k'), 0.05, delta=0.002)
        self.assertAlmostEqual(res.get('t_half'), 50, delta=2)            # A0 / 2k from the first time
        growth = 2.0 - 2.0 / (1 + 2.0 * 0.05 * (t - 100)) + rng.normal(0, 0.005, t.size)
        _, _, res = self.pm.run('recipe_kinetics', pd.DataFrame({'t': t, 'c': growth}),
                                {'x': 't', 'y': 'c', 'order': '2'}, lang='en')
        self.assertAlmostEqual(res.get('k'), 0.05, delta=0.005)           # positive, not −0.05

    def test_names_that_collide_with_result_columns(self):
        import numpy as np
        import pandas as pd
        v = np.random.default_rng(1).normal(1.0, 0.05, 3000)
        _, _, res = self.pm.run('recipe_gaussian', pd.DataFrame({'density': v}), {'y': 'density', 'series': False})
        self.assertAlmostEqual(res.get('mu'), 1.0, delta=0.01)
        self.assertAlmostEqual(res.get('sigma'), 0.05, delta=0.005)
        _, _, res = self.pm.run('fit_curve', pd.DataFrame({'density': v}), {'source': 'hist', 'y': 'density',
                                                                           'model': 'gaussian'})
        self.assertEqual(len(set(res.frame.columns)), len(res.frame.columns))
        self.assertEqual(res.frame.columns[0], 'density')
        x = np.linspace(0, 10, 50)
        df = pd.DataFrame({'t': x, 'fit': 2 * x + 1})                     # a column called "fit"
        _, _, res = self.pm.run('fit_curve', df, {'source': 'xy', 'x': 't', 'y': 'fit', 'model': 'linear'})
        self.assertTrue(np.allclose(res.frame['fit'], 2 * x + 1))           # the data, not the fitted curve
        self.assertIn(res.get('fit_column'), res.frame.columns)

    def test_weighted_fit_aic_uses_chi2(self):
        import numpy as np
        import pandas as pd
        x = np.linspace(0, 10, 40)
        err = np.where(x < 5, 0.1, 2.0)
        y = 3 * x + 1 + np.random.default_rng(2).normal(0, err)
        _, _, res = self.pm.run('fit_curve', pd.DataFrame({'x': x, 'y': y, 'e': err}),
                                {'source': 'xy', 'x': 'x', 'y': 'y', 'sigma': 'e', 'model': 'linear'})
        resid = y - (res.get('a') * x + res.get('b'))
        self.assertAlmostEqual(res.get('aic'), float(np.sum((resid / err) ** 2)) + 4, places=6)

    def test_equilibration_inefficiency_matches_reference(self):
        """The vectorised statistical inefficiency equals the plain loop (as in pymbar)."""
        import numpy as np
        mod = self.pm.builtins['recipe_equilibration']['module']

        def reference(a):
            a = np.asarray(a, float) - np.mean(a)
            n, var = a.size, a.var()
            f = np.fft.rfft(a, 2 * n)
            c = np.fft.irfft(f * np.conj(f))[:n] / np.arange(n, 0, -1) / var
            g, t = 1.0, 1
            while t < n - 1:
                if c[t] <= 0 and t > 3:
                    break
                g += 2 * c[t] * (1 - t / n)
                t += 1
            return max(1.0, g)
        rng = np.random.default_rng(3)
        for phi in (0.0, 0.5, 0.95):
            e = np.zeros(3000)
            for i in range(1, e.size):
                e[i] = phi * e[i - 1] + rng.normal()
            self.assertAlmostEqual(mod.inefficiency(e), reference(e), places=9)

    def test_equilibration_layers_need_the_figure_x(self):
        """No time column in the recipe but a time axis in the figure: layers stay on the result plot."""
        import numpy as np
        import pandas as pd
        y = -50 + 30 * np.exp(-np.arange(2000) / 100) + np.random.default_rng(4).normal(0, 1, 2000)
        df = pd.DataFrame({'time (ps)': np.arange(2000) * 2.0, 'E': y})
        _, _, res = self.pm.run('recipe_equilibration', df, {'y': 'E', 'x': None}, spec={'x': 'time (ps)'})
        self.assertFalse(any(o['on_figure'] for o in res.overlays))
        _, _, res = self.pm.run('recipe_equilibration', df, {'y': 'E', 'x': 'time (ps)'}, spec={'x': 'time (ps)'})
        self.assertTrue(all(o['on_figure'] for o in res.overlays))

    def test_new_plugin_title_is_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pm = plugins.PluginManager(user_dir=tmp)
            out = pm.create('media \\ "prova" l\'altra')
            self.assertEqual(out['errors'], [])
            p = [q for q in pm.plugins.values() if q['source'] == 'user'][0]
            self.assertEqual(p['name']['en'], 'media \\ "prova" l\'altra')

    def test_distribution_fit_normal(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({'v': np.random.default_rng(2).normal(108, 11, 5000)})
        _, _, res = self.pm.run('distribution_fit', df, {'y': 'v', 'dists': 'norm, gamma'})
        cols = res.tables[0]['columns']
        self.assertNotIn('note', cols)          # a failing distribution reports its error in 'note'
        best = dict(zip(cols, res.tables[0]['rows'][0]))
        self.assertGreater(best['KS p'], 0.01)

    def test_block_average_white_noise(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({'v': np.random.default_rng(1).normal(0, 1, 4096)})
        _, _, res = self.pm.run('block_average', df, {'y': 'v'})
        g = next(s['value'] for s in res.summary if 'inefficiency' in s['label'])
        self.assertLess(g, 1.6)          # uncorrelated data: g ≈ 1

    def test_fit_overlay_band_and_render(self):
        import io as _io
        import zipfile as _zip
        import numpy as np
        import pandas as pd
        from piplotter import exporters
        from piplotter.modules import load_registry
        rng = np.random.default_rng(3)
        x = np.linspace(0, 40, 60)
        sig = np.full(x.size, 0.03)
        df = pd.DataFrame({'t': x, 's': 2.0 * np.exp(-x / 9.0) + 0.1 + rng.normal(0, 0.03, x.size), 'e': sig})
        _, _, res = self.pm.run('fit_curve', df, {'x': 't', 'y': 's', 'sigma': 'e', 'model': 'exp_decay'})
        ov = res.overlays[0]
        curve = ov['frame']
        truth = 2.0 * np.exp(-curve['t'] / 9.0) + 0.1
        inside = ((curve[ov['lo']] <= truth) & (truth <= curve[ov['hi']])).mean()
        self.assertGreater(inside, 0.8)              # the 95 % band covers the true curve
        self.assertEqual(res.plot['kind'], 'errorbar')
        spec = {'kind': 'errorbar', 'x': 't', 'y': ['s'], 'yerr': 'e',
                'overlays': [{'id': 'o1', 'dataset_id': 'd', 'x': 't', 'y': 'fit', 'lo': ov['lo'], 'hi': ov['hi'],
                              'label': 'fit', 'band_label': '95% CI'}]}
        png = plotting.render(df, spec, 'png', dpi=50, overlay_data={'o1': curve})
        self.assertTrue(png.startswith(b'\x89PNG'))
        svg = plotting.render(df, spec, 'svg', overlay_data={'o1': curve}).decode()
        self.assertIn('95% CI', svg)
        # missing overlay data is skipped, not an error
        self.assertTrue(plotting.render(df, spec, 'png', dpi=40).startswith(b'\x89PNG'))
        data = exporters.script_bundle(df, spec, 'fig', load_registry(), overlay_data={'o1': curve})
        with tempfile.TemporaryDirectory() as tmp:
            _zip.ZipFile(_io.BytesIO(data)).extractall(tmp)
            self.assertTrue((Path(tmp) / 'fig' / 'overlay_1.csv').exists())
            run = subprocess.run([sys.executable, 'make_figure.py'], cwd=Path(tmp) / 'fig', capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_regression_and_block_overlays(self):
        _, _, res = self.pm.run('regression', samples.make('cloud'), {'y': 'y', 'predictors': ['x']})
        self.assertEqual(len(res.overlays), 2)       # confidence and prediction bands
        ci, pi = res.overlays
        width_ci = (ci['frame'][ci['hi']] - ci['frame'][ci['lo']]).mean()
        width_pi = (pi['frame'][pi['hi']] - pi['frame'][pi['lo']]).mean()
        self.assertLess(width_ci, width_pi)
        _, _, res = self.pm.run('block_average', samples.make('spectra'), {'y': 'Sample A', 'x': 'Wavelength (nm)'})
        self.assertEqual(res.overlays[0]['x'], 'Wavelength (nm)')

    def test_role_defaults(self):
        df = samples.make('kinetics')
        spec = {'x': 'Time (min)', 'y': ['Concentration (mM)'], 'yerr': 'Std. dev. (mM)'}
        _, values, _ = self.pm.run('fit_curve', df, {'model': 'linear'}, spec=spec)
        self.assertEqual((values['x'], values['y'], values['sigma']), ('Time (min)', 'Concentration (mM)', 'Std. dev. (mM)'))

    def test_global_fit_shares_parameters(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(1)
        t = np.linspace(0, 50, 80)
        files = [{'name': f'T{i}.csv', 'df': pd.DataFrame({'t': t, 'I': A * np.exp(-t / 7.5) + 1 + rng.normal(0, 0.1, t.size)}),
                  'x': 't', 'y': ['I'], 'main': i == 0} for i, A in enumerate([5, 10, 20])]
        run = lambda **p: self.pm.run('global_fit', files[0]['df'], {'model': 'exp_decay', **p}, files=files)[2]
        res = run(shared='tau')
        tau = next(s for s in res.summary if s['label'].startswith('τ'))
        self.assertAlmostEqual(tau['value'], 7.5, delta=3 * tau['error'])
        report = res.tables[0]
        col = report['columns'].index
        self.assertEqual([r[col('curve')] for r in report['rows']], ['T0.csv', 'T1.csv', 'T2.csv'])
        self.assertEqual({r[col('tau')] for r in report['rows']}, {tau['value']})       # one τ for all
        self.assertEqual([round(r[col('A')]) for r in report['rows']], [5, 10, 20])     # their own amplitudes
        self.assertEqual(len(res.overlays), 3)
        self.assertIn('τ = ', res.overlays[0]['note'])
        # No shared parameter: each curve as if fitted alone, errors included.
        alone = self.pm.run('fit_curve', files[1]['df'], {'x': 't', 'y': 'I', 'model': 'exp_decay', 'source': 'xy'})[2]
        single = {r[0]: (r[1], r[2]) for r in alone.tables[0]['rows']}
        row = run(shared='').tables[0]['rows'][1]
        self.assertAlmostEqual(row[col('tau')], single['tau'][0], places=4)
        self.assertAlmostEqual(row[col('σ(tau)')], single['tau'][1], places=4)
        self.assertLess(tau['error'], single['tau'][1])                                  # all the data: a tighter τ
        with self.assertRaises(ValueError):
            run(shared='k')

    def test_signal_analyses_work_on_the_histogram_drawn(self):
        """On a histogram figure, peaks / baseline / area / peak fit use the bars as drawn (bin centres and
        heights), so points clicked on the figure (value, count) are in the same units as the signal."""
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(3)
        v = np.concatenate([rng.normal(-110, 8, 3000), rng.normal(-70, 5, 1200)])
        df = pd.DataFrame({'Frame': np.arange(v.size), 'dih': v})
        spec = {'kind': 'hist', 'x': 'Frame', 'y': ['dih'], 'style': {'bins': 50, 'density': True}}
        res = self.pm.run('peaks', df, {'y': 'dih'}, spec=spec)[2]
        self.assertTrue(res.texts[0].startswith('On the histogram of dih'))
        positions = sorted(r[0] for r in res.tables[0]['rows'])
        self.assertEqual(len(positions), 2)
        self.assertAlmostEqual(positions[0], -110, delta=5)                       # the two modes, in degrees
        self.assertAlmostEqual(positions[1], -70, delta=5)
        area = self.pm.run('integrate', df, {'y': 'dih'}, spec=spec)[2]
        self.assertAlmostEqual(area.get('area'), 1.0, delta=0.02)                 # a density integrates to 1
        clicked = self.pm.run('baseline', df, {'y': 'dih', 'baseline': 'points', 'show_original': True,
                                               'bl_points': '-135 0.002\n-50 0.002'}, spec=spec, lang='en')[2]
        base = next(o for o in clicked.overlays if o['label'] == 'baseline')
        self.assertTrue(np.allclose(base['frame'][base['y']], 0.002))           # through the clicked points
        self.assertEqual(list(clicked.frame.columns[:2]), ['dih', 'density'])   # named as the histogram's axes
        fitted = self.pm.run('recipe_peak_fit', df, {'y': 'dih'}, spec=spec)[2]   # its steps are not binned twice
        self.assertEqual(fitted.get('n_peaks'), 2)
        series = self.pm.run('peaks', df, {'y': 'dih'}, spec={**spec, 'kind': 'line'})[2]
        self.assertFalse(series.texts and series.texts[0].startswith('On the histogram'))   # other figures: as before

    def test_statistics(self):
        import numpy as np
        import pandas as pd
        from scipy import stats
        run = lambda pid, df, p, **kw: self.pm.run(pid, df, p, **kw)[2]              # noqa: E731
        cg = self.pm.plugins['compare_groups']['module']
        rng = np.random.default_rng(4)
        a, b = rng.normal(0, 1, 25), rng.normal(0.8, 2, 30)
        gh = cg.games_howell([a, b], ['a', 'b'], 0.05, lambda en, it=None: en)[0]
        self.assertAlmostEqual(gh['p (Games–Howell)'], stats.ttest_ind(a, b, equal_var=False).pvalue, places=6)  # = Welch
        dn = cg.dunn([a, b], ['a', 'b'], lambda en, it=None: en)[0]
        mw = stats.mannwhitneyu(a, b, use_continuity=False, method='asymptotic')
        self.assertAlmostEqual(dn['p'], mw.pvalue, places=6)                                   # = normal Mann–Whitney
        self.assertEqual(list(cg.holm([0.01, 0.04, 0.03])), [0.03, 0.06, 0.06])
        g = pd.DataFrame({'g': np.repeat(['a', 'b', 'c'], 30),
                          'v': np.r_[rng.normal(0, 1, 30), rng.normal(0, 3, 30), rng.normal(2, 1, 30)]})
        self.assertEqual(run('compare_groups', g, {'value': 'v', 'group': 'g', 'test': 'welch_anova'}).tables[-1]['title'],
                         'Games–Howell')
        self.assertIn('Dunn', run('compare_groups', g, {'value': 'v', 'group': 'g', 'test': 'kruskal'}).tables[-1]['title'])
        w = pd.DataFrame({'t0': rng.normal(0, 1, 20)})
        w['t1'], w['t2'] = w.t0 + rng.normal(0.1, .3, 20), w.t0 + rng.normal(1, .3, 20)
        fr = run('compare_groups', w, {'columns': ['t0', 't1', 't2'], 'test': 'friedman'})
        self.assertAlmostEqual(fr.get('p'), stats.friedmanchisquare(w.t0, w.t1, w.t2).pvalue)
        c = pd.DataFrame({'treat': ['a'] * 20 + ['b'] * 20, 'out': ['y'] * 14 + ['n'] * 6 + ['y'] * 6 + ['n'] * 14})
        ct = run('contingency', c, {'source': 'columns', 'row': 'treat', 'col': 'out'})
        self.assertAlmostEqual(ct.get('p_fisher'), stats.fisher_exact([[6, 14], [14, 6]]).pvalue)
        self.assertAlmostEqual(ct.get('odds_ratio'), 36 / 196)
        self.assertAlmostEqual(ct.get('cramer_v'), 0.4)
        counts = pd.DataFrame({'site': ['A', 'B', 'C'], 'yes': [10, 20, 30], 'no': [30, 20, 10]})
        cc = run('contingency', counts, {'source': 'counts', 'row': 'site', 'counts': ['yes', 'no']})
        self.assertAlmostEqual(cc.get('chi2'), stats.chi2_contingency([[10, 30], [20, 20], [30, 10]])[0])
        t = np.r_[np.minimum(rng.exponential(10, 40), 30), np.minimum(rng.exponential(20, 40), 30)]
        e = (t < 30).astype(int)
        s = pd.DataFrame({'t': t, 'e': e, 'g': ['A'] * 40 + ['B'] * 40})
        sv = run('survival', s, {'time': 't', 'event': 'e', 'group': 'g'})
        cens = lambda m: stats.CensoredData(uncensored=s.t[m & (s.e == 1)], right=s.t[m & (s.e == 0)])  # noqa: E731
        ref = stats.logrank(cens(s.g == 'A'), cens(s.g == 'B'))
        self.assertAlmostEqual(sv.get('chi2'), ref.statistic ** 2, places=6)
        km = sv.frame
        self.assertAlmostEqual(float(km.A[km.t <= 12].iloc[-1]), float(stats.ecdf(cens(s.g == 'A')).sf.evaluate(12)))
        # Drawn as steps after each event; each band in the colour of its curve, listed once (no empty line entry).
        import matplotlib.colors
        import matplotlib.pyplot as plt
        layers = [{k: v for k, v in o.items() if k != 'frame'} | {'id': f'o{i}'} for i, o in enumerate(sv.overlays)]
        spec = plotting.normalize_spec({**sv.plot, 'overlays': layers})
        fig = plotting.build_figure(km, spec, overlay_data={f'o{i}': o['frame'] for i, o in enumerate(sv.overlays)})
        ax = fig.axes[0]
        self.assertEqual([h.get_label() for h in ax.get_legend_handles_labels()[0]],
                         ['A', 'B', 'A (95% CI)', 'B (95% CI)'])
        lines, bands = ax.get_lines()[:2], ax.collections[:2]
        for line, band in zip(lines, bands):
            self.assertEqual(matplotlib.colors.to_hex(line.get_color()), matplotlib.colors.to_hex(band.get_facecolor()[0]))
        self.assertEqual(lines[0].get_drawstyle(), 'steps-post')
        plt.close(fig)
        X = np.r_[rng.normal(0, 1, (50, 3)), rng.normal(5, 1, (50, 3))]
        blobs = pd.DataFrame(X, columns=['u', 'v', 'w'])
        pc = run('pca', blobs, {'columns': ['u', 'v', 'w']})
        self.assertGreater(pc.get('pc1'), 85)
        for method in ('kmeans', 'ward'):
            cl = run('clustering', blobs, {'columns': ['u', 'v', 'w'], 'method': method})
            self.assertEqual(cl.get('k'), 2)
            self.assertEqual(sorted(cl.frame.iloc[:, 0].value_counts().tolist()), [50, 50])

    def test_profile_kept_on_a_3d_surface(self):
        """The path of a profile drawn over a 3D surface when asked (on_surface), at the surface's height, in front of
        it in the figure and in the rotatable preview; not asked, a 3D figure draws no layer (2D ones still do)."""
        import numpy as np
        import matplotlib.pyplot as plt
        df = samples.make('surface')
        spec = {'kind': 'surface3d', 'x': 'x', 'y': ['y'], 'z': 'z'}
        run = lambda p: self.pm.run('matrix_profile', df, p, spec=spec)[2]                # noqa: E731
        on = run({'along': 'row', 'at': 0.5, 'on_surface': True})
        off = run({'along': 'row', 'at': 0.5})
        self.assertIsNone(off.overlays[0]['z'])
        ov = on.overlays[0]
        frame = ov['frame']
        np.testing.assert_allclose(frame[ov['z']], on.frame.iloc[:, 1])                  # the heights are the profile
        self.assertTrue(np.allclose(frame[ov['y']], 0.5))
        wide = run({'along': 'line', 'points': '-2 -1\n2 1', 'width': 5, 'on_surface': True}).overlays[0]
        centre = run({'along': 'line', 'points': '-2 -1\n2 1', 'on_surface': True}).overlays[0]
        np.testing.assert_allclose(wide['frame'][wide['z']], centre['frame'][centre['z']])   # the centre line, not the strip
        layer = {'id': 'p', 'x': ov['x'], 'y': ov['y'], 'z': ov['z'], 'label': ov['label'], 'style': ov['style'],
                 'dataset_id': 'd'}
        for over, drawn in ((layer, 1), ({**layer, 'z': None}, 0), ({**layer, 'hidden': True}, 0)):
            fig = plotting.build_figure(df, {**spec, 'overlays': [over]}, overlay_data={'p': frame})
            ax = next(a for a in fig.axes if a.name == '3d')
            front = [ln for ln in ax.lines if getattr(ln, '_pp_front', False)]
            self.assertEqual(len(front), drawn)
            if drawn:
                self.assertFalse(ax.computed_zorder)                                    # kept in front of the faces
                np.testing.assert_allclose(front[0].get_data_3d()[2], frame[ov['z']])
            plt.close(fig)
        info = {}
        plotting.render(df, {**spec, 'overlays': [layer]}, 'png', 50, overlay_data={'p': frame}, info=info)
        lines = [L for L in info['view3d']['axes'][0]['layers'] if L['type'] == 'line']
        self.assertEqual([L.get('front') for L in lines], [True])                       # the preview draws it too
        self.assertIn({'key': 'overlay:p', 'overlay': 'p', 'label': ov['label'], 'color': '#ff3b30'}, info['series'])
        fig = plotting.build_figure(df, {**spec, 'kind': 'heatmap', 'overlays': [layer]}, overlay_data={'p': frame})
        self.assertEqual(len(fig.axes[0].lines), 1)                                     # 2D: as before, z unused
        plt.close(fig)
        import io
        import zipfile
        from piplotter import exporters
        bundle = zipfile.ZipFile(io.BytesIO(exporters.script_bundle(df, {**spec, 'overlays': [layer]},
                                                                    overlay_data={'p': frame})))
        self.assertIn(ov['z'], bundle.read('figure/overlay_1.csv').decode().splitlines()[0])   # the Python script too
        if has('plotly'):
            html = exporters.plotly_html(df, {**spec, 'overlays': [layer]}, overlay_data={'p': frame})
            self.assertIn(b'scatter3d', html)

    def test_matrices(self):
        import numpy as np
        import pandas as pd
        from piplotter import matrices
        run = lambda pid, df, p, spec: self.pm.run(pid, df, p, spec=spec)[2]                # noqa: E731
        yy, xx = np.mgrid[0:60, 0:90]
        img = 20 + 0.5 * xx + 150 * np.exp(-((xx - 60) ** 2 + (yy - 15) ** 2) / 50)     # a bright spot near the top
        df = matrices.to_frame(img[::-1], np.arange(90.), np.arange(60.), 'y (px)')      # rows from the top, y up
        spec = {'kind': 'heatmap', 'x': 'y (px)', 'y': []}
        Z, xs, ys = matrices.from_wide(df, 'y (px)')
        self.assertEqual(float(Z[44, 60]), float(img[15, 60]))                          # y = 59 − 15 = 44
        prof = run('matrix_profile', df, {'along': 'row', 'at': 44}, spec)
        self.assertEqual(prof.get('at_max'), 60)
        seg = run('matrix_profile', df, {'along': 'line', 'points': '40 44\n80 44'}, spec)
        self.assertAlmostEqual(seg.get('length'), 40)
        self.assertAlmostEqual(seg.get('max'), Z[44].max())
        st = run('matrix_stats', df, {'corners': '50 34\n70 54'}, spec)
        self.assertAlmostEqual(st.get('cx'), 60.5, delta=1)        # the spot (slightly pulled right by the slope)
        self.assertAlmostEqual(st.get('cy'), 44, delta=0.5)
        whole = run('matrix_stats', df, {}, spec)
        self.assertAlmostEqual(whole.get('volume'), Z.sum())                            # cells of area 1
        rot = run('matrix_transform', df, {'operation': 'rotate'}, spec)
        rot2 = run('matrix_transform', rot.frame, {'operation': 'rotate'}, spec)
        self.assertTrue(np.allclose(matrices.from_wide(rot2.frame, 'y (px)')[0], Z[::-1, ::-1]))
        self.assertEqual(run('matrix_transform', df, {'operation': 'bin', 'factor': 3}, spec).frame.shape, (20, 31))
        X, Y = np.meshgrid(np.arange(30.), np.arange(20.))
        tilt = matrices.to_frame(3 + 0.5 * X - 0.2 * Y, np.arange(30.), np.arange(20.), 'y')
        pl = run('matrix_filter', tilt, {'filter': 'plane'}, {'x': 'y', 'y': []})
        self.assertAlmostEqual(pl.get('b'), 0.5)
        self.assertAlmostEqual(pl.get('c'), -0.2)
        wave = matrices.to_frame(np.cos(2 * np.pi * 0.1 * X), np.arange(30.), np.arange(20.), 'y')
        ps = run('matrix_filter', wave, {'filter': 'fft'}, {'x': 'y', 'y': []})
        P, fx, fy = matrices.from_wide(ps.frame, ps.frame.columns[0])
        i, j = np.unravel_index(np.nanargmax(P), P.shape)
        self.assertAlmostEqual(abs(fx[j]), 0.1)                                         # cycles per unit of x
        self.assertAlmostEqual(fy[i], 0.0)
        rng = np.random.default_rng(0)                      # scattered X, Y, Z → a grid (exact for a plane)
        pts = pd.DataFrame({'a': rng.uniform(0, 1, 400), 'b': rng.uniform(0, 1, 400)})
        pts['c'] = pts.a + 2 * pts.b
        gr = run('matrix_transform', pts, {'operation': 'grid', 'nx': 30}, {'x': 'a', 'y': ['b'], 'z': 'c'})
        Zg, gx, gy = matrices.from_wide(gr.frame, 'b')
        Xg, Yg = np.meshgrid(gx, gy)
        ok = np.isfinite(Zg)
        self.assertLess(np.abs(Zg[ok] - (Xg[ok] + 2 * Yg[ok])).max(), 1e-6)
        with self.assertRaises(plugins.PluginError):
            run('matrix_stats', pd.DataFrame({'a': [1.0, 2], 'b': [3.0, 4]}), {}, {'x': 'a', 'y': ['b']})

    def test_anova_designs_against_sums_of_squares(self):
        import numpy as np
        import pandas as pd
        run = lambda df, **p: self.pm.run('anova_models', df, p)[2]                  # noqa: E731
        # Two-way, balanced: SS of the factor = n·b·Σ(mean of its level − grand mean)².
        g = samples.make('groups')
        two = run(g, design='twoway', value='Response (a.u.)', a='Group', b='Batch')
        y = g['Response (a.u.)']
        ss_a = 30 * ((g.groupby('Group')['Response (a.u.)'].mean() - y.mean()) ** 2).sum()
        self.assertAlmostEqual(two.tables[0]['rows'][0][1], ss_a, places=6)
        self.assertLess(two.get('p_A'), 1e-10)
        self.assertGreater(two.get('p_AB'), 0.05)                                    # no interaction built in
        # Repeated measures, one within factor, spread growing with the condition (not spherical).
        rng = np.random.default_rng(4)
        n, k = 30, 4
        subj = rng.normal(0, 2, n)[:, None]
        Y = 10 + subj + np.array([0, 0.5, 1.0, 0.2]) + rng.normal(0, 1, (n, k)) * np.array([0.5, 1, 1.5, 3])
        rm = run(pd.DataFrame(Y, columns=['c1', 'c2', 'c3', 'c4']), design='rm', columns=['c1', 'c2', 'c3', 'c4'])
        gm = Y.mean()
        ss_c, ss_s = n * ((Y.mean(0) - gm) ** 2).sum(), k * ((Y.mean(1) - gm) ** 2).sum()
        ss_e = ((Y - gm) ** 2).sum() - ss_c - ss_s
        self.assertAlmostEqual(rm.get('F'), (ss_c / (k - 1)) / (ss_e / ((k - 1) * (n - 1))), places=9)
        S = np.cov(Y, rowvar=False)
        lam = np.linalg.eigvalsh((np.eye(k) - 1 / k) @ S @ (np.eye(k) - 1 / k))         # double-centred
        self.assertAlmostEqual(rm.get('eps_gg'), lam.sum() ** 2 / ((k - 1) * (lam ** 2).sum()), places=9)
        self.assertLess(rm.get('mauchly_p'), 0.01)
        spherical = 10 + subj + rng.normal(0, 1, (n, k))
        from piplotter.analyses import anova_models
        self.assertGreater(anova_models.sphericity(spherical)['p_w'], 0.05)
        # Two within factors (long table): the F of A and of A × B from the univariate sums of squares.
        Y3 = rng.normal(0, 1, (20, 2, 3)) + np.array([[0, 1, 2], [0.5, 1.5, 4]]) + rng.normal(0, 1.5, (20, 1, 1))
        long = pd.DataFrame([(f's{s_}', f'A{i}', f'B{j}', Y3[s_, i, j]) for s_ in range(20) for i in range(2)
                             for j in range(3)], columns=['S', 'fa', 'fb', 'y'])
        r2 = run(long, design='rm', value='y', a='fa', b='fb', subject='S')
        m, mi, mj, mij = Y3.mean(), Y3.mean((0, 2)), Y3.mean((0, 1)), Y3.mean(0)
        ms, msi, msj = Y3.mean((1, 2)), Y3.mean(2), Y3.mean(1)
        ss_ab = 20 * ((mij - mi[:, None] - mj + m) ** 2).sum()
        ss_abs = ((Y3 - msi[:, :, None] - msj[:, None, :] - mij + ms[:, None, None] + mi[None, :, None]
                   + mj[None, None, :] - m) ** 2).sum()
        self.assertAlmostEqual(r2.get('F_AB'), (ss_ab / 2) / (ss_abs / (2 * 19)), places=9)
        # Mixed model on balanced data: its Wald χ² equals (k − 1)·F of the repeated-measures ANOVA.
        Yb = 10 + subj + np.array([0, 0.5, 1.0, 0.2]) + rng.normal(0, 1, (n, k))
        lb = pd.DataFrame(Yb, columns=['c1', 'c2', 'c3', 'c4']).assign(S=[f's{i}' for i in range(n)]) \
            .melt(id_vars='S', var_name='cond', value_name='y')
        rm_b = run(lb, design='rm', value='y', a='cond', subject='S')
        mx = run(lb, design='mixed', value='y', a='cond', subject='S')
        self.assertAlmostEqual(mx.tables[1]['rows'][0][1], (k - 1) * rm_b.get('F'), delta=0.01 * rm_b.get('F'))
        self.assertAlmostEqual(mx.get('icc'), 0.85, delta=0.1)                       # σ²_subject 4, σ²_noise 1
        with self.assertRaises(ValueError):
            run(lb, design='rm', value='y', a='cond')                                # no subject

    def test_cox_recovers_hazard_ratios(self):
        import numpy as np
        import pandas as pd
        from piplotter.analyses.cox import concordance
        rng = np.random.default_rng(7)
        n = 2000
        treat, dose = rng.integers(0, 2, n), rng.normal(0, 1, n)
        t = rng.exponential(1 / (0.1 * np.exp(np.log(2.0) * treat + 0.5 * dose)))
        c = rng.exponential(15, n)
        df = pd.DataFrame({'time': np.minimum(t, c), 'event': (t <= c).astype(int),
                           'group': np.where(treat, 'drug', 'placebo'), 'dose': dose})
        res = self.pm.run('cox', df, {'time': 'time', 'event': 'event', 'covariates': ['group', 'dose']})[2]
        hr = {row[0]: row[1:4] for row in res.tables[0]['rows']}
        self.assertAlmostEqual(hr['group = placebo'][0], 0.5, delta=0.06)            # drug doubles the hazard
        self.assertTrue(hr['dose'][1] < np.exp(0.5) < hr['dose'][2])                 # true HR inside the interval
        tt, ee, rk = df['time'].to_numpy()[:300], df['event'].to_numpy()[:300], (np.log(2) * treat + 0.5 * dose)[:300]
        num = den = 0.0
        for i in range(300):
            later = ee[i] == 1 and tt[i] < tt
            if ee[i]:
                den += np.sum(tt[i] < tt)
                num += np.sum((tt[i] < tt) & (rk[i] > rk)) + 0.5 * np.sum((tt[i] < tt) & (rk[i] == rk))
        self.assertAlmostEqual(concordance(tt, ee, rk), num / den, places=12)
        # Not proportional: the drug group's hazard rises with time (Weibull k = 3) — flagged.
        t2 = np.where(treat == 1, rng.weibull(3, n) * 8, rng.exponential(8, n))
        bad = self.pm.run('cox', pd.DataFrame({'time': t2, 'group': np.where(treat, 'drug', 'placebo')}),
                          {'time': 'time', 'covariates': ['group']})[2]
        self.assertLess(bad.tables[1]['rows'][0][2], 1e-6)

    def test_spots_and_polygon_regions(self):
        import numpy as np
        import pandas as pd
        from piplotter import matrices
        rng = np.random.default_rng(3)
        X, Y = np.meshgrid(np.arange(200.), np.arange(150.))
        true = [(30, 40, 50, 2.0), (80, 100, 30, 3.0), (150, 30, 70, 1.5), (170, 120, 40, 2.5), (60, 120, 60, 2.0),
                (120, 70, 45, 2.2), (199, 75, 60, 2.0)]                            # the last one sits on the edge
        Z = 10 + rng.normal(0, 2, X.shape)
        for cx, cy, a, s_ in true:
            Z += a * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * s_ * s_))
        df = matrices.to_frame(Z, np.arange(200.), np.arange(150.), 'y')
        run = lambda pid, d, p: self.pm.run(pid, d, p, spec={'x': 'y', 'y': []})[2]          # noqa: E731
        base = {'polarity': 'bright', 'smooth': 1, 'min_cells': 3}
        self.assertEqual(run('matrix_spots', df, {**base, 'method': 'sigma', 'k': 5}).get('count'), 7)
        self.assertEqual(run('matrix_spots', df, {**base, 'method': 'otsu'}).get('count'), 7)
        res = run('matrix_spots', df, {**base, 'method': 'sigma', 'k': 5, 'edge': True})
        self.assertEqual(res.get('count'), 6)                                        # the edge one left out
        t = pd.DataFrame(res.tables[0]['rows'], columns=res.tables[0]['columns'])
        found = t[['centroid x', 'centroid y']].to_numpy()
        for cx, cy, _, _ in true[:-1]:
            self.assertLess(np.hypot(found[:, 0] - cx, found[:, 1] - cy).min(), 0.25)  # sub-cell centroids
        dark = matrices.to_frame(20 - (Z - 10), np.arange(200.), np.arange(150.), 'y')
        self.assertEqual(run('matrix_spots', dark, {**base, 'polarity': 'dark', 'method': 'sigma', 'k': 5}).get('count'), 7)
        # A polygon region: a right triangle of legs 80 on a matrix of ones.
        flat = matrices.to_frame(np.ones((100, 100)), np.arange(100.), np.arange(100.), 'y')
        tri = run('matrix_stats', flat, {'corners': '10 10\n90 10\n10 90'})
        self.assertEqual(tri.get('area'), 3200.0)
        self.assertAlmostEqual(tri.get('cells'), 3200, delta=0.05 * 3200)          # the cells whose centre is inside
        self.assertEqual(tri.get('volume'), tri.get('cells'))
        self.assertTrue(any(len(o) for o in [res.overlays]))

    def test_matrix_frequency_filters_and_edges(self):
        import numpy as np
        from piplotter import matrices
        run = lambda df, p: self.pm.run('matrix_filter', df, p, spec={'x': 'y', 'y': []})[2]      # noqa: E731
        X, Y = np.meshgrid(np.arange(64.), np.arange(48.))
        blob = 5 * np.exp(-((X - 30) ** 2 + (Y - 22) ** 2) / (2 * 8.0 ** 2))       # large: σ = 8 cells
        checks = 0.3 * (-1.0) ** (X + Y)                                              # period 2 cells
        df = matrices.to_frame(blob + checks + 2.0, np.arange(64.), np.arange(48.), 'y')
        back = lambda res: matrices.from_wide(res.frame, res.frame.columns[0])[0]     # noqa: E731
        low = back(run(df, {'filter': 'lowpass', 'cutoff': 6, 'order': 4}))
        self.assertLess(np.abs(low - (blob + 2.0)).max(), 0.05)                      # checks gone, blob and mean kept
        high = back(run(df, {'filter': 'highpass', 'cutoff': 6, 'order': 4}))
        self.assertLess(np.abs(high - checks).max(), 0.05)                           # only the checks remain
        ramp = matrices.to_frame(3 * (0.5 * X) + 2 * (0.25 * Y), 0.5 * np.arange(64.), 0.25 * np.arange(48.), 'y')
        grad = back(run(ramp, {'filter': 'edges'}))
        self.assertTrue(np.allclose(grad[2:-2, 2:-2], np.hypot(3, 2)))               # |∇z| in units of x and y

    def test_decimation_keeps_the_peaks(self):
        import numpy as np
        import pandas as pd
        from piplotter import signals
        rng = np.random.default_rng(3)
        x = np.arange(200_000, dtype=float)
        y = rng.normal(0, 1, x.size)
        y[[1234, 98765, 150001]] = [25.0, -30.0, 18.0]
        for method in ('lttb', 'minmax'):
            res = self.pm.run('decimate', pd.DataFrame({'t': x, 's': y}), {'x': 't', 'y': 's', 'method': method,
                                                                        'n': 2000})[2]
            kept = res.frame.iloc[:, 1].to_numpy()
            self.assertLessEqual(len(kept), 2000)
            for v in (25.0, -30.0, 18.0):
                self.assertIn(v, kept, method)                                       # every spike survives
        every = self.pm.run('decimate', pd.DataFrame({'t': x, 's': y}), {'x': 't', 'y': 's', 'method': 'every',
                                                                        'n': 2000})[2]
        self.assertLess(every.frame.iloc[:, 1].max(), 25.0)                          # the naive way loses them
        # M4 is exactly the first, last, lowest and highest point of each slice.
        xs = np.sort(rng.uniform(0, 10, 5000))
        ys = rng.normal(0, 1, 5000)
        b = np.minimum(((xs - xs[0]) / (xs[-1] - xs[0]) * 50).astype(int), 49)
        ref = set()
        for q in range(50):
            w = np.flatnonzero(b == q)
            ref |= {w[0], w[-1], w[np.argmin(ys[w])], w[np.argmax(ys[w])]}
        self.assertEqual(set(signals.m4_indices(xs, ys, 50).tolist()), ref)
        j = signals.lttb_indices(xs, ys, 300)
        self.assertEqual((len(j), j[0], j[-1]), (300, 0, 4999))
        self.assertTrue(np.all(np.diff(j) > 0))

    def test_signal_tools(self):
        import numpy as np
        import pandas as pd
        run = lambda pid, df, p, **kw: self.pm.run(pid, df, p, **kw)[2]              # noqa: E731
        t = np.linspace(0, 1, 1000, endpoint=False)
        slow, fast = np.sin(2 * np.pi * 5 * t), 0.5 * np.sin(2 * np.pi * 120 * t)
        df = pd.DataFrame({'t': t, 's': slow + fast})
        for design in ('butter', 'fft'):                       # frequencies in cycles per unit of x (here Hz)
            for kind, cut, keep in (('lowpass', 30, slow), ('highpass', 30, fast)):
                out = run('frequency_filter', df, {'x': 't', 'y': 's', 'kind': kind, 'cutoff': cut, 'design': design})
                self.assertGreater(np.corrcoef(out.frame.iloc[50:-50, 2], keep[50:-50])[0, 1], 0.999, (design, kind))
        with self.assertRaises(ValueError):                    # above Nyquist (500 Hz)
            run('frequency_filter', df, {'x': 't', 'y': 's', 'cutoff': 900})
        x = np.linspace(-20, 20, 2001)
        line = pd.DataFrame({'x': x, 'y': np.exp(-4 * np.log(2) * x ** 2)})            # FWHM 1
        broad = run('convolution', line, {'x': 'x', 'y': 'y', 'mode': 'convolve', 'kernel': 'gaussian', 'width': 2.0})
        self.assertAlmostEqual(broad.get('fwhm_after'), np.sqrt(5), places=3)          # widths add in quadrature
        back = pd.DataFrame({'x': x, 'y': broad.frame.iloc[:, 2]})
        sharp = run('convolution', back, {'x': 'x', 'y': 'y', 'mode': 'lucy', 'kernel': 'gaussian', 'width': 2.0,
                                          'iterations': 300})
        self.assertAlmostEqual(sharp.get('fwhm_after'), 1.0, delta=0.05)
        wiener = run('convolution', back, {'x': 'x', 'y': 'y', 'mode': 'wiener', 'kernel': 'gaussian', 'width': 2.0,
                                           'noise': 1e-4})
        self.assertLess(wiener.get('fwhm_after'), 1.5)
        xs = np.linspace(0, 10, 25)
        coarse = pd.DataFrame({'x': xs, 'y': np.sin(xs)})
        for method, tol in (('linear', 0.03), ('cubic', 0.01), ('pchip', 0.02), ('akima', 0.01)):
            g = run('interpolate', coarse, {'x': 'x', 'y': 'y', 'method': method, 'n': 200}).frame
            self.assertLess(np.nanmax(np.abs(g.iloc[:, 1] - np.sin(g.iloc[:, 0]))), tol, method)
        g = run('interpolate', coarse, {'x': 'x', 'y': 'y', 'method': 'linear', 'grid': 'values', 'values': '2,5; 12'}).frame
        self.assertAlmostEqual(g.iloc[0, 1], np.interp(2.5, xs, np.sin(xs)))
        self.assertTrue(np.isnan(g.iloc[1, 1]))                                          # no extrapolation
        other = {'name': 'B.csv', 'df': pd.DataFrame({'x': [1.0, 2.0, 3.5]}), 'x': 'x', 'y': [], 'main': False}
        main = {'name': 'A.csv', 'df': coarse, 'x': 'x', 'y': ['y'], 'main': True}
        g = run('interpolate', coarse, {'x': 'x', 'y': 'y', 'method': 'cubic', 'grid': 'file'}, files=[main, other]).frame
        self.assertEqual(list(g.iloc[:, 0]), [1.0, 2.0, 3.5])                           # on the other file's x
        xa, xb = np.linspace(0, 10, 101), np.linspace(-1, 11, 37)                         # different x
        files = [{'name': 'sample', 'df': pd.DataFrame({'x': xa, 'y': 3 * xa + 2}), 'x': 'x', 'y': ['y'], 'main': True},
                 {'name': 'blank', 'df': pd.DataFrame({'x': xb, 'y': xb}), 'x': 'x', 'y': ['y'], 'main': False}]
        diff = run('curve_math', files[0]['df'], {'op': 'sub', 'a': 1, 'b': 2}, files=files).frame
        self.assertTrue(np.allclose(diff['A − B'], 2 * xa + 2))
        scaled = run('curve_math', files[0]['df'], {'op': 'scaled', 'a': 1, 'b': 2, 'k': 3.0}, files=files)
        self.assertTrue(np.allclose(scaled.frame.iloc[:, 3], 2.0))
        with self.assertRaises(ValueError):
            run('curve_math', files[0]['df'], {'op': 'sub', 'a': 1, 'b': 1}, files=files)

    def test_global_fit_subsets_fixed_and_weights(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(2)
        t = np.linspace(0, 40, 60)
        taus = [5, 5, 12, 12]
        files = [{'name': f'S{i}.csv', 'df': pd.DataFrame({'t': t, 'I': (3 + i) * np.exp(-t / tau) + rng.normal(0, 0.05, t.size),
                                                          'e': np.full(t.size, 0.05)}),
                  'x': 't', 'y': ['I'], 'yerr': 'e', 'main': i == 0} for i, tau in enumerate(taus)]
        run = lambda **p: self.pm.run('global_fit', files[0]['df'], {'model': 'exp_decay', **p}, files=files)[2]
        res = run(shared='tau[1,2], tau[3-4]', fixed='C=0')
        report = res.tables[0]
        col = report['columns'].index
        self.assertEqual([round(r[col('tau')]) for r in report['rows']], [5, 5, 12, 12])   # two lifetimes
        self.assertTrue(all(r[col('C')] == 0 and r[col('σ(C)')] is None for r in report['rows']))   # fixed, no error
        self.assertEqual(len([s for s in res.summary if s['label'].startswith('τ')]), 2)
        self.assertIn('χ²_red', [s['label'] for s in res.summary])            # weighted by the error column
        self.assertAlmostEqual(res.get('chi2_red'), 1.0, delta=0.4)
        unweighted = run(shared='tau[1,2], tau[3-4]', fixed='C=0', weights='none')
        self.assertIsNone(unweighted.get('chi2_red'))
        for bad in ({'shared': 'tau[1,5]'}, {'shared': 'tau[1,2], tau[2,3]'}, {'shared': 'tau', 'fixed': 'tau=3'},
                    {'fixed': 'A=1, tau=2, C=0'}, {'fixed': 'k=1'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run(**bad)

    def test_global_fit_constraints_between_parameters(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(5)
        t = np.linspace(0, 60, 120)
        # Two lifetimes, the slow amplitude twice the fast one: A₂ = 2·A₁.
        y = 3 * np.exp(-t / 2) + 6 * np.exp(-t / 15) + 0.1 + rng.normal(0, 0.03, t.size)
        one = [{'name': 'D.csv', 'df': pd.DataFrame({'t': t, 'I': y}), 'x': 't', 'y': ['I'], 'yerr': None, 'main': True}]
        run = lambda files, **p: self.pm.run('global_fit', files[0]['df'], p, files=files)[2]
        res = run(one, model='exp2_decay', constraints='A2 = 2*A1', p0='tau1=1, tau2=20')
        row = dict(zip(res.tables[0]['columns'], res.tables[0]['rows'][0]))
        self.assertAlmostEqual(row['A2'], 2 * row['A1'], places=9)              # computed, not fitted
        self.assertAlmostEqual(row['σ(A2)'], 2 * row['σ(A1)'], delta=1e-6 * row['σ(A1)'] + 1e-12)
        self.assertAlmostEqual(row['A1'], 3, delta=0.15)
        self.assertTrue(any('A2 = 2*A1' in tx for tx in res.texts))
        # The same model written with 2·a in the formula: the same a and the same error.
        same = run(one, model='custom', formula='a*exp(-x/t1) + 2*a*exp(-x/t2) + c', p0='a=3, t1=1, t2=20, c=0')
        alt = dict(zip(same.tables[0]['columns'], same.tables[0]['rows'][0]))
        self.assertAlmostEqual(row['A1'], alt['a'], places=5)
        self.assertAlmostEqual(row['σ(A1)'], alt['σ(a)'], delta=0.01 * alt['σ(a)'])
        self.assertAlmostEqual(row['tau2'], alt['t2'], places=4)
        # Between curves: one τ, the amplitude of curve 2 twice that of curve 1.
        two = [{'name': f'S{i}.csv', 'df': pd.DataFrame({'t': t, 'I': a * np.exp(-t / 8) + rng.normal(0, 0.03, t.size)}),
                'x': 't', 'y': ['I'], 'yerr': None, 'main': i == 0} for i, a in enumerate((2.0, 4.0))]
        res = run(two, model='exp_decay', shared='tau', fixed='C=0', constraints='A[2] = 2*A[1]')
        col = res.tables[0]['columns'].index
        r1, r2 = res.tables[0]['rows']
        self.assertAlmostEqual(r2[col('A')], 2 * r1[col('A')], places=9)
        self.assertAlmostEqual(r2[col('σ(A)')], 2 * r1[col('σ(A)')], delta=1e-6)
        self.assertAlmostEqual(r1[col('A')], 2.0, delta=0.05)
        for bad in ('A2 = 2*A3', 'A2 = 2*A2', 'A2 = 2*A1; A1 = tau1', 'A2 = __import__("os")', 'A2 = A1.real',
                    'A[9] = A[1]', 'A2 2*A1', 'A2 = 2*A1; A2 = A1'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run(one, model='exp2_decay', constraints=bad)
        with self.assertRaises(ValueError):                                     # fixed and constrained
            run(one, model='exp2_decay', constraints='C = 0.1*A1', fixed='C=0')
        with self.assertRaises(ValueError):                                     # shared and constrained
            run(two, model='exp_decay', shared='A', constraints='A[2] = 2*A[1]')

    def test_formula_is_sandboxed(self):
        from importlib import import_module  # noqa: F401
        mod = self.pm.plugins['fit_curve']['module']
        for bad in ('__import__("os").system("x")', 'x.__class__', 'open("f")', 'lambda: x'):
            with self.assertRaises(ValueError):
                mod.compile_formula(bad)


class TestUserPlugins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pm = plugins.PluginManager(user_dir=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_template_creates_working_plugin(self):
        r = self.pm.create('Mio test')
        self.assertEqual(r['errors'], [])
        pid = Path(r['file']).stem
        self.assertEqual(self.pm.plugins[pid]['name'], {'en': 'Mio test', 'it': 'Mio test'})
        _, _, res = self.pm.run(pid, samples.make('spectra'), {'x': 'Wavelength (nm)', 'y': 'Sample A'})
        self.assertEqual(res.frame.shape[1], 3)

    def test_customize_overrides_builtin(self):
        r = self.pm.customize('block_average')
        self.assertTrue((Path(self.tmp.name) / r['file']).exists())
        p = self.pm.plugins['block_average']
        self.assertEqual((p['source'], p['overrides']), ('user', True))
        self.pm.disable(r['file'])
        self.assertEqual(self.pm.plugins['block_average']['source'], 'builtin')
        self.assertTrue((Path(self.tmp.name) / 'block_average.py.disabled').exists())

    def test_errors_are_reported_not_raised(self):
        r = self.pm.save('broken.py', 'PLUGIN = {"id": "broken"}\ndef run(df, p, ctx)\n    pass\n')
        self.assertIn('SyntaxError', r['errors'][0]['error'])
        r = self.pm.save('noid.py', 'PLUGIN = {}\ndef run(df, p, ctx):\n    return ctx.result()\n')
        self.assertTrue(r['errors'])
        self.assertIn('fit_curve', self.pm.plugins)        # built-ins still there

    def test_column_count_limits(self):
        params = [{'id': 'cols', 'type': 'columns', 'min_count': 2, 'max_count': 3, 'label': {'en': 'Columns'}}]
        df = samples.make('cloud')
        self.assertEqual(plugins.coerce_params(params, {'cols': ['x', 'y', 'z']}, df)['cols'], ['x', 'y', 'z'])
        for chosen in (['x'], ['x', 'y', 'z', 'w']):
            with self.assertRaises(plugins.PluginError):
                plugins.coerce_params(params, {'cols': chosen}, df)

    def test_unsafe_file_names_rejected(self):
        for name in ('../evil.py', 'a/b.py', 'x.sh', '.hidden.py'):
            with self.assertRaises(plugins.PluginError):
                self.pm.save(name, '')


class TestPersistentToken(unittest.TestCase):
    def test_token_survives_restart(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as home:
            code = ('import os, sys, runpy; sys.argv=["x"]; '
                    'g = runpy.run_path(r"%s", run_name="not_main"); print(g["persistent_token"]())' % (root / 'start_piplotter.py'))
            env = dict(os.environ, PIPLOTTER_HOME=home, PIPLOTTER_NO_VENV='1')
            a = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True).stdout.strip()
            b = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True).stdout.strip()
            self.assertTrue(len(a) >= 32)
            self.assertEqual(a, b)
            if os.name != 'nt':
                self.assertEqual(os.stat(Path(home) / 'token').st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
