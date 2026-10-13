"""The Python console: code typed in the page runs in a Python process of its own, which keeps its variables from
one run to the next (like a notebook). A run that does not end can be stopped — the process is closed and a new one
started — and nothing the code does can freeze or crash the program serving the page.

In the console:
    df           the data of the figure on screen (a pandas DataFrame; a copy: changing it changes no table)
    files        the files open, {name: DataFrame}
    spec         the figure (a dict: kind, x, y, …)
    np, pd, plt  NumPy, pandas, Matplotlib (figures made with plt are shown under the code)
    new_table(frame, name)    opens a DataFrame (or a dict of columns) as a new table of π-plotter
    run(analysis, **params)   runs an analysis of π-plotter on df: run('fit_curve', x='t', y='s', model='exp_decay')

The value of the last line is shown (tables as tables), as in an interactive Python. The code runs with the
user's own rights, like any Python program on this computer."""
import threading
import time

TIMEOUT = 600                  # seconds a run may take before it is stopped
MAX_TEXT = 200_000             # characters of printed text kept from one run
MAX_FIGURES = 8
MAX_TABLES = 20


# ------------------------------------------------------------------ the process that runs the code
def _fresh(user_dir):
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return {'__name__': '__console__', 'np': np, 'pd': pd, 'plt': plt, 'df': None, 'files': {}, 'spec': {},
            '_user_dir': user_dir}


def _split(code):
    """(statements, last expression or None): the value of a final expression is shown, as in a Python prompt."""
    import ast
    tree = ast.parse(code, '<console>', 'exec')
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = ast.Expression(tree.body.pop().value)
        return compile(tree, '<console>', 'exec'), compile(last, '<console>', 'eval')
    return compile(tree, '<console>', 'exec'), None


def _shown(value):
    """An output for the value of the last line."""
    import pandas as pd
    if isinstance(value, pd.Series):
        value = value.to_frame()
    if isinstance(value, pd.DataFrame):
        return {'type': 'table', 'html': value.to_html(max_rows=40, max_cols=20, border=0, float_format=lambda v: f'{v:.6g}'),
                'shape': list(value.shape)}
    if hasattr(value, 'summary') and hasattr(value, 'tables') and hasattr(value, 'get'):      # a Result of run()
        rows = ''.join(f'<tr><td>{_esc(s["label"])}</td><td>{_esc(_fmt(s.get("value")))}</td>'
                       f'<td>{_esc(_fmt(s.get("error")) if s.get("error") is not None else "")}</td></tr>'
                       for s in value.summary)
        return {'type': 'table', 'html': f'<table class="dataframe">{rows}</table>', 'shape': [len(value.summary), 3]}
    import numpy as np
    if isinstance(value, np.generic):              # np.float64(1.5) → 1.5, as a number reads
        value = value.item()
    text = repr(value)
    return {'type': 'value', 'text': text[:MAX_TEXT]}


def _fmt(v):
    return f'{v:.6g}' if isinstance(v, float) else str(v)


def _esc(s):
    import html
    return html.escape(str(s))


def _figures(plt):
    import base64
    import io
    out = []
    for num in plt.get_fignums()[:MAX_FIGURES]:
        buf = io.BytesIO()
        plt.figure(num).savefig(buf, format='png', dpi=100, bbox_inches='tight')
        out.append({'type': 'image', 'png': base64.b64encode(buf.getvalue()).decode('ascii')})
    plt.close('all')
    return out


def _execute(ns, msg):
    import contextlib
    import io
    import traceback
    import pandas as pd
    for key in ('df', 'files', 'spec'):
        if key in msg:
            ns[key] = msg[key]
    made = []

    def new_table(frame, name='console'):
        """Open a DataFrame (or a dict of columns) as a new table of π-plotter."""
        if len(made) >= MAX_TABLES:
            raise ValueError(f'At most {MAX_TABLES} tables from one run.')
        made.append((str(name), pd.DataFrame(frame).copy()))

    def run(analysis, data=None, **params):
        """Run an analysis of π-plotter on df (or on data) with these parameters; returns its result
        (.get('key') a number, .frame its table of data, .summary all its values)."""
        from piplotter import plugins
        pm = ns.get('_pm') or (plugins.PluginManager(user_dir=ns['_user_dir']) if ns.get('_user_dir')
                               else plugins.PluginManager())        # the same analyses as the page
        ns['_pm'] = pm
        frame = ns['df'] if data is None else data
        if frame is None:
            raise ValueError('No data: open a file first, or pass data=…')
        return pm.run(analysis, frame, params, lang=msg.get('lang', 'en'), spec=ns.get('spec') or {})[2]

    ns['new_table'], ns['run'] = new_table, run
    out = io.StringIO()
    outputs = []
    started = time.perf_counter()
    try:
        body, last = _split(msg['code'])
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(body, ns)
            value = eval(last, ns) if last is not None else None
        if value is not None:
            outputs.append(_shown(value))
            ns['_'] = value
    except BaseException as exc:                              # also SystemExit, KeyboardInterrupt from the code
        tb = traceback.TracebackException.from_exception(exc)
        tb.stack = traceback.StackSummary.from_list([f for f in tb.stack if f.filename == '<console>'])
        outputs.insert(0, {'type': 'error', 'text': ''.join(tb.format()).strip()[-MAX_TEXT:]})
    text = out.getvalue()
    if text:
        outputs.insert(0, {'type': 'text', 'text': text[:MAX_TEXT] + ('\n…' if len(text) > MAX_TEXT else '')})
    outputs += _figures(ns['plt'])
    names = sorted(k for k, v in ns.items() if not k.startswith('_') and k not in BUILTIN_NAMES
                   and not callable(v) and not type(v).__name__ == 'module')
    return {'outputs': outputs, 'tables': made, 'seconds': round(time.perf_counter() - started, 3),
            'variables': names[:200]}


