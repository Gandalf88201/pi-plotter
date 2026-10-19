"""Reading pictures of graphs back into data (piplotter/digitize.py, service/digitize.py): python -m unittest tests.test_digitize"""
import io
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
import matplotlib  # noqa: E402
matplotlib.use('Agg')
from matplotlib.figure import Figure  # noqa: E402

from piplotter import digitize, sources  # noqa: E402

RED, BLUE, GREEN = '#d62728', '#1f77b4', '#2ca02c'


def has(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def gauss(x):
    return 3 * np.exp(-(x - 4) ** 2 / 2) + 0.5


def picture(log=False, rotate=0):
    """A figure drawn by Matplotlib with known curves, as PNG bytes, and the pixels of its axis points."""
    fig = Figure(figsize=(6, 4), dpi=100)
    ax = fig.add_subplot()
    x = np.linspace(0, 10, 400)
    if log:
        ax.semilogy(x, 10 ** (x / 2.5), color=RED, lw=1.5)
        ax.set_ylim(1, 1e4)
    else:
        ax.plot(x, gauss(x), color=RED, lw=1.5)
        ax.plot(x, 2 - 0.1 * x, color=BLUE, lw=1.5)
        ax.plot([1, 3, 5, 7, 9], [0.8, 1.6, 2.2, 1.1, 0.9], 'o', color=GREEN, ms=6, ls='none')
        ax.set_ylim(0, 4)
    ax.set_xlim(0, 10)
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    h = fig.canvas.get_width_height()[1]

    def px(X, Y):
        u, v = ax.transData.transform((X, Y))
        return [u - 0.5, h - v - 0.5]                     # pixel centres, rows from the top
    y0, y1 = (1, 1e4) if log else (0, 4)
    axes = {'x': [{'px': px(0, y0), 'value': 0}, {'px': px(10, y0), 'value': 10}],
            'y': [{'px': px(0, y0), 'value': y0}, {'px': px(0, y1), 'value': y1}], 'ylog': log}
    data = buf.getvalue()
    if rotate:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert('RGB')
        w, hh = im.size
        out = im.rotate(rotate, resample=Image.BICUBIC, center=(w / 2, hh / 2), fillcolor=(255, 255, 255))
        t = np.deg2rad(rotate)                            # PIL turns counter-clockwise on screen (rows downwards)

        def turn(p):
            du, dv = p[0] + 0.5 - w / 2, p[1] + 0.5 - hh / 2
            return [w / 2 + du * np.cos(t) + dv * np.sin(t) - 0.5, hh / 2 - du * np.sin(t) + dv * np.cos(t) - 0.5]
        for a in ('x', 'y'):
            for e in axes[a]:
                e['px'] = turn(e['px'])
        buf = io.BytesIO()
        out.save(buf, format='png')
        data = buf.getvalue()
    return data, axes


def rgb_of(data):
    from PIL import Image
    return np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))


