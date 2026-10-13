"""Tables written or edited by hand (piplotter/tables.py) and their service endpoints."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from piplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from piplotter import tables  # noqa: E402
from piplotter.tables import TableError, apply_ops  # noqa: E402


class TestCells(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(tables.parse_cell('1.5'), 1.5)
        self.assertEqual(tables.parse_cell('1,5'), 1.5)            # decimal comma
        self.assertEqual(tables.parse_cell('-2e3'), -2000.0)
        self.assertTrue(np.isnan(tables.parse_cell('')))
        self.assertTrue(np.isnan(tables.parse_cell(None)))
        self.assertEqual(tables.parse_cell('1,000,5'), '1,000,5')   # not a number: kept as text
        self.assertEqual(tables.parse_cell('sample A'), 'sample A')

    def test_column_names(self):
        self.assertEqual(tables.column_names(3), ['A', 'B', 'C'])
        self.assertEqual(tables.column_names(2, ['A', 'C']), ['B', 'D'])
        self.assertEqual(tables.column_names(28)[-2:], ['AA', 'AB'])


class TestOps(unittest.TestCase):
    def test_blank_and_typing(self):
        df = tables.blank(2, 3)
        self.assertEqual(list(df.columns), ['A', 'B'])
        out = apply_ops(df, [{'op': 'set', 'row': 0, 'col': 'A', 'value': '1,5'},
                             {'op': 'set', 'row': 3, 'col': 'B', 'value': '7'}])     # just past the end: a new row
        self.assertEqual(len(out), 4)
        self.assertEqual(out.at[0, 'A'], 1.5)
        self.assertEqual(out.at[3, 'B'], 7.0)
        self.assertTrue(pd.api.types.is_float_dtype(out['B']))
        self.assertEqual(len(df), 3)                                 # the original is not changed

    def test_text_makes_a_text_column_and_back(self):
        df = tables.blank(1, 2)
        out = apply_ops(df, [{'op': 'set', 'row': 0, 'col': 'A', 'value': 'ctrl'}])
        self.assertFalse(pd.api.types.is_numeric_dtype(out['A']))
        back = apply_ops(out, [{'op': 'set', 'row': 0, 'col': 'A', 'value': '3'}])
        self.assertTrue(pd.api.types.is_numeric_dtype(back['A']))

    def test_paste_grows_the_table(self):
        df = tables.blank(1, 1)
        out = apply_ops(df, [{'op': 'paste', 'row': 0, 'col': 'A',
                              'values': [['1', '2', 'x'], ['3', '4,5', 'y'], ['5', '', 'z']]}])
        self.assertEqual(out.shape, (3, 3))
        self.assertEqual(list(out['B'].iloc[:2]), [2.0, 4.5])
        self.assertTrue(np.isnan(out['B'].iloc[2]))
        self.assertEqual(list(out['C']), ['x', 'y', 'z'])

    def test_rows_and_columns(self):
        df = pd.DataFrame({'t': [0.0, 1.0, 2.0], 'y': [5.0, 6.0, 7.0]})
        out = apply_ops(df, [{'op': 'add_rows', 'n': 2, 'at': 1}, {'op': 'del_rows', 'rows': [0]},
                             {'op': 'add_col', 'name': 'z'}, {'op': 'rename', 'col': 'y', 'to': 'signal'},
                             {'op': 'del_col', 'col': 't'}])
        self.assertEqual(list(out.columns), ['signal', 'z'])
        self.assertEqual(len(out), 4)
        self.assertEqual(out['signal'].iloc[2], 6.0)
        with self.assertRaises(TableError):
            apply_ops(df, [{'op': 'rename', 'col': 't', 'to': 'y'}])       # name already used
        with self.assertRaises(TableError):
            apply_ops(df, [{'op': 'set', 'row': 9, 'col': 't', 'value': 1}])
        with self.assertRaises(TableError):
            apply_ops(df, [{'op': 'drop_everything'}])

    def test_formula(self):
        df = pd.DataFrame({'A': [1.0, 4.0, 9.0], 'time (s)': [60.0, 120.0, 180.0]})
        out = apply_ops(df, [{'op': 'formula', 'col': 'B', 'expr': 'sqrt(A) * 2'},
                             {'op': 'formula', 'col': 'min', 'expr': 'col("time (s)") / 60'},
                             {'op': 'formula', 'col': 'C', 'expr': 'A - mean(A)'},
                             {'op': 'formula', 'col': 'D', 'expr': 'i'},
                             {'op': 'formula', 'col': 'E', 'expr': 'A if A > 2 else 0'}])
        self.assertEqual(list(out['B']), [2.0, 4.0, 6.0])
        self.assertEqual(list(out['min']), [1.0, 2.0, 3.0])
        self.assertAlmostEqual(out['C'].sum(), 0.0)
        self.assertEqual(list(out['D']), [0.0, 1.0, 2.0])
        self.assertEqual(list(out['E']), [0.0, 4.0, 9.0])

    def test_formula_is_safe(self):
        df = pd.DataFrame({'A': [1.0]})
        for bad in ('__import__("os")', 'A.__class__', '[x for x in A]', 'open("x")', 'lambda: 1', 'A; B'):
            with self.subTest(bad=bad), self.assertRaises(TableError):
                tables.evaluate(df, bad)

    def test_mask_follows_the_rows(self):
        df = pd.DataFrame({'x': [0.0, 1, 2, 3, 4], 'y': [0.0, 1, 2, 3, 4]})
        out = apply_ops(df, [{'op': 'mask', 'rows': [1, 3]}])
        self.assertEqual(tables.masked(out), [1, 3])
        self.assertEqual(list(tables.kept(out)['y']), [0.0, 2, 4])
        out = apply_ops(out, [{'op': 'add_rows', 'n': 2, 'at': 0}])          # rows above: the mask moves down
        self.assertEqual(tables.masked(out), [3, 5])
        out = apply_ops(out, [{'op': 'del_rows', 'rows': [0, 3]}])          # a deleted row leaves the mask
        self.assertEqual(tables.masked(out), [3])
        self.assertEqual(out['y'].iloc[3], 3.0)
        out = apply_ops(out, [{'op': 'mask', 'rows': [3], 'value': False}])
        self.assertEqual(tables.masked(out), [])
        self.assertEqual(tables.page(apply_ops(df, [{'op': 'mask', 'rows': [4]}]), 0, 3)['masked'], [])

    def test_nearest_point(self):
        df = pd.DataFrame({'t': [0.0, 10, 20], 'a': [1.0, 100, 1], 'b': [50.0, 50, 50]})
        hit = tables.nearest(df, 't', ['a', 'b'], 9.0, 95.0, [0, 20], [0, 100])
        self.assertEqual(hit['row'], 1)
        self.assertLess(hit['distance'], 0.1)
        self.assertIsNone(tables.nearest(df, 't', ['nope'], 0, 0, [0, 1], [0, 1]))

    def test_page(self):
        df = pd.DataFrame({'a': range(500), 'b': range(500)})
        p = tables.page(df, 450, 100)
        self.assertEqual((p['start'], p['total'], len(p['rows'])), (450, 500, 50))


@unittest.skipUnless(__import__('importlib').util.find_spec('scipy') is not None, 'needs scipy')
class TestService(unittest.TestCase):
    def setUp(self):
        from piplotter.server import App
        from piplotter.modules import ModuleManager
        self._tmp = tempfile.TemporaryDirectory()
        mods = ModuleManager()
        mods.require = lambda ids: None
        self.app = App('t', Path(self._tmp.name), mods, 10 ** 9)

    def tearDown(self):
        self._tmp.cleanup()

    def test_new_edit_undo_reopen(self):
        new = self.app.blank_table({'cols': 2, 'rows': 3, 'name': 'by hand'})
        ed = self.app.edit_table({'dataset_id': new['dataset_id'], 'ops': [
            {'op': 'paste', 'row': 0, 'col': 'A', 'values': [['1', '10'], ['2', '20'], ['3', '30']]}]})
        ed2 = self.app.edit_table({'dataset_id': ed['dataset_id'], 'ops': [
            {'op': 'formula', 'col': 'C', 'expr': 'A * B'}]})
        self.assertEqual(ed2['replaces'], ed['dataset_id'])
        self.assertEqual(len(ed2['source']['ops']), 2)                 # one flat list of operations
        df = self.app.dataset(ed2['dataset_id'])['df']
        self.assertEqual(list(df['C']), [10.0, 40.0, 90.0])
        self.assertEqual(list(self.app.dataset(ed['dataset_id'])['df'].columns), ['A', 'B'])   # undo = previous
        again = self.app.reopen(ed2['source'])                          # after a restart
        self.assertTrue(self.app.dataset(again['dataset_id'])['df'].equals(df))
        rows = self.app.table_rows({'dataset_id': ed2['dataset_id'], 'start': 1, 'count': 1})
        self.assertEqual(rows['rows'], [[2.0, 20.0, 40.0]])

    def test_excluded_rows_leave_analyses_and_curves(self):
        new = self.app.blank_table({'cols': 2, 'rows': 0})
        pts = [[str(x), str(2 * x + 1)] for x in range(10)] + [['10', '500']]          # one wild point
        ds = self.app.edit_table({'dataset_id': new['dataset_id'], 'ops': [{'op': 'paste', 'row': 0, 'col': 'A', 'values': pts}]})
        fit = lambda d: self.app.run_analysis({'dataset_id': d['dataset_id'], 'id': 'fit_curve', 'lang': 'en', 'spec': {},
                                              'params': {'x': 'A', 'y': 'B', 'model': 'linear', 'source': 'xy'}})
        slope = lambda r: next(row[1] for row in r['tables'][0]['rows'] if row[0] == 'a')
        self.assertGreater(slope(fit(ds)), 10)                                       # the outlier pulls the line
        hit = self.app.table_nearest({'dataset_id': ds['dataset_id'], 'x': 'A', 'ys': ['B'], 'px': 10, 'py': 480,
                                      'xlim': [0, 10], 'ylim': [0, 500]})
        self.assertEqual((hit['row'], hit['masked']), (10, False))
        out = self.app.edit_table({'dataset_id': ds['dataset_id'], 'ops': [{'op': 'mask', 'rows': [hit['row']]}]})
        self.assertEqual(out['masked'], 1)
        self.assertAlmostEqual(slope(fit(out)), 2.0, places=6)                       # excluded: the true line
        svg, _ = self.app.render({'dataset_id': out['dataset_id'], 'spec': {'kind': 'scatter', 'x': 'A', 'y': ['B']}},
                                 export='svg')
        self.assertIn(b'excluded', svg)                                              # drawn apart, in the legend
        again = self.app.reopen(out['source'])                                       # and it survives a project
        self.assertEqual(again['masked'], 1)


    def test_global_fit_takes_every_file_of_the_figure(self):
        sets = []
        for amp in (4, 8):
            new = self.app.blank_table({'cols': 2, 'rows': 0})
            pts = [[str(t), str(amp * np.exp(-t / 5) + 1)] for t in range(0, 30)]
            sets.append(self.app.edit_table({'dataset_id': new['dataset_id'],
                                             'ops': [{'op': 'paste', 'row': 0, 'col': 'A', 'values': pts}]}))
        wild = self.app.edit_table({'dataset_id': sets[1]['dataset_id'], 'ops': [
            {'op': 'set', 'row': 29, 'col': 'B', 'value': '90'}, {'op': 'mask', 'rows': [29]}]})
        spec = {'kind': 'scatter', 'x': 'A', 'y': ['B'],
                'extra': [{'id': 'e1', 'dataset_id': wild['dataset_id'], 'name': 'second', 'x': 'A', 'y': ['B']}]}
        out = self.app.run_analysis({'dataset_id': sets[0]['dataset_id'], 'id': 'global_fit', 'lang': 'en', 'spec': spec,
                                     'params': {'model': 'exp_decay', 'shared': 'tau'}})
        report = next(t for t in out['tables'] if t['title'].startswith('Fit report'))
        self.assertEqual(len(report['rows']), 2)
        self.assertEqual([r[report['columns'].index('N')] for r in report['rows']], [30, 29])   # excluded point left out
        tau = report['rows'][0][report['columns'].index('tau')]
        self.assertAlmostEqual(tau, 5.0, places=4)


    def test_batch_runs_one_analysis_on_every_file(self):
        def table(amp, n=30, names=None):
            new = self.app.blank_table({'cols': 2, 'rows': 0})
            ops = [{'op': 'paste', 'row': 0, 'col': 'A',
                    'values': [[str(t), str(amp * np.exp(-t / 5) + 1)] for t in range(n)]}]
            if names:
                ops += [{'op': 'rename', 'col': 'A', 'to': names[0]}, {'op': 'rename', 'col': 'B', 'to': names[1]}]
            return self.app.edit_table({'dataset_id': new['dataset_id'], 'ops': ops})
        sets = [table(4), table(8, names=('t', 'signal')), table(3, n=2)]       # other names; too few points
        files = [{'dataset_id': d['dataset_id'], 'source': d['source'], 'name': f'f{k}', 'x': x, 'y': [y]}
                 for k, (d, (x, y)) in enumerate(zip(sets, [('A', 'B'), ('t', 'signal'), ('A', 'B')]))]
        out = self.app.batch_analysis({'id': 'fit_curve', 'lang': 'en', 'files': files, 'main': {'x': 'A', 'y': ['B']},
                                       'params': {'x': 'A', 'y': 'B', 'model': 'exp_decay', 'source': 'xy'}})
        rows, cols = out['tables'][0]['rows'], out['tables'][0]['columns']
        self.assertEqual([r[1] for r in rows], ['f0', 'f1'])                     # the X/Y names follow each file
        tau = 'tau'                                                              # the fit's own names
        self.assertTrue(all(abs(r[cols.index(tau)] - 5) < 1e-4 for r in rows))
        self.assertIn(f'σ({tau})', cols)
        self.assertEqual([r[0] for r in out['tables'][1]['rows']], ['f2'])      # listed apart, the others still done
        self.assertEqual(out['plot']['x'], '#')
        again = self.app.reopen(out['dataset']['source'])                         # projects: rebuilt from the files
        self.assertTrue(self.app.dataset(again['dataset_id'])['df'].equals(self.app.dataset(out['dataset']['dataset_id'])['df']))


    def test_layout_of_figures_with_their_own_data(self):
        from piplotter.server import ApiError
        a = self.app.edit_table({'dataset_id': self.app.blank_table({'cols': 2, 'rows': 0})['dataset_id'], 'ops': [
            {'op': 'paste', 'row': 0, 'col': 'A', 'values': [[str(x), str(x * x)] for x in range(10)]}]})
        b = self.app.sample('kinetics')
        spec = {'kind': 'line', 'figure': {'width': 160, 'height': 60}, 'layout': {'ncols': 2},
                'compose': [{'dataset_id': a['dataset_id'], 'source': a['source'], 'spec': {'kind': 'scatter', 'x': 'A', 'y': ['B']}},
                            {'dataset_id': 'gone', 'source': b['source'],                     # rebuilt from its source
                             'spec': {'kind': 'line', 'x': 'Time (min)', 'y': ['Concentration (mM)']}}]}
        info = {}
        png, mime = self.app.render({'dataset_id': a['dataset_id'], 'spec': spec, 'dpi': 40}, info=info)
        self.assertTrue(png.startswith(b'\x89PNG'))
        self.assertEqual(info['axes'], [])                                      # nothing to zoom on a layout
        self.assertEqual(sorted(m['id'] for m in info['movables']), ['panel:0', 'panel:1'])
        svg, _ = self.app.render({'dataset_id': a['dataset_id'], 'spec': spec}, export='svg')
        self.assertIn(b'(b)', svg)
        with self.assertRaises(ApiError):
            self.app.render({'dataset_id': a['dataset_id'], 'spec': spec}, export='html')

    def test_every_kind_draws_in_a_layout(self):
        # A panel is a matplotlib SubFigure, which lacks some Figure methods (get_size_inches broke the
        # correlation matrix in a layout): every kind that draws alone must draw as a panel, value boxes included.
        from piplotter import plotting
        rows = [[f'{i % 7 + 0.1 * i:.2f}', f'{(i * 37) % 11 - 5:.1f}', f'{(i * 13) % 5:.1f}', 'abc'[i % 3]]
                for i in range(40)]
        t = self.app.edit_table({'dataset_id': self.app.blank_table({'cols': 4, 'rows': 0})['dataset_id'], 'ops': [
            {'op': 'paste', 'row': 0, 'col': 'A', 'values': rows}]})
        notes = [{'id': 'n1', 'text': 'a = 1'}, {'id': 'n2', 'text': 'b = 2'}]       # two boxes: stacked, not overlapping
        drawn = []
        for kind in plotting.PLOTTERS:
            panel = {'kind': kind, 'x': 'A', 'y': ['B'], 'z': 'C', 'notes': notes}
            if kind == 'pie':
                panel['x'] = 'D'
            try:
                self.app.render({'dataset_id': t['dataset_id'], 'spec': panel, 'dpi': 30})
            except Exception:
                continue                                  # a kind these columns do not suit: not a layout matter
            spec = {'kind': 'line', 'layout': {'ncols': 2}, 'compose': [
                {'dataset_id': t['dataset_id'], 'source': t['source'], 'spec': panel}] * 2}
            png, _ = self.app.render({'dataset_id': t['dataset_id'], 'spec': spec, 'dpi': 30})
            self.assertTrue(png.startswith(b'\x89PNG'), kind)
            drawn.append(kind)
        self.assertIn('corr', drawn)
        self.assertGreater(len(drawn), len(plotting.PLOTTERS) * 0.8)


if __name__ == '__main__':
    unittest.main()
