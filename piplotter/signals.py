"""Helpers shared by the signal analyses (filters, convolution, interpolation, curve arithmetic):
a regular grid for methods that need evenly spaced points, kernels, sorting and merging repeated x."""
import numpy as np


def clean(x, y):
    """x sorted ascending, repeated x merged (mean of their y), non-finite points dropped."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    order = np.argsort(x, kind='stable')
    x, y = x[order], y[order]
    if x.size and np.any(np.diff(x) == 0):
        ux, inv = np.unique(x, return_inverse=True)
        y = np.bincount(inv, weights=y) / np.bincount(inv)
        x = ux
    return x, y


def uniform(x, y, tolerance=0.01):
    """(x, y, resampled): the signal on evenly spaced x. Already even (every step within tolerance of the median
    step): as it is; otherwise linearly resampled with the median step over the same range."""
    x, y = clean(x, y)
    if x.size < 4:
        raise ValueError('At least four points are needed.')
    steps = np.diff(x)
    dx = float(np.median(steps))
    if dx <= 0:
        raise ValueError('The x values do not increase.')
    if np.all(np.abs(steps - dx) <= tolerance * dx):
        return x, y, False
    n = int(round((x[-1] - x[0]) / dx)) + 1
    grid = x[0] + dx * np.arange(n)
    return grid, np.interp(grid, x, y), True


KERNELS = ('gaussian', 'lorentzian', 'boxcar', 'exponential')


def kernel(kind, width, dx):
    """A kernel sampled every dx, centred, of unit area (sum 1). width: the FWHM for gaussian and lorentzian, the
    full width for boxcar, the decay constant τ for exponential (one-sided, causal)."""
    if not width or width <= 0:
        raise ValueError('The width of the kernel must be positive.')
    if kind == 'boxcar':
        half = max(1, int(round(width / dx / 2)))
        k = np.ones(2 * half + 1)
    else:
        reach = {'gaussian': 4 * width, 'lorentzian': 25 * width, 'exponential': 8 * width}[kind]
        half = max(2, int(np.ceil(reach / dx)))
        t = dx * np.arange(-half, half + 1)
        if kind == 'gaussian':
            k = np.exp(-4 * np.log(2) * t ** 2 / width ** 2)
        elif kind == 'lorentzian':
            k = 1 / (1 + (2 * t / width) ** 2)
        else:
            k = np.where(t >= 0, np.exp(-np.clip(t, 0, None) / width), 0.0)
    return k / k.sum()


def fwhm(x, y):
    """Full width at half maximum of the highest peak of y (linear interpolation between points), or nan."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    i = int(np.nanargmax(y))
    half = y[i] / 2
    left = np.where(y[:i] < half)[0]
    right = np.where(y[i:] < half)[0]
    if not left.size or not right.size:
        return float('nan')
    a, b = left[-1], i + right[0]
    xl = np.interp(half, [y[a], y[a + 1]], [x[a], x[a + 1]])
    xr = np.interp(half, [y[b], y[b - 1]], [x[b], x[b - 1]])
    return float(xr - xl)


def _as_float(x):
    """x as float numbers (dates as nanoseconds), for bucketing only."""
    x = np.asarray(x)
    return x.astype('datetime64[ns]').astype(np.int64).astype(float) if x.dtype.kind == 'M' else x.astype(float)


def m4_indices(x, y, buckets):
    """Points that draw a long curve exactly at a given width: in each of `buckets` equal slices of x, the first,
    last, lowest and highest point (M4 aggregation; Jugel et al., Proc. VLDB Endow. 7, 797–808, 2014). Drawn with
    one slice per pixel column the line looks the same as with every point. x increasing; returns sorted indices."""
    n = len(y)
    if n <= 4 * buckets:
        return np.arange(n)
    xf, y = _as_float(x), np.asarray(y, float)
    span = xf[-1] - xf[0]
    if not span > 0:
        return np.arange(n)
    b = np.minimum(((xf - xf[0]) / span * buckets).astype(np.int64), buckets - 1)
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    lengths = np.diff(np.r_[starts, n])
    seg = np.repeat(np.arange(starts.size), lengths)

    def first_where(eq):
        pos = np.flatnonzero(eq)
        _, at = np.unique(seg[pos], return_index=True)
        return pos[at]
    lo = first_where(y == np.repeat(np.minimum.reduceat(y, starts), lengths))
    hi = first_where(y == np.repeat(np.maximum.reduceat(y, starts), lengths))
    return np.unique(np.r_[starts, starts + lengths - 1, lo, hi])


def lttb_indices(x, y, n_out):
    """n_out points that keep the look of a curve, peaks included: Largest-Triangle-Three-Buckets (Steinarsson, S.
    Downsampling time series for visual representation, MSc thesis, University of Iceland, 2013). The first and last
    points are kept; from each bucket, the point making the largest triangle with the point kept before and the mean
    of the next bucket. x increasing; returns sorted indices."""
    n = len(y)
    if n_out >= n or n_out < 3:
        return np.arange(n)
    xf, y = _as_float(x), np.asarray(y, float)
    every = (n - 2) / (n_out - 2)
    edges = np.minimum(np.floor(np.arange(n_out - 1) * every).astype(np.int64) + 1, n - 1)
    out = np.empty(n_out, np.int64)
    out[0], out[-1], a = 0, n - 1, 0
    for i in range(n_out - 2):
        s, e = edges[i], max(edges[i + 1], edges[i] + 1)
        if i + 2 < n_out - 1:
            ns, ne = edges[i + 1], max(edges[i + 2], edges[i + 1] + 1)
            cx, cy = xf[ns:ne].mean(), y[ns:ne].mean()
        else:
            cx, cy = xf[-1], y[-1]
        area = np.abs((xf[a] - cx) * (y[s:e] - y[a]) - (xf[a] - xf[s:e]) * (cy - y[a]))
        a = s + int(np.argmax(area))
        out[i + 1] = a
    return out
