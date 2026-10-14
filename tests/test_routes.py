"""The route table of the service (service/routes.py): every request of the page has a route, and requests on one
kept-alive connection stay apart whatever each route does with its body."""
import http.client
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest

from piplotter.modules import ModuleManager
from piplotter.server import App, Server, make_handler
from piplotter.service import routes

ROOT = Path(__file__).resolve().parent.parent
TOKEN = 't' * 32


class TestRoutes(unittest.TestCase):
    def test_every_request_of_the_page_has_a_route(self):
        used = set()
        for f in (ROOT / 'web').glob('*.js'):
            if f.name.startswith('.'):
                continue
            used.update(re.findall(r"""['"`](/api/[\w/.-]*)""", f.read_text(encoding='utf-8')))
        self.assertGreater(len(used), 20)
        missing = [p for p in sorted(used) if not routes.find('POST', p) and not routes.find('GET', p)]
        self.assertEqual(missing, [])

    def test_unknown_paths_are_not_found(self):
        self.assertIsNone(routes.find('POST', '/api/nothing'))
        self.assertIsNone(routes.find('GET', '/api/analyses/run'))
        self.assertIsNotNone(routes.find('GET', '/api/jobs/abc'))

    def test_bodies_left_unused_do_not_spill_into_the_next_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(TOKEN, tmp, ModuleManager(state_dir=tmp, online=False), 10 ** 9)
            httpd = Server(('127.0.0.1', 0), make_handler(app, 0))
            port = httpd.server_address[1]
            httpd.RequestHandlerClass = make_handler(app, port)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                c = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
                headers = {'X-Token': TOKEN, 'Content-Type': 'application/json', 'Host': f'127.0.0.1:{port}'}
                # Routes that do not look at the body, an unknown path, then a route that does: one connection.
                for path, status in (('/api/console/stop', 200), ('/api/autosave/info', 200), ('/api/nothing', 404),
                                     ('/api/console/reset', 200)):
                    c.request('POST', path, json.dumps({'some': 'body ' * 50}), headers)
                    r = c.getresponse()
                    data = json.loads(r.read())
                    self.assertEqual(r.status, status, (path, data))
                c.close()
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == '__main__':
    unittest.main()
