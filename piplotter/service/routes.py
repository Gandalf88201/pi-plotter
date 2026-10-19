"""The routes of the local service, in one table: which request goes to which method of the App.

A route is a function (app, req) that returns the answer: a dict or a list (sent as JSON), a Reply (bytes of a given
type, with headers), a FileReply (a file sent in pieces, then removed) or a Then (JSON, then an action once it has
been sent). The JSON body of a POST is read only when the route uses it (req.body): the routes that receive a large
file read the request themselves, in pieces (req.stream, req.length). Exact paths are looked up first, then the
prefixes in the order of their table."""
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs, quote, unquote

from .. import catalog, manual
from .common import ApiError, content_disposition, json_safe, safe_name

WEB = Path(__file__).resolve().parent.parent.parent / 'web'
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.json': 'application/json'}
PAGE_CSP = ("default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
MANUAL_CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; "
              "base-uri 'none'; frame-ancestors 'none'")


class Request:
    def __init__(self, path, query, headers, stream, read_body):
        self.path, self.query, self.headers, self.stream = path, query, headers, stream
        self._read_body, self._body = read_body, None

    @property
    def body(self):
        if self._body is None:
            self._body = self._read_body()
        return self._body

    @property
    def length(self):
        return int(self.headers.get('Content-Length') or 0)

    @property
    def last(self):
        """The last part of the path (the id in /api/jobs/<id>)."""
        return self.path.rsplit('/', 1)[-1]

    def filename(self, default):
        return unquote(self.headers.get('X-Filename', '')) or default


class Reply:
    def __init__(self, data, mime, headers=None):
        self.data, self.mime, self.headers = data, mime, headers or {}


class FileReply:
    def __init__(self, path, mime, headers=None):
        self.path, self.mime, self.headers = path, mime, headers or {}


class Then:
    """JSON answered first; action() runs delay seconds later (the service stopping or starting again)."""
    def __init__(self, data, action, delay):
        self.data, self.action, self.delay = data, action, delay


def not_found():
    return ApiError('Not found', 404, 'not_found')


# ------------------------------------------------------------------ GET
def page(app, req):
    html = (WEB / 'index.html').read_text(encoding='utf-8').replace('{{TOKEN}}', app.token).replace('{{BUILD}}', app.build)
    return Reply(html.encode('utf-8'), MIME['.html'], {'Content-Security-Policy': PAGE_CSP})


def manual_page(app, req):
    query = parse_qs(req.query)
    text = manual.render_page(lang=(query.get('lang') or [''])[0], explicit='lang' in query)
    return Reply(text.encode('utf-8'), MIME['.html'], {'Content-Security-Policy': MANUAL_CSP})


def manual_image(app, req):
    image = manual.image_path(unquote(req.path[len('/manual/img/'):]))
    if image is None:
        raise not_found()
    return Reply(image.read_bytes(), MIME[image.suffix])


def static(app, req):
    target = (WEB / unquote(req.path[len('/static/'):])).resolve()
    if WEB.resolve() not in target.parents or not target.is_file() or target.suffix not in MIME:
        raise not_found()
    return Reply(target.read_bytes(), MIME[target.suffix])


def download(app, req):
    """A one-off link: the id is the permission."""
    d = app.take_download(req.last)
    return FileReply(d['path'], 'application/zip', {'Content-Disposition': content_disposition(d['name'])})


def view3d(app, req):
    view = app.views3d.get(req.last)
    if view is None:
        raise not_found()
    return view


def job(app, req):
    found = app.modules.job(req.last)
    if not found:
        raise ApiError('Unknown job.', 404)
    return found.to_dict()


GET = {
    '/': page,
    '/index.html': page,
    '/manual': manual_page,
    '/manual/': manual_page,
    '/api/status': lambda app, req: {**app.modules.status(), 'build': app.build, 'started': app.started},
    '/api/meta': lambda app, req: app.meta(),
}
GET_PREFIX = [
    ('/manual/img/', manual_image),
    ('/static/', static),
    ('/download/', download),
    ('/api/view3d/', view3d),
    ('/api/jobs/', job),
]


