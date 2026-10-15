"""Local HTTP service for the π-plotter web interface.

Listens on loopback only. Every /api call must carry the per-session token embedded in the page
and a loopback Host header. Uploaded files live in a private session directory that is removed
when π-plotter stops. The server starts with the standard library alone; NumPy, pandas and
Matplotlib are imported on first use, after the interface has installed them.

The work is done by one module per area (service/: files, tables, projects, console, analyses, render), joined in
App; which request goes where is the table of service/routes.py.
"""
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback
from urllib.parse import urlsplit

from . import AUTHOR, NAME, __version__
from .modules import MissingModules, MissingUserModules, ModuleManager, clean_appledouble
from .service import routes
from .service.analyses import AnalysesArea
from .service.common import (CHUNK, DOWNLOAD_TTL, MAX_BATCH_FILES, MAX_DATASET_BYTES, MAX_DATASETS,  # noqa: F401
                             MAX_JSON, PREVIEW_COLS, PREVIEW_ROWS, ApiError, content_disposition, json_safe, safe_name)
from .service.console import ConsoleArea
from .service.files import FilesArea
from .service.projects import ProjectsArea
from .service.render import RenderArea
from .service.tables import TablesArea

ROOT = Path(__file__).resolve().parent.parent
WEB = routes.WEB
MIME = routes.MIME


def build_id():
    """Fingerprint of the program files: pages from another version ask to reload."""
    import hashlib
    h = hashlib.sha1(__version__.encode())
    here = Path(__file__).parent
    for folder, pattern in ((WEB, '*'), (here, '*.py'), (here / 'service', '*.py')):
        for f in sorted(folder.glob(pattern)):
            if f.is_file() and not f.name.startswith('.'):
                h.update(f.name.encode())
                h.update(f.read_bytes())
    return h.hexdigest()[:12]


class App(FilesArea, TablesArea, ProjectsArea, ConsoleArea, AnalysesArea, RenderArea):
    """The state of one session; its methods come from the areas of service/."""

    def __init__(self, token, session_dir, modules, max_upload_bytes):
        self.token = token
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.modules = modules
        self.max_upload = max_upload_bytes
        self.datasets = OrderedDict()
        self.made = OrderedDict()         # sources.key(source) -> the data set made from it (service/files.py)
        self.render_lock = threading.Lock()
        self.lock = threading.Lock()
        self.files = self._load_files()
        self.restart_hook = None
        self.shutdown_hook = None
        self.started = time.time()
        self.build = build_id()
        self._plugins = None
        self.views3d = OrderedDict()      # id -> view3d of a recent 3D render (the rotatable preview)
        self._overlay_alias = {}
        self._console = None              # the Python console's process (console.py), started on first use
        self._autosaved = False           # this session has written its autosave (autosave.py)
        self.downloads = {}               # one-off links to files written on disk (a project): id -> path, name
        self._extra_refs = []


def make_handler(app, port):
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}

    class Handler(BaseHTTPRequestHandler):
        server_version = f'piplotter/{__version__}'
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):   # quiet; errors are printed explicitly
            pass

        # ------------------------------------------------ responses
        def _send(self, status, body, ctype, extra=None):
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path, ctype, extra=None):
            """A file in pieces (any size), removed once sent or abandoned."""
            try:
                size = path.stat().st_size
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(size))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                with open(path, 'rb') as f:
                    while chunk := f.read(CHUNK):
                        self.wfile.write(chunk)
            finally:
                path.unlink(missing_ok=True)

        def _json(self, data, status=200):
            self._send(status, json.dumps(data, allow_nan=False, default=json_safe).encode('utf-8'),
                       'application/json; charset=utf-8')

        def _log_error(self, status, message):
            if status in (404,) and 'gone' not in message:
                return
            print(f'[π-plotter {time.strftime("%H:%M:%S")}] {status} {self.command} {urlsplit(self.path).path} — {message}',
                  file=sys.stderr, flush=True)

        def _error(self, exc):
            if isinstance(exc, ConnectionError):
                return      # the page cancelled the request (e.g. a newer render replaced it): nothing to answer
            if isinstance(exc, MissingModules):
                return self._json({'error': str(exc), 'code': 'missing_modules', 'modules': exc.ids}, 409)
            if isinstance(exc, MissingUserModules):
                return self._json({'error': str(exc), 'code': 'missing_user_modules', 'modules': exc.names}, 409)
            if isinstance(exc, ApiError):
                self._log_error(exc.status, f'{exc.code}: {exc}')
                return self._json({'error': str(exc), 'code': exc.code, **exc.extra}, exc.status)
            self._log_error(500, f'{exc.__class__.__name__}: {exc}')
            traceback.print_exc()
            return self._json({'error': f'Internal error: {exc}', 'code': 'internal'}, 500)

        def _body(self):
            length = int(self.headers.get('Content-Length') or 0)
            if length > MAX_JSON:
                raise ApiError('Request too large.', 413)
            raw = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(raw or b'{}')
            except json.JSONDecodeError:
                raise ApiError('Invalid JSON.')
            if not isinstance(data, dict):
                raise ApiError('Invalid request.')
            return data

        def _guard(self):
            if self.headers.get('Host', '') not in allowed_hosts:
                raise ApiError('Forbidden host.', 403, 'forbidden')
            if self.path.startswith('/api/') and not secrets.compare_digest(self.headers.get('X-Token', ''), app.token):
                raise ApiError('Invalid session token; reload the page.', 403, 'token')

        # ------------------------------------------------ the route table (service/routes.py)
        def _dispatch(self):
            try:
                self._guard()
                url = urlsplit(self.path)
                req = routes.Request(url.path, url.query, self.headers, self.rfile, self._body)
                if self.command == 'POST' and url.path not in routes.STREAMING:
                    req.body                                  # read now, whatever the route does with it
                route = routes.find(self.command, url.path)
                if route is None:
                    raise routes.not_found()
                out = route(app, req)
                if isinstance(out, routes.Reply):
                    self._send(200, out.data, out.mime, out.headers)
                elif isinstance(out, routes.FileReply):
                    self._send_file(out.path, out.mime, out.headers)
                elif isinstance(out, routes.Then):
                    self._json(out.data)
                    if out.action:
                        threading.Timer(out.delay, out.action).start()
                else:
                    self._json(out)
            except Exception as exc:
                self._error(exc)

        do_GET = do_POST = _dispatch

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # A browser that closes a connection early (cancelled render, closed tab) is not an error.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


def serve(port, token, session_dir, open_browser=True, max_upload_gb=20, online=True, quiet=False):
    clean_appledouble()          # exFAT drives on macOS: see modules.clean_appledouble
    modules = ModuleManager(online=online)
    app = App(token, session_dir, modules, int(max_upload_gb * 1024 ** 3))
    httpd = Server(('127.0.0.1', port), make_handler(app, port))
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(app, port)
    url = f'http://127.0.0.1:{port}/'
    modules.refresh_async()      # latest versions from PyPI, at every start
    modules.verify_async()       # installed modules really import (separate Python, in the background)
    if not quiet:
        status = modules.status()
        print(f'{NAME} {__version__} — {url}')
        print(AUTHOR)
        print(f'Python {status["python"]} ({sys.executable})')
        if not status['core_ready']:
            print('First start: the browser page will install NumPy, pandas and Matplotlib.')
        print('Keep this window open; press Ctrl+C to stop.')
    if open_browser:
        threading.Timer(0.6, lambda: _open(url)).start()
    return httpd, app, url


def _open(url):
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass
