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


if __name__ == '__main__':
    unittest.main()