class TestReading(unittest.TestCase):
    def test_line_markers_and_points(self):
        data, axes = picture()
        rgb = rgb_of(data)
        curves = digitize.extract(rgb, axes, [
            {'name': 'gauss', 'mode': 'line', 'colour': RED, 'tolerance': 15},
            {'name': 'straight', 'mode': 'line', 'colour': BLUE, 'tolerance': 15},
            {'name': 'dots', 'mode': 'markers', 'colour': GREEN, 'tolerance': 15, 'min_size': 8},
            {'name': 'clicked', 'mode': 'points', 'points': [axes['x'][1]['px'], axes['y'][1]['px']]}])
        g, s, d, c = curves
        self.assertGreater(len(g['x']), 400)                                   # a point per column of pixels
        self.assertTrue(np.all(np.diff(g['x']) > 0))
        self.assertLess(np.abs(g['y'] - gauss(g['x'])).max(), 0.06)            # 1.5 % of the axis, steep flanks included
        self.assertLess(np.abs(s['y'] - (2 - 0.1 * s['x'])).max(), 0.02)       # crossing the other curve: followed
        np.testing.assert_allclose(np.c_[d['x'], d['y']], [[1, 0.8], [3, 1.6], [5, 2.2], [7, 1.1], [9, 0.9]], atol=0.03)
        np.testing.assert_allclose(np.c_[c['x'], c['y']], [[10, 0], [0, 4]], atol=1e-9)   # the axis points themselves
        frame = digitize.to_frame(curves, 'time', 'signal')
        self.assertEqual(list(frame.columns), ['curve', 'time', 'signal'])
        self.assertEqual(frame['curve'].unique().tolist(), ['gauss', 'straight', 'dots', 'clicked'])
        one = digitize.to_frame(curves[:1], 'time', 'time')
        self.assertEqual(list(one.columns), ['time', 'time (y)'])            # one curve: just X and Y

    def test_logarithmic_axis_and_a_rotated_scan(self):
        data, axes = picture(log=True)
        c = digitize.extract(rgb_of(data), axes, [{'mode': 'line', 'colour': RED, 'tolerance': 15}])[0]
        self.assertLess(np.abs(np.log10(c['y']) - c['x'] / 2.5).max(), 0.03)   # decades read on a log axis
        data, axes = picture(rotate=2.0)
        c = digitize.extract(rgb_of(data), axes, [{'mode': 'line', 'colour': BLUE, 'tolerance': 18}])[0]
        self.assertLess(np.abs(c['y'] - (2 - 0.1 * c['x'])).max(), 0.05)       # a scan turned by 2°

    def test_region_and_mistakes(self):
        data, axes = picture()
        rgb = rgb_of(data)
        left = axes['x'][0]['px'][0] + 0.5 * (axes['x'][1]['px'][0] - axes['x'][0]['px'][0])
        c = digitize.extract(rgb, axes, [{'mode': 'line', 'colour': RED, 'region': [0, 0, left, rgb.shape[0]]}])[0]
        self.assertLessEqual(c['x'].max(), 5.05)                              # only the left half
        bad = [({'x': axes['x'][:1], 'y': axes['y']}, 'two points'),
               ({**axes, 'x': [{**axes['x'][0]}, {**axes['x'][1], 'value': 0}]}, 'different values'),
               ({**axes, 'ylog': True}, 'positive'),
               ({**axes, 'x': [axes['x'][0], {**axes['x'][1], 'value': ''}]}, 'Type the values')]
        for a, words in bad:
            with self.assertRaises(digitize.DigitizeError) as cm:
                digitize.extract(rgb, a, [{'mode': 'line', 'colour': RED}])
            self.assertIn(words, str(cm.exception))
        with self.assertRaises(digitize.DigitizeError):
            digitize.extract(rgb, axes, [{'mode': 'line', 'colour': '#ff00ff', 'tolerance': 2}])   # no such colour
        with self.assertRaises(digitize.DigitizeError):
            digitize.extract(rgb, axes, [])
        with self.assertRaises(digitize.DigitizeError):
            digitize.parse_colour('not a colour')
        self.assertEqual(digitize.parse_colour('#abc'), [170, 187, 204])


@unittest.skipUnless(has('scipy') and has('PIL'), 'needs scipy and Pillow')
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

    def test_picture_preview_table_and_its_source(self):
        data, axes = picture()
        info = self.app.add_upload('figure 3.png', io.BytesIO(data), len(data))
        png, meta = self.app.digitize_picture({'file_id': info['id']})
        self.assertEqual((meta['width'], meta['height']), (600, 400))
        self.assertTrue(png.startswith(b'\x89PNG'))
        body = {'file_id': info['id'], 'axes': axes, 'xname': 'E (eV)', 'yname': 'I',
                'series': [{'name': 'band', 'mode': 'line', 'colour': RED, 'tolerance': 15},
                           {'name': 'dots', 'mode': 'markers', 'colour': GREEN, 'tolerance': 15}]}
        pv = self.app.digitize_preview(body)
        self.assertEqual([c['n'] for c in pv['curves']][1], 5)
        self.assertEqual(len(pv['curves'][0]['px']), len(pv['curves'][0]['x']))
        ds = self.app.digitize(body)
        self.assertEqual(ds['columns'][1]['name'], 'E (eV)')
        self.assertEqual(sources.check(ds['source']), 'digitize')
        self.assertEqual(sources.lineage(ds['source'])[0]['curves'], 2)
        again = self.app.reopen(ds['source'])                                 # after a restart, or from a project
        self.assertTrue(self.app.dataset(again['dataset_id'])['df'].equals(self.app.dataset(ds['dataset_id'])['df']))
        from piplotter import projects
        self.assertIn(info['id'], projects.file_ids({'files': [{'source': ds['source']}]}))   # the picture goes in it
        csv, mime, ext = self.app.table_file({'dataset_id': ds['dataset_id'], 'format': 'csv'})
        self.assertTrue(csv.startswith('﻿'.encode('utf-8')))           # spreadsheets read the accents
        back = pd.read_csv(io.BytesIO(csv), encoding='utf-8-sig')
        self.assertEqual(list(back.columns), ['curve', 'E (eV)', 'I'])
        self.assertEqual((ext, len(back)), ('csv', ds['rows']))
        if has('openpyxl'):
            xlsx, _, ext = self.app.table_file({'dataset_id': ds['dataset_id'], 'format': 'xlsx'})
            self.assertEqual(len(pd.read_excel(io.BytesIO(xlsx))), ds['rows'])
        from piplotter.service.common import ApiError
        with self.assertRaises(ApiError):
            self.app.digitize({**body, 'axes': {}})
        table = io.BytesIO(b'a,b\n1,2\n')
        csvfile = self.app.add_upload('t.csv', table, 8)
        with self.assertRaises(ApiError):                                    # only pictures
            self.app.digitize_picture({'file_id': csvfile['id']})


if __name__ == '__main__':
    unittest.main()
