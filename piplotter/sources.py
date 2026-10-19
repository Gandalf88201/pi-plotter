"""Where every data set comes from, as data: the kinds of source, the fields of each, how it is made again and what
it is made from.

A data set is never stored: it is its source, made again when needed (projects, results that follow their table,
the console, a restart). Seven kinds, recognised in this order by their key:

    sample    {'sample'}                                        one of the examples
    blank     {'blank': {cols, rows, names}, 'name'}            an empty table typed in
    edit      {'edit': source, 'ops': [...]}                    changes made by hand to another source (tables.py)
    batch     {'batch', 'files': [{'source', …}], 'params', …}  one analysis on many files, a row per file
    analysis  {'analysis', 'parent': source, 'params', …}       the result of an analysis (or one of its layers)
    digitize  {'digitize': {'file_id', 'axes', 'series', …}}    the curves read from a picture of a graph
    file      {'file_id', 'table', 'options'}                   a table read from an uploaded file

KINDS is the table, as the routes are (service/routes.py): kind_of() names the kind of a source, check() says what
is wrong with one, make() builds it with the service, parents() and lineage() say what it comes from, key() is the
same text for the same source (the service's cache) and defs() the JSON Schema of each kind (schema.py).
"""
from collections import Counter
import hashlib
import json

MAX_DEPTH = 10            # sources inside sources (edits of analyses of edits…)


class SourceError(ValueError):
    pass


SOURCE = {'$ref': '#/$defs/source'}
_TEXT = {'type': 'string'}
_NTEXT = {'type': ['string', 'null']}
_OBJ = {'type': 'object'}
_NOBJ = {'type': ['object', 'null']}


# ------------------------------------------------------------------ making each kind again (app: the service)
def _make_sample(app, s, depth):
    return app.sample(str(s['sample']))


def _make_blank(app, s, depth):
    return app.blank_table({**(s['blank'] or {}), 'name': s.get('name')})


def _make_edit(app, s, depth):
    parent = app.reopen(s['edit'], depth + 1)
    return app.edit_table({'dataset_id': parent['dataset_id'], 'ops': s.get('ops') or []})


def _make_batch(app, s, depth):
    return app.batch_analysis({'id': s['batch'], 'params': s.get('params') or {}, 'main': s.get('main') or {},
                               'files': s.get('files') or [], 'spec': s.get('spec') or {},
                               'lang': s.get('lang', 'en')})['dataset']


def _make_analysis(app, s, depth):
    parent = app.reopen(s['parent'], depth + 1)
    out = app.run_analysis({'dataset_id': parent['dataset_id'], 'id': s['analysis'], 'params': s.get('params') or {},
                            'spec': s.get('spec') or {}, 'lang': s.get('lang', 'en')})
    if s.get('overlay') is not None:
        return out['overlays'][int(s['overlay'])]['dataset']
    return out['dataset']


def _make_file(app, s, depth):
    return app.open_table(s)


def _make_digitize(app, s, depth):
    return app.digitize({**(s['digitize'] or {}), 'name': s.get('name')})


# ------------------------------------------------------------------ one step of the lineage
def _step_sample(s):
    return {'step': 'sample', 'sample': s['sample']}


def _step_blank(s):
    b = s.get('blank') or {}
    return {'step': 'blank', 'name': s.get('name'), 'columns': b.get('cols'), 'rows': b.get('rows')}


def _step_edit(s):
    ops = [o for o in s.get('ops') or [] if isinstance(o, dict)]
    return {'step': 'edit', 'operations': len(ops), 'kinds': dict(Counter(str(o.get('op')) for o in ops))}


def _step_batch(s):
    return {'step': 'batch', 'analysis': s['batch'], 'parameters': s.get('params') or {},
            'files': [{'name': f.get('name'), 'lineage': lineage(f['source'])}
                      for f in s.get('files') or [] if isinstance(f, dict) and isinstance(f.get('source'), dict)]}


