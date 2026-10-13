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

    def test_batch_on_every_file(self):
        self.open_files('D1.csv', 'D2.csv', 'A.csv')
        self.kind('scatter')
        self.page.select_option('#anSelect', 'fit_curve')
        self.page.select_option('#anMain [data-param="model"] select', 'exp_decay')
        self.page.locator('#anMain button', has_text='Run on all 3 files').click()
        self.page.wait_for_selector('#anResults table', timeout=60000)
        self.drawn()
        tables = self.page.locator('#anResults table')
        files = tables.first.locator('tbody tr td:nth-child(2)').all_inner_texts()
        self.assertEqual(files[:2], ['D1.csv', 'D2.csv'])                       # one row per file that fits
        self.assertEqual(self.state('state.dataset.source.batch'), 'fit_curve')  # plotted as a figure of its own
        self.assertEqual(self.state('state.spec.x'), '#')

    def test_values_of_any_analysis_in_the_figure(self):
        self.open_files('A.csv')
        self.kind('line')
        self.run_analysis('descriptive')                                        # no curve, no box of its own
        self.page.locator('#anResults button', has_text='Values in the figure').click()
        self.page.wait_for_selector('#valuesDialog[open]')
        self.assertTrue(self.page.input_value('#valuesText'))                  # some numbers ticked already
        self.page.fill('#valuesText', 'mean angle = 71.0 ± 0.3')
        self.page.click('#valuesAdd')
        self.drawn()
        self.assertEqual(self.state('state.spec.notes.map(n => n.text)'), ['mean angle = 71.0 ± 0.3'])
        self.page.locator('#overlayList textarea.note-text').fill('edited box')   # rewritten under Overlays
        self.drawn()
        self.assertEqual(self.state('state.spec.notes[0].text'), 'edited box')
        self.page.locator('#overlayList .overlay-row .reset').first.click()      # and removed
        self.drawn()
        self.assertEqual(self.state('state.spec.notes.length'), 0)

    def click_figure_at(self, x, y):
        """Click the figure at data coordinates (x, y) of its first axes."""
        box = self.page.evaluate("""([x, y]) => { const g = state.axesGeom[0], r = document.querySelector('#figure').getBoundingClientRect();
            const fx = g.box[0] + (x - g.xlim[0]) / (g.xlim[1] - g.xlim[0]) * (g.box[2] - g.box[0]);
            const fy = g.box[1] + (y - g.ylim[0]) / (g.ylim[1] - g.ylim[0]) * (g.box[3] - g.box[1]);
            return [r.left + fx * r.width, r.top + (1 - fy) * r.height]; }""", [x, y])
        self.page.mouse.click(*box)

    def test_reference_lines_and_bands(self):
        self.page.click('[data-sample="spectra"]')
        self.drawn()
        self.page.click('#refCard summary')
        self.page.click('#refAddLine')                                          # then a click on the figure
        self.page.wait_for_selector('#pickHint')
        self.click_figure_at(450, 0.5)
        self.drawn()
        self.assertAlmostEqual(float(self.state('state.spec.refs[0].value')), 450, delta=3)
        self.page.locator('#refList .overlay-row').first.locator('input.label').fill('λ max')
        self.page.click('#refAddBand')                                          # two clicks: the ends of the band
        self.click_figure_at(500, 0.5)
        self.click_figure_at(520, 0.5)
        self.drawn()
        band = self.state('state.spec.refs[1]')
        self.assertAlmostEqual(float(band['value']), 500, delta=3)
        self.assertAlmostEqual(float(band['to']), 520, delta=3)
        row = self.page.locator('#refList .overlay-row').nth(1)
        row.locator('select.axis').select_option('y')                          # now a horizontal band, typed
        row.locator('input.value').fill('0.2')
        row.locator('input.to').fill('0.4')
        self.drawn()
        self.assertEqual(self.state('[state.spec.refs[1].axis, state.spec.refs[1].value, state.spec.refs[1].to]'), ['y', '0.2', '0.4'])
        self.page.locator('#refList .overlay-row').first.locator('.reset').click()
        self.drawn()
        self.assertEqual(self.state('state.spec.refs.length'), 1)

    def test_inset_region_dragged_on_the_figure(self):
        self.page.click('[data-sample="spectra"]')
        self.drawn()
        self.page.click('#insetCard summary')
        self.page.click('#insetPick')
        self.page.wait_for_selector('#boxPickHint')
        limits = self.state('JSON.stringify(state.spec.axes)')
        start = self.page.evaluate("""() => { const g = state.axesGeom[0], r = document.querySelector('#figure').getBoundingClientRect();
            const at = (x, y) => [r.left + (g.box[0] + (x - g.xlim[0]) / (g.xlim[1] - g.xlim[0]) * (g.box[2] - g.box[0])) * r.width,
                                  r.top + (1 - (g.box[1] + (y - g.ylim[0]) / (g.ylim[1] - g.ylim[0]) * (g.box[3] - g.box[1]))) * r.height];
            return [at(600, 0.1), at(700, 0.6)]; }""")
        self.page.mouse.move(*start[0])
        self.page.mouse.down()
        self.page.mouse.move(*start[1], steps=6)
        self.page.mouse.up()
        self.drawn()
        inset = self.state('state.spec.inset')
        self.assertTrue(inset['show'])
        self.assertAlmostEqual(float(inset['xmin']), 600, delta=4)
        self.assertAlmostEqual(float(inset['xmax']), 700, delta=4)
        self.assertEqual(self.state('JSON.stringify(state.spec.axes)'), limits)     # the figure did not zoom
        self.assertIsNone(self.page.query_selector('#boxPickHint'))
        self.page.select_option('#insetCard select[data-path="inset.where"]', 'upper left')
        self.drawn()
        self.assertEqual(self.state('state.spec.inset.where'), 'upper left')

    def test_axis_break_dragged_on_the_figure(self):
        self.page.click('[data-sample="spectra"]')
        self.drawn()
        at = """([x, y]) => { const g = state.axesGeom[0], r = document.querySelector('#figure').getBoundingClientRect();
            return [r.left + axisFraction(x, g.box[0], g.box[2], g.xlim, g.xscale) * r.width,
                    r.top + (1 - axisFraction(y, g.box[1], g.box[3], g.ylim, g.yscale)) * r.height]; }"""
        self.page.click('summary[data-i18n="sec.axes"]')
        self.page.click('#xbreakPick')
        self.page.wait_for_selector('#boxPickHint')
        self.page.mouse.move(*self.page.evaluate(at, [520, 0.3]))
        self.page.mouse.down()
        self.page.mouse.move(*self.page.evaluate(at, [650, 0.3]), steps=6)       # across x only
        self.page.mouse.up()
        self.drawn()
        lo, hi = [float(v) for v in self.state('state.spec.axes.xbreak').split('–')]
        self.assertAlmostEqual(lo, 520, delta=4)
        self.assertAlmostEqual(hi, 650, delta=4)
        self.assertIsNone(self.state('state.spec.axes.xmin'))                       # the figure did not zoom
        # The spec was changed in place, so drawn() may still see the previous image: wait for the broken axis.
        self.page.wait_for_function('() => (state.axesGeom[0] || {}).xscale?.cuts', timeout=30000)
        cuts = self.state('state.axesGeom[0].xscale.cuts')
        self.assertAlmostEqual(cuts[0][0], lo, places=3)
        # A click past the gap reads the value under it (the page knows how the axis was squeezed).
        self.page.click('#refCard summary')
        self.page.click('#refAddLine')
        self.page.wait_for_selector('#pickHint')
        self.page.mouse.click(*self.page.evaluate(at, [700, 0.3]))
        self.drawn()
        self.assertAlmostEqual(float(self.state('state.spec.refs[0].value')), 700, delta=3)

    @staticmethod
    def grey_png(rows):
        """An 8-bit grey PNG from rows of 0–255 values (standard library only: this test's Python has no NumPy)."""
        import struct
        import zlib
        chunk = lambda tag, data: (struct.pack('>I', len(data)) + tag + data                    # noqa: E731
                                   + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))
        raw = b''.join(b'\x00' + bytes(r) for r in rows)
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', len(rows[0]), len(rows), 8, 0, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))

    def test_image_opened_as_a_matrix(self):
        import math
        spot = [[int(20 + 150 * math.exp(-((x - 60) ** 2 + (y - 12) ** 2) / 30)) for x in range(80)]
                for y in range(50)]                                                    # a spot near the top right
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'spot.png'
            path.write_bytes(self.grey_png(spot))
            self.page.set_input_files('#fileInput', str(path))
            self.page.wait_for_function('() => Files.list().length >= 1', timeout=30000)
            self.drawn()
        self.assertEqual(self.state('[state.spec.kind, state.spec.x]'), ['heatmap', 'y (px)'])
        self.page.locator('#anSuggest .chip').nth(1).click()                     # statistics of a region
        self.page.wait_for_selector('#anMain .points-field')
        self.page.locator('#anMain .points-field button.primary').click()
        at = """([x, y]) => { const g = state.axesGeom[0], r = document.querySelector('#figure').getBoundingClientRect();
            return [r.left + axisFraction(x, g.box[0], g.box[2], g.xlim, g.xscale) * r.width,
                    r.top + (1 - axisFraction(y, g.box[1], g.box[3], g.ylim, g.yscale)) * r.height]; }"""
        for corner in ([50, 27], [70, 47]):                                      # around the spot (y = 49 − 12 = 37)
            self.page.mouse.click(*self.page.evaluate(at, corner))
        self.page.locator('#anMain .points-field button').first.click()          # stop picking
        self.page.locator('#anMain button', has_text='Run analysis').click()
        self.page.wait_for_selector('#anResults table', timeout=60000)
        self.drawn()
        text = self.page.locator('#anResults table').first.inner_text()
        self.assertIn('maximum at (x, y)\t(60, 37)', text)
        self.assertTrue(self.state("state.spec.overlays.some(o => o.label === 'region')"))   # drawn on the copy

    def test_python_console(self):
        self.page.click('[data-sample="kinetics"]')
        self.drawn()
        self.page.click('.tab[data-tab="console"]')
        self.assertTrue(self.page.locator('#consoleBox').is_visible())
        self.page.fill('#consoleInput', "fast = df[df['Time (min)'] < 20]\nprint(len(fast))\n"
                                        "new_table(fast, 'early')\nfast['Concentration (mM)'].max()")
        self.page.press('#consoleInput', 'Control+Enter')
        self.page.wait_for_selector('.con-entry .con-made', timeout=60000)
        entry = self.page.locator('.con-entry').last
        self.assertEqual(entry.locator('.con-text').inner_text().strip(), '8')
        self.assertTrue(entry.locator('.con-value').inner_text().startswith('1.01828'))   # a plain number
        self.assertIn('early', self.state('Files.list().map(f => f.name)'))
        self.assertEqual(self.page.input_value('#consoleInput'), '')               # cleared after a good run
        entry.locator('.con-made button').click()                                    # the new table on screen
        self.page.wait_for_function("() => state.dataset && state.dataset.name === 'early' && state.tab === 'table'")
        self.page.click('.tab[data-tab="console"]')
        self.page.fill('#consoleInput', 'import time\ntime.sleep(60)')
        self.page.click('#conRun')
        self.page.wait_for_selector('#conStop:not([hidden])')
        self.page.click('#conStop')
        self.page.wait_for_selector('.con-entry:last-child .con-error', timeout=30000)
        self.assertIn('Stopped', self.page.locator('.con-entry').last.inner_text())

    def test_layout_of_several_figures(self):
        self.page.click('[data-sample="spectra"]')
        self.drawn()
        self.run_analysis('peaks')                                              # a copy of the figure with the peaks
        self.drawn()
        self.page.wait_for_selector('#btnLayout:not([hidden])')
        self.page.click('#btnLayout')
        self.drawn()
        self.assertEqual(len(self.state('state.spec.layout') and self.state('currentLayout().compose')), 2)
        self.assertFalse(self.page.locator('#layoutCard').is_hidden())
        self.assertEqual(self.page.locator('#layoutList input:checked').count(), 2)
        self.assertEqual(self.state('specForServer().compose.length'), 2)
        self.assertEqual(self.state('state.axesGeom.length'), 0)                 # no zoom on a layout
        self.page.select_option('#exportFormat', 'png')
        with self.page.expect_download() as dl:
            self.page.click('#btnExport')
        self.assertTrue(dl.value.suggested_filename.endswith('.png'))
        self.page.locator('#layoutList input').nth(1).uncheck()                  # one figure left
        self.drawn()
        self.assertEqual(self.state('currentLayout().compose'), ['main'])

    def test_signal_tools_on_the_figure(self):
        self.page.click('[data-sample="spectra"]')
        self.drawn()
        self.run_analysis('frequency_filter')                                   # default: low-pass at Nyquist/10
        self.drawn()
        layers = self.state('state.spec.overlays.map(o => o.label)')
        self.assertTrue(any('filtered' in l for l in layers), layers)           # on a copy of the figure
        self.page.evaluate("() => showView(null)")
        self.drawn()
        self.run_analysis('curve_math')                                         # A − B of the first two curves
        self.drawn()
        self.assertTrue(any('A − B' in l for l in self.state('state.spec.overlays.map(o => o.label)')))

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