# ------------------------------------------------------------------ POST
def open_project(app, req):
    return app.open_project(req.filename('project.piplot'), req.stream, req.length)


def save_project(app, req):
    fname = safe_name(req.body.get('filename') or 'project', 'project') + '.piplot'
    return Reply(app.save_project(req.body), 'application/zip', {'Content-Disposition': content_disposition(fname)})


def upload(app, req):
    return app.describe_file(app.add_upload(req.filename('data.csv'), req.stream, req.length))


def render(app, req):
    info = {}
    data, mime = app.render(req.body, info=info)
    # The colour each series really got, for the Series panel (JSON, URL-encoded).
    series = quote(json.dumps(info.get('series', []), ensure_ascii=False, default=json_safe))
    axes = quote(json.dumps(info.get('axes', []), default=json_safe))
    # The texts that can be dragged and rewritten on the preview, and the polar / 3D axes the wheel zooms.
    movable = quote(json.dumps({'items': info.get('movables', []), 'face': info.get('face'), 'zoom': info.get('zoom', [])},
                               default=json_safe))
    headers = {'X-Series': series, 'X-Axes': axes, 'X-Movables': movable}
    if info.get('view3d'):          # fetched by the page only when the user starts rotating
        vid = secrets.token_hex(8)
        app.views3d[vid] = info['view3d']
        while len(app.views3d) > 8:
            app.views3d.popitem(last=False)
        headers['X-View3D'] = vid
    return Reply(data, mime, headers)


def export(app, req):
    body = req.body
    fmt = str(body.get('format') or 'png').lower()
    if fmt not in catalog.EXPORT_FORMATS:
        raise ApiError('Unknown export format.')
    data, mime = app.render(body, export=fmt)
    ext = 'zip' if fmt == 'py' else fmt
    fname = safe_name(body.get('filename') or 'figure', 'figure') + '.' + ext
    return Reply(data, mime, {'Content-Disposition': content_disposition(fname)})


def table_export(app, req):
    data, mime, ext = app.table_file(req.body)
    fname = safe_name(req.body.get('filename') or 'data', 'data') + '.' + ext
    return Reply(data, mime, {'Content-Disposition': content_disposition(fname)})


def digitize_picture(app, req):
    data, info = app.digitize_picture(req.body)
    return Reply(data, 'image/png', {'X-Picture': json.dumps(info, ensure_ascii=True)})


def modules_refresh(app, req):
    app.modules.refresh_async()
    return app.modules.status()


def modules_verify(app, req):
    app.modules.verify_async(force=True)
    return app.modules.status()


def modules_install(app, req):
    body = req.body
    ids = body.get('ids') or []
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ApiError('ids must be a list of module ids.')
    unknown = [i for i in ids if i not in app.modules.by_id]
    if unknown:
        raise ApiError('Unknown module: ' + ', '.join(unknown))
    return app.modules.start_install(ids, upgrade=bool(body.get('upgrade')), reinstall=bool(body.get('reinstall'))).to_dict()


def user_module(app, req):
    """Modules the user adds from PyPI: inspect (licences first), install, uninstall, cite."""
    action, body, modules = req.last, req.body, app.modules
    try:
        if action == 'inspect':
            return modules.start_inspect(body.get('name')).to_dict()
        if action == 'install':
            return modules.start_user_install(body.get('inspection'), accept=body.get('accept') is True).to_dict()
        if action == 'uninstall':
            return modules.start_uninstall(body.get('name')).to_dict()
        if action == 'cite':
            modules.set_user_cite(body.get('name'), body.get('cite'))
            return modules.status()
    except ValueError as exc:
        raise ApiError(str(exc), 400, 'user_module')
    raise not_found()


