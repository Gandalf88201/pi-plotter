"""Project files (.piplot): the whole work saved in one file and opened again, here or on another computer.

A project is a zip archive:

    project.json          what the page had on screen: the loaded files with their settings, the figure, its copies
                          with analyses, result figures, the parameters of the analyses, the language…
    data/1-name.csv …     the data files that were opened, byte for byte (so the same import options give the same
                          table, and the project does not depend on where the files were)

Every data set is described by its source (a file and its import options, a blank table, a list of edits, an
analysis of another data set), so nothing computed needs to be stored: on opening, the files are put back in the
session, the file ids in the project are replaced by the new ones, and the page rebuilds each data set from its
source (analyses are run again). The format has a version number; newer versions are refused with a clear message.
"""
import io
import json
import re
import zipfile
from pathlib import Path

FORMAT = 'pi-plotter project'
VERSION = 1
EXTENSION = '.piplot'
MANIFEST = 'project.json'
MAX_JSON = 64 * 1024 ** 2          # the description of a project (specs, edit lists…) — not the data files
STORE_ABOVE = 64 * 1024 ** 2       # data files larger than this are stored as they are (compressing them is slow)


class ProjectError(ValueError):
    """A project that cannot be saved or opened (the message is shown to the user)."""


def file_ids(obj):
    """Every uploaded-file id referenced anywhere in obj (sources, file infos…): values of 'file_id' keys."""
    found = []

    def walk(v):
        if isinstance(v, dict):
            fid = v.get('file_id')
            if isinstance(fid, str) and fid and fid not in found:
                found.append(fid)
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(obj)
    return found


def remap(obj, mapping):
    """A copy of obj with every 'file_id' value replaced through mapping (ids not in mapping are kept)."""
    if isinstance(obj, dict):
        return {k: (mapping.get(v, v) if k == 'file_id' and isinstance(v, str) else remap(v, mapping))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [remap(v, mapping) for v in obj]
    return obj


def _entry_name(k, name):
    stem = re.sub(r'[^\w.\-]+', '_', Path(str(name)).name).strip('._') or 'data'
    return f'data/{k}-{stem[:120]}'


def pack(project, files, out):
    """Write the project archive to the binary stream out. files: {file id: {'name', 'path', …}} for every id the
    project references (file_ids(project)); a missing one is an error, as the project could not be opened again."""
    if not isinstance(project, dict):
        raise ProjectError('Nothing to save.')
    embedded = {}
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for k, fid in enumerate(file_ids(project), 1):
            info = files.get(fid)
            if not info or not Path(info['path']).is_file():
                raise ProjectError(f'A data file of the project is no longer available ({fid}); open it again first.')
            path = Path(info['path'])
            entry = _entry_name(k, info.get('name') or path.name)
            big = path.stat().st_size > STORE_ABOVE
            z.write(path, entry, compress_type=zipfile.ZIP_STORED if big else zipfile.ZIP_DEFLATED)
            embedded[fid] = {'entry': entry, 'name': info.get('name') or path.name, 'size': path.stat().st_size}
        doc = {'format': FORMAT, 'version': VERSION, **project, 'embedded': embedded}
        z.writestr(MANIFEST, json.dumps(doc, ensure_ascii=False, indent=1, default=str))
    return embedded


def read(path, max_bytes):
    """(project, [(old file id, name, zip entry)]) of the archive at path, checked: a zip with project.json of a
    format and version this program reads, data entries that exist and are not larger than max_bytes in all."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ProjectError('This is not a π-plotter project (.piplot).')
    with z:
        try:
            info = z.getinfo(MANIFEST)
        except KeyError:
            raise ProjectError('This is not a π-plotter project: project.json is missing.')
        if info.file_size > MAX_JSON:
            raise ProjectError('project.json is too large.')
        try:
            doc = json.loads(z.read(MANIFEST).decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            raise ProjectError('project.json cannot be read.')
        if not isinstance(doc, dict) or doc.get('format') != FORMAT:
            raise ProjectError('This is not a π-plotter project.')
        version = doc.get('version')
        if not isinstance(version, int) or version > VERSION:
            raise ProjectError(f'This project was saved by a newer π-plotter (format {version}); update π-plotter to open it.')
        embedded = doc.pop('embedded', {}) or {}
        names = set(z.namelist())
        files, total = [], 0
        for fid, e in embedded.items():
            entry = str((e or {}).get('entry') or '')
            if entry not in names or not entry.startswith('data/') or '..' in entry:
                raise ProjectError(f'The project is damaged: {entry or fid} is missing.')
            total += z.getinfo(entry).file_size
            files.append((str(fid), str(e.get('name') or Path(entry).name), entry))
        if total > max_bytes:
            raise ProjectError(f'The data in the project are larger than the limit ({max_bytes / 1024 ** 3:.0f} GB).')
    return doc, files


def open_entry(path, entry):
    """A binary stream of one data entry of the archive (to copy it into the session)."""
    z = zipfile.ZipFile(path)
    return z, z.open(entry), z.getinfo(entry).file_size


def to_bytes(project, files):
    buf = io.BytesIO()
    pack(project, files, buf)
    return buf.getvalue()
