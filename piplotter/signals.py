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
