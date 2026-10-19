"""Data back from a picture of a graph (a scanned figure, a screenshot of a paper): the "reverse plot".

The picture is calibrated with four points clicked on it — two on the X axis and two on the Y axis, each with its
value — on linear or logarithmic axes. A value is read from the position of a pixel along each axis (its projection
on the line through the two points of that axis), so a picture scanned slightly rotated is read as well. The curves
are then taken from the picture:

    points   the points clicked on the picture, as they are
    line     every pixel of the colour of a curve: one point per column of pixels, the middle of the run of that
             colour nearest to the curve found so far (a curve crossing another one, or its own label, is followed)
    markers  the symbols of a scatter plot in one colour: the centre of each blob of that colour

Only NumPy and Pillow (already needed to read pictures); the markers need SciPy (ndimage.label). The method is the
one of the usual digitisers (Engauge Digitizer, WebPlotDigitizer, LabPlot's Data Picker), written here anew.
"""
import math

import numpy as np

MAX_PIXELS = 60e6           # larger pictures are refused (a scan at 600 dpi of a whole page is about 35 Mpx)
MAX_POINTS = 20000          # points of one curve kept (a very wide picture: evenly thinned)
MODES = ('points', 'line', 'markers')


class DigitizeError(ValueError):
    """The calibration or a curve cannot be read (said to the user as it is)."""


