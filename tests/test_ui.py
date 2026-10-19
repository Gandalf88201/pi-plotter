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
        try:                                           # the keys of the state change only through setState
            writes = self.page.evaluate("() => typeof stateWrites === 'function' ? stateWrites() : []")
        except Exception:                              # the page went away (a reload at the end of a path)
            writes = []
        self.page.close()
        self.assertEqual(self.errors, [], 'JavaScript errors on the page')
        self.assertEqual(writes, [], 'state changed outside setState')

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

    def test_batch_on_chosen_files_and_on_a_folder(self):
        self.open_files('D1.csv', 'D2.csv', 'A.csv')
        self.page.locator('#loadedList .file-row', has_text='D1.csv').click()
        self.drawn()
        self.kind('scatter')
        self.page.select_option('#anSelect', 'fit_curve')
        self.page.select_option('#anMain [data-param="model"] select', 'exp_decay')
        self.page.click('#anMain .batch-pick summary')
        self.page.locator('#anMain .batch-pick label', has_text='A.csv').locator('input').uncheck()
        self.page.locator('#anMain button', has_text='Run on the 2 chosen files').click()
        self.page.wait_for_function("() => state.dataset && state.dataset.source && state.dataset.source.batch",
                                    timeout=60000)
        self.page.wait_for_selector('#anResults table', timeout=60000)
        self.assertEqual(self.page.locator('#anResults table').count(), 1)          # no file failed: A.csv left out
        self.assertEqual(self.state('state.dataset.source.files.map(f => f.name)'), ['D1.csv', 'D2.csv'])
        # A folder: the .csv files like the one on screen, read for the batch only (not added to the list).
        self.page.evaluate("() => showView(null)")
        self.drawn()
        self.page.select_option('#anSelect', 'fit_curve')
        self.page.select_option('#anMain [data-param="model"] select', 'exp_decay')
        self.page.evaluate("""() => {
            const rows = amp => 'time (s),signal\\n' + Array.from({ length: 40 }, (_, t) =>
                `${t},${(amp * Math.exp(-t / 6) + 0.5).toFixed(6)}`).join('\\n') + '\\n';
            const dt = new DataTransfer();
            [['run 2.csv', rows(3)], ['run 10.csv', rows(5)], ['run 1.csv', rows(7)], ['._run 1.csv', 'x'],
             ['notes.txt', 'hello']].forEach(([n, text]) => dt.items.add(new File([text], n, { type: 'text/csv' })));
            const input = document.querySelector('#anMain input[type=file]');
            input.files = dt.files;
            input.dispatchEvent(new Event('change'));
        }""")
        self.page.wait_for_function("""() => state.dataset && state.dataset.source && state.dataset.source.batch
            && state.dataset.source.files.length === 3""", timeout=60000)
        self.assertEqual(self.state('state.dataset.source.files.map(f => f.name)'), ['run 1.csv', 'run 2.csv', 'run 10.csv'])
        self.assertEqual(self.state('Files.list().length'), 3)                      # the loaded files are the same
        taus = self.state("(() => { const i = state.dataset.columns.findIndex(c => c.name === 'tau');"
                          " return i < 0 ? null : state.dataset.preview.map(r => r[i]); })()")
        self.assertEqual(len(taus), 3, self.state('state.dataset.columns.map(c => c.name)'))
        for tau in taus:                                                          # τ = 6 s in every file
            self.assertAlmostEqual(tau, 6.0, places=3)

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

    def test_normalised_curves_and_their_analyses(self):
        self.page.click('[data-sample="spectra"]')
        self.drawn()
        self.page.click('#normCard summary')
        self.assertTrue(self.page.locator('#normRange').is_hidden())              # off: nothing else to fill
        self.page.select_option('#normMode', 'max')
        self.drawn()
        self.assertAlmostEqual(self.state('state.axesGeom[0].ylim[1]'), 1.05, delta=0.03)   # every curve up to 1
        self.assertEqual(self.page.locator('#normBadge').inner_text(), 'on')
        self.run_analysis('peaks')
        self.assertIn('normalised', self.page.locator('#anResults').inner_text())
        self.page.locator('#anResults button', has_text='copy').first.click()
        self.drawn()
        layers = "JSON.stringify(state.spec.overlays.filter(o => o.analysis_run === 'peaks').map(o => [o.id, o.dataset_id]))"
        before = self.state(layers)
        self.assertEqual(self.state('state.spec.normalize.mode'), 'max')          # the copy keeps it
        self.page.select_option('#normMode', 'at')
        self.assertTrue(self.page.locator('#normRange').is_hidden())
        self.assertTrue(self.page.locator('#normAt').is_visible())
        self.page.select_option('#normMode', 'minmax')
        self.page.wait_for_function(f"() => {layers} !== {json.dumps(before)}", timeout=60000)   # the peaks ran again
        after = json.loads(self.state(layers))
        self.assertEqual([i for i, _ in after], [i for i, _ in json.loads(before)])  # same layers, same place
        self.drawn()

    def test_graph_picture_read_back_into_a_table(self):
        # A picture of a graph drawn in the page: axes 0…10 × 0…4 on pixels 100…700 × 420…60, a red Gaussian, green dots.
        self.page.evaluate("""async () => {
            const c = document.createElement('canvas'); c.width = 800; c.height = 500;
            const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, 800, 500);
            const X = x => 100 + x * 60, Y = y => 420 - y * 90;
            g.strokeStyle = '#000'; g.lineWidth = 1.5; g.strokeRect(100, 60, 600, 360);
            g.strokeStyle = '#d62728'; g.lineWidth = 2.5; g.beginPath();
            for (let i = 0; i <= 600; i++) { const x = i / 60, y = 3 * Math.exp(-((x - 4) ** 2) / 2) + 0.5; i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y)); }
            g.stroke();
            g.fillStyle = '#2ca02c'; [[1, 0.8], [3, 1.6], [5, 2.2], [7, 1.1], [9, 0.9]].forEach(([x, y]) => { g.beginPath(); g.arc(X(x), Y(y), 6, 0, 7); g.fill(); });
            const blob = await new Promise(r => c.toBlob(r, 'image/png'));
            await openFiles([new File([blob], 'graph.png', { type: 'image/png' })]);
        }""")
        self.drawn()
        self.page.click('#btnDigitize')
        self.page.wait_for_function('() => document.querySelector("#digitizeDialog").open && Digitizer.state.img')
        self.page.wait_for_timeout(300)
        at = """([u, v]) => { const D = Digitizer.state, cv = document.querySelector('#digCanvas'), r = cv.getBoundingClientRect(),
            kx = r.width / cv.width, ky = r.height / cv.height;
            return [r.left + (D.view.ox + (u + 0.5) * D.view.scale) * kx, r.top + (D.view.oy + (v + 0.5) * D.view.scale) * ky]; }"""
        click = lambda u, v: self.page.mouse.click(*self.page.evaluate(at, [u, v]))    # noqa: E731
        # The bitmap of the canvas has the shape it is shown at (a stretched one put points above the pointer).
        shape = self.state("(() => { const c = document.querySelector('#digCanvas'), r = c.getBoundingClientRect(); "
                           "return [c.width / c.height, r.width / r.height]; })()")
        self.assertAlmostEqual(shape[0], shape[1], delta=0.01)
        for key, (u, v), value in (('x0', (100, 420), '0'), ('x1', (700, 420), '10'), ('y0', (100, 420), '0'), ('y1', (100, 60), '4')):
            self.assertEqual(self.state('Digitizer.state.tool'), key)          # the next point to click, in order
            self.page.click('#digFit')
            self.page.mouse.move(*self.page.evaluate(at, [u, v]))
            self.page.mouse.wheel(0, -300)                                     # zoomed on it, as one does for precision
            self.page.wait_for_timeout(150)
            click(u, v)
            placed = self.state(f'Digitizer.state.axes.{key[0]}[{key[1]}].px')
            self.assertLess(abs(placed[0] - u) + abs(placed[1] - v), 1.5)        # where the pointer was
            self.page.fill(f'#digAxes [data-axis="{key}"] input', value)
        self.page.click('#digPickColour')
        click(340, 106)                                                        # on the red curve, at its top
        self.page.wait_for_function('() => Digitizer.state.preview && Digitizer.state.preview[0].n > 500')
        self.assertEqual(self.state('Digitizer.state.series[0].colour'), '#d62728')
        self.page.click('#digAddCurve')
        self.page.select_option('#digMode', 'markers')
        click(400, 222)                                                        # a green dot
        self.page.wait_for_function('() => Digitizer.state.preview && Digitizer.state.preview[1] && Digitizer.state.preview[1].n === 5')
        self.page.fill('#digXName', 'time')
        self.page.fill('#digYName', 'signal')
        self.page.click('#digMake')
        self.page.wait_for_function('() => !document.querySelector("#digitizeDialog").open', timeout=30000)
        self.drawn()
        self.assertEqual(self.state('state.dataset.columns.map(c => c.name)'), ['curve', 'time', 'signal'])
        self.assertEqual(self.state('[state.spec.kind, state.spec.hue, state.spec.series["signal::curve 2"].linestyle]'),
                         ['line', 'curve', 'none'])
        top = self.state("""(async () => { const r = await api('/api/table/rows', { dataset_id: state.dataset.dataset_id, start: 0, count: 2000 });
            return Math.max(...r.rows.filter(x => x[0] === 'curve 1').map(x => x[2])); })()""")
        self.assertAlmostEqual(top, 3.5, delta=0.05)                           # the top of the Gaussian
        self.page.click('#btnDigitize')                                       # opened again: as it was read
        self.page.wait_for_function('() => document.querySelector("#digitizeDialog").open && Digitizer.state.preview')
        self.assertEqual(self.state('Digitizer.state.series.map(s => s.mode)'), ['line', 'markers'])
        self.page.click('#digClose')
        self.page.click('.tab[data-tab="table"]')
        with self.page.expect_download() as dl:
            self.page.locator('.table-tools button', has_text='CSV').click()
        self.assertTrue(dl.value.suggested_filename.endswith('.csv'))

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

    @staticmethod
    def rgb_png(rows):
        """An 8-bit colour PNG from rows of (r, g, b) values (standard library only)."""
        import struct
        import zlib
        chunk = lambda tag, data: (struct.pack('>I', len(data)) + tag + data                    # noqa: E731
                                   + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))
        raw = b''.join(b'\x00' + bytes(v for px in r for v in px) for r in rows)
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', len(rows[0]), len(rows), 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))

    def test_colour_image_channels_and_polygon(self):
        rows = [[(200, 100, 50)] * 40 for _ in range(30)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'colour.png'
            path.write_bytes(self.rgb_png(rows))
            self.page.set_input_files('#fileInput', str(path))
            self.page.wait_for_function('() => Files.list().length >= 1', timeout=30000)
            self.drawn()
        self.assertEqual(self.state("[...document.querySelectorAll('#tableSelect option')].map(o => o.value)"),
                         ['luminance', 'red', 'green', 'blue'])
        self.page.click('#btnChannels')
        self.page.wait_for_function('() => Files.list().length === 4', timeout=30000)
        self.page.select_option('#anSelect', 'matrix_stats')
        self.page.locator('#anMain button', has_text='Run on all 4 files').click()
        self.page.wait_for_function("() => state.dataset && state.dataset.source && state.dataset.source.batch",
                                    timeout=60000)
        means = self.state("(() => { const i = state.dataset.columns.findIndex(c => c.name === 'mean');"
                           " return state.dataset.preview.map(r => r[i]); })()")
        self.assertEqual([round(m, 3) for m in means], [round(0.299 * 200 + 0.587 * 100 + 0.114 * 50, 3), 200, 100, 50])
        # A polygon region: three points clicked on the figure.
        self.page.evaluate("() => showView(null)")
        self.drawn()
        self.page.select_option('#anSelect', 'matrix_stats')
        self.page.wait_for_selector('#anMain .points-field')
        self.page.locator('#anMain .points-field button.primary').click()
        at = """([x, y]) => { const g = state.axesGeom[0], r = document.querySelector('#figure').getBoundingClientRect();
            return [r.left + axisFraction(x, g.box[0], g.box[2], g.xlim, g.xscale) * r.width,
                    r.top + (1 - axisFraction(y, g.box[1], g.box[3], g.ylim, g.yscale)) * r.height]; }"""
        for point in ([5, 5], [35, 5], [5, 25]):
            self.page.mouse.click(*self.page.evaluate(at, point))
        self.page.locator('#anMain .points-field button').first.click()
        self.page.locator('#anMain button', has_text='Run analysis').click()
        self.page.wait_for_selector('#anResults table', timeout=60000)
        text = self.page.locator('#anResults table').first.inner_text()
        self.assertIn('polygon of 3 points', text)
        area = float(text.split('area of the polygon\t')[1].split('\n')[0])
        self.assertAlmostEqual(area, 300, delta=6)                                    # ½ · 30 · 20, as clicked

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

    def test_console_completion_every_file_and_project(self):
        self.open_files('D1.csv', 'D2.csv')
        self.page.click('.tab[data-tab="console"]')
        self.page.fill('#consoleInput', 'df.describe()')
        self.page.click('#conRun')                                                   # the console starts
        self.page.wait_for_selector('.con-entry .con-table', timeout=60000)
        self.page.fill('#consoleInput', "df['si")
        self.page.press('#consoleInput', 'End')
        self.page.press('#consoleInput', 'Tab')
        self.page.wait_for_function("() => document.querySelector('#consoleInput').value === \"df['signal\"",
                                    timeout=30000)
        self.page.fill('#consoleInput', "{'peak': df['signal'].max(), 'n': len(df)}")
        self.page.click('#conEach')
        self.page.wait_for_selector('.con-entry:last-child .con-made', timeout=60000)
        made = self.state("Files.list().find(f => f.name.startsWith('console'))")
        self.assertIsNotNone(made)
        self.page.locator('.con-entry').last.locator('.con-made button').click()
        self.page.wait_for_function("() => state.dataset && state.dataset.name.startsWith('console')")
        self.assertEqual(self.state("state.dataset.columns.map(c => c.name)"), ['file', 'peak', 'n'])
        self.assertEqual(self.state("state.dataset.preview.map(r => r[0])"), ['D1.csv', 'D2.csv'])
        self.assertEqual(self.state("state.dataset.preview.map(r => Math.round(r[1] * 1000) / 1000)"), [4.5, 9.5])
        # Saved in a project, the code comes back in the console, ready to run again.
        self.page.evaluate("() => { window.prompt = () => 'console-test'; window.confirm = () => true; }")
        with self.page.expect_download() as dl:
            self.page.click('#btnSaveProject')
        path = dl.value.path()
        self.page.evaluate("() => Console.importState(null)")
        self.page.set_input_files('#projectInput', path)
        self.page.wait_for_function("() => Console.history().length === 2", timeout=30000)
        self.page.click('.tab[data-tab="console"]')
        self.assertIn('df.describe()', self.page.locator('#consoleLog').inner_text())
        self.assertTrue(self.page.locator('#consoleLog button', has_text='Run it again').is_visible())

    def test_last_work_recovered(self):
        # The work of an earlier session, as the autosave left it (piplotter/autosave.py): offered on an empty page.
        prev = Path(self._tmp.name) / 'home' / 'autosave' / 'previous'
        prev.mkdir(parents=True, exist_ok=True)
        (prev / 'project.json').write_text(json.dumps({'saved': time.time(), 'files': {}, 'project': {
            'files': [], 'main': {'source': {'sample': 'groups'}, 'name': 'sample: groups'}, 'active': 'old',
            'spec': {'kind': 'box', 'x': 'Group', 'y': ['Response (a.u.)']}, 'views': []}}), encoding='utf-8')
        self.page.reload()
        self.page.wait_for_function('() => state.ready === true')
        self.page.wait_for_selector('#recoverBox:not([hidden])', timeout=30000)
        self.assertIn('sample: groups', self.page.inner_text('#recoverText'))
        self.page.click('#recoverYes')
        self.drawn()
        self.assertEqual(self.state('[state.dataset.name, state.spec.kind]'), ['sample: groups', 'box'])
        self.assertTrue(self.page.locator('#recoverBox').is_hidden())

    def test_cache_cleared_after_asking(self):
        home = Path(self._tmp.name) / 'home'

        def clear(autosave=False, prefs=False, go=True):
            self.page.click('#btnClearCache')
            self.page.wait_for_selector('#cacheDialog[open]')
            self.assertFalse(self.page.is_checked('#cacheAutosave'))          # nothing kept is deleted unless ticked
            self.assertFalse(self.page.is_checked('#cachePrefs'))
            if autosave:
                self.page.check('#cacheAutosave')
            if prefs:
                self.page.check('#cachePrefs')
            if not go:
                self.page.locator('#cacheDialog button[value=no]').click()
                return
            with self.page.expect_navigation():
                self.page.click('#cacheGo')
            self.page.wait_for_function('() => state.ready === true', timeout=30000)

        self.open_files('A.csv')
        clear(go=False)                                                         # asked first: cancelled, nothing changes
        self.assertEqual(self.state('Files.list().length'), 1)
        self.assertEqual(self.state('state.dataset.name'), 'A.csv')
        clear()
        self.page.wait_for_selector('#toasts >> text=Cache cleared')
        self.assertEqual(self.state('[state.dataset, Files.list().length]'), [None, 0])
        self.assertTrue(self.page.locator('#recoverBox').is_hidden())          # the work closed is not offered back …
        self.assertTrue((home / 'autosave' / 'current' / 'project.json').is_file())   # … but stays recoverable
        self.assertEqual(self.state("localStorage.getItem('pp-lang')"), '"en"')
        # Everything, the autosave and the preferences too, when ticked.
        self.open_files('line.csv')
        clear(autosave=True, prefs=True)
        self.assertFalse((home / 'autosave' / 'current').exists())
        self.assertIsNone(self.state("localStorage.getItem('pp-lang')"))
        self.assertEqual(self.state('Files.list().length'), 0)

    def test_profile_line_kept_on_the_3d_surface(self):
        self.page.click('[data-sample="surface"]')
        self.drawn()
        self.kind('surface3d')
        self.page.select_option('#anSelect', 'matrix_profile')
        self.page.select_option('#anMain [data-param="along"] select', 'row')
        self.assertFalse(self.page.is_checked('#anMain [data-param="on_surface"] input'))   # only when asked
        self.page.check('#anMain [data-param="on_surface"] input')
        self.page.locator('#anMain button', has_text='Run analysis').click()
        self.page.wait_for_selector('#anResults table', timeout=60000)
        self.page.wait_for_function('() => state.view !== null', timeout=30000)                # the copy of the figure
        self.drawn()
        self.assertEqual(self.state('state.spec.kind'), 'surface3d')
        # The rotatable preview has the line too, drawn in front of the surface in its colour.
        red = self.page.evaluate("""async () => {
            const d = await view3dData(), v = d.axes[0];
            const c = document.createElement('canvas');
            c.width = 600; c.height = 450;
            View3D.draw(c, d, v.elev + 20, v.azim + 40);
            const px = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
            let n = 0;
            for (let i = 0; i < px.length; i += 4) if (px[i] > 230 && px[i + 1] < 90 && px[i + 2] < 80) n++;
            return [v.layers.filter(L => L.type === 'line').map(L => L.front), n];
        }""")
        self.assertEqual(red[0], [True])
        self.assertGreater(red[1], 50)

    def test_point_reader_pointer_cross_and_pin(self):
        self.open_files('line.csv')
        at = """([x, y]) => { const g = state.axesGeom[0], r = document.querySelector('#figure').getBoundingClientRect();
            return [r.left + axisFraction(x, g.box[0], g.box[2], g.xlim, g.xscale) * r.width,
                    r.top + (1 - axisFraction(y, g.box[1], g.box[3], g.ylim, g.yscale)) * r.height]; }"""
        self.assertTrue(self.page.is_visible('#readerSeg'))
        self.assertEqual(self.state("document.querySelector('#readerSeg .active').dataset.mode"), 'pointer')
        self.page.mouse.move(*self.page.evaluate(at, [3, 30]))
        self.page.wait_for_selector('#readerTip')
        x, y = (float(v) for v in self.page.inner_text('#readerTip').replace('x', '').split('y'))
        self.assertAlmostEqual(x, 3, delta=0.05)                                       # where the mouse is
        self.assertAlmostEqual(y, 30, delta=0.3)
        self.assertEqual(self.page.locator('#readerCross').count(), 0)
        self.page.click('#readerSeg [data-mode="cross"]')                              # the × sight
        self.assertTrue(self.state("document.querySelector('#figure').classList.contains('reader-cross-mode')"))
        self.assertEqual(self.state("localStorage.getItem('pp-reader')"), '"cross"')
        self.page.mouse.move(*self.page.evaluate(at, [4, 40]))
        self.page.wait_for_selector('#readerCross .rc-x')
        # A click pins the nearest point of the data, with its exact values.
        self.page.mouse.click(*self.page.evaluate(at, [5.1, 11.6]))
        self.page.wait_for_selector('#readerPinBox')
        self.assertEqual(self.page.inner_text('#readerPinBox').split('\n')[:3], ['y · row 6', 'x 5', 'y 11'])
        self.page.keyboard.press('Escape')
        self.assertEqual(self.page.locator('#readerPinBox').count(), 0)
        # The boxes of values never cover the figure's texts and legend: here just above-left of the legend, where
        # the first place tried (below right) would lie over it.
        self.page.reload()                                                               # a figure with a legend
        self.page.wait_for_function('() => state.ready === true', timeout=30000)
        self.page.click('[data-sample="spectra"]')
        self.drawn()
        self.page.wait_for_function("() => Drag.items.some(i => i.kind === 'legend')")
        corner = self.page.evaluate("""() => { const m = Drag.items.find(i => i.kind === 'legend'), p = boxPixels(m.box),
            o = document.querySelector('#figureBox').getBoundingClientRect(); return [o.left + p.left - 8, o.top + p.top - 6]; }""")
        self.page.mouse.move(*corner)
        self.page.wait_for_selector('#readerTip')
        self.page.mouse.click(*corner)
        self.page.wait_for_selector('#readerPinBox')
        overlaps = self.page.evaluate("""() => {
            const o = document.querySelector('#figureBox').getBoundingClientRect();
            const boxes = ['#readerTip', '#readerPinBox'].map(s => document.querySelector(s).getBoundingClientRect());
            const cut = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
                * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
            return boxes.flatMap(b => Drag.items.map(m => { const p = boxPixels(m.box);
                return cut(b, { left: o.left + p.left, top: o.top + p.top, right: o.left + p.left + p.width,
                                bottom: o.top + p.top + p.height }); })).concat([cut(boxes[0], boxes[1])]);
        }""")
        self.assertTrue(len(overlaps) >= 3)
        self.assertEqual(max(overlaps), 0)

    def test_events_between_parts_of_the_page(self):
        got = self.page.evaluate("""() => {
            const seen = [];
            const off = Bus.on('test:event', d => seen.push(['first', d.n]));
            Bus.on('test:event', () => { throw new Error('a listener that fails'); });
            Bus.on('test:event', d => seen.push(['last', d.n]));
            Bus.emit('test:event', { n: 1 });
            off();
            Bus.emit('test:event', { n: 2 });
            return seen; }""")
        self.assertEqual(got, [['first', 1], ['last', 1], ['last', 2]])            # the others still run
        self.page.wait_for_timeout(200)
        self.assertEqual(len([e for e in self.errors if 'a listener that fails' in e]), 2)   # reported, not hidden
        self.errors.clear()
        self.page.click('[data-sample="kinetics"]')                                 # the parts follow the data
        self.drawn()
        self.assertFalse(self.page.locator('#btnSaveProject').is_disabled())
        self.assertIn('sample: kinetics', self.page.inner_text('#loadedList'))
        # The keys of the state change through setState, which says so on the Bus; a direct write is noted.
        heard = self.page.evaluate("""() => { const got = []; const off = Bus.on('state', e => got.push(...e.keys));
            setTab('table'); setTab('figure'); off(); state.tab = 'table';
            const w = stateWrites(true); setTab('figure'); return { got, w }; }""")
        self.assertEqual(heard['got'], ['tab', 'tab'])
        self.assertEqual(len(heard['w']), 1)
        self.assertTrue(heard['w'][0].startswith('tab ←'), heard['w'])

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

    def test_where_a_result_comes_from(self):
        # A value typed in the table, then an analysis: the result says it comes from the file, one change by hand,
        # and the analysis with its parameters.
        self.open_files('line.csv')
        self.page.click('.tab[data-tab="table"]')
        self.page.wait_for_selector('#tableBox td[data-r="0"][data-c="1"]')
        self.page.click('#tableBox td[data-r="0"][data-c="1"]')
        self.page.keyboard.type('5')
        self.page.keyboard.press('Enter')
        self.page.wait_for_function("() => state.dataset.preview[0][1] === 5")
        self.page.click('.tab[data-tab="figure"]')
        self.drawn()
        self.run_analysis('descriptive')
        det = self.page.locator('#anResults details.lineage')
        det.locator('summary').click()
        self.assertEqual(det.locator('summary').inner_text(), 'Where it comes from')
        items = det.locator('ol > li').all_inner_texts()
        self.assertEqual(len(items), 3, items)
        self.assertEqual(items[0], 'File line.csv')
        self.assertEqual(items[1], '1 change by hand (cells 1)')
        self.assertTrue(items[2].startswith('Descriptive statistics — '), items[2])
        self.page.evaluate("() => setLang('it')")                       # the panel follows the language
        self.page.wait_for_function("() => document.querySelector('#anResults details.lineage summary')"
                                    "?.textContent === 'Da dove viene'")
        self.assertEqual(self.page.locator('#anResults details.lineage ol > li').nth(1).text_content(),
                         '1 modifica a mano (celle 1)')

    def test_old_figure_descriptions_open_complete(self):
        # A project whose copy was saved before insets existed: the service completes the description, so the copy
        # shows, and has an inset to switch on, without the page mending it.
        import zipfile
        x, a, b = 'Wavelength (nm)', 'Sample A', 'Sample B'
        doc = {'format': 'pi-plotter project', 'version': 1, 'lang': 'en', 'active': 'a',
               'files': [{'id': 'a', 'name': 'spectra', 'source': {'sample': 'spectra'}}],
               'spec': {'kind': 'line', 'x': x, 'y': [a]},
               'views': [{'id': 'v1', 'spec': {'kind': 'line', 'x': x, 'y': [b]}, 'runs': []}]}
        path = self.data / 'old.piplot'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('project.json', json.dumps(doc))
        self.page.set_input_files('#projectInput', str(path))
        self.page.wait_for_function("() => state.views.length === 1", timeout=30000)
        self.page.evaluate("() => showView('v1')")
        self.drawn()
        self.assertEqual(self.state("state.spec.y"), ['Sample B'])
        self.assertEqual(self.state("state.spec.inset.show"), False)
        self.assertEqual(self.state("state.spec.inset.size"), 40)

    def test_schema_messages_in_the_page(self):
        # A figure description that does not match its schema: the error box says where, the figure comes back
        # once it is right again.
        self.open_files('A.csv')
        self.page.evaluate("() => { state.spec.kind = 'nope'; scheduleRender(0); }")
        box = self.page.locator('#errorBox')
        box.wait_for(state='visible', timeout=30000)
        self.assertIn("spec.kind: 'nope' is not one of", box.inner_text())
        self.page.evaluate("() => { state.spec.kind = 'line'; scheduleRender(0); }")
        self.drawn()
        # A project that does not match: refused with the place of the problem, the work on screen left as it was.
        import zipfile
        bad = {'format': 'pi-plotter project', 'version': 1, 'lang': 'en', 'spec': {'kind': 'line', 'y': ['angle']},
               'files': [{'id': 'a', 'name': 'a.csv', 'source': {'analysis': 'peaks', 'params': {}}}],
               'views': [{'id': 'v1', 'spec': {'kind': 'nope'}}]}
        for name, doc, where in (('source.piplot', {**bad, 'views': []}, 'files[0].source: “parent” is missing'),
                                 ('view.piplot', {**bad, 'files': []}, "views[0].spec.kind: 'nope' is not one of")):
            path = self.data / name
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('project.json', json.dumps(doc))
            self.page.evaluate("() => { window.confirm = () => true; }")
            self.page.set_input_files('#projectInput', str(path))
            self.page.wait_for_function("() => !document.querySelector('#dataError').hidden", timeout=30000)
            text = self.page.locator('#dataError').inner_text()
            self.assertIn(f'{name}: The project does not match its schema', text)
            self.assertIn(where, text)
            self.assertEqual(self.state("Files.list().map(f => f.name)"), ['A.csv'])

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

    def test_results_outdated_until_they_run_on_the_new_table(self):
        self.open_files('line.csv')
        self.kind('scatter')
        self.run_analysis('descriptive')
        before = self.page.inner_text('#anResults table')
        self.page.evaluate("() => closeView(state.view)")                 # its figure closed: numbers only in the panel
        self.page.wait_for_function("() => !state.view")
        self.page.select_option('#anSelect', 'fit_curve')
        self.page.select_option('#anMain [data-param="model"] select', 'linear')
        self.page.locator('#anMain button', has_text='Run analysis').click()
        self.page.wait_for_function("() => state.view && state.spec.overlays.some(o => o.note)", timeout=60000)
        slope = "() => parseFloat(state.spec.overlays.find(o => o.note).note.match(/a = ([-0-9.]+)/)[1])"
        first = self.page.evaluate(slope)
        # An edit: the numbers of the panel follow too, not only the curves on the copy.
        self.page.click('.tab[data-tab="table"]')
        self.page.click('#tableBox td[data-r="0"][data-c="1"]')
        self.page.keyboard.type('31')
        self.page.keyboard.press('Enter')
        self.page.wait_for_function(f'() => ({slope})() < {first} - 0.1', timeout=60000)
        self.page.wait_for_function("() => !document.querySelector('.view-tab.outdated')", timeout=60000)
        self.page.select_option('#anSelect', 'descriptive')
        self.page.wait_for_selector('#anResults table')
        self.assertNotEqual(self.page.inner_text('#anResults table'), before)
        self.assertEqual(self.page.locator('#anResults .an-outdated').count(), 0)
        edited = self.page.evaluate(slope)
        # The column the fit uses is renamed: it cannot run, so the copy and its numbers are marked outdated.
        rename = lambda frm, to: (self.page.evaluate(f"() => {{ window.prompt = () => '{to}'; }}"),
                                  self.page.locator('#tableBox th', has_text=frm).first.dblclick())
        rename('y', 'z')
        self.page.wait_for_selector('.view-tab.outdated.old', timeout=60000)
        self.page.select_option('#anSelect', 'fit_curve')
        self.page.wait_for_selector('#anResults .an-outdated button')
        # Undo: the results are made from the current version again.
        self.page.locator('.table-tools button', has_text='Undo').click()
        self.page.wait_for_function("() => !document.querySelector('.view-tab.outdated')", timeout=30000)
        self.page.wait_for_function("() => !document.querySelector('#anResults .an-outdated')")
        # Renamed and renamed back (two new versions): Run again brings the fit to the last one.
        rename('y', 'z')
        self.page.wait_for_selector('.view-tab.outdated.old', timeout=60000)
        self.page.wait_for_function("() => state.dataset.columns.some(c => c.name === 'z')")
        rename('z', 'y')
        self.page.wait_for_function("() => state.dataset.columns.some(c => c.name === 'y')")
        self.page.select_option('#anSelect', 'fit_curve')
        self.page.locator('#anResults .an-outdated button', has_text='Run again').click()
        self.page.wait_for_function("() => !document.querySelector('.view-tab.outdated')", timeout=60000)
        self.assertAlmostEqual(self.page.evaluate(slope), edited, places=4)

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
