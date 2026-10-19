"""The versioned JSON Schemas (draft 2020-12) of the two documents π-plotter writes and reads back: the description
of a figure (the spec: what is plotted and how it looks) and the project file (project.json in a .piplot archive).

Each document carries its version (spec['version'], project['version']). A document of an older version is brought
up to date step by step (SPEC_UPGRADES, PROJECT_UPGRADES: version n → n + 1) before it is checked, and a figure
description is completed with the defaults of its version (complete_spec: parts written before they existed, as the
inset before 0.2.4) — here, in one place, so the page receives descriptions it does not need to mend; one of a newer
version is refused with a clear message instead of being half understood. The schemas are generated here from the
defaults of the figure (plotting.DEFAULT_SPEC) and the catalogue, and kept as files in piplotter/schemas/ — the
published contract, checked by the tests against what the code would generate — so a change of the documents is
always a deliberate one: written to the files (python -m piplotter.schema), and given a new version when older
documents need an upgrade.

Checking needs the standard library only; it covers the part of JSON Schema these schemas use (type, enum, const,
properties, required, items, additionalProperties, anyOf, $ref to the same file). Keys a schema does not name are
allowed, so a document written by a newer π-plotter of the same version still opens."""
import json
import numbers
from pathlib import Path

from . import sources
from .catalog import SPEC_VERSION

PROJECT_VERSION = 1
FOLDER = Path(__file__).resolve().parent / 'schemas'
DIALECT = 'https://json-schema.org/draft/2020-12/schema'
SPEC_UPGRADES = {}       # {n: function(spec) -> the same figure described in version n + 1}
PROJECT_UPGRADES = {}    # {n: function(project) -> the same project in version n + 1 (specs are upgraded apart)}


class SchemaError(ValueError):
    """A document that does not match its schema, or of a version this program does not read."""


def file_of(name, version=None):
    version = version or {'figure': SPEC_VERSION, 'project': PROJECT_VERSION}[name]
    return FOLDER / f'{name}-{version}.schema.json'


_loaded = {}


def load(name):
    """The schema as published in piplotter/schemas/."""
    if name not in _loaded:
        _loaded[name] = json.loads(file_of(name).read_text(encoding='utf-8'))
    return _loaded[name]


# ------------------------------------------------------------------ checking
_TYPES = {
    'null': lambda v: v is None,
    'boolean': lambda v: isinstance(v, bool),
    'integer': lambda v: isinstance(v, numbers.Integral) and not isinstance(v, bool),
    'number': lambda v: isinstance(v, numbers.Real) and not isinstance(v, bool),
    'string': lambda v: isinstance(v, str),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
}
_NAMES = {type(None): 'null', bool: 'boolean', int: 'integer', float: 'number', str: 'string', list: 'array',
          dict: 'object'}


def _resolve(root, ref):
    if ref == '#':
        return root
    if not ref.startswith('#/'):
        raise ValueError(f'Only references inside the schema are used: {ref}')
    node = root
    for part in ref[2:].split('/'):
        node = node[part]
    return node


def problems(doc, schema, path='', root=None, limit=20):
    """[(where, what is wrong)] of doc against schema (empty when it matches), the first `limit` of them."""
    root = root if root is not None else schema
    out = []

    def check(v, s, where):
        if len(out) >= limit:
            return
        if '$ref' in s:
            check(v, _resolve(root, s['$ref']), where)
        if 'anyOf' in s:
            found = [problems(v, alt, where, root, limit) for alt in s['anyOf']]
            if all(found):
                # Forms told apart by their first required key (the kinds of a data source): what is wrong with the
                # form whose key is there, or the keys it could have; otherwise the form it comes closest to.
                keys = [_first_required(alt, root) for alt in s['anyOf']]
                if isinstance(v, dict) and all(keys):
                    known = [f for f, k in zip(found, keys) if k in v]
                    if not known:
                        out.append((where or '(document)', 'needs one of ' + ', '.join(f'“{k}”' for k in keys)))
                        return
                    found = known
                out.extend(min(found, key=len)[:limit - len(out)])
            return
        if 'type' in s:
            allowed = s['type'] if isinstance(s['type'], list) else [s['type']]
            if not any(_TYPES[t](v) for t in allowed):
                got = _NAMES.get(type(v), type(v).__name__)
                out.append((where or '(document)', f'expected {" or ".join(allowed)}, got {got}'))
                return
        if 'const' in s and v != s['const']:
            out.append((where or '(document)', f'must be {s["const"]!r}'))
        if 'enum' in s and v not in s['enum']:
            out.append((where or '(document)', f'{v!r} is not one of {", ".join(map(repr, s["enum"][:12]))}'
                        + (' …' if len(s['enum']) > 12 else '')))
        if isinstance(v, dict):
            for key in s.get('required', []):
                if key not in v:
                    out.append((where or '(document)', f'“{key}” is missing'))
            props = s.get('properties', {})
            extra = s.get('additionalProperties', True)
            for key, item in v.items():
                sub = f'{where}.{key}' if where else str(key)
                if key in props:
                    check(item, props[key], sub)
                elif extra is False:
                    out.append((sub, 'is not allowed here'))
                elif isinstance(extra, dict):
                    check(item, extra, sub)
        if isinstance(v, list) and isinstance(s.get('items'), dict):
            for i, item in enumerate(v):
                check(item, s['items'], f'{where}[{i}]')
    check(doc, schema, path)
    return out[:limit]


