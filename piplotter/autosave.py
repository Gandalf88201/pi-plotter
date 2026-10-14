"""Autosave: the work on screen, kept on disk while you work, to get it back after the browser, the computer or
π-plotter stopped before it was saved as a project.

The page sends its description of the work (the same as for a project file) when it changes; it is written to
<home>/autosave/current/project.json, and each data file it uses is copied once into current/files/<id>/. Data sets
are rebuilt from their sources on recovery, exactly as when a project is opened. The first save of a new session
first moves the previous session's copy to previous/, so starting new work never overwrites the last one."""
import json
import os
import shutil
import time
from pathlib import Path

SLOTS = ('current', 'previous')


def folder():
    from . import home_dir
    return home_dir() / 'autosave'


def _write_json(path, doc):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc), encoding='utf-8')
    os.replace(tmp, path)                       # all at once: a crash leaves the old copy or the new one


def save(project, files, first, build=''):
    """Write the work. project: the page's description; files: the session's uploaded files {id: info};
    first: the first save of this session (the previous session's copy moves to previous/ first)."""
    from .projects import file_ids
    base = folder()
    cur = base / 'current'
    if first and (cur / 'project.json').exists():
        prev = base / 'previous'
        shutil.rmtree(prev, ignore_errors=True)
        os.replace(cur, prev)
    (cur / 'files').mkdir(parents=True, exist_ok=True)
    kept = {}
    for fid in file_ids(project):
        info = files.get(fid)
        if not info or not Path(info['path']).is_file():
            continue
        target = cur / 'files' / fid / Path(info['path']).name
        if not target.exists():                 # a data file is copied once
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(info['path'], target.with_suffix(target.suffix + '.part'))
            os.replace(target.with_suffix(target.suffix + '.part'), target)
        kept[fid] = {'name': info['name'], 'file': f'{fid}/{target.name}', 'format': info.get('format'),
                     'compression': info.get('compression'), 'size': info.get('size')}
    for old in (cur / 'files').iterdir():       # files the work no longer uses
        if old.name not in kept and not old.name.startswith('._'):
            shutil.rmtree(old, ignore_errors=True)
    _write_json(cur / 'project.json', {'project': project, 'files': kept, 'saved': time.time(), 'app': build})


def info(skip_current=False):
    """What can be recovered, newest first: [{'slot', 'saved' (s since 1970), 'files': names, 'figures'}]."""
    out = []
    for slot in SLOTS:
        if slot == 'current' and skip_current:
            continue
        doc = _read(slot)
        if not doc:
            continue
        p = doc.get('project') or {}
        out.append({'slot': slot, 'saved': doc.get('saved'),
                    'files': [f.get('name') for f in p.get('files') or [] if isinstance(f, dict)][:12]
                    or [(p.get('main') or {}).get('name') or '—'],          # an example or a table typed in
                    'figures': 1 + len(p.get('views') or [])})
    return sorted(out, key=lambda d: -(d['saved'] or 0))


def _read(slot):
    if slot not in SLOTS:
        return None
    path = folder() / slot / 'project.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def recover(slot, add_file):
    """(project with its file ids remapped, files that could not be found). add_file(name, path) puts a data file
    back into the session and returns its new id."""
    from .projects import remap
    doc = _read(slot)
    if not doc:
        raise FileNotFoundError('Nothing to recover.')
    mapping, missing = {}, []
    for fid, f in (doc.get('files') or {}).items():
        path = folder() / slot / 'files' / f['file']
        if path.is_file():
            mapping[fid] = add_file(f['name'], path)
        else:
            missing.append(f['name'])
    return remap(doc['project'], mapping), missing


def discard(slot):
    if slot in SLOTS:
        shutil.rmtree(folder() / slot, ignore_errors=True)
