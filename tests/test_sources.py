"""Where data sets come from (piplotter/sources.py): every kind of source made again, its errors, its lineage, and
the data set made only once per source."""
from pathlib import Path
import io
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from piplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

from piplotter import sources  # noqa: E402
from piplotter.sources import SourceError  # noqa: E402

FILE = {'file_id': 'abc', 'table': None, 'options': {}}


class TestKinds(unittest.TestCase):
    def test_kind_of_each(self):
        self.assertEqual(sources.kind_of({'sample': 'ir'}), 'sample')
        self.assertEqual(sources.kind_of({'blank': {'cols': 2}, 'name': 'x'}), 'blank')
        self.assertEqual(sources.kind_of({'edit': FILE, 'ops': []}), 'edit')
        self.assertEqual(sources.kind_of({'batch': 'fit_curve', 'files': []}), 'batch')
        self.assertEqual(sources.kind_of({'analysis': 'peaks', 'parent': FILE}), 'analysis')
        self.assertEqual(sources.kind_of(FILE), 'file')
        self.assertIsNone(sources.kind_of({'colour': 'red'}))
        self.assertIsNone(sources.kind_of(None))

    def test_unknown_or_incomplete_sources_are_named(self):
        with self.assertRaisesRegex(SourceError, r'Unknown data source \(colour\).*sample, blank, edit'):
            sources.check({'colour': 'red'})
        with self.assertRaisesRegex(SourceError, r'Unknown data source \(NoneType\)'):
            sources.check(None)
        with self.assertRaisesRegex(SourceError, r'\(analysis\).*source: “parent” is missing'):
            sources.check({'analysis': 'peaks', 'params': {}})
        with self.assertRaisesRegex(SourceError, r'\(file\).*source.file_id: expected string, got integer'):
            sources.check({'file_id': 3})
        with self.assertRaisesRegex(SourceError, r'\(edit\).*source.ops\[0\]: “op” is missing'):
            sources.check({'edit': FILE, 'ops': [{'row': 1}]})
        with self.assertRaisesRegex(SourceError, r'Unknown data source \(nothing\)'):     # the parent, by itself
            sources.check({'analysis': 'peaks', 'parent': {}})
        self.assertEqual(sources.check({'analysis': 'peaks', 'parent': {'edit': FILE, 'ops': []}}), 'analysis')

    def test_depth(self):
        s = FILE
        for _ in range(sources.MAX_DEPTH):
            s = {'edit': s, 'ops': []}
        sources.check(s)
        with self.assertRaisesRegex(SourceError, 'more than 10 steps'):
            sources.check({'edit': s, 'ops': []})
        with self.assertRaisesRegex(SourceError, 'more than 10 steps'):
            sources.lineage({'edit': s, 'ops': []})

    def test_lineage(self):
        s = {'analysis': 'fit_curve', 'params': {'model': 'gaussian'}, 'overlay': 0,
             'parent': {'edit': FILE, 'ops': [{'op': 'set'}, {'op': 'set'}, {'op': 'mask'}]}}
        self.assertEqual(sources.lineage(s), [
            {'step': 'file', 'file_id': 'abc', 'table': None, 'options': {}},
            {'step': 'edit', 'operations': 3, 'kinds': {'set': 2, 'mask': 1}},
            {'step': 'analysis', 'analysis': 'fit_curve', 'parameters': {'model': 'gaussian'}, 'layer': 0}])
        batch = {'batch': 'peaks', 'params': {}, 'files': [{'name': 'a', 'source': {'sample': 'ir'}}]}
        self.assertEqual(sources.lineage(batch), [{'step': 'batch', 'analysis': 'peaks', 'parameters': {}, 'files': [
            {'name': 'a', 'lineage': [{'step': 'sample', 'sample': 'ir'}]}]}])
        self.assertEqual(sources.parents(batch), [{'sample': 'ir'}])
        self.assertTrue(sources.computed({'edit': s, 'ops': []}))
        self.assertFalse(sources.computed({'edit': FILE, 'ops': []}))

    def test_key(self):
        a = {'analysis': 'peaks', 'parent': FILE, 'params': {'x': 'A', 'y': 'B'}}
        b = {'params': {'y': 'B', 'x': 'A'}, 'parent': dict(reversed(list(FILE.items()))), 'analysis': 'peaks'}
        self.assertEqual(sources.key(a), sources.key(b))
        self.assertNotEqual(sources.key(a), sources.key({**a, 'params': {'x': 'A', 'y': 'C'}}))

    def test_schema_of_each_kind(self):
        d = sources.defs()
        self.assertEqual(len(d['source']['anyOf']), len(sources.KINDS))
        for name, kind in sources.KINDS.items():
            self.assertEqual(d[f'source_{name}']['required'], kind['required'])
            self.assertIn(kind['key'], d[f'source_{name}']['properties'])


