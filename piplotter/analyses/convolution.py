"""Convolution with a kernel (instrument broadening, a decay response) and deconvolution: Wiener (regularised
division in the Fourier domain) or Richardson–Lucy (iterative, keeps the signal positive). The kernel — Gaussian,
Lorentzian, box or one-sided exponential — has unit area and its width in x units; unevenly spaced points are first
resampled evenly."""
import numpy as np
import pandas as pd

from piplotter import signals

PLUGIN = {
    'id': 'convolution',
    'order': 13,
    'name': {'en': 'Convolution & deconvolution', 'it': 'Convoluzione e deconvoluzione'},
    'category': 'signal',
    'description': {'en': 'Broaden with a Gaussian, Lorentzian, box or exponential kernel, or remove a known broadening '
                          '(Wiener, Richardson–Lucy).',
                    'it': 'Allarga con un nucleo gaussiano, lorentziano, rettangolare o esponenziale, o togli un '
                          'allargamento noto (Wiener, Richardson–Lucy).'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        {'id': 'mode', 'type': 'choice', 'default': 'convolve', 'label': {'en': 'Operation', 'it': 'Operazione'},
         'choices': [{'value': 'convolve', 'label': {'en': 'convolve (broaden)', 'it': 'convolvi (allarga)'}},
                     {'value': 'wiener', 'label': {'en': 'deconvolve: Wiener', 'it': 'deconvolvi: Wiener'}},
                     {'value': 'lucy', 'label': {'en': 'deconvolve: Richardson–Lucy (positive signals)', 'it': 'deconvolvi: Richardson–Lucy (segnali positivi)'}}]},
        {'id': 'kernel', 'type': 'choice', 'default': 'gaussian', 'label': {'en': 'Kernel', 'it': 'Nucleo'},
         'choices': [{'value': 'gaussian', 'label': {'en': 'Gaussian', 'it': 'gaussiano'}},
                     {'value': 'lorentzian', 'label': {'en': 'Lorentzian', 'it': 'lorentziano'}},
                     {'value': 'boxcar', 'label': {'en': 'box (moving average)', 'it': 'rettangolare (media mobile)'}},
                     {'value': 'exponential', 'label': {'en': 'one-sided exponential (decay)', 'it': 'esponenziale (decadimento)'}}]},
        {'id': 'width', 'type': 'float', 'default': 1.0, 'min': 0,
         'label': {'en': 'Width in x units (FWHM; box: full width; exponential: τ)',
                   'it': 'Larghezza in unità di x (FWHM; rettangolare: intera; esponenziale: τ)'}},
        {'id': 'noise', 'type': 'float', 'default': 0.01, 'min': 0, 'show_if': {'mode': ['wiener']},
         'label': {'en': 'Regularisation (noise / signal power)', 'it': 'Regolarizzazione (potenza rumore / segnale)'},
         'help': {'en': 'Larger values give a smoother, less sharpened result.',
                  'it': 'Valori più grandi danno un risultato più liscio, meno affinato.'}},
        {'id': 'iterations', 'type': 'int', 'default': 30, 'min': 1, 'max': 2000, 'show_if': {'mode': ['lucy']},
         'label': {'en': 'Iterations', 'it': 'Iterazioni'}},
    ],
    'references': [
        'Wiener, N. Extrapolation, Interpolation, and Smoothing of Stationary Time Series (MIT Press, 1949).',
        'Richardson, W. H. Bayesian-based iterative method of image restoration. J. Opt. Soc. Am. 62, 55–59 (1972). '
        'doi:10.1364/JOSA.62.000055',
        'Lucy, L. B. An iterative technique for the rectification of observed distributions. Astron. J. 79, 745–754 '
        '(1974). doi:10.1086/111605',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def convolve(y, k):
    """y convolved with the centred kernel k, same length; the ends padded with their edge values."""
    from scipy.signal import fftconvolve
    h = k.size // 2
    padded = np.pad(y, h, mode='edge')
    return fftconvolve(padded, k, mode='same')[h:h + y.size]


def wiener(y, k, noise):
    h = k.size // 2
    padded = np.pad(y, h, mode='edge')
    n = padded.size
    kk = np.zeros(n)
    kk[:k.size] = k
    kk = np.roll(kk, -h)                                    # kernel centred on index 0
    K = np.fft.rfft(kk)
    lam = noise * np.max(np.abs(K)) ** 2
    out = np.fft.irfft(np.fft.rfft(padded) * np.conj(K) / (np.abs(K) ** 2 + lam), n=n)
    return out[h:h + y.size]


def lucy(y, k, iterations):
    u = np.full_like(y, max(float(np.mean(y)), 1e-12))
    flipped = k[::-1]
    for _ in range(int(iterations)):
        ratio = y / np.maximum(convolve(u, k), 1e-12)
        u = u * convolve(ratio, flipped)
    return u


def run(df, p, ctx):
    try:
        x, y, resampled = signals.uniform(*ctx.signal(df, p['x'], p['y']))
        dx = float(x[1] - x[0])
        k = signals.kernel(p['kernel'], p['width'], dx)
    except ValueError as exc:
        raise ValueError(ctx.tr(str(exc), 'Servono almeno quattro punti e una larghezza positiva.'))
    if k.size > y.size:
        raise ValueError(ctx.tr('The kernel is wider than the signal: lower its width.',
                                'Il nucleo è più largo del segnale: riduci la larghezza.'))
    r = ctx.result()
    if resampled:
        r.text(ctx.tr(f'The points were not evenly spaced: resampled every {dx:.4g} (linear).',
                      f'I punti non erano equispaziati: ricampionati ogni {dx:.4g} (lineare).'))
    shift = 0.0
    if p['mode'] == 'convolve':
        out, word = convolve(y, k), ctx.tr('convolved', 'convoluto')
    elif p['mode'] == 'wiener':
        out, word = wiener(y, k, p['noise']), ctx.tr('deconvolved', 'deconvoluto')
    else:
        if y.min() <= 0:                                    # Richardson–Lucy works on positive values
            shift = -float(y.min()) + 1e-9 * (float(np.ptp(y)) or 1.0)
            r.text(ctx.tr(f'Shifted by {shift:.4g} to be positive, and back after.',
                          f'Spostato di {shift:.4g} per renderlo positivo, e riportato dopo.'))
        out, word = lucy(y + shift, k, p['iterations']) - shift, ctx.tr('deconvolved', 'deconvoluto')
    xname, yname = ctx.signal_names(p['x'], p['y'])
    name = f'{yname} ({word})'
    r.value(ctx.tr('kernel', 'nucleo'), f'{p["kernel"]}, {p["width"]:g}')
    r.value(ctx.tr('kernel points', 'punti del nucleo'), int(k.size))
    for label, curve, key in ((ctx.tr('FWHM before', 'FWHM prima'), y, 'fwhm_before'),
                              (ctx.tr('FWHM after', 'FWHM dopo'), out, 'fwhm_after')):
        w = signals.fwhm(x, curve)
        if np.isfinite(w):
            r.value(label, w, key=key)
    r.overlay(pd.DataFrame({xname: x, name: out}), xname, name, label=name, style={'linewidth': 1.1})
    r.data(pd.DataFrame({xname: x, yname: y, name: out}), name=name,
           plot={'kind': 'line', 'x': xname, 'y': [yname, name], 'series': {yname: {'alpha': 0.4}}})
    return r
