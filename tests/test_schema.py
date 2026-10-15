"""The versioned JSON Schemas of the figure description and of the project file (schema.py, piplotter/schemas/)."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from piplotter import catalog, projects, schema
from piplotter.modules import ModuleManager


def figure_problems(spec):
    return schema.problems(spec, schema.load('figure'), 'spec')


class TestSchema(unittest.TestCase):
    def test_the_published_schemas_are_the_ones_the_code_makes(self):
        # A change of the documents is deliberate: python -m piplotter.schema writes the files, and a change older
        # documents cannot follow gets a new version and an upgrade step.
        for name, made in schema.generated().items():
            stored = json.loads(schema.file_of(name).read_text(encoding='utf-8'))
            self.assertEqual(stored, json.loads(json.dumps(made)), f'{name}: run python -m piplotter.schema')
            self.assertTrue(stored['$id'].endswith(f':{stored["properties"]["version"]["const"]}'))

    def test_defaults_match_and_carry_the_version(self):
        from piplotter.plotting import DEFAULT_SPEC
        self.assertEqual(DEFAULT_SPEC['version'], schema.SPEC_VERSION)
        self.assertEqual(figure_problems(DEFAULT_SPEC), [])
        self.assertEqual(projects.VERSION, schema.PROJECT_VERSION)

    def test_wrong_descriptions_are_named_where_they_are_wrong(self):
        from piplotter.plotting import DEFAULT_SPEC
        cases = [(('kind',), 'pie-in-the-sky', 'spec.kind'),
                 (('y',), 'signal', 'spec.y'),
                 (('axes', 'xmin'), [1, 2], 'spec.axes.xmin'),
                 (('style', 'base'), 'no-such-style', 'spec.style.base'),
                 (('figure', 'dpi'), '600', 'spec.figure.dpi'),
                 (('legend', 'show'), True, 'spec.legend.show')]
        for path, value, where in cases:
            spec = copy.deepcopy(DEFAULT_SPEC)
            node = spec
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = value
            found = figure_problems(spec)
            self.assertEqual([w for w, _ in found], [where], (path, found))
        # What the page writes beyond the defaults, and what it leaves empty, is fine.
        ok = {**DEFAULT_SPEC, 'axes': {**DEFAULT_SPEC['axes'], 'xmin': '2024-01-01', 'xbreak': '3, 5'},
              'legend': {**DEFAULT_SPEC['legend'], 'pos': [0.2, 0.8]}, 'x': 'time', 'y': ['a', 'b'],
              'compose': [{'dataset_id': 'abc', 'source': {'sample': 'ir'}, 'spec': {'kind': 'scatter'}}],
              'something_new': {'kept': True}}
        self.assertEqual(figure_problems(ok), [])
        bad_panel = {**ok, 'compose': [{'spec': {'kind': 'nope'}}]}          # a figure of a layout is checked too
        self.assertEqual([w for w, _ in figure_problems(bad_panel)], ['spec.compose[0].spec.kind'])

    def test_versions(self):
        self.assertEqual(schema.upgrade_spec({'kind': 'line'})['version'], schema.SPEC_VERSION)   # unnumbered = 1
        with self.assertRaisesRegex(schema.SchemaError, 'newer π-plotter'):
            schema.upgrade_spec({'version': schema.SPEC_VERSION + 1})
        with self.assertRaisesRegex(schema.SchemaError, 'version'):
            schema.upgrade_spec({'version': 'one'})
        # An upgrade step is applied once for each version the document is behind.
        saved = schema.SPEC_VERSION, dict(schema.SPEC_UPGRADES)
        try:
            schema.SPEC_VERSION = saved[0] + 1
            schema.SPEC_UPGRADES[saved[0]] = lambda s: {**s, 'renamed': s.get('old')}
            out = schema.upgrade_spec({'version': saved[0], 'old': 7, 'compose': [{'spec': {'old': 8}}]})
            self.assertEqual((out['version'], out['renamed']), (saved[0] + 1, 7))
            self.assertEqual(out['compose'][0]['spec']['renamed'], 8)
        finally:
            schema.SPEC_VERSION = saved[0]
            schema.SPEC_UPGRADES.clear()
            schema.SPEC_UPGRADES.update(saved[1])

    def test_palettes_and_colour_maps_of_the_catalogue(self):
        from piplotter import catalog
        for palette in [*catalog.PALETTES, 'style']:
            schema.check_spec(schema.upgrade_spec({'kind': 'line', 'style': {'palette': palette}}))
        for cmap in [c for group in catalog.COLORMAPS.values() for c in group]:
            schema.check_spec(schema.upgrade_spec({'kind': 'heatmap', 'style': {'cmap': cmap}}))
        with self.assertRaisesRegex(schema.SchemaError, r"spec\.style\.palette: 'rainbow-2030' is not one of 'okabe-ito'"):
            schema.check_spec(schema.upgrade_spec({'kind': 'line', 'style': {'palette': 'rainbow-2030'}}))
        with self.assertRaisesRegex(schema.SchemaError, r"spec\.style\.cmap: 'jet' is not one of 'viridis'"):
            schema.check_spec(schema.upgrade_spec({'kind': 'heatmap', 'style': {'cmap': 'jet'}}))

    def test_older_descriptions_are_completed(self):
        # A figure saved before insets and layouts existed: the parts it lacks take their defaults, what it has
        # stays — done once, here, not by the page.
        from piplotter.plotting import DEFAULT_SPEC
        old = {'kind': 'scatter', 'y': ['a'], 'style': {'palette': 'okabe-ito'}, 'axes': {'xlabel': 'time'},
               'compose': [{'spec': {'kind': 'line'}}]}
        out = schema.upgrade_spec(old)
        self.assertEqual(out['inset'], DEFAULT_SPEC['inset'])
        self.assertEqual((out['kind'], out['y'], out['style']['palette'], out['axes']['xlabel']),
                         ('scatter', ['a'], 'okabe-ito', 'time'))
        self.assertEqual(out['style']['linewidth'], DEFAULT_SPEC['style']['linewidth'])
        self.assertEqual(out['compose'][0]['spec']['inset'], DEFAULT_SPEC['inset'])
        self.assertNotIn('inset', old)                                       # the description given is not changed
        self.assertEqual(schema.upgrade_spec(out), out)                      # complete already: the same again

    def test_projects_are_checked_when_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            def archive(doc):
                path = Path(tmp) / 'p.piplot'
                with zipfile.ZipFile(path, 'w') as z:
                    z.writestr('project.json', json.dumps({'format': projects.FORMAT, 'version': 1, **doc}))
                return path
            good = {'lang': 'en', 'files': [], 'spec': {'kind': 'line', 'y': ['a']}, 'views': [{'id': 'v1', 'spec': None}]}
            doc, _ = projects.read(archive(good), 10 ** 9)
            self.assertEqual(doc['spec']['version'], catalog.SPEC_VERSION)        # saved before figures were numbered
            with self.assertRaisesRegex(projects.ProjectError, r'views\[0\]\.spec\.kind'):
                projects.read(archive({**good, 'views': [{'id': 'v1', 'spec': {'kind': 'nope'}}]}), 10 ** 9)
            with self.assertRaisesRegex(projects.ProjectError, 'files'):
                projects.read(archive({**good, 'files': {'not': 'a list'}}), 10 ** 9)
            # A data source: the kind it is says what it misses; none at all, the keys it could have.
            def bad_source(source):
                return archive({**good, 'files': [{'id': 'a', 'name': 'a', 'source': source}]})
            with self.assertRaisesRegex(projects.ProjectError, r'files\[0\]\.source: “parent” is missing'):
                projects.read(bad_source({'analysis': 'peaks', 'params': {}}), 10 ** 9)
            with self.assertRaisesRegex(projects.ProjectError, r'files\[0\]\.source: needs one of “sample”, “blank”'):
                projects.read(bad_source({'colour': 'red'}), 10 ** 9)
            with self.assertRaisesRegex(projects.ProjectError, r'files\[0\]\.source\.edit\.file_id: expected string'):
                projects.read(bad_source({'edit': {'file_id': 3}, 'ops': []}), 10 ** 9)

    def test_the_service_refuses_a_description_that_does_not_match(self):
        from piplotter.server import ApiError, App
        with tempfile.TemporaryDirectory() as tmp:
            app = App('t' * 32, tmp, ModuleManager(state_dir=tmp, online=False), 10 ** 9)
            ds = app.sample('spectra')
            did, cols = ds['dataset_id'], {'x': ds['mapping']['x'], 'y': ds['mapping']['y']}
            data, mime = app.render({'dataset_id': did, 'spec': {'kind': 'line', 'version': 1, **cols}})
            self.assertEqual(mime, 'image/png')
            with self.assertRaises(ApiError) as cm:
                app.render({'dataset_id': did, 'spec': {'kind': 'line', 'axes': {'ymin': [0]}}})
            self.assertEqual((cm.exception.status, cm.exception.code), (422, 'spec'))
            self.assertIn('spec.axes.ymin', str(cm.exception))
            with self.assertRaisesRegex(ApiError, 'newer'):
                app.render({'dataset_id': did, 'spec': {'kind': 'line', 'version': 99}})


if __name__ == '__main__':
    unittest.main()
