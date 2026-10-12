"""Project files (.piplot): piplotter/projects.py and the service's save / open."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from piplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

from piplotter import projects  # noqa: E402
from piplotter.projects import ProjectError  # noqa: E402


class TestFormat(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ids_and_remap(self):
        p = {'files': [{'source': {'file_id': 'a1', 'table': None}, 'info': {'file_id': 'a1'}}],
             'views': [{'dataset': {'source': {'analysis': 'x', 'parent': {'file_id': 'b2'}}}}]}
        self.assertEqual(projects.file_ids(p), ['a1', 'b2'])
        q = projects.remap(p, {'a1': 'N1', 'b2': 'N2'})
        self.assertEqual(projects.file_ids(q), ['N1', 'N2'])
        self.assertEqual(projects.file_ids(p), ['a1', 'b2'])          # the original is not changed

    def test_roundtrip(self):
        data = self.dir / 'spectrum 1.csv'
        data.write_text('x,y\n1,2\n3,4\n', encoding='utf-8')
        project = {'files': [{'source': {'file_id': 'f1'}}], 'spec': {'kind': 'line'}}
        blob = projects.to_bytes(project, {'f1': {'name': 'spectrum 1.csv', 'path': str(data)}})
        path = self.dir / 'p.piplot'
        path.write_bytes(blob)
        doc, files = projects.read(path, 10 ** 9)
        self.assertEqual(doc['format'], projects.FORMAT)
        self.assertEqual(doc['spec'], {'kind': 'line'})
        self.assertEqual(files[0][:2], ('f1', 'spectrum 1.csv'))
        z, f, size = projects.open_entry(path, files[0][2])
        with z, f:
            self.assertEqual(f.read(), data.read_bytes())
        self.assertEqual(size, data.stat().st_size)

    def test_missing_file_is_an_error(self):
        with self.assertRaises(ProjectError):
            projects.to_bytes({'files': [{'source': {'file_id': 'gone'}}]}, {})

    def test_refuses_what_it_cannot_read(self):
        bad = self.dir / 'bad.piplot'
        bad.write_bytes(b'not a zip')
        with self.assertRaises(ProjectError):
            projects.read(bad, 10 ** 9)
        newer = self.dir / 'newer.piplot'
        with zipfile.ZipFile(newer, 'w') as z:
            z.writestr('project.json', json.dumps({'format': projects.FORMAT, 'version': projects.VERSION + 1}))
        with self.assertRaisesRegex(ProjectError, 'newer'):
            projects.read(newer, 10 ** 9)
        sneaky = self.dir / 'sneaky.piplot'
        with zipfile.ZipFile(sneaky, 'w') as z:
            z.writestr('project.json', json.dumps({'format': projects.FORMAT, 'version': 1,
                                                   'embedded': {'f': {'entry': '../etc/passwd'}}}))
        with self.assertRaises(ProjectError):
            projects.read(sneaky, 10 ** 9)
        big = self.dir / 'big.piplot'
        with zipfile.ZipFile(big, 'w') as z:
            z.writestr('data/1-a.csv', 'x' * 1000)
            z.writestr('project.json', json.dumps({'format': projects.FORMAT, 'version': 1,
                                                   'embedded': {'f': {'entry': 'data/1-a.csv', 'name': 'a.csv'}}}))
        with self.assertRaisesRegex(ProjectError, 'limit'):
            projects.read(big, 100)


@unittest.skipUnless(__import__('importlib').util.find_spec('scipy') is not None, 'needs scipy')
class TestService(unittest.TestCase):
    """Save in one session, open in another (a new session folder, as after a restart or on another computer)."""

    def app(self, folder):
        from piplotter.server import App
        from piplotter.modules import ModuleManager
        mods = ModuleManager()
        mods.require = lambda ids: None
        return App('t', Path(folder), mods, 10 ** 9)

    def test_save_and_open_elsewhere(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a = self.app(one)
            text = 'time,signal\n' + '\n'.join(f'{t},{2.0 * 0.8 ** t + 0.1}' for t in range(30)) + '\n'
            info = a.add_upload('decay.csv', io.BytesIO(text.encode()), len(text))
            ds = a.open_table({'file_id': info['id'], 'table': None, 'options': {}})
            edited = a.edit_table({'dataset_id': ds['dataset_id'], 'ops': [
                {'op': 'formula', 'col': 'log signal', 'expr': 'log(signal)'}]})
            fit = a.run_analysis({'dataset_id': edited['dataset_id'], 'id': 'fit_curve', 'lang': 'en',
                                  'params': {'x': 'time', 'y': 'signal', 'model': 'exp_decay'}, 'spec': {}})
            project = {'files': [{'id': edited['dataset_id'], 'name': 'decay.csv', 'source': edited['source'],
                                  'info': {'file_id': info['id'], 'name': 'decay.csv'}}],
                       'active': edited['dataset_id'], 'spec': {'kind': 'scatter', 'x': 'time', 'y': ['signal']},
                       'views': [{'id': 'v1', 'dataset': {'source': fit['dataset']['source']}}]}
            blob = a.save_project({'project': project})

            b = self.app(two)
            out = b.open_project('mine.piplot', io.BytesIO(blob), len(blob))
            self.assertEqual(out['name'], 'mine')
            p = out['project']
            new_id = p['files'][0]['info']['file_id']
            self.assertNotEqual(new_id, info['id'])                    # the file is in the new session…
            self.assertEqual(projects.file_ids(p), [new_id])           # …and every reference follows it
            again = b.reopen(p['files'][0]['source'])
            df_a, df_b = a.dataset(edited['dataset_id'])['df'], b.dataset(again['dataset_id'])['df']
            self.assertTrue(df_a.equals(df_b))                          # the edited table, rebuilt
            res = b.reopen(p['views'][0]['dataset']['source'])          # the fit, run again
            self.assertTrue(b.dataset(res['dataset_id'])['df'].equals(a.dataset(fit['dataset']['dataset_id'])['df']))


if __name__ == '__main__':
    unittest.main()