@unittest.skipUnless(__import__('importlib').util.find_spec('scipy') is not None, 'needs scipy')
class TestService(unittest.TestCase):
    """Every kind: source → data set → source → the same data set, made again in a new service (as after a
    restart; the session folder keeps the uploaded files)."""

    def app(self, folder):
        from piplotter.server import App
        from piplotter.modules import ModuleManager
        mods = ModuleManager()
        mods.require = lambda ids: None
        return App('t', Path(folder), mods, 10 ** 9)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = self.app(self.tmp.name)
        text = 'time,signal\n' + '\n'.join(f'{t},{2.0 * 0.8 ** t + 0.1}' for t in range(30)) + '\n'
        self.info = self.a.add_upload('decay.csv', io.BytesIO(text.encode()), len(text))

    def tearDown(self):
        self.tmp.cleanup()

    def same(self, made):
        """The data set made again from made's source by a new service: the same rows, columns and values, and the
        same source."""
        b = self.app(self.tmp.name)
        again = b.reopen(made['source'])
        df_a, df_b = self.a.dataset(made['dataset_id'])['df'], b.dataset(again['dataset_id'])['df']
        self.assertEqual(list(df_a.columns), list(df_b.columns))
        self.assertTrue(df_a.equals(df_b), made['source'])
        self.assertEqual(b.dataset(again['dataset_id'])['source'], made['source'])
        return again

    def fit(self, ds):
        return self.a.run_analysis({'dataset_id': ds['dataset_id'], 'id': 'fit_curve', 'lang': 'en', 'spec': {},
                                    'params': {'x': 'time', 'y': 'signal', 'model': 'exp_decay'}})

    def test_every_kind_made_again(self):
        file = self.a.open_table({'file_id': self.info['id'], 'table': None, 'options': {}})
        self.assertEqual(sources.kind_of(file['source']), 'file')
        self.same(file)
        self.same(self.a.sample('ir'))
        self.same(self.a.blank_table({'cols': 3, 'rows': 4, 'name': 'empty'}))
        edit = self.a.edit_table({'dataset_id': file['dataset_id'], 'ops': [
            {'op': 'formula', 'col': 'log signal', 'expr': 'log(signal)'}, {'op': 'mask', 'rows': [2, 3]}]})
        self.assertEqual(sources.kind_of(edit['source']), 'edit')
        self.same(edit)
        fit = self.fit(edit)
        self.assertEqual(sources.kind_of(fit['dataset']['source']), 'analysis')
        self.same(fit['dataset'])
        self.same(fit['overlays'][0]['dataset'])                          # a layer of the result
        batch = self.a.batch_analysis({'id': 'fit_curve', 'lang': 'en', 'main': {'x': 'time', 'y': ['signal']},
                                       'params': {'x': 'time', 'y': 'signal', 'model': 'exp_decay'},
                                       'files': [{'source': file['source'], 'name': 'a', 'x': 'time', 'y': ['signal']},
                                                 {'source': edit['source'], 'name': 'b', 'x': 'time', 'y': ['signal']}]})
        self.assertEqual(sources.kind_of(batch['dataset']['source']), 'batch')
        self.same(batch['dataset'])

    def test_errors_from_the_service(self):
        from piplotter.server import ApiError
        with self.assertRaises(ApiError) as e:
            self.a.reopen({'colour': 'red'})
        self.assertEqual((e.exception.status, e.exception.code), (400, 'source'))
        with self.assertRaisesRegex(ApiError, '“parent” is missing'):
            self.a.reopen({'analysis': 'fit_curve'})
        with self.assertRaisesRegex(ApiError, 'no longer available'):            # a file this session does not have
            self.a.reopen({'file_id': 'nope', 'table': None})

    def test_made_once_per_source(self):
        file = self.a.open_table({'file_id': self.info['id'], 'table': None, 'options': {}})
        fit = self.fit(file)
        runs = []
        run = self.a.run_analysis
        self.a.run_analysis = lambda body: runs.append(body['id']) or run(body)
        # A project with the result and its layer on several copies: the analysis is not run again.
        made = [self.a.reopen(fit['dataset']['source']), self.a.reopen(fit['overlays'][0]['dataset']['source']),
                self.a.reopen(dict(reversed(list(fit['dataset']['source'].items()))))]
        self.assertEqual(runs, [])
        ids = {m['dataset_id'] for m in made} | {fit['dataset']['dataset_id']}
        self.assertEqual(len(ids), 4)                                       # each user gets its own id
        self.assertIs(self.a.dataset(made[0]['dataset_id'])['df'], self.a.dataset(fit['dataset']['dataset_id'])['df'])
        self.assertTrue(self.a.dataset(made[1]['dataset_id'])['df'].equals(
            self.a.dataset(fit['overlays'][0]['dataset']['dataset_id'])['df']))
        # Analyses loaded again (a plugin edited): their results are made anew, the file is not read again.
        self.a.plugin_manager().reload()
        self.a.reopen(fit['dataset']['source'])
        self.assertEqual(runs, ['fit_curve'])
        reads = []
        open_table = self.a.open_table
        self.a.open_table = lambda body: reads.append(1) or open_table(body)
        self.a.reopen(file['source'])
        self.assertEqual(reads, [])
        # Dropped from memory: made again.
        with self.a.lock:
            self.a.datasets.clear()
        self.a.reopen(file['source'])
        self.assertEqual(reads, [1])

    def test_projects_saved_by_earlier_versions_open_the_same(self):
        # tests/golden/projects: a project with every kind of source, saved by 0.2.3 and by 0.2.4, and the data each
        # source made then (rows, columns, excluded rows, sha256 of the table as CSV).
        import hashlib
        import json
        for version in ('0_2_3', '0_2_4'):
            stem = ROOT / 'tests' / 'golden' / 'projects' / f'saved-by-{version}'
            blob = Path(f'{stem}.piplot').read_bytes()
            want = json.loads(Path(f'{stem}.json').read_text(encoding='utf-8'))['data']
            with tempfile.TemporaryDirectory() as folder:
                b = self.app(folder)
                p = b.open_project('old.piplot', io.BytesIO(blob), len(blob))['project']
                found = {f['name']: f['source'] for f in p['files']}
                found.update({v['id']: v['dataset']['source'] for v in p['views']})
                self.assertEqual(sorted(found), sorted(want))
                for name, source in found.items():
                    with self.subTest(version=version, data=name):
                        df = b.dataset(b.reopen(source)['dataset_id'])['df']
                        got = {'columns': [str(c) for c in df.columns], 'rows': int(len(df)),
                               'sha256': hashlib.sha256(df.to_csv(index=False).encode()).hexdigest(),
                               'masked': sorted(int(r) for r in df.attrs.get('masked', []))}
                        self.assertEqual(got, want[name])

    def test_provenance_of_an_export(self):
        from piplotter import exporters
        file = self.a.open_table({'file_id': self.info['id'], 'table': None, 'options': {}})
        edit = self.a.edit_table({'dataset_id': file['dataset_id'], 'ops': [{'op': 'mask', 'rows': [0]}]})
        fit = self.fit(edit)
        p = exporters._provenance(fit['dataset']['source'])
        self.assertEqual([s['step'] for s in p['steps']], ['file', 'edit', 'analysis'])
        self.assertEqual(p['origin'], {'table': None, 'options': {}})
        self.assertEqual(p['analyses'], [{'analysis': 'fit_curve', 'parameters': fit['dataset']['source']['params']}])


if __name__ == '__main__':
    unittest.main()
