"""The Python console: code run in a process of its own that keeps its variables, can be stopped, and opens tables."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from piplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()


def has(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


@unittest.skipUnless(has('pandas') and has('matplotlib') and has('scipy'), 'pandas, matplotlib and scipy needed')
class TestConsole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from piplotter.console import Console
        from piplotter import samples
        cls.console = Console()
        cls.df = samples.make('kinetics')

    @classmethod
    def tearDownClass(cls):
        cls.console.close()

    def run_code(self, code, **kw):
        return self.console.run(code, df=self.df, df_id='kinetics', **kw)

    def kinds(self, out):
        return [o['type'] for o in out['outputs']]

    def test_variables_values_text_and_errors(self):
        out = self.run_code("a = 6\nprint('hello', a)\na * 7")
        self.assertEqual(self.kinds(out), ['text', 'value'])
        self.assertEqual(out['outputs'][0]['text'], 'hello 6\n')
        self.assertEqual(out['outputs'][1]['text'], '42')
        self.assertIn('a', out['variables'])
        self.assertEqual(self.run_code('a + 1')['outputs'][0]['text'], '7')          # kept from one run to the next
        table = self.run_code("df[['Time (min)', 'Concentration (mM)']].head(3)")['outputs'][0]
        self.assertEqual((table['type'], table['shape']), ('table', [3, 2]))
        self.assertIn('Concentration (mM)', table['html'])
        err = self.run_code("x = 1\n1 / 0")['outputs'][0]
        self.assertEqual(err['type'], 'error')
        self.assertIn('line 2', err['text'])
        self.assertIn('ZeroDivisionError', err['text'])
        self.assertNotIn('console.py', err['text'])                                   # only the user's lines
        self.assertEqual(self.run_code('x')['outputs'][0]['text'], '1')               # lines before the error ran
        self.assertEqual(self.kinds(self.run_code('def f(:')), ['error'])             # a syntax error is reported

    def test_figures_analyses_and_tables(self):
        out = self.run_code("plt.plot([1, 2, 3])\nres = run('fit_curve', x='Time (min)', y='Concentration (mM)', "
                            "model='exp_decay')\nnew_table({'t': [1.0, 2.0], 'label': ['a', 'b']}, 'small')\n"
                            "round(res.get('tau'), 1)")
        self.assertIn('image', self.kinds(out))
        self.assertEqual(out['outputs'][0]['text'], '13.5')                          # the analysis of the page
        self.assertEqual(self.run_code('np.float64(2.5)')['outputs'][0]['text'], '2.5')    # NumPy numbers plain
        name, frame = out['tables'][0]
        self.assertEqual((name, frame.shape), ('small', (2, 2)))
        self.assertEqual(self.run_code('res')['outputs'][0]['type'], 'table')        # a result shown as its values

    def test_stop_timeout_and_reset(self):
        self.run_code('keep = 1')
        threading.Timer(1.0, self.console.stop).start()
        started = time.time()
        out = self.run_code('while True:\n    pass')
        self.assertLess(time.time() - started, 15)
        self.assertEqual(out['outputs'][0]['code'], 'stopped')
        self.assertEqual(self.run_code("'keep' in dir()")['outputs'][0]['text'], 'False')    # a fresh Python
        out = self.run_code('import time\ntime.sleep(30)', timeout=1.5)
        self.assertEqual(out['outputs'][0]['code'], 'timeout')
        self.run_code('z = 3')
        self.console.reset()
        self.assertEqual(self.run_code("'z' in dir()")['outputs'][0]['text'], 'False')


@unittest.skipUnless(has('pandas') and has('matplotlib') and has('scipy'), 'pandas, matplotlib and scipy needed')
class TestConsoleInTheService(unittest.TestCase):
    def test_tables_made_in_the_console_are_kept_like_typed_ones(self):
        from piplotter.server import App
        from piplotter.modules import ModuleManager
        mods = ModuleManager()
        mods.require = lambda ids: None
        with tempfile.TemporaryDirectory() as tmp:
            app = App('t', Path(tmp), mods, 10 ** 9)
            try:
                k = app.sample('kinetics')
                out = app.console_run({'code': "early = df[df['Time (min)'] < 20].copy()\n"
                                               "early['log c'] = np.log(early['Concentration (mM)'])\n"
                                               "new_table(early, 'early')\nsorted(files)",
                                       'dataset_id': k['dataset_id'],
                                       'files': [{'name': 'kin', 'dataset_id': k['dataset_id']}]})
                self.assertEqual(out['outputs'][0]['text'], "['kin']")
                made = out['tables'][0]
                self.assertEqual((made['name'], made['rows']), ('early', 8))
                self.assertEqual(made['columns'][-1]['name'], 'log c')
                again = app.reopen(made['source'])                      # a project rebuilds it from its source
                self.assertTrue(app.dataset(again['dataset_id'])['df'].equals(app.dataset(made['dataset_id'])['df']))
                none = app.console_run({'code': 'df is None'})          # no data open: the console still works
                self.assertEqual(none['outputs'][0]['text'], 'True')
            finally:
                app.console_reset()


if __name__ == '__main__':
    unittest.main()
