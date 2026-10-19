"""Clearing the cache (service/cache.py): the session starts from zero, and what cannot be made again stays."""
import io
import json
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
class TestClearCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.home = tmp / 'home'
        self.env = mock.patch.dict(os.environ, {'PIPLOTTER_HOME': str(self.home)})
        self.env.start()
        from piplotter.modules import ModuleManager
        from piplotter.server import App
        self.home.mkdir()
        # What the user made and π-plotter cannot make again, next to its caches.
        (self.home / 'plugins').mkdir()
        (self.home / 'plugins' / 'mine.py').write_text('PLUGIN = {}\n', encoding='utf-8')
        (self.home / 'user-modules.json').write_text('{}', encoding='utf-8')
        (self.home / 'token').write_text('x', encoding='utf-8')
        (self.home / 'pypi-cache.json').write_text(json.dumps({'versions': {'numpy': '9.9'}, 'checked_at': 1}),
                                                   encoding='utf-8')
        (self.home / 'import-check.json').write_text('{}', encoding='utf-8')
        self.mods = ModuleManager(state_dir=self.home, online=False)
        self.mods.require = lambda ids: None
        self.mods.verify_async = mock.Mock()
        self.session = tmp / 'session'
        self.app = App('t', self.session, self.mods, 10 ** 9)

    def tearDown(self):
        self.env.stop()
        self._tmp.cleanup()

    def work(self):
        csv = b't,s\n0,1\n1,2.5\n2,4\n'
        f = self.app.add_upload('run.csv', io.BytesIO(csv), len(csv))
        ds = self.app.open_table({'file_id': f['id']})
        self.app.sample('spectra')
        project = {'files': [{'id': ds['dataset_id'], 'name': 'run.csv', 'source': ds['source'],
                              'info': {'file_id': f['id']}}],
                   'active': ds['dataset_id'], 'main': {'source': ds['source'], 'name': 'run.csv'},
                   'spec': {'kind': 'scatter'}, 'views': []}
        self.app.autosave_write({'project': project})
        return f, ds

    def test_the_session_starts_from_zero(self):
        f, ds = self.work()
        self.app.views3d['v'] = {'x': 1}
        link = self.app.save_project_file({'project': {'files': [], 'main': {'source': {'sample': 'spectra'}},
                                                       'spec': {}}, 'filename': 'p'})
        self.assertTrue(link['url'].startswith('/download/'))
        self.assertTrue(Path(f['path']).is_file())
        out = self.app.clear_cache({})
        self.assertTrue(out['ok'])
        self.assertEqual(out['files'], 1)
        self.assertGreaterEqual(out['datasets'], 2)
        self.assertEqual((len(self.app.datasets), len(self.app.made), len(self.app.views3d), len(self.app.files)),
                         (0, 0, 0, 0))
        self.assertFalse(Path(f['path']).exists())                    # the session's copy of the file
        self.assertEqual(json.loads((self.session / 'files.json').read_text()), {})
        self.assertEqual(self.app.downloads, {})
        self.assertEqual([p.name for p in self.session.iterdir() if not p.name.startswith('._')], ['files.json'])
        with self.assertRaises(Exception):                            # the page's data sets are gone
            self.app.dataset(ds['dataset_id'])
        # The module caches are forgotten and the checks run again; the user's things stay.
        self.assertFalse((self.home / 'pypi-cache.json').exists())
        self.assertFalse((self.home / 'import-check.json').exists())
        self.assertEqual(self.mods.status()['modules'][0]['latest'], None)
        self.mods.verify_async.assert_called_with(force=True)
        for kept in ('plugins/mine.py', 'user-modules.json', 'token'):
            self.assertTrue((self.home / kept).is_file(), kept)

    def test_the_autosave_stays_unless_asked(self):
        from piplotter import autosave
        self.work()
        self.app.clear_cache({})
        self.assertEqual([i['slot'] for i in autosave.info()], ['current'])
        self.assertTrue(any((self.home / 'autosave' / 'current' / 'files').iterdir()))     # its own copy of the file
        # New work after the clearing does not write over the work cleared: that one moves to previous/.
        self.work()
        self.assertEqual(sorted(i['slot'] for i in autosave.info()), ['current', 'previous'])
        out = self.app.clear_cache({'autosave': True})
        self.assertTrue(out['autosave'])
        self.assertEqual(autosave.info(), [])

    def test_the_route(self):
        from piplotter.service import routes
        self.work()
        route = routes.find('POST', '/api/cache/clear')
        req = routes.Request('/api/cache/clear', '', {}, None, lambda: {'autosave': False})
        out = route(self.app, req)
        self.assertEqual(out['files'], 1)
        self.assertEqual(len(self.app.files), 0)


if __name__ == '__main__':
    unittest.main()
