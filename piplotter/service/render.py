"""Figures: the preview and the exports, the figures of a layout, the layers and other files drawn with the main
one, the chart advice and the catalogue the page is built from."""
import traceback

from .. import __version__, catalog, schema
from ..modules import MissingModules
from .common import ApiError


class RenderArea:
    # -------------------------------------------------------------- figures
    def check_spec(self, spec, export=None):
        st = spec.get('style') or {}
        need = catalog.requirements_for(spec.get('kind'), st.get('base'), st.get('cmap'), export)
        self.modules.require(self.modules.core_ids() + need)

    def render(self, body, export=None, info=None):
        ds = self.dataset(body.get('dataset_id'))
        try:
            spec = schema.upgrade_spec(body.get('spec') or {})
            schema.check_spec(spec)                    # the figures of a layout are part of it
        except schema.SchemaError as exc:
            raise ApiError(str(exc), 422, 'spec')
        self.check_spec(spec, export)
        from .. import plotting, exporters
        from ..tables import kept, masked
        fmt = export or 'png'
        df = kept(ds['df'])                       # excluded rows: out of the curves, drawn apart as crosses
        hidden = ds['df'].iloc[masked(ds['df'])] if masked(ds['df']) else None
        compose = [p for p in spec.get('compose') or [] if isinstance(p, dict)]
        if compose and fmt in ('html', 'py'):
            raise ApiError('A layout of several figures exports as an image, PDF, SVG or EPS.', 422, 'layout')
        try:
            with self.render_lock:
                self._extra_refs = []
                panels = [self._panel(p) for p in compose[:plotting.MAX_PANELS]] or None
                overlays = self.overlay_data(spec)
                extras = self.extra_data(spec)
                if fmt == 'html':
                    return exporters.plotly_html(df, spec, overlays, extras), catalog.EXPORT_FORMATS['html']['mime']
                if fmt == 'py':
                    data = exporters.script_bundle(df, spec, 'figure', self.modules.modules,
                                                   extra_refs=ds.get('references', []) + self._extra_refs,
                                                   source=ds['source'], overlay_data=overlays, extra_data=extras)
                    return data, catalog.EXPORT_FORMATS['py']['mime']
                dpi = body.get('dpi') if not export else (body.get('dpi') or None)
                return (plotting.render(df, spec, fmt, dpi, overlays, extras, info=info, masked=hidden, panels=panels),
                        catalog.EXPORT_FORMATS[fmt]['mime'])
        except plotting.SpecError as exc:
            raise ApiError(str(exc), 422, 'spec', key=exc.key, values=exc.values)
        except (MissingModules, ApiError):
            raise
        except ImportError as exc:
            raise ApiError(f'A module is missing: {exc}', 409, 'import_error')
        except Exception as exc:
            traceback.print_exc()
            raise ApiError(f'The figure could not be drawn: {exc}', 422, 'render')

    def _panel(self, p):
        """One figure of a layout: its data (loaded, or rebuilt from its source), spec, layers and other files."""
        from ..tables import kept, masked
        pspec = p.get('spec') if isinstance(p.get('spec'), dict) else {}
        self.check_spec(pspec)
        try:
            ds = self.dataset(p.get('dataset_id'))
        except ApiError:
            if not p.get('source'):
                raise
            ds = self.dataset(self.reopen(p['source'])['dataset_id'])
        rows = masked(ds['df'])
        return {'df': kept(ds['df']), 'spec': pspec, 'overlay_data': self.overlay_data(pspec),
                'extra_data': self.extra_data(pspec), 'masked': ds['df'].iloc[rows] if rows else None}

    def recommend(self, body):
        ds = self.dataset(body.get('dataset_id'))
        from .. import smart
        mapping = body.get('mapping') or {}
        return {'recommend': smart.recommend(ds['columns'], mapping, len(ds['df'])),
                'warnings': smart.warnings_for(mapping, body.get('kind'), len(ds['df']))}

    def meta(self):
        fonts, default_spec, previews = [], None, {}
        if not self.modules.missing(self.modules.core_ids()):
            from ..plotting import DEFAULT_SPEC, palette_previews
            default_spec = DEFAULT_SPEC
            previews = palette_previews()
            try:
                from matplotlib import font_manager
                fonts = sorted({f.name for f in font_manager.fontManager.ttflist})
            except Exception:
                fonts = []
        from ..plotting import NORMALIZE_KINDS
        return {'version': __version__, 'kinds': catalog.KINDS, 'twin_kinds': sorted(catalog.TWIN_KINDS),
                'normalize_kinds': sorted(NORMALIZE_KINDS),
                'styles': catalog.STYLES, 'palettes': catalog.PALETTES, 'colormaps': catalog.COLORMAPS,
                'export_formats': catalog.EXPORT_FORMATS, 'size_presets': catalog.SIZE_PRESETS,
                'file_formats': catalog.FILE_FORMATS, 'extensions': catalog.all_extensions(), 'fonts': fonts,
                'default_spec': default_spec, 'palette_previews': previews}

    def _frames(self, items):
        """{item id: DataFrame} for overlay / extra-file entries of a spec ({'id', 'dataset_id', 'source'});
        data sets that are gone (e.g. after a restart) are rebuilt from their source when possible."""
        data = {}
        for o in items or []:
            if not isinstance(o, dict) or not o.get('dataset_id'):
                continue
            did = self._overlay_alias.get(o['dataset_id'], o['dataset_id'])
            with self.lock:
                ds = self.datasets.get(did)
                if ds is not None:
                    self.datasets.move_to_end(did)
            if ds is None and o.get('source'):
                try:
                    ds_new = self.reopen(o['source'])
                    self._overlay_alias[o['dataset_id']] = ds_new['dataset_id']
                    ds = self.datasets.get(ds_new['dataset_id'])
                except Exception:
                    ds = None
            if ds is not None:
                from ..tables import kept
                data[o.get('id')] = kept(ds['df'])           # another file's excluded rows stay out too
                for r in ds.get('references', []):
                    if r not in self._extra_refs:
                        self._extra_refs.append(r)
        return data

    def overlay_data(self, spec):
        return self._frames(spec.get('overlays'))

    def extra_data(self, spec):
        return self._frames(spec.get('extra'))