def _first_required(s, root):
    while '$ref' in s:
        s = _resolve(root, s['$ref'])
    return (s.get('required') or [None])[0]


def _message(what, found):
    lines = [f'{where}: {why}' for where, why in found[:5]]
    more = f' (and {len(found) - 5} more)' if len(found) > 5 else ''
    return f'{what} does not match its schema: ' + '; '.join(lines) + more


def check_spec(spec):
    """The figure description as it is (raises SchemaError)."""
    found = problems(spec, load('figure'), 'spec')
    if found:
        raise SchemaError(_message('The figure description', found))


def check_project(doc):
    found = problems(doc, load('project'))
    if found:
        raise SchemaError(_message('The project', found))


# ------------------------------------------------------------------ versions
def _version(doc, current, what):
    v = doc.get('version', 1)                  # documents written before versions were numbered are version 1
    if not isinstance(v, int) or isinstance(v, bool) or v < 1:
        raise SchemaError(f'{what} has no valid version number ({v!r}).')
    if v > current:
        raise SchemaError(f'{what} was made by a newer π-plotter (version {v}); update π-plotter to open it.')
    return v


def upgrade_spec(spec):
    """The figure description in the current version (a copy when it changes)."""
    if not isinstance(spec, dict):
        return spec
    v = _version(spec, SPEC_VERSION, 'This figure')
    while v < SPEC_VERSION:
        spec = SPEC_UPGRADES[v](spec)
        v += 1
    for panel in spec.get('compose') or []:   # the figures of a layout carry descriptions of their own
        if isinstance(panel, dict) and isinstance(panel.get('spec'), dict):
            panel['spec'] = upgrade_spec(panel['spec'])
    return {**complete_spec(spec), 'version': SPEC_VERSION}


def complete_spec(spec):
    """The description with every part of the figure of this version: what it lacks — written before the part
    existed (the inset before 0.2.4, a layout before 0.2.4…) or left out — takes its default; what it has stays.
    The figure drawn does not change (plotting merges the same defaults); the page gets a description it can use as
    it is."""
    from .plotting import DEFAULT_SPEC, deep_merge
    return deep_merge(DEFAULT_SPEC, spec)


def upgrade_project(doc):
    """The project in the current version, every figure description in it too, checked against the schema."""
    v = _version(doc, PROJECT_VERSION, 'This project')
    while v < PROJECT_VERSION:
        doc = PROJECT_UPGRADES[v](doc)
        v += 1
    doc = {**doc, 'version': PROJECT_VERSION}
    if isinstance(doc.get('spec'), dict):
        doc['spec'] = upgrade_spec(doc['spec'])
    for view in doc.get('views') or []:
        if isinstance(view, dict) and isinstance(view.get('spec'), dict):
            view['spec'] = upgrade_spec(view['spec'])
    check_project(doc)
    return doc