def _step_analysis(s):
    out = {'step': 'analysis', 'analysis': s['analysis'], 'parameters': s.get('params') or {}}
    if s.get('overlay') is not None:
        out['layer'] = s['overlay']
    return out


def _step_digitize(s):
    d = s.get('digitize') or {}
    series = [c for c in d.get('series') or [] if isinstance(c, dict)]
    return {'step': 'digitize', 'file_id': d.get('file_id'), 'curves': len(series),
            'modes': dict(Counter(str(c.get('mode', 'points')) for c in series)),
            'log': [a for a in ('x', 'y') if (d.get('axes') or {}).get(f'{a}log')]}


def _step_file(s):
    return {'step': 'file', 'file_id': s['file_id'], 'table': s.get('table'), 'options': s.get('options') or {}}


def _present(key):
    return lambda s: bool(s.get(key))


def _given(key):
    return lambda s: s.get(key) is not None


KINDS = {
    'sample': {'key': 'sample', 'present': _present('sample'), 'make': _make_sample, 'step': _step_sample,
               'parents': lambda s: [],
               'required': ['sample'], 'properties': {'sample': _TEXT}},
    'blank': {'key': 'blank', 'present': _given('blank'), 'make': _make_blank, 'step': _step_blank,
              'parents': lambda s: [],
              'required': ['blank'],
              'properties': {'blank': {'type': 'object', 'properties': {
                  'cols': {'type': 'integer'}, 'rows': {'type': 'integer'},
                  'names': {'type': 'array', 'items': _TEXT}}}, 'name': _NTEXT}},
    'edit': {'key': 'edit', 'present': _given('edit'), 'make': _make_edit, 'step': _step_edit,
             'parents': lambda s: [s['edit']],
             'required': ['edit'],
             'properties': {'edit': SOURCE, 'ops': {'type': 'array', 'items': {
                 'type': 'object', 'required': ['op'], 'properties': {'op': _TEXT}}}}},
    'batch': {'key': 'batch', 'present': _present('batch'), 'make': _make_batch, 'step': _step_batch,
              'parents': lambda s: [f['source'] for f in s.get('files') or []
                                    if isinstance(f, dict) and isinstance(f.get('source'), dict)],
              'required': ['batch', 'files'],
              'properties': {'batch': _TEXT, 'params': _NOBJ, 'main': _NOBJ, 'spec': _NOBJ, 'lang': _TEXT,
                             'files': {'type': 'array', 'items': {'type': 'object', 'properties': {
                                 'source': SOURCE, 'name': _TEXT, 'x': _NTEXT,
                                 'y': {'type': 'array', 'items': _TEXT}, 'yerr': _NTEXT}}}}},
    'analysis': {'key': 'analysis', 'present': _present('analysis'), 'make': _make_analysis, 'step': _step_analysis,
                 'parents': lambda s: [s['parent']],
                 'required': ['analysis', 'parent'],
                 'properties': {'analysis': _TEXT, 'parent': SOURCE, 'params': _NOBJ, 'spec': _NOBJ, 'lang': _TEXT,
                                'overlay': {'type': ['integer', 'null']}}},
    'digitize': {'key': 'digitize', 'present': _given('digitize'), 'make': _make_digitize, 'step': _step_digitize,
                 'parents': lambda s: [],
                 'required': ['digitize'],
                 'properties': {'digitize': {'type': 'object', 'required': ['file_id'], 'properties': {
                     'file_id': _TEXT, 'axes': _NOBJ, 'series': {'type': ['array', 'null'], 'items': _OBJ},
                     'xname': _NTEXT, 'yname': _NTEXT}}, 'name': _NTEXT}},
    'file': {'key': 'file_id', 'present': lambda s: 'file_id' in s, 'make': _make_file, 'step': _step_file,
             'parents': lambda s: [],
             'required': ['file_id'],
             'properties': {'file_id': _TEXT, 'table': _NTEXT, 'options': _NOBJ}},
}

