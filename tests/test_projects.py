"""Project files (.piplot): piplotter/projects.py and the service's save / open."""
import io
import json
import os
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
        self.assertEqual((doc['spec']['kind'], doc['spec']['version']), ('line', 1))   # numbered on opening (schema.py)…
        from piplotter.plotting import DEFAULT_SPEC
        self.assertEqual(doc['spec']['inset'], DEFAULT_SPEC['inset'])        # …and completed with the defaults
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

    def test_excluded_points_are_an_edit_kept_in_the_project(self):
        from piplotter.tables import masked
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            a = self.app(one)
            text = 'x,y\n' + '\n'.join(f'{x},{2 * x + 1 if x != 7 else 90}' for x in range(12)) + '\n'
            info = a.add_upload('line.csv', io.BytesIO(text.encode()), len(text))
            ds = a.open_table({'file_id': info['id'], 'table': None, 'options': {}})
            out = a.edit_table({'dataset_id': ds['dataset_id'], 'ops': [{'op': 'mask', 'rows': [7]},
                                                                         {'op': 'del_rows', 'rows': [0]}]})
            self.assertIn({'op': 'mask', 'rows': [7]}, [{k: v for k, v in o.items() if k != 'value'}
                                                       for o in out['source']['ops']])   # in the list of edits
            self.assertEqual(masked(a.dataset(out['dataset_id'])['df']), [6])           # follows the deleted row
            project = {'files': [{'id': out['dataset_id'], 'name': 'line.csv', 'source': out['source'],
                                  'info': {'file_id': info['id'], 'name': 'line.csv'}}], 'spec': {}}
            blob = a.save_project({'project': project})
            b = self.app(two)
            p = b.open_project('m.piplot', io.BytesIO(blob), len(blob))['project']
            again = b.reopen(p['files'][0]['source'])
            self.assertEqual(masked(b.dataset(again['dataset_id'])['df']), [6])        # rebuilt with the mask
            fit = b.run_analysis({'dataset_id': again['dataset_id'], 'id': 'fit_curve', 'lang': 'en', 'spec': {},
                                  'params': {'x': 'x', 'y': 'y', 'model': 'linear'}})
            self.assertAlmostEqual(next(v['value'] for v in fit['values'] if v['key'] == 'a'), 2.0, places=6)          # the wild point left out

    def test_batch_on_files_never_opened(self):
        with tempfile.TemporaryDirectory() as one:
            a = self.app(one)
            files = []
            for k, tau in enumerate((4, 6, 9)):
                text = 't,s\n' + '\n'.join(f'{t},{3 * 2.718281828 ** (-t / tau):.8f}' for t in range(40)) + '\n'
                info = a.add_upload(f'r{k}.csv', io.BytesIO(text.encode()), len(text))
                files.append({'source': {'file_id': info['id'], 'table': None, 'options': {}}, 'name': f'r{k}.csv',
                              'x': 't', 'y': ['s'], 'yerr': None})
            before = len(a.datasets)
            out = a.batch_analysis({'id': 'fit_curve', 'params': {'x': 't', 'y': 's', 'model': 'exp_decay'},
                                    'main': {'x': 't', 'y': ['s'], 'yerr': None}, 'files': files, 'spec': {}, 'lang': 'en'})
            rows = out['tables'][0]
            col = rows['columns'].index('tau')
            self.assertEqual([round(r[col], 3) for r in rows['rows']], [4, 6, 9])
            self.assertEqual(len(a.datasets), before + 1)               # only the table of the batch is kept

    def test_a_result_runs_again_only_on_the_columns_it_was_made_from(self):
        from piplotter.server import ApiError
        with tempfile.TemporaryDirectory() as one:
            a = self.app(one)
            text = 'x,y\n' + '\n'.join(f'{x},{2 * x + 1}' for x in range(12)) + '\n'
            info = a.add_upload('line.csv', io.BytesIO(text.encode()), len(text))
            ds = a.open_table({'file_id': info['id'], 'table': None, 'options': {}})
            res = a.run_analysis({'dataset_id': ds['dataset_id'], 'id': 'fit_curve', 'lang': 'en', 'spec': {},
                                  'params': {'x': 'x', 'y': 'y', 'model': 'linear'}})
            self.assertEqual(res['source']['analysis'], 'fit_curve')            # a result knows how it was made
            self.assertEqual(res['source']['params']['y'], 'y')
            renamed = a.edit_table({'dataset_id': ds['dataset_id'], 'ops': [{'op': 'rename', 'col': 'y', 'to': 'z'}]})
            again = {'dataset_id': renamed['dataset_id'], 'id': 'fit_curve', 'lang': 'en', 'spec': {},
                     'params': res['source']['params']}
            self.assertNotEqual(a.run_analysis(again)['params']['y'], 'y')     # by hand: it takes another column…
            with self.assertRaisesRegex(ApiError, '“y”'):                      # …run again on a new version: refused
                a.run_analysis({**again, 'strict': True})

    def test_a_large_project_is_written_and_sent_without_holding_it_in_memory(self):
        import http.client
        import json
        import threading
        import tracemalloc
        from piplotter.server import Server, make_handler
        with tempfile.TemporaryDirectory() as one:
            a = self.app(one)
            big = Path(one) / 'big.bin'
            with open(big, 'wb') as f:                                  # 60 MB that do not compress
                for _ in range(60):
                    f.write(os.urandom(1 << 20))
            with open(big, 'rb') as f:
                info = a.add_upload('big.csv', f, big.stat().st_size)
            project = {'files': [{'id': 'x', 'name': 'big.csv', 'source': {'file_id': info['id']},
                                  'info': {'file_id': info['id']}}], 'spec': {}}
            httpd = Server(('127.0.0.1', 0), make_handler(a, 0))
            port = httpd.server_address[1]
            httpd.RequestHandlerClass = make_handler(a, port)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                tracemalloc.start()
                c = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
                c.request('POST', '/api/project/prepare', json.dumps({'project': project, 'filename': 'big'}),
                          {'X-Token': 't', 'Content-Type': 'application/json', 'Host': f'127.0.0.1:{port}'})
                ready = json.loads(c.getresponse().read())
                self.assertEqual(ready['name'], 'big.piplot')
                c.request('GET', ready['url'], headers={'Host': f'127.0.0.1:{port}'})
                r = c.getresponse()
                self.assertEqual(r.status, 200)
                got = Path(one) / 'got.piplot'
                with open(got, 'wb') as out:
                    while chunk := r.read(1 << 20):
                        out.write(chunk)
                peak = tracemalloc.get_traced_memory()[1]
                tracemalloc.stop()
                self.assertLess(peak, 20 << 20)                         # well under the 60 MB of the data
                doc, files = projects.read(got, 10 ** 9)
                z, f, size = projects.open_entry(got, files[0][2])
                with z, f:
                    self.assertEqual(size, big.stat().st_size)
                    with open(big, 'rb') as orig:
                        self.assertEqual(f.read(1 << 20), orig.read(1 << 20))
                c.request('GET', ready['url'], headers={'Host': f'127.0.0.1:{port}'})
                self.assertEqual(c.getresponse().status, 404)          # a link is used once
                self.assertEqual(list(Path(one).glob('_save_*')), [])   # and its file is gone
                c.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
            late = a.save_project_file({'project': project, 'filename': 'late'})
            did = late['url'].rsplit('/', 1)[1]
            a.downloads[did]['until'] = 0                              # never fetched: removed after a while
            with self.assertRaises(Exception):
                a.take_download(did)
            self.assertEqual(list(Path(one).glob('_save_*')), [])


if __name__ == '__main__':
    unittest.main()