# ------------------------------------------------------------------ generating the schemas
NULLABLE_TEXT = {'type': ['string', 'null']}
LIMIT = {'type': ['number', 'string', 'null'], 'description': 'a number, a date (text) or empty for automatic'}
# Values whose default (None, or an empty container) does not say their type.
SPEC_FIELDS = {
    'x': NULLABLE_TEXT, 'hue': NULLABLE_TEXT, 'z': NULLABLE_TEXT, 'xerr': NULLABLE_TEXT, 'yerr': NULLABLE_TEXT,
    'y': {'type': 'array', 'items': {'type': 'string'}},
    'y2': {'type': 'array', 'items': {'type': 'string'}},
    'series': {'type': 'object', 'additionalProperties': {'type': 'object'},
               'description': 'the look of each series, by its name'},
    'overlays': {'type': 'array', 'items': {'$ref': '#/$defs/layer'}},
    'moved': {'type': 'object', 'additionalProperties': {'type': 'array', 'items': {'type': 'number'}},
              'description': 'texts dragged on the preview: id -> [x, y] in figure fractions'},
    'texts': {'type': 'object', 'additionalProperties': {'type': ['string', 'null']},
              'description': 'texts rewritten on the preview, by id'},
    'axes.xmin': LIMIT, 'axes.xmax': LIMIT, 'axes.ymin': LIMIT, 'axes.ymax': LIMIT, 'axes.zmin': LIMIT,
    'axes.zmax': LIMIT, 'axes.y2min': LIMIT, 'axes.y2max': LIMIT,
    'axes.xbreak': NULLABLE_TEXT, 'axes.ybreak': NULLABLE_TEXT,
    'axes.xbreak_scale': {'type': ['number', 'string', 'null']},
    'axes.ybreak_scale': {'type': ['number', 'string', 'null']},
    'legend.pos': {'type': ['array', 'null'], 'items': {'type': 'number'},
                   'description': 'where the legend was dragged, in axes fractions'},
    'style.vmin': LIMIT, 'style.vmax': LIMIT,
    'inset.xmin': LIMIT, 'inset.xmax': LIMIT, 'inset.ymin': LIMIT, 'inset.ymax': LIMIT,
    'normalize.mode': {'type': 'string', 'enum': ['none', 'max', 'absmax', 'minmax', 'area', 'at'],
                       'description': 'each curve scaled on its own: highest value = 1, highest |value| = 1, '
                                      'from 0 to 1, area = 1, value at X = at is 1'},
    'normalize.xmin': {'type': ['number', 'null']}, 'normalize.xmax': {'type': ['number', 'null']},
    'normalize.at': {'type': ['number', 'null']},
}
SOURCE = sources.SOURCE        # how the data are made again: $defs/source_<kind> for each kind of sources.py
# Parts of the description the page adds to the defaults.
SPEC_EXTRA = {
    'version': {'type': 'integer', 'const': SPEC_VERSION},
    'name': {'type': 'string'},
    'main_pos': {'type': 'integer', 'description': 'place of the main file in the list of files'},
    'extra': {'type': 'array', 'description': 'the other files drawn in the same figure',
              'items': {'type': 'object', 'properties': {
                  'id': {'type': 'string'}, 'dataset_id': {'type': 'string'}, 'name': {'type': 'string'},
                  'source': SOURCE, 'enabled': {'type': 'boolean'}, 'pos': {'type': 'integer'},
                  'x': NULLABLE_TEXT, 'y': {'type': 'array', 'items': {'type': 'string'}}, 'yerr': NULLABLE_TEXT}}},
    'compose': {'type': 'array', 'description': 'the figures of a layout',
                'items': {'type': 'object', 'properties': {
                    'dataset_id': {'type': 'string'}, 'source': SOURCE, 'spec': {'$ref': '#'}}}},
    'layout': {'type': 'object', 'properties': {
        'mode': {'type': 'string'}, 'ncols': {'type': 'integer'}, 'letters': {'type': 'boolean'},
        'share': {'type': 'boolean'}, 'titles': {'type': 'boolean'},
        'spans': {'type': 'array', 'items': {'type': 'array', 'items': {'type': 'integer'}}}}},
    'notes': {'type': 'array', 'description': 'boxes of text or values drawn in the figure',
              'items': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'text': {'type': 'string'}}}},
    'refs': {'type': 'array', 'description': 'reference lines and bands',
             'items': {'type': 'object', 'properties': {
                 'id': {'type': 'string'}, 'axis': {'type': 'string'}, 'label': {'type': 'string'},
                 'value': {'type': ['number', 'string']}, 'to': {'type': ['number', 'string', 'null']},
                 'linestyle': {'type': 'string'}}}},
}
LAYER = {'type': 'object', 'description': 'a layer drawn over the figure: the curve of an analysis, its band',
         'properties': {'id': {'type': 'string'}, 'dataset_id': {'type': 'string'}, 'source': SOURCE,
                        'x': {'type': 'string'}, 'y': {'type': 'string'}, 'lo': NULLABLE_TEXT, 'hi': NULLABLE_TEXT,
                        'z': {**NULLABLE_TEXT, 'description': 'heights: the layer is drawn on 3D figures, at (x, y, z)'},
                        'label': {'type': 'string'}, 'band': {'type': 'boolean'}, 'on_figure': {'type': 'boolean'},
                        'style': {'type': 'object'}, 'references': {'type': 'array', 'items': {'type': 'string'}}}}


def _leaf(value):
    if isinstance(value, bool):
        return {'type': 'boolean'}
    if isinstance(value, numbers.Real):
        return {'type': 'number'}
    if isinstance(value, str):
        return {'type': 'string'}
    if isinstance(value, list):
        return {'type': 'array'}
    if isinstance(value, dict):
        return {'type': 'object'}
    return {}


