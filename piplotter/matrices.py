"""Matrices: a grid of values kept in a table. The first column holds the y of each row, the other columns are named
by their x (the 'XYZ matrix' many instruments write: maps, 2D spectra, images). An image opens in this layout, its
pixels as coordinates and y counted from the bottom, so the picture stands upright on ordinary axes.

The plots (heat map, contour, 3D surface) and the matrix analyses read a matrix with from_frame — from this layout
or from X, Y, Z columns, gridded when the points are scattered — and write one back with to_frame."""
import re

import numpy as np
import pandas as pd

MAX_IMAGE_SIDE = 4096          # larger images are binned down to this many pixels on their longer side
MIN_COLUMNS = 8                # fewer number-named columns: an ordinary table (e.g. replicates 1, 2, 3)
NUMBER = re.compile(r'\s*[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?\s*')


def coordinate(name):
    """The number a column is named by ('12.5', '1e-3', '400'), or None."""
    s = str(name).replace(',', '.') if str(name).count(',') == 1 and '.' not in str(name) else str(name)
    return float(s) if NUMBER.fullmatch(s) else None


def matrix_columns(df, exclude=()):
    """The numeric columns named by a number, in table order."""
    return [c for c in df.columns if c not in exclude and coordinate(c) is not None
            and pd.api.types.is_numeric_dtype(df[c])]


def row_column(df):
    """The column with the y of each row: the first column, when it is numeric and not named by a number."""
    if len(df.columns) and coordinate(df.columns[0]) is None and pd.api.types.is_numeric_dtype(df[df.columns[0]]):
        return df.columns[0]
    return None


def is_matrix(df):
    """A table laid out as a matrix: at least MIN_COLUMNS number-named numeric columns, and (apart from the column
    of row coordinates) nothing else."""
    cols = matrix_columns(df)
    ycol = row_column(df)
    return len(cols) >= MIN_COLUMNS and len(cols) == len(df.columns) - (1 if ycol is not None else 0)


def evenly_spaced(v, rtol=1e-3):
    v = np.asarray(v, float)
    if v.size < 3:
        return True
    d = np.diff(v)
    return bool(np.all(np.abs(d - d.mean()) <= rtol * max(abs(d.mean()), 1e-300)))


def _sorted(Z, xs, ys):
    ix, iy = np.argsort(xs, kind='stable'), np.argsort(ys, kind='stable')
    return Z[np.ix_(iy, ix)], xs[ix], ys[iy]


def from_wide(df, ycol=None, cols=None):
    """(Z, xs, ys) of a table in matrix layout; xs from the column names (else 0, 1, 2…), ys from ycol (else the
    row number). Rows and columns come out in increasing x and y."""
    cols = list(cols) if cols else matrix_columns(df, exclude=[ycol] if ycol else ())
    if not cols:
        raise ValueError('No columns of values for a matrix.')
    Z = df[cols].apply(pd.to_numeric, errors='coerce').to_numpy(float)
    xs = np.array([coordinate(c) for c in cols], dtype=float)
    if np.isnan(xs).any() or len(set(xs)) != len(xs):
        xs = np.arange(len(cols), dtype=float)
    ys = pd.to_numeric(df[ycol], errors='coerce').to_numpy(float) if ycol else np.arange(len(df), dtype=float)
    keep = np.isfinite(ys)
    return _sorted(Z[keep], xs, ys[keep])


def from_xyz(df, x, y, z, size=None, method='linear'):
    """(Z, xs, ys) from X, Y, Z columns: their own grid when the points form one (missing cells NaN), else the
    scattered points interpolated on a size × size grid over their range (Delaunay; NaN outside the hull)."""
    frame = df[[x, y, z]].apply(pd.to_numeric, errors='coerce').dropna()
    if len(frame) < 4:
        raise ValueError('Not enough points for a matrix.')
    ux, uy = np.unique(frame[x]), np.unique(frame[y])
    if ux.size * uy.size <= 4 * len(frame) and ux.size >= 2 and uy.size >= 2:     # a grid (maybe with gaps)
        grid = frame.pivot_table(index=y, columns=x, values=z, aggfunc='mean')
        return grid.to_numpy(float), grid.columns.to_numpy(float), grid.index.to_numpy(float)
    from scipy.interpolate import griddata
    n = int(size or min(200, max(20, int(np.sqrt(len(frame)) * 2))))
    xs = np.linspace(frame[x].min(), frame[x].max(), n)
    ys = np.linspace(frame[y].min(), frame[y].max(), n)
    X, Y = np.meshgrid(xs, ys)
    Z = griddata(frame[[x, y]].to_numpy(float), frame[z].to_numpy(float), (X, Y), method=method)
    return Z, xs, ys