BUILTIN_NAMES = {'np', 'pd', 'plt', 'df', 'files', 'spec', 'new_table', 'run'}


def _connect(port, key, user_dir):
    """Entry point of the console process (started with python -c): connect back to the server and serve."""
    from multiprocessing.connection import Client
    conn = Client(('127.0.0.1', int(port)), authkey=bytes.fromhex(key))
    _worker(conn, user_dir or None)


def _worker(conn, user_dir):
    ns = _fresh(user_dir)
    conn.send({'ready': True})
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return
        if msg.get('op') == 'reset':
            ns = _fresh(user_dir)
            conn.send({'ready': True})
        elif msg.get('op') == 'run':
            try:
                conn.send(_execute(ns, msg))
            except Exception as exc:                          # a result that cannot be sent back (not picklable…)
                conn.send({'outputs': [{'type': 'error', 'text': f'{type(exc).__name__}: {exc}'}], 'tables': [],
                           'seconds': 0, 'variables': []})


# ------------------------------------------------------------------ the server's side
class Console:
    """One console process for the session; started on the first run."""

    def __init__(self, user_dir=None):
        self.user_dir = str(user_dir) if user_dir else None
        self.proc = self.conn = None
        self.lock = threading.Lock()          # one run at a time
        self.sent = {}                        # what the process already has: {'df': id, 'files': ids}
        self.stopped = False

    def _start(self):
        """A fresh Python (the same interpreter) that connects back on a loopback port with a one-off key. Started
        with python -c, not multiprocessing's spawn, so the script that launched the server is never run again."""
        import secrets
        import subprocess
        import sys
        from multiprocessing.connection import Listener
        from pathlib import Path
        key = secrets.token_bytes(32)
        root = str(Path(__file__).resolve().parent.parent)
        with Listener(('127.0.0.1', 0), authkey=key) as listener:
            port = listener.address[1]
            code = (f'import sys; sys.path.insert(0, {root!r}); from piplotter.console import _connect; '
                    f'_connect({port}, {key.hex()!r}, {self.user_dir or ""!r})')
            self.proc = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL)
            listener._listener._socket.settimeout(60)
            try:
                self.conn = listener.accept()
            except OSError:
                self._kill()
                raise RuntimeError('The console did not start.')
        if not self.conn.poll(120) or not self.conn.recv().get('ready'):
            self._kill()
            raise RuntimeError('The console did not start.')
        self.sent = {}

    def _alive(self):
        return self.proc is not None and self.proc.poll() is None

    def _kill(self):
        proc, conn = self.proc, self.conn
        self.proc = self.conn = None
        self.sent = {}
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(3)
            except Exception:
                proc.kill()
        if conn is not None:
            conn.close()

    def run(self, code, df=None, df_id=None, files=None, files_id=None, spec=None, lang='en', timeout=TIMEOUT):
        """{'outputs': […], 'tables': [(name, DataFrame)], 'seconds', 'variables'}; data are sent only when they
        changed since the last run."""
        with self.lock:
            self.stopped = False
            if not self._alive():
                self._start()
            msg = {'op': 'run', 'code': str(code), 'spec': spec or {}, 'lang': lang}
            if self.sent.get('df') != df_id or df_id is None:
                msg['df'] = None if df is None else df.copy()
                self.sent['df'] = df_id
            if self.sent.get('files') != files_id or files_id is None:
                msg['files'] = {k: v.copy() for k, v in (files or {}).items()}
                self.sent['files'] = files_id
            conn = self.conn
            try:
                conn.send(msg)
                end = time.monotonic() + timeout
                while not conn.poll(0.1):
                    if self.stopped or not self._alive() or time.monotonic() > end:
                        late = time.monotonic() > end
                        self._kill()
                        why = (f'Stopped after {timeout:g} s; the console starts again (its variables are lost).'
                               if late else 'Stopped; the console starts again (its variables are lost).')
                        return {'outputs': [{'type': 'error', 'text': why, 'code': 'timeout' if late else 'stopped',
                                             'seconds': timeout}],
                                'tables': [], 'seconds': 0, 'variables': [], 'restarted': True}
                return conn.recv()
            except (EOFError, OSError, BrokenPipeError):
                stopped = self.stopped
                self._kill()
                why = ('Stopped; the console starts again (its variables are lost).' if stopped else
                       'The console stopped (the code ended Python or crashed it); it starts again, its variables lost.')
                return {'outputs': [{'type': 'error', 'text': why, 'code': 'stopped' if stopped else 'crashed'}],
                        'tables': [], 'seconds': 0, 'variables': [], 'restarted': True}

    def stop(self):
        """Stop a run in progress (from another request): the process is closed, a new one starts on the next run."""
        self.stopped = True
        if self._alive():
            self.proc.terminate()

    def reset(self):
        """Forget every variable."""
        self.stop()
        with self.lock:
            self._kill()

    def close(self):
        self.reset()