def load_rgb(path):
    """The picture as an H × W × 3 array of 0…255 (transparent pixels on white)."""
    from PIL import Image
    with Image.open(path) as im:
        im.seek(0)
        if im.width * im.height > MAX_PIXELS:
            raise DigitizeError(f'The picture has {im.width * im.height / 1e6:.0f} Mpx; the limit is '
                                f'{MAX_PIXELS / 1e6:.0f} Mpx: save it at a lower resolution.')
        if im.mode in ('RGBA', 'LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info):
            im = im.convert('RGBA')
            white = Image.new('RGBA', im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(white, im)
        return np.asarray(im.convert('RGB'))


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class Axes:
    """The calibration: pixel (u right, v down) → data (x, y).

    axes = {'x': [{'px': [u, v], 'value': x1}, {'px': [u, v], 'value': x2}], 'y': [... two ...],
            'xlog': False, 'ylog': False}
    """

    def __init__(self, axes):
        if not isinstance(axes, dict):
            raise DigitizeError('Calibrate the axes first: two points on X and two on Y.')
        self.log = {'x': bool(axes.get('xlog')), 'y': bool(axes.get('ylog'))}
        self.p, self.val = {}, {}
        for name in ('x', 'y'):
            pts = axes.get(name) or []
            if len(pts) != 2 or not all(isinstance(p, dict) for p in pts):
                raise DigitizeError(f'Click two points on the {name.upper()} axis and type their values.')
            px = [p.get('px') for p in pts]
            if not all(isinstance(q, (list, tuple)) and len(q) == 2 and None not in map(_num, q) for q in px):
                raise DigitizeError(f'Click the two points of the {name.upper()} axis on the picture.')
            vals = [_num(p.get('value')) for p in pts]
            if None in vals:
                raise DigitizeError(f'Type the values of the two points of the {name.upper()} axis.')
            if vals[0] == vals[1]:
                raise DigitizeError(f'The two points of the {name.upper()} axis need two different values.')
            if self.log[name]:
                if min(vals) <= 0:
                    raise DigitizeError(f'A logarithmic {name.upper()} axis needs positive values.')
                vals = [math.log10(v) for v in vals]
            a, b = (np.array([_num(c) for c in q], float) for q in px)
            if np.hypot(*(b - a)) < 2:
                raise DigitizeError(f'The two points of the {name.upper()} axis are on the same place of the picture.')
            self.p[name], self.val[name] = (a, b), vals

    def _along(self, name, uv):
        a, b = self.p[name]
        d = b - a
        t = ((uv - a) @ d) / (d @ d)                       # where the pixel falls along the axis, 0 at a, 1 at b
        v0, v1 = self.val[name]
        out = v0 + t * (v1 - v0)
        return 10 ** out if self.log[name] else out

    def data(self, uv):
        """(x, y) of pixels uv (N × 2)."""
        uv = np.asarray(uv, float).reshape(-1, 2)
        return self._along('x', uv), self._along('y', uv)


def colour_mask(rgb, colour, tolerance, region=None):
    """Pixels whose colour is within tolerance (percent of the largest RGB distance) of colour, inside region
    [u0, v0, u1, v1] (the whole picture when None)."""
    target = np.array(parse_colour(colour), float)
    h, w = rgb.shape[:2]
    u0, v0, u1, v1 = _region(region, w, h)
    sub = rgb[v0:v1, u0:u1].astype(float)
    dist = np.sqrt(((sub - target) ** 2).sum(axis=2))
    limit = max(0.0, min(100.0, float(tolerance))) / 100 * math.sqrt(3) * 255
    mask = np.zeros((h, w), bool)
    mask[v0:v1, u0:u1] = dist <= limit
    return mask


def _region(region, w, h):
    if not region:
        return 0, 0, w, h
    vals = [_num(c) for c in region]
    if len(vals) != 4 or None in vals:
        raise DigitizeError('The region is not a box on the picture.')
    u0, u1 = sorted(vals[0::2])
    v0, v1 = sorted(vals[1::2])
    u0, v0 = max(0, int(math.floor(u0))), max(0, int(math.floor(v0)))
    u1, v1 = min(w, int(math.ceil(u1)) + 1), min(h, int(math.ceil(v1)) + 1)
    if u1 - u0 < 2 or v1 - v0 < 2:
        raise DigitizeError('The region is too small.')
    return u0, v0, u1, v1


def parse_colour(colour):
    if isinstance(colour, (list, tuple)) and len(colour) >= 3:
        return [int(max(0, min(255, round(float(c))))) for c in colour[:3]]
    s = str(colour or '').strip().lstrip('#')
    if len(s) == 3:
        s = ''.join(c * 2 for c in s)
    try:
        if len(s) != 6:
            raise ValueError
        return [int(s[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        raise DigitizeError('Pick the colour of the curve on the picture.') from None


def trace_line(mask, gap=3):
    """One pixel point (u, v) per column of the mask: the middle of the run of pixels nearest to the curve so far
    (the longest run where the curve starts). Runs closer than gap pixels are one run."""
    cols = np.flatnonzero(mask.any(axis=0))
    out, last = [], None
    for u in cols:
        rows = np.flatnonzero(mask[:, u])
        breaks = np.flatnonzero(np.diff(rows) > gap)
        runs = np.split(rows, breaks + 1)
        mids = np.array([(r[0] + r[-1]) / 2 for r in runs])
        if last is None or u - last[0] > 50:              # the start, or after a long empty stretch
            k = int(np.argmax([len(r) for r in runs]))
        else:
            k = int(np.argmin(np.abs(mids - last[1])))
        last = (u, mids[k])
        out.append(last)
    return np.array(out, float).reshape(-1, 2)


def find_markers(mask, min_size=4):
    """Centres (u, v) of the blobs of the mask with at least min_size pixels."""
    from scipy import ndimage
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), bool))
    if not n:
        return np.zeros((0, 2))
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum(mask, labels, idx)
    keep = idx[sizes >= max(1, int(min_size))]
    if not len(keep):
        return np.zeros((0, 2))
    centres = np.array(ndimage.center_of_mass(mask, labels, keep), float)       # (row, column)
    return centres[:, ::-1]


def thin(uv, most=MAX_POINTS):
    if len(uv) <= most:
        return uv
    return uv[np.linspace(0, len(uv) - 1, most).round().astype(int)]


def series_pixels(rgb, s):
    """The pixel points of one curve description s ({'mode', 'points' | 'colour', 'tolerance', 'region',
    'min_size', 'every'})."""
    mode = s.get('mode', 'points')
    if mode not in MODES:
        raise DigitizeError(f'Unknown way of reading a curve: {mode}.')
    if mode == 'points':
        pts = [p for p in s.get('points') or [] if isinstance(p, (list, tuple)) and len(p) == 2
               and None not in (_num(p[0]), _num(p[1]))]
        return np.array(pts, float).reshape(-1, 2)
    if rgb is None:
        raise DigitizeError('The picture is needed to read a curve by its colour.')
    mask = colour_mask(rgb, s.get('colour'), s.get('tolerance', 12), s.get('region'))
    if not mask.any():
        raise DigitizeError(f'No pixel of that colour in “{s.get("name") or "the curve"}”: '
                            'pick the colour on the curve again, or raise the tolerance.')
    if mode == 'markers':
        return find_markers(mask, s.get('min_size', 4))
    uv = trace_line(mask)
    every = int(_num(s.get('every')) or 1)
    return thin(uv[::max(1, every)])


def needs_scipy(series):
    return any(isinstance(s, dict) and s.get('mode') == 'markers' for s in series or [])


def extract(rgb, axes, series):
    """[{'name', 'mode', 'px': N × 2 pixels, 'x', 'y'}] for each curve; x sorted for lines and markers (points
    clicked on request: a loop is clicked in its order)."""
    cal = Axes(axes)
    if not series:
        raise DigitizeError('Add a curve: click its points, or pick its colour.')
    out = []
    for k, s in enumerate(series):
        if not isinstance(s, dict):
            continue
        name = str(s.get('name') or f'curve {k + 1}')
        uv = series_pixels(rgb, {**s, 'name': name})
        x, y = cal.data(uv) if len(uv) else (np.zeros(0), np.zeros(0))
        if s.get('mode') in ('line', 'markers') or s.get('sort'):      # points clicked keep their order (loops)
            order = np.argsort(x, kind='stable')
            uv, x, y = uv[order], x[order], y[order]
        out.append({'name': name, 'mode': s.get('mode', 'points'), 'px': uv, 'x': x, 'y': y})
    return out


def to_frame(curves, xname='x', yname='y'):
    """The table of the curves: X and Y for one curve; a column of the curve's name before them for several."""
    import pandas as pd
    xname, yname = str(xname or 'x'), str(yname or 'y')
    if xname == yname:
        yname += ' (y)'
    frames = []
    for c in curves:
        f = pd.DataFrame({xname: c['x'], yname: c['y']})
        if len(curves) > 1:
            f.insert(0, 'curve', c['name'])
        frames.append(f)
    if not frames or not sum(len(f) for f in frames):
        raise DigitizeError('No point was read: click points on the curves, or pick their colour.')
    return pd.concat(frames, ignore_index=True)