def cancel_job(app, req):
    if not req.path.endswith('/cancel'):
        raise not_found()
    found = app.modules.job(req.path.split('/')[3])
    if found:
        found.cancel()
    return found.to_dict() if found else {}


def shutdown(app, req):
    """A newer π-plotter is starting: give it the port."""
    return Then({'ok': True}, app.shutdown_hook, 0.2)


def restart(app, req):
    if not app.restart_hook:
        raise ApiError('Restart is not available.')
    return Then({'ok': True}, app.restart_hook, 0.4)


POST = {
    # files and tables
    '/api/upload': upload,
    '/api/file': lambda app, req: app.describe_file(app.file(req.body.get('file_id'))),
    '/api/open': lambda app, req: app.open_table(req.body),
    '/api/sample': lambda app, req: app.sample(str(req.body.get('name') or 'spectra')),
    '/api/reopen': lambda app, req: app.reopen(req.body.get('source')),
    '/api/table/new': lambda app, req: app.blank_table(req.body),
    '/api/table/edit': lambda app, req: app.edit_table(req.body),
    '/api/table/nearest': lambda app, req: app.table_nearest(req.body),
    '/api/table/rows': lambda app, req: app.table_rows(req.body),
    '/api/table/export': table_export,
    # pictures of graphs read back into data
    '/api/digitize/picture': digitize_picture,
    '/api/digitize/preview': lambda app, req: app.digitize_preview(req.body),
    '/api/digitize': lambda app, req: app.digitize(req.body),
    # projects and autosave
    '/api/project/open': open_project,
    '/api/project/prepare': lambda app, req: app.save_project_file(req.body),
    '/api/project/save': save_project,
    '/api/autosave': lambda app, req: app.autosave_write(req.body),
    '/api/autosave/info': lambda app, req: app.autosave_info(),
    '/api/autosave/recover': lambda app, req: app.autosave_recover(req.body),
    '/api/autosave/discard': lambda app, req: app.autosave_discard(req.body),
    # analyses
    '/api/analyses': lambda app, req: app.analyses(),
    '/api/analyses/suggest': lambda app, req: app.suggest_analyses(req.body),
    '/api/analyses/run': lambda app, req: app.run_analysis(req.body),
    '/api/analyses/batch': lambda app, req: app.batch_analysis(req.body),
    # the console
    '/api/console/run': lambda app, req: app.console_run(req.body),
    '/api/console/complete': lambda app, req: app.console_complete(req.body),
    '/api/console/each': lambda app, req: app.console_each(req.body),
    '/api/console/stop': lambda app, req: app.console_stop(),
    '/api/console/reset': lambda app, req: app.console_reset(),
    # figures
    '/api/render': render,
    '/api/export': export,
    '/api/recommend': lambda app, req: app.recommend(req.body),
    # modules and the service itself
    '/api/modules/refresh': modules_refresh,
    '/api/modules/verify': modules_verify,
    '/api/modules/install': modules_install,
    '/api/cache/clear': lambda app, req: app.clear_cache(req.body),
    '/api/shutdown': shutdown,
    '/api/restart': restart,
}
POST_PREFIX = [
    ('/api/plugins/', lambda app, req: app.plugin_action(req.last, req.body)),
    ('/api/modules/user/', user_module),
    ('/api/jobs/', cancel_job),
]

TABLES = {'GET': (GET, GET_PREFIX), 'POST': (POST, POST_PREFIX)}
# The routes that read the request themselves, in pieces. Every other POST has its body read before the route runs,
# used or not: a body left unread on a kept-alive connection would be taken for the start of the next request.
STREAMING = {'/api/upload', '/api/project/open'}


def find(method, path):
    """The route of a request, or None."""
    exact, prefixes = TABLES[method]
    if path in exact:
        return exact[path]
    return next((fn for prefix, fn in prefixes if path.startswith(prefix)), None)