def from_frame(df, x=None, ys=None, z=None):
    """(Z, xs, ys) from a figure's mapping: X, Y, Z columns when z is given, else the matrix layout (x = the column
    of row coordinates, ys = the columns of values, all number-named ones when empty)."""
    if z:
        return from_xyz(df, x, ys[0] if isinstance(ys, (list, tuple)) else ys, z)
    ycol = x if x and x in df.columns else row_column(df)
    cols = [c for c in (ys or []) if c != ycol] if ys and len(ys) >= 2 else None
    return from_wide(df, ycol, cols)


def column_names(xs):
    """Column names for the x of a matrix: as short as they can be while staying distinct."""
    for digits in (6, 8, 10, 12, 15):
        names = [f'{v:.{digits}g}' for v in xs]
        if len(set(names)) == len(names):
            return names
    return [repr(float(v)) for v in xs]


def to_frame(Z, xs, ys, yname='y'):
    """A matrix as a table: yname first, then one column per x."""
    out = pd.DataFrame(np.asarray(Z, float), columns=column_names(xs))
    out.insert(0, yname, np.asarray(ys, float))
    return out


def to_xyz(Z, xs, ys, names=('x', 'y', 'z')):
    """A matrix as X, Y, Z columns (one row per cell, missing cells left out)."""
    X, Y = np.meshgrid(xs, ys)
    out = pd.DataFrame({names[0]: X.ravel(), names[1]: Y.ravel(), names[2]: np.asarray(Z, float).ravel()})
    return out.dropna().reset_index(drop=True)


# ------------------------------------------------------------------ images
CHANNELS = ('luminance', 'red', 'green', 'blue')


def image_channels(path):
    """The tables an image offers: its luminance and each colour channel for a colour picture, one for grey."""
    from PIL import Image
    with Image.open(path) as im:
        colour = im.mode not in ('1', 'L', 'LA', 'I', 'I;16', 'I;16B', 'I;16L', 'F')
    return list(CHANNELS) if colour else ['data']


def read_image(path, channel='luminance'):
    """An image file as a matrix of intensities: grey levels as they are (8 or 16 bit), colour as luminance
    (ITU-R BT.601) or one channel. Rows from the top of the picture, y counted from the bottom (pixels). Returns
    (DataFrame, notes)."""
    from PIL import Image
    notes = []
    with Image.open(path) as im:
        if getattr(im, 'n_frames', 1) > 1:
            notes.append(f'The file has {im.n_frames} images: the first one is read.')
        im.seek(0)
        mode = im.mode
        if mode in ('P', 'PA', 'CMYK', 'YCbCr', 'LAB', 'HSV', '1'):
            im = im.convert('RGBA' if 'A' in mode else 'RGB')
            mode = im.mode
        arr = np.asarray(im)
    arr = arr.astype(float)
    if arr.ndim == 3:
        rgb = arr[..., :3]
        if channel in ('red', 'green', 'blue'):
            arr = rgb[..., ('red', 'green', 'blue').index(channel)]
        else:
            arr = rgb @ np.array([0.299, 0.587, 0.114])
            notes.append('Colour image: read as luminance (0.299 R + 0.587 G + 0.114 B).')
    h, w = arr.shape
    k = int(np.ceil(max(h, w) / MAX_IMAGE_SIDE))
    if k > 1:
        arr = bin_matrix(arr, k)
        notes.append(f'{w} × {h} pixels: binned {k} × {k} to {arr.shape[1]} × {arr.shape[0]}.')
    h, w = arr.shape
    xs = np.arange(w, dtype=float) * k
    ys = (h - 1 - np.arange(h, dtype=float)) * k            # the top row has the largest y: the picture upright
    return to_frame(arr, xs, ys, 'y (px)'), notes


def bin_matrix(Z, kx, ky=None):
    """Mean of each kx × ky block (the edges that do not fill a block are left out)."""
    ky = ky or kx
    Z = np.asarray(Z, float)
    h, w = (Z.shape[0] // ky) * ky, (Z.shape[1] // kx) * kx
    if not h or not w:
        raise ValueError('The blocks are larger than the matrix.')
    with np.errstate(invalid='ignore'):
        return np.nanmean(Z[:h, :w].reshape(h // ky, ky, w // kx, kx), axis=(1, 3))