def figure_schema():
    from . import catalog
    from .plotting import DEFAULT_SPEC

    def build(defaults, prefix):
        props = {}
        for key, value in defaults.items():
            path = f'{prefix}{key}'
            if path in SPEC_FIELDS:
                props[key] = SPEC_FIELDS[path]
            elif isinstance(value, dict) and value:
                props[key] = {'type': 'object', 'properties': build(value, path + '.')}
            else:
                props[key] = _leaf(value)
        return props
    props = build(DEFAULT_SPEC, '')
    props['kind'] = {'type': 'string', 'enum': list(catalog.KINDS)}
    props['style']['properties']['base'] = {'type': 'string', 'enum': list(catalog.STYLES)}
    # Palettes and colour maps of the catalogue (and 'style': the colours of the style sheet). A name from a later
    # π-plotter is refused with the list, rather than drawn with another palette without a word.
    props['style']['properties']['palette'] = {'type': 'string', 'enum': [*catalog.PALETTES, 'style']}
    props['style']['properties']['cmap'] = {'type': 'string',
                                            'enum': [c for group in catalog.COLORMAPS.values() for c in group]}
    props['lang'] = {'type': 'string', 'enum': ['en', 'it']}
    props.update(SPEC_EXTRA)
    return {'$schema': DIALECT, '$id': f'urn:pi-plotter:figure:{SPEC_VERSION}',
            'title': f'π-plotter figure description, version {SPEC_VERSION}',
            'description': 'What is plotted and how it looks. Missing keys take the default of the version; keys '
                           'not named here are kept and ignored.',
            'type': 'object', 'properties': props, '$defs': {'layer': LAYER, **sources.defs()}}


def project_schema():
    from .projects import FORMAT
    figure = figure_schema()
    figure_ref = {'$ref': '#/$defs/figure'}

    def inside(node):            # in the project, the figure's reference to itself points to its definition
        if isinstance(node, dict):
            return figure_ref if node == {'$ref': '#'} else {k: inside(v) for k, v in node.items()}
        return [inside(v) for v in node] if isinstance(node, list) else node
    defs = {'figure': inside({k: v for k, v in figure.items() if k not in ('$schema', '$id', '$defs')}),
            'layer': figure['$defs']['layer'], **sources.defs()}
    return {
        '$schema': DIALECT, '$id': f'urn:pi-plotter:project:{PROJECT_VERSION}',
        'title': f'π-plotter project (project.json of a .piplot archive), version {PROJECT_VERSION}',
        'description': 'The work on screen: the files with their sources and settings, the figure, its copies with '
                       'their analyses. Data are not stored: each data set is made again from its source; the data '
                       'files themselves are entries of the archive (embedded).',
        'type': 'object', 'required': ['format', 'version'],
        'properties': {
            'format': {'const': FORMAT},
            'version': {'type': 'integer', 'const': PROJECT_VERSION},
            'app': {'type': 'string', 'description': 'build of π-plotter that saved it'},
            'saved': {'type': 'string', 'description': 'when (ISO 8601)'},
            'lang': {'type': 'string', 'enum': ['en', 'it']},
            'files': {'type': 'array', 'items': {'type': 'object', 'required': ['source'], 'properties': {
                'id': {'type': 'string'}, 'name': {'type': 'string'}, 'source': SOURCE,
                'info': {'type': ['object', 'null']}, 'settings': {'type': ['object', 'null']}}}},
            'active': NULLABLE_TEXT,
            'main': {'type': ['object', 'null'], 'properties': {'name': {'type': 'string'}, 'source': SOURCE}},
            'spec': {'anyOf': [figure_ref, {'type': 'null'}]},
            'views': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'id': {'type': 'string'}, 'spec': {'anyOf': [figure_ref, {'type': 'null'}]},
                'runs': {'type': 'array', 'items': {'type': 'object'}},
                'compose': {'type': ['array', 'null'], 'items': {'type': 'string'}},
                'dataset': {'type': ['object', 'null']}, 'result': {'type': ['object', 'null']}}}},
            'view': NULLABLE_TEXT,
            'tab': {'type': 'string'},
            'analysis': {'type': ['object', 'null'], 'description': 'the analyses panel: parameters, runs'},
            'console': {'type': ['object', 'null'], 'description': 'the console: its history and the code typed'},
            'embedded': {'type': 'object', 'description': 'file id -> its entry in the archive',
                         'additionalProperties': {'type': 'object', 'required': ['entry'], 'properties': {
                             'entry': {'type': 'string'}, 'name': {'type': 'string'}, 'size': {'type': 'integer'}}}},
        },
        '$defs': defs,
    }


def generated():
    return {'figure': figure_schema(), 'project': project_schema()}


def write():
    """Write the schemas of this version to piplotter/schemas/ (after a deliberate change of the documents)."""
    FOLDER.mkdir(exist_ok=True)
    for name, schema in generated().items():
        file_of(name).write_text(json.dumps(schema, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print('written', file_of(name))


if __name__ == '__main__':
    write()
