"""Digitising a picture of a graph (piplotter/digitize.py): the picture for the page, a preview of the curves read
from it, and the table made of them — a data set like any other, made again from its source
{'digitize': {'file_id', 'axes', 'series', 'xname', 'yname'}, 'name'} (projects, a restart)."""
from collections import OrderedDict
import io

from .common import ApiError

PREVIEW_POINTS = 4000           # points of a curve sent back for the preview (the table keeps them all)


class DigitizeArea:
    def _picture(self, fid):
        """The RGB array of an uploaded picture (the last few kept in memory: every preview reads it again)."""
        from .. import digitize
        info = self.file(fid)
        if info.get('format') != 'image':
            raise ApiError('Only a picture (PNG, JPEG, TIFF…) can be digitised.', 422, 'digitize')
        cache = self.__dict__.setdefault('_pictures', OrderedDict())
        with self.lock:
            rgb = cache.get(info['id'])
        if rgb is None:
            self.modules.require(self.modules.core_ids())
            try:
                rgb = digitize.load_rgb(info['path'])
            except digitize.DigitizeError as exc:
                raise ApiError(str(exc), 422, 'digitize')
            except Exception as exc:
                raise ApiError(f'Cannot read the picture {info["name"]}: {exc}', 422, 'read_error')
            with self.lock:
                cache[info['id']] = rgb
                while len(cache) > 2:
                    cache.popitem(last=False)
        return info, rgb

    def digitize_picture(self, body):
        """The picture as PNG, as the page shows it to be clicked on (any format the reader opens, TIFF too)."""
        from PIL import Image
        info, rgb = self._picture(body.get('file_id'))
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format='PNG', compress_level=1)
        return buf.getvalue(), {'width': int(rgb.shape[1]), 'height': int(rgb.shape[0]), 'name': info['name']}

    def _curves(self, body):
        from .. import digitize
        series = body.get('series') if isinstance(body.get('series'), list) else []
        if digitize.needs_scipy(series):
            self.modules.require(self.modules.core_ids() + ['scipy'])
        info, rgb = self._picture(body.get('file_id'))
        try:
            return info, digitize.extract(rgb, body.get('axes'), series)
        except digitize.DigitizeError as exc:
            raise ApiError(str(exc), 422, 'digitize')

    def digitize_preview(self, body):
        """The points of each curve, in pixels (to draw on the picture) and in data units."""
        import numpy as np
        from .. import digitize
        _, curves = self._curves(body)
        out = []
        for c in curves:
            keep = [int(i) for i in digitize.thin(np.arange(len(c['x'])), PREVIEW_POINTS)]
            out.append({'name': c['name'], 'mode': c['mode'], 'n': int(len(c['x'])),
                        'px': [[round(float(c['px'][i][0]), 2), round(float(c['px'][i][1]), 2)] for i in keep],
                        'x': [float(c['x'][i]) for i in keep], 'y': [float(c['y'][i]) for i in keep]})
        return {'curves': out}

    def digitize(self, body):
        """The table of the curves read from the picture, registered with its source."""
        from .. import digitize
        info, curves = self._curves(body)
        try:
            df = digitize.to_frame(curves, body.get('xname'), body.get('yname'))
        except digitize.DigitizeError as exc:
            raise ApiError(str(exc), 422, 'digitize')
        keep = {k: body.get(k) for k in ('axes', 'series', 'xname', 'yname')}
        source = {'digitize': {'file_id': info['id'], **keep}, 'name': body.get('name')}
        name = str(body.get('name') or f'{info["name"]} › digitised')
        return self._register(df, name, source, {})
