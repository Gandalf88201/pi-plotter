"""Filters on a matrix (an image, a map): Gaussian or moving-average smoothing and median filter (sizes in cells),
subtraction of a tilted background plane (least squares), normalisation to 0–1, and the 2D Fourier power spectrum.
Empty cells stay empty and do not spread: averages are taken over the cells that have a value (normalised
convolution)."""
import numpy as np

from piplotter import matrices

PLUGIN = {
    'id': 'matrix_filter',
    'order': 2,
    'name': {'en': 'Matrix: smooth & filter', 'it': 'Matrice: smussa e filtra'},
    'category': 'matrix',
    'description': {'en': 'Gaussian, median or moving-average filter; subtract a background plane; normalise; 2D FFT '
                          'power spectrum.',
                    'it': 'Filtro gaussiano, mediano o a media mobile; sottrai un piano di fondo; normalizza; spettro '
                          'di potenza FFT 2D.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'filter', 'type': 'choice', 'default': 'gaussian', 'label': {'en': 'Filter', 'it': 'Filtro'},
         'choices': [{'value': 'gaussian', 'label': {'en': 'Gaussian smoothing', 'it': 'smussatura gaussiana'}},
                     {'value': 'median', 'label': {'en': 'median (removes spikes, keeps edges)', 'it': 'mediana (toglie i picchi isolati, tiene i bordi)'}},
                     {'value': 'mean', 'label': {'en': 'moving average', 'it': 'media mobile'}},
                     {'value': 'plane', 'label': {'en': 'subtract a background plane', 'it': 'sottrai un piano di fondo'}},
                     {'value': 'normalize', 'label': {'en': 'normalise to 0–1', 'it': 'normalizza a 0–1'}},
                     {'value': 'fft', 'label': {'en': '2D FFT power spectrum (log₁₀)', 'it': 'spettro di potenza FFT 2D (log₁₀)'}}]},
        {'id': 'size', 'type': 'float', 'default': 2, 'min': 0.3, 'max': 200, 'show_if': {'filter': ['gaussian', 'median', 'mean']},
         'label': {'en': 'Size in cells (Gaussian: σ; median, average: width)', 'it': 'Dimensione in celle (gaussiana: σ; mediana, media: larghezza)'}},
    ],
    'references': [
        'Knutsson, H. & Westin, C.-F. Normalized and differential convolution. Proc. IEEE CVPR, 515–523 (1993). '
        'doi:10.1109/CVPR.1993.341081',
        'Gonzalez, R. C. & Woods, R. E. Digital Image Processing, 4th ed. Pearson (2018).',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def smooth(Z, kind, size):
    """Gaussian (σ = size) or moving-average (width = size) filter over the cells that have a value."""
    from scipy import ndimage
    ok = np.isfinite(Z)
    filled = np.where(ok, Z, 0.0)
    if kind == 'gaussian':
        f = lambda a: ndimage.gaussian_filter(a, size, mode='nearest')                    # noqa: E731
    else:
        w = max(1, int(round(size)))
        f = lambda a: ndimage.uniform_filter(a, w, mode='nearest')                         # noqa: E731
    with np.errstate(invalid='ignore', divide='ignore'):
        out = f(filled) / f(ok.astype(float))
    out[~ok] = np.nan
    return out


def median(Z, size):
    from scipy import ndimage
    ok = np.isfinite(Z)
    w = max(1, int(round(size)))
    out = ndimage.median_filter(np.where(ok, Z, np.nanmedian(Z)), size=w, mode='nearest')
    out[~ok] = np.nan
    return out


def plane(Z, xs, ys):
    """The least-squares plane a + b·x + c·y through the cells with a value."""
    X, Y = np.meshgrid(xs, ys)
    ok = np.isfinite(Z)
    A = np.c_[np.ones(ok.sum()), X[ok], Y[ok]]
    coef, *_ = np.linalg.lstsq(A, Z[ok], rcond=None)
    return coef[0] + coef[1] * X + coef[2] * Y, coef


def power_spectrum(Z, xs, ys):
    """log10 |F|² of the matrix (mean removed, empty cells as the mean), frequencies in cycles per unit of x and y;
    zero frequency at the centre."""
    Zc = np.where(np.isfinite(Z), Z, np.nanmean(Z)) - np.nanmean(Z)
    F = np.fft.fftshift(np.fft.fft2(Zc))
    dx = (xs[-1] - xs[0]) / (len(xs) - 1)
    dy = (ys[-1] - ys[0]) / (len(ys) - 1)
    fx = np.fft.fftshift(np.fft.fftfreq(len(xs), dx))
    fy = np.fft.fftshift(np.fft.fftfreq(len(ys), dy))
    with np.errstate(divide='ignore'):
        P = np.log10(np.abs(F) ** 2)
    P[~np.isfinite(P)] = np.nan
    return P, fx, fy


def run(df, p, ctx):
    Z, xs, ys, yname = ctx.matrix(df)
    kind = p['filter']
    r = ctx.result()
    label = kind
    if kind in ('gaussian', 'mean'):
        out = smooth(Z, kind, float(p['size']))
        label = ctx.tr('smoothed', 'smussata')
    elif kind == 'median':
        out = median(Z, float(p['size']))
        label = ctx.tr('median filter', 'filtro mediano')
    elif kind == 'plane':
        bg, coef = plane(Z, xs, ys)
        out = Z - bg
        r.value(ctx.tr('plane: constant', 'piano: costante'), coef[0], key='a')
        r.value(ctx.tr('plane: slope along x', 'piano: pendenza lungo x'), coef[1], key='b')
        r.value(ctx.tr('plane: slope along y', 'piano: pendenza lungo y'), coef[2], key='c')
        label = ctx.tr('background removed', 'fondo sottratto')
    elif kind == 'normalize':
        lo, hi = np.nanmin(Z), np.nanmax(Z)
        if hi == lo:
            raise ValueError(ctx.tr('The matrix is constant.', 'La matrice è costante.'))
        out = (Z - lo) / (hi - lo)
        r.value(ctx.tr('minimum (→ 0)', 'minimo (→ 0)'), lo, key='min')
        r.value(ctx.tr('maximum (→ 1)', 'massimo (→ 1)'), hi, key='max')
        label = ctx.tr('normalised', 'normalizzata')
    else:
        if not (matrices.evenly_spaced(xs) and matrices.evenly_spaced(ys)):
            raise ValueError(ctx.tr('The FFT needs evenly spaced x and y: resample the matrix first.',
                                    'La FFT richiede x e y equispaziate: ricampiona prima la matrice.'))
        out, xs, ys = power_spectrum(Z, xs, ys)
        yname = ctx.tr('frequency along y', 'frequenza lungo y')
        label = ctx.tr('power spectrum', 'spettro di potenza')
        r.text(ctx.tr('Frequencies in cycles per unit of x and y; zero frequency at the centre.',
                      'Frequenze in cicli per unità di x e di y; frequenza zero al centro.'))
    if kind not in ('fft', 'normalize'):
        changed = np.nanstd(out - Z) if kind != 'plane' else np.nanstd(bg)
        r.value(ctx.tr('RMS of what was removed', 'RMS di ciò che è stato tolto'), float(changed), key='rms_removed')
    r.data(matrices.to_frame(out, xs, ys, yname), name=ctx.tr('matrix', 'matrice') + f' ({label})',
           plot={'kind': 'heatmap', 'x': yname, 'y': []})
    return r