DESCRIPTIONS = {
    'sample': 'one of the examples',
    'blank': 'an empty table typed in: its columns, rows and their names',
    'edit': 'changes made by hand (ops of tables.py) to the data of another source',
    'batch': 'one analysis on many files, a row per file',
    'analysis': 'the result of an analysis of the data of another source (or one of its layers: overlay)',
    'digitize': 'the curves read from a picture of a graph: its calibration (two points per axis) and each curve '
                '(points clicked, or the pixels of its colour)',
    'file': 'a table read from an uploaded file, with the options used to read it',
}


# ------------------------------------------------------------------ reading a source
def kind_of(source):
    """The kind of a source (None when it is none of them)."""
    if not isinstance(source, dict):
        return None
    return next((name for name, k in KINDS.items() if k['present'](source)), None)


def defs():
    """$defs of the JSON Schema: 'source' (any kind) and 'source_<kind>' for each."""
    out = {'source': {'description': 'how the data are made again', 'anyOf': [
        {'$ref': f'#/$defs/source_{name}'} for name in KINDS]}}
    for name, k in KINDS.items():
        out[f'source_{name}'] = {'type': 'object', 'description': DESCRIPTIONS[name], 'required': k['required'],
                                 'properties': k['properties']}
    return out


def check(source, depth=0):
    """The kind of the source, after checking it and the sources inside it (raises SourceError)."""
    from .schema import problems
    kind = kind_of(source)
    if kind is None:
        what = type(source).__name__ if not isinstance(source, dict) else ', '.join(sorted(source)) or 'nothing'
        raise SourceError(f'Unknown data source ({what}): it needs one of '
                          + ', '.join(k['key'] for k in KINDS.values()) + '.')
    # This kind's own fields here; the sources inside it are checked one by one below, each with its own kind.
    found = problems(source, _shallow(defs()[f'source_{kind}']), 'source', limit=5)
    if found:
        raise SourceError(f'The data source ({kind}) is not complete: '
                          + '; '.join(f'{where}: {why}' for where, why in found))
    for parent in parents(source):
        _depth(depth + 1)
        check(parent, depth + 1)
    return kind


def _shallow(node):
    if node == SOURCE:
        return {'type': 'object'}
    if isinstance(node, dict):
        return {k: _shallow(v) for k, v in node.items()}
    return [_shallow(v) for v in node] if isinstance(node, list) else node


def computed(source):
    """Whether an analysis makes the data (somewhere along the source): it changes when the analyses change."""
    return kind_of(source) in ('analysis', 'batch') or any(computed(p) for p in parents(source))


def _depth(depth):
    if depth > MAX_DEPTH:
        raise SourceError(f'The data source is made of more than {MAX_DEPTH} steps inside each other.')


def parents(source):
    """The sources this one is made from (none for a file, a sample or a blank table)."""
    kind = kind_of(source)
    return KINDS[kind]['parents'](source) if kind else []


def make(app, source, depth=0):
    """The data set of the source, made with the service app (its reopen() for the parents); check() it first."""
    _depth(depth)
    kind = kind_of(source)
    if kind is None:
        check(source)                     # says what is missing
    return KINDS[kind]['make'](app, source, depth)


def lineage(source, depth=0):
    """The steps that make the data, first to last: where they start (a file, a sample, a blank table), then each
    edit and analysis; a batch lists the lineage of each of its files."""
    _depth(depth)
    kind = kind_of(source)
    if kind is None:
        raise SourceError('Unknown data source.')
    up = parents(source)
    steps = lineage(up[0], depth + 1) if up and kind != 'batch' else []
    return steps + [KINDS[kind]['step'](source)]


def key(source):
    """The same text for the same source, whatever the order of its keys."""
    text = json.dumps(source, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
