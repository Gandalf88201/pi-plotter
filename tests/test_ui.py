"""Smoke tests of the page in a real browser: the main paths a user takes, end to end.

They start π-plotter on a free port with its own state folder (nothing of yours is touched), drive the system
Chrome with Playwright (no browser download) and fail on any JavaScript error. Skipped when Playwright or Chrome
is missing:

    python -m pip install playwright        # development only, in any Python
    python -m unittest tests.test_ui         # with that Python; the service runs with .venv's Python
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
CHROME = Path('/Applications/Google Chrome.app')

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                  # the tests are skipped
    sync_playwright = None


def service_python():
    venv = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    return str(venv) if venv.exists() else sys.executable


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@unittest.skipUnless(sync_playwright is not None, 'needs Playwright (pip install playwright)')
class TestPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.port = free_port()
        cls.token = 'uitest' + str(cls.port)
        env = dict(os.environ, PIPLOTTER_HOME=str(tmp / 'home'), PIPLOTTER_SESSION=str(tmp / 'session'),
                   PIPLOTTER_TOKEN=cls.token, PIPLOTTER_NO_VENV='1', MPLBACKEND='Agg')
        cls.server = subprocess.Popen([service_python(), str(ROOT / 'start_piplotter.py'), '--no-browser', '--offline',
                                       '--port', str(cls.port)], cwd=ROOT, env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cls.url = f'http://127.0.0.1:{cls.port}/'
        for _ in range(120):
            try:
                urllib.request.urlopen(cls.url, timeout=1).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            cls.server.kill()
            raise RuntimeError('π-plotter did not start: ' + cls.server.stdout.read().decode(errors='replace')[-2000:])
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch(channel='chrome', headless=True)
        except Exception as exc:                      # no system Chrome
            cls.pw.stop()
            cls.server.kill()
            raise unittest.SkipTest(f'needs Google Chrome: {exc}')
        # Data files made here, opened through the page like a user would.
        cls.data = tmp / 'data'
        cls.data.mkdir()
        rows = '\n'.join(f'{i},{60 + (i * 37 % 23)}' for i in range(400))
        (cls.data / 'A.csv').write_text('Frame,angle\n' + rows + '\n', encoding='utf-8')
        rows = '\n'.join(f'{x},{2 * x + 1 if x != 7 else 90}' for x in range(12))    # a line with one wild point
        (cls.data / 'line.csv').write_text('x,y\n' + rows + '\n', encoding='utf-8')
        rows = '\n'.join(f'{i},{-100 - (i * 41 % 19)}' for i in range(400))
        (cls.data / 'B.csv').write_text('Frame,dihedral\n' + rows + '\n', encoding='utf-8')
        for name, amp in (('D1.csv', 4), ('D2.csv', 9)):                          # decays with one lifetime, 6 s
            rows = '\n'.join(f'{t},{amp * 2.718281828 ** (-t / 6) + 0.5:.6f}' for t in range(40))
            (cls.data / name).write_text('time (s),signal\n' + rows + '\n', encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.terminate()
        try:
            cls.server.wait(10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
        cls.server.stdout.close()
        cls._tmp.cleanup()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1400, 'height': 900}, locale='en-US',
                                          accept_downloads=True)
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.goto(self.url)
        self.page.evaluate("() => setLang('en')")
        self.page.wait_for_function('() => state.ready === true', timeout=30000)     # handlers bound

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [], 'JavaScript errors on the page')

    # ---------------------------------------------------------------- helpers
    def drawn(self, timeout=30000):
        """Wait for the figure on screen to be drawn without an error."""
        self.page.wait_for_function("""() => state.dataset && state.drawn && state.drawn.spec === state.spec
            && document.querySelector('#spinner').hidden""", timeout=timeout)
        err = self.page.locator('#errorBox')
        self.assertFalse(err.is_visible(), err.inner_text() if err.is_visible() else '')

    def open_files(self, *names):
        self.page.set_input_files('#fileInput', [str(self.data / n) for n in names])
        self.page.wait_for_function(f'() => Files.list().length >= {len(names)}', timeout=30000)
        self.drawn()

    def kind(self, name):
        self.page.click(f'.kind[data-kind="{name}"]')
        self.drawn()

    def run_analysis(self, pid):
        self.page.select_option('#anSelect', pid)
        self.page.locator('#anMain button', has_text='Run analysis').click()
        self.page.wait_for_function("() => !document.querySelector('#anMain button.primary')?.disabled", timeout=60000)
        self.page.wait_for_selector('#anResults table', timeout=60000)

    def state(self, expr):
        return self.page.evaluate(f'() => {expr}')

    # ---------------------------------------------------------------- the paths
    def test_example_figure_suggestions_and_export(self):
        self.page.click('[data-sample="ir"]')
        self.drawn()
        self.page.wait_for_selector('#anSuggest .chip')
        chips = self.page.locator('#anSuggest .chip').all_inner_texts()
        self.assertEqual(chips[0], 'Baseline')
        self.page.select_option('#exportFormat', 'png')
        with self.page.expect_download() as dl:
            self.page.click('#btnExport')
        self.assertTrue(dl.value.suggested_filename.endswith('.png'))

    def test_global_fit_of_two_files(self):
        self.open_files('D1.csv', 'D2.csv')
        self.kind('scatter')
        self.page.locator('#anSuggest .chip', has_text='Global fit').click()       # suggested, with τ shared
        self.page.locator('#anMain button', has_text='Run analysis').click()
        self.page.wait_for_selector('#anResults table', timeout=60000)
        self.drawn()
        report = self.page.locator('#anResults table', has_text='σ(tau)')
        self.assertEqual(report.locator('tbody tr').count(), 2)                 # one row per file
        notes = self.state('state.spec.overlays.map(o => o.note || "")')
        self.assertEqual(len(notes), 2)                                         # a curve per file, on the copy
        self.assertTrue(notes[0].startswith('τ = '), notes)
        self.assertAlmostEqual(float(notes[0].split()[2]), 6.0, places=4)          # the shared lifetime

    def test_two_files_lines_switch_and_gaussians(self):
        self.open_files('A.csv', 'B.csv')
        self.kind('line')
        self.assertEqual(len(self.state('state.drawn.list')), 2)              # both curves
        colours = self.state('state.drawn.list.map(e => e.color)')
        self.page.locator('#loadedList .file-row', has_text='B.csv').locator('.fname').click()
        self.drawn()
        self.assertEqual(self.state('state.spec.kind'), 'line')                # the figure stays
        self.assertEqual(self.state('state.drawn.list.map(e => e.color)'), colours)   # and its colours
        self.kind('hist')
        self.run_analysis('recipe_gaussian')                                   # on B
        self.page.locator('#loadedList .file-row', has_text='A.csv').locator('.fname').click()
        self.drawn()
        self.run_analysis('recipe_gaussian')                                   # on A: same copy
        self.drawn()
        layers = self.state('state.spec.overlays.map(o => (o.note || "").split("\\n")[0])')
        self.assertEqual(len(layers), 2)
        self.assertTrue(all(n.startswith('mean = ') for n in layers), layers)

    def test_new_table_typing_formula_undo_and_project(self):
        self.page.click('#btnNewTable')
        self.page.wait_for_selector('#tableBox td[data-r="0"][data-c="0"]')
        self.page.click('#tableBox td[data-r="0"][data-c="0"]')
        for value in ('1', '2', '3'):                                         # A1…A3, Enter goes down
            self.page.keyboard.type(value)
            self.page.keyboard.press('Enter')
            self.page.wait_for_function(f'() => state.dataset.preview.filter(r => r[0] !== null).length >= {value}')
        self.page.evaluate("() => { const a = ['B', 'A * 10']; window.prompt = () => a.shift(); }")
        self.page.locator('.table-tools button', has_text='Column formula').click()
        self.page.wait_for_function("() => state.dataset.preview[2][1] === 30")
        self.page.keyboard.press('Meta+z' if sys.platform == 'darwin' else 'Control+z')   # the formula goes…
        self.page.wait_for_function("() => state.dataset.preview[2][1] === null")
        self.page.evaluate("() => { const a = ['B', 'A * 10']; window.prompt = () => a.shift(); }")
        self.page.locator('.table-tools button', has_text='Column formula').click()   # …and comes back
        self.page.wait_for_function("() => state.dataset.preview[2][1] === 30")

        # Save the project, open it again: the table is rebuilt from its list of edits.
        self.page.evaluate("() => { window.prompt = () => 'ui-test'; window.confirm = () => true; }")
        with self.page.expect_download() as dl:
            self.page.click('#btnSaveProject')
        path = dl.value.path()
        self.assertEqual(dl.value.suggested_filename, 'ui-test.piplot')
        self.page.click('[data-sample="spectra"]')                            # something else on screen
        self.drawn()
        self.page.set_input_files('#projectInput', path)
        self.page.wait_for_function("() => state.dataset && state.dataset.columns.map(c => c.name).join() === 'A,B'",
                                    timeout=30000)
        self.assertEqual(self.state('state.dataset.preview.slice(0, 3).map(r => r[1])'), [10, 20, 30])

    def test_fit_follows_edits_and_excluded_points(self):
        self.open_files('line.csv')
        self.kind('scatter')
        self.page.select_option('#anSelect', 'fit_curve')
        self.page.select_option('#anMain [data-param="model"] select', 'linear')
        self.page.locator('#anMain button', has_text='Run analysis').click()
        self.page.wait_for_function("() => state.view && state.spec.overlays.some(o => o.note)", timeout=60000)
        slope = "() => parseFloat(state.spec.overlays.find(o => o.note).note.match(/a = ([-0-9.]+)/)[1])"
        self.assertGreater(self.page.evaluate(slope), 2.3)                # pulled by the wild point
        # Exclude it from the table: the fit on the copy runs again by itself.
        self.page.click('.tab[data-tab="table"]')
        self.page.wait_for_selector('#tableBox td.idx >> text="8"')
        self.page.locator('#tableBox td.idx', has_text='8').first.click()
        self.page.locator('.table-tools button', has_text='Exclude 1 rows').click()
        self.page.wait_for_function(f'() => ({slope})() < 2.01 && ({slope})() > 1.99', timeout=60000)
        self.page.wait_for_selector('#tableBox tr.masked')
        # An edit of a value: the fit follows again (y of x = 0 from 1 to 31 changes the line).
        self.page.click('#tableBox td[data-r="0"][data-c="1"]')
        self.page.keyboard.type('31')
        self.page.keyboard.press('Enter')
        self.page.wait_for_function(f'() => ({slope})() < 1.99', timeout=60000)
        # Back to the original figure: it shows the edited table, not the old one.
        self.page.evaluate("() => showView(null)")
        self.assertEqual(self.state("state.dataset.preview[0][1]"), 31)

    def test_wrong_input_is_reported_not_frozen(self):
        self.open_files('A.csv')
        self.page.evaluate("() => { state.spec.y = []; }")
        self.kind('line')                                                      # Lines picks a Y column itself
        self.assertEqual(self.state('state.spec.y'), ['angle'])
        self.page.evaluate("() => { window.prompt = () => 'B'; }")
        self.page.click('.tab[data-tab="table"]')
        self.page.evaluate("() => { const a = ['C', 'nonsense(('] ; window.prompt = () => a.shift(); }")
        self.page.locator('.table-tools button', has_text='Column formula').click()
        self.page.wait_for_selector('.toast.err', timeout=10000)                  # a message, the table unchanged
        self.assertEqual(self.state('state.dataset.columns.length'), 2)


if __name__ == '__main__':
    unittest.main()
