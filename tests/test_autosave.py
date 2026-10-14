"""Autosave: the work kept on disk while working, recovered in a new session after a crash."""
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from piplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()


def has(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


@unittest.skipUnless(has('pandas'), 'pandas needed')
class TestAutosave(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / 'home'
        self.env = mock.patch.dict(os.environ, {'PIPLOTTER_HOME': str(self.home)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self._tmp.cleanup()

    def session(self):
        from piplotter.server import App
        from piplotter.modules import ModuleManager
        mods = ModuleManager()
        mods.require = lambda ids: None
        return App('t', Path(tempfile.mkdtemp(dir=self._tmp.name)), mods, 10 ** 9)

    def work(self, app, csv=b't,s\n0,1\n1,2.5\n2,4\n', name='run.csv'):
        """A file uploaded, opened and edited; the project the page would describe."""
        f = app.add_upload(name, io.BytesIO(csv), len(csv))
        ds = app.open_table({'file_id': f['id']})
        ds = app.edit_table({'dataset_id': ds['dataset_id'], 'ops': [{'op': 'set', 'row': 0, 'col': 's', 'value': '9'}]})
        return f, {'files': [{'id': ds['dataset_id'], 'name': name, 'source': ds['source'], 'info': {'file_id': f['id']}}],
                   'active': ds['dataset_id'], 'main': {'source': ds['source'], 'name': name},
                   'spec': {'kind': 'scatter'}, 'views': [{'id': 'copy'}]}

    def test_work_comes_back_in_a_new_session(self):
        a = self.session()
        f, project = self.work(a)
        a.autosave_write({'project': project})
        self.assertEqual(a.autosave_info()['items'], [])                       # its own work is not offered to itself
        copy = self.home / 'autosave' / 'current' / 'files' / f['id'] / 'run.csv'
        self.assertTrue(copy.is_file())                                         # the data file is kept with it
        b = self.session()                                                      # π-plotter stopped; it starts again
        items = b.autosave_info()['items']
        self.assertEqual([(i['slot'], i['files'], i['figures']) for i in items], [('current', ['run.csv'], 2)])
        rec = b.autosave_recover({'slot': 'current'})
        self.assertEqual(rec['missing'], [])
        source = rec['project']['files'][0]['source']
        self.assertNotEqual(source['edit']['file_id'], f['id'])                 # the file is back under a new id
        df = b.dataset(b.reopen(source)['dataset_id'])['df']
        self.assertEqual(df['s'].tolist(), [9.0, 2.5, 4.0])                     # with the edit made by hand
        self.assertEqual(rec['project']['spec']['kind'], 'scatter')

    def test_new_work_keeps_the_last_one_and_old_files_go(self):
        a = self.session()
        _, first = self.work(a, name='first.csv')
        a.autosave_write({'project': first})
        b = self.session()
        f2, second = self.work(b, csv=b't,s\n1,2\n3,4\n', name='second.csv')
        b.autosave_write({'project': second})                                  # new work: the last one is kept
        self.assertEqual([(i['slot'], i['files']) for i in b.autosave_info()['items']], [('previous', ['first.csv'])])
        second['files'] = []                                                    # the file closed: its copy goes
        second['main'] = {'source': {'sample': 'kinetics'}, 'name': 'sample'}
        b.autosave_write({'project': second})
        self.assertEqual(list((self.home / 'autosave' / 'current' / 'files').iterdir()), [])
        b.autosave_discard({'slot': 'previous'})
        self.assertEqual(b.autosave_info()['items'], [])
        self.assertEqual(b.autosave_write({'project': {'files': [], 'main': None}})['saved'], None)   # nothing open

    def test_a_missing_data_file_is_reported(self):
        a = self.session()
        f, project = self.work(a)
        a.autosave_write({'project': project})
        for p in (self.home / 'autosave' / 'current' / 'files').rglob('run.csv'):
            p.unlink()
        rec = self.session().autosave_recover({'slot': 'current'})
        self.assertEqual(rec['missing'], ['run.csv'])


if __name__ == '__main__':
    unittest.main()
