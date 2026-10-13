"""Frequency filters (scipy.signal): low-pass, high-pass, band-pass and band-stop, as a zero-phase Butterworth
filter (forward and backward, no shift of the peaks) or an ideal cut in the Fourier transform. Frequencies are in
cycles per unit of x (e.g. Hz when x is in seconds); unevenly spaced points are first resampled evenly."""
import numpy as np
import pandas as pd

from piplotter import signals

PLUGIN = {
    'id': 'frequency_filter',
    'order': 11,
    'name': {'en': 'Frequency filter (FFT / Butterworth)', 'it': 'Filtro in frequenza (FFT / Butterworth)'},
    'category': 'signal',
    'description': {'en': 'Low-pass, high-pass, band-pass or band-stop: zero-phase Butterworth or ideal FFT cut; '
                          'cut-off in cycles per unit of x.',
                    'it': 'Passa-basso, passa-alto, passa-banda o elimina-banda: Butterworth a fase nulla o taglio '
                          'ideale nella FFT; frequenza di taglio in cicli per unità di x.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        {'id': 'kind', 'type': 'choice', 'default': 'lowpass', 'label': {'en': 'Filter', 'it': 'Filtro'},
         'choices': [{'value': 'lowpass', 'label': {'en': 'low-pass (keeps slow changes, removes noise)', 'it': 'passa-basso (tiene le variazioni lente, toglie il rumore)'}},
                     {'value': 'highpass', 'label': {'en': 'high-pass (removes drift)', 'it': 'passa-alto (toglie la deriva)'}},
                     {'value': 'bandpass', 'label': {'en': 'band-pass', 'it': 'passa-banda'}},
                     {'value': 'bandstop', 'label': {'en': 'band-stop (e.g. mains 50 Hz)', 'it': 'elimina-banda (es. rete 50 Hz)'}}]},
        {'id': 'cutoff', 'type': 'float', 'optional': True, 'min': 0,
         'label': {'en': 'Cut-off frequency (empty = 1/10 of Nyquist); band: lower edge',
                   'it': 'Frequenza di taglio (vuoto = 1/10 di Nyquist); banda: estremo inferiore'}},
        {'id': 'cutoff2', 'type': 'float', 'optional': True, 'min': 0, 'show_if': {'kind': ['bandpass', 'bandstop']},
         'label': {'en': 'Upper edge of the band', 'it': 'Estremo superiore della banda'}},
        {'id': 'design', 'type': 'choice', 'default': 'butter', 'label': {'en': 'Design', 'it': 'Tipo'},
         'choices': [{'value': 'butter', 'label': {'en': 'Butterworth, zero phase', 'it': 'Butterworth, fase nulla'}},
                     {'value': 'fft', 'label': {'en': 'ideal cut in the FFT', 'it': 'taglio ideale nella FFT'}}]},
        {'id': 'order', 'type': 'int', 'default': 4, 'min': 1, 'max': 12, 'show_if': {'design': ['butter']},
         'label': {'en': 'Order (steepness)', 'it': 'Ordine (pendenza)'}},
    ],
    'references': [
        'Butterworth, S. On the theory of filter amplifiers. Wireless Engineer 7, 536–541 (1930).',
        'Gustafsson, F. Determining the initial states in forward-backward filtering. IEEE Trans. Signal Process. 44, '
        '988–992 (1996). doi:10.1109/78.492552',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def apply(x, y, kind, low, high, design, order):
    """The filtered signal (x evenly spaced)."""
    from scipy import signal
    dx = float(x[1] - x[0])
    fs = 1.0 / dx
    if design == 'fft':
        spec = np.fft.rfft(y)
        f = np.fft.rfftfreq(y.size, dx)
        if kind == 'lowpass':
            keep = f <= low
        elif kind == 'highpass':
            keep = f >= low
        else:
            keep = (f >= low) & (f <= high) if kind == 'bandpass' else (f < low) | (f > high)
        return np.fft.irfft(spec * keep, n=y.size)
    wn = low if kind in ('lowpass', 'highpass') else [low, high]
    sos = signal.butter(int(order), wn, btype=kind, fs=fs, output='sos')
    pad = min(y.size - 1, 3 * (2 * len(sos) + 1))
    return signal.sosfiltfilt(sos, y, padlen=pad)


def run(df, p, ctx):
    x0, y0 = signals.clean(*ctx.signal(df, p['x'], p['y']))
    try:
        x, y, resampled = signals.uniform(x0, y0)
    except ValueError as exc:
        raise ValueError(ctx.tr(str(exc), 'Servono almeno quattro punti.'))
    dx = float(x[1] - x[0])
    nyq = 0.5 / dx
    low = p.get('cutoff') if p.get('cutoff') else nyq / 10
    high = p.get('cutoff2')
    band = p['kind'] in ('bandpass', 'bandstop')
    if band and not high:
        raise ValueError(ctx.tr('A band needs its upper edge too.', 'Una banda richiede anche l’estremo superiore.'))
    for f in (low, high) if band else (low,):
        if not 0 < f < nyq:
            raise ValueError(ctx.tr(f'Frequencies must be between 0 and the Nyquist frequency {nyq:.4g} '
                                    f'(half of 1/step).',
                                    f'Le frequenze devono stare tra 0 e la frequenza di Nyquist {nyq:.4g} '
                                    f'(metà di 1/passo).'))
    if band and not low < high:
        raise ValueError(ctx.tr('The lower edge must be below the upper one.', 'L’estremo inferiore deve stare sotto quello superiore.'))
    filtered = apply(x, y, p['kind'], low, high, p['design'], p['order'])
    xname, yname = ctx.signal_names(p['x'], p['y'])
    name = f'{yname} ({ctx.tr("filtered", "filtrato")})'
    removed = ctx.tr('removed', 'rimosso')
    r = ctx.result()
    if resampled:
        r.text(ctx.tr(f'The points were not evenly spaced: resampled every {dx:.4g} (linear) before filtering.',
                      f'I punti non erano equispaziati: ricampionati ogni {dx:.4g} (lineare) prima del filtro.'))
    r.value(ctx.tr('step of x', 'passo di x'), dx, key='dx')
    r.value(ctx.tr('Nyquist frequency', 'frequenza di Nyquist'), nyq, key='nyquist')
    r.value(ctx.tr('cut-off', 'taglio'), f'{low:.4g}' + (f' … {high:.4g}' if band else ''))
    r.keep('cutoff', low)
    r.value(ctx.tr('RMS of what was removed', 'RMS di ciò che è stato tolto'), float(np.sqrt(np.mean((y - filtered) ** 2))),
            key='rms_removed')
    r.overlay(pd.DataFrame({xname: x, name: filtered}), xname, name, label=name, style={'linewidth': 1.1})
    out = pd.DataFrame({xname: x, yname: y, name: filtered, removed: y - filtered})
    r.data(out, name=name, plot={'kind': 'line', 'x': xname, 'y': [yname, name], 'series': {yname: {'alpha': 0.35}}})
    return r
