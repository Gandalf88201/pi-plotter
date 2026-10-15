"""Spots and particles in a matrix (an image, a map): the connected regions brighter (or darker) than a threshold —
Otsu's automatic threshold, a number of standard deviations above the background (median and MAD of the matrix), or
a value — after an optional Gaussian smoothing that only guides the detection. For each spot: its cells, area,
equivalent diameter, centroid weighted by the values above the threshold, maximum and its position, integrated value
above the threshold; spots smaller than a minimum area and, if asked, those touching the edge are left out. The
centroids are marked on a copy of the figure; the areas are given as a histogram."""
import numpy as np
import pandas as pd

from piplotter.analyses.matrix_stats import cell_widths

PLUGIN = {
    'id': 'matrix_spots',
    'order': 5,
    'name': {'en': 'Matrix: find spots / particles', 'it': 'Matrice: trova spot / particelle'},
    'category': 'matrix',
    'description': {'en': 'Count the spots brighter (or darker) than a threshold (Otsu, n σ, a value): area, '
                          'diameter, centroid, intensity of each.',
                    'it': 'Conta gli spot più chiari (o più scuri) di una soglia (Otsu, n σ, un valore): area, '
                          'diametro, baricentro, intensità di ciascuno.'},
    'suits': [                                          # figures it suits (piplotter/advisor.py)
        {'figure': 'matrix', 'score': 66,
         'reason': {'en': 'Spots or particles: count them, with their areas and centres.',
                    'it': 'Spot o particelle: contali, con le loro aree e i centri.'}},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'polarity', 'type': 'choice', 'default': 'bright', 'label': {'en': 'Spots are', 'it': 'Gli spot sono'},
         'choices': [{'value': 'bright', 'label': {'en': 'brighter than the background', 'it': 'più chiari del fondo'}},
                     {'value': 'dark', 'label': {'en': 'darker than the background', 'it': 'più scuri del fondo'}}]},
        {'id': 'method', 'type': 'choice', 'default': 'sigma', 'label': {'en': 'Threshold', 'it': 'Soglia'},
         'choices': [{'value': 'sigma', 'label': {'en': 'n σ above the background (robust)', 'it': 'n σ sopra il fondo (robusta)'}},
                     {'value': 'otsu', 'label': {'en': 'Otsu (automatic, two populations)', 'it': 'Otsu (automatica, due popolazioni)'}},
                     {'value': 'value', 'label': {'en': 'a value', 'it': 'un valore'}}]},
        {'id': 'k', 'type': 'float', 'default': 5, 'min': 0.5, 'max': 100, 'show_if': {'method': ['sigma']},
         'label': {'en': 'n (σ above the median)', 'it': 'n (σ sopra la mediana)'}},
        {'id': 'value', 'type': 'float', 'optional': True, 'show_if': {'method': ['value']},
         'label': {'en': 'Threshold value', 'it': 'Valore di soglia'}},
        {'id': 'smooth', 'type': 'float', 'default': 1, 'min': 0, 'max': 50,
         'label': {'en': 'Smoothing before detecting (σ in cells, 0 = none)', 'it': 'Smussatura prima di cercare (σ in celle, 0 = nessuna)'}},
        {'id': 'min_cells', 'type': 'int', 'default': 3, 'min': 1, 'max': 1000000,
         'label': {'en': 'Smallest spot (cells)', 'it': 'Spot più piccolo (celle)'}},
        {'id': 'edge', 'type': 'bool', 'default': False,
         'label': {'en': 'Leave out spots touching the edge', 'it': 'Escludi gli spot che toccano il bordo'}},
    ],
    'references': [
        'Otsu, N. A threshold selection method from gray-level histograms. IEEE Trans. Syst. Man Cybern. 9, 62–66 '
        '(1979). doi:10.1109/TSMC.1979.4310076',
        'Gonzalez, R. C. & Woods, R. E. Digital Image Processing, 4th ed. Pearson (2018).',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def otsu(values, bins=256):
    """Otsu's threshold: the cut of the histogram that maximises the variance between the two classes."""
    v = values[np.isfinite(values)]
    hist, edges = np.histogram(v, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centres) / np.maximum(w0, 1)
    m1 = (np.sum(hist * centres) - np.cumsum(hist * centres)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(edges[int(np.argmax(between[:-1])) + 1])


def find_spots(Z, xs, ys, threshold, polarity='bright', smooth=0.0, min_cells=1, edge=False):
    """[{…}] of the spots of Z beyond threshold (8-connected), the labels and the mask."""
    from scipy import ndimage
    ok = np.isfinite(Z)
    fill = np.where(ok, Z, np.nanmedian(Z))
    guide = ndimage.gaussian_filter(fill, smooth, mode='nearest') if smooth > 0 else fill
    sign = 1.0 if polarity == 'bright' else -1.0
    mask = (sign * (guide - threshold) > 0) & ok
    labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
    area = np.outer(cell_widths(ys), cell_widths(xs))
    X, Y = np.meshgrid(xs, ys)
    above = np.clip(sign * (fill - threshold), 0, None)
    spots = []
    for k, sl in enumerate(ndimage.find_objects(labels), 1):
        if sl is None:
            continue
        cells = labels[sl] == k
        count = int(cells.sum())
        if count < min_cells:
            continue
        touches = sl[0].start == 0 or sl[1].start == 0 or sl[0].stop == Z.shape[0] or sl[1].stop == Z.shape[1]
        if edge and touches:
            continue
        a, w = area[sl][cells], above[sl][cells] * area[sl][cells]
        vals = fill[sl][cells]
        i = int(np.argmax(sign * vals))
        wsum = w.sum()
        xw, yw = X[sl][cells], Y[sl][cells]
        cx = float((w * xw).sum() / wsum) if wsum > 0 else float(xw.mean())
        cy = float((w * yw).sum() / wsum) if wsum > 0 else float(yw.mean())
        total = float(a.sum())
        spots.append({'cells': count, 'area': total, 'diameter': float(2 * np.sqrt(total / np.pi)),
                      'x': cx, 'y': cy, 'peak': float(vals[i]), 'peak_x': float(xw[i]), 'peak_y': float(yw[i]),
                      'integral': float(wsum), 'edge': bool(touches)})
    return spots, labels, mask


def run(df, p, ctx):
    Z, xs, ys, yname = ctx.matrix(df)
    vals = Z[np.isfinite(Z)]
    if vals.size < 9:
        raise ValueError(ctx.tr('The matrix is too small.', 'La matrice è troppo piccola.'))
    sign = 1.0 if p['polarity'] == 'bright' else -1.0
    med = float(np.median(vals))
    sigma = float(1.4826 * np.median(np.abs(vals - med)))
    r = ctx.result()
    if p['method'] == 'value':
        if p.get('value') is None:
            raise ValueError(ctx.tr('Write the threshold value.', 'Scrivi il valore di soglia.'))
        thr = float(p['value'])
        how = ctx.tr('a value', 'un valore')
    elif p['method'] == 'otsu':
        thr = otsu(vals)
        how = 'Otsu'
    else:
        if sigma == 0:
            sigma = float(np.std(vals))
        thr = med + sign * float(p['k']) * sigma
        how = ctx.tr(f'median {sign * float(p["k"]):+g} σ (σ = 1.4826 × MAD = {sigma:.4g})',
                     f'mediana {sign * float(p["k"]):+g} σ (σ = 1,4826 × MAD = {sigma:.4g})')
    spots, labels, mask = find_spots(Z, xs, ys, thr, p['polarity'], float(p['smooth'] or 0), int(p['min_cells']),
                                     bool(p['edge']))
    r.text(ctx.tr(f'Threshold {thr:.6g} ({how}); {len(spots)} spots of at least {int(p["min_cells"])} cells.',
                  f'Soglia {thr:.6g} ({how}); {len(spots)} spot di almeno {int(p["min_cells"])} celle.'))
    r.value(ctx.tr('spots', 'spot'), len(spots), key='count')
    r.value(ctx.tr('threshold', 'soglia'), thr, key='threshold')
    if not spots:
        r.text(ctx.tr('No spot: lower the threshold (n σ, or a value) or the smallest size.',
                      'Nessuno spot: abbassa la soglia (n σ, o un valore) o la dimensione minima.'))
        return r
    t = pd.DataFrame(spots)
    r.value(ctx.tr('mean area', 'area media'), float(t['area'].mean()), float(t['area'].std(ddof=1)) if len(t) > 1 else None,
            key='mean_area')
    r.value(ctx.tr('covered fraction', 'frazione coperta'), float(t['area'].sum() / np.outer(cell_widths(ys), cell_widths(xs)).sum()),
            key='fraction')
    names = {'cells': ctx.tr('cells', 'celle'), 'area': ctx.tr('area', 'area'),
             'diameter': ctx.tr('equivalent diameter', 'diametro equivalente'), 'x': ctx.tr('centroid x', 'baricentro x'),
             'y': ctx.tr('centroid y', 'baricentro y'), 'peak': ctx.tr('peak', 'picco'),
             'peak_x': ctx.tr('peak x', 'picco x'), 'peak_y': ctx.tr('peak y', 'picco y'),
             'integral': ctx.tr('integral above the threshold', 'integrale sopra la soglia'),
             'edge': ctx.tr('touches the edge', 'tocca il bordo')}
    shown = t.rename(columns=names)
    shown.insert(0, '#', np.arange(1, len(t) + 1))
    r.table(ctx.tr('Spots', 'Spot'), shown)
    marks = pd.DataFrame({'x': t['x'], yname: t['y']})
    r.overlay(marks, 'x', yname, label=ctx.tr(f'{len(t)} spots', f'{len(t)} spot'),
              style={'linestyle': 'none', 'marker': '+', 'markersize': 9, 'color': '#ff3b30'})
    r.data(shown, name=ctx.tr('spots', 'spot'), plot={'kind': 'hist', 'y': [names['area']]})
    return r
