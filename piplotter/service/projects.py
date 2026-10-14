"""Project files (.piplot) and the autosave: the archive written to the session folder and downloaded from a
one-off link, a project opened from an upload, the work kept on disk while it changes (autosave.py)."""
from pathlib import Path
import secrets
import time

from .common import CHUNK, DOWNLOAD_TTL, ApiError, safe_name


class ProjectsArea:
    # -------------------------------------------------------------- project files (.piplot)
    def save_project(self, body):
        """The project archive (bytes): the page's description of the work + the data files it uses."""
        from .. import projects
        project = body.get('project')
        try:
            with self.lock:
                files = dict(self.files)
            return projects.to_bytes(project, files)
        except projects.ProjectError as exc:
            raise ApiError(str(exc), 422, 'project')

    def save_project_file(self, body):
        """Write the project archive to a file of the session and give a one-off link to download it: the data
        files are copied from disk to disk and sent in pieces, so a project of many GB never sits in memory (neither
        here nor in the page)."""
        from .. import projects
        project = body.get('project')
        name = safe_name(body.get('filename') or 'project', 'project') + projects.EXTENSION
        with self.lock:
            files = dict(self.files)
        did = secrets.token_hex(16)
        path = self.session_dir / f'_save_{did}{projects.EXTENSION}'
        try:
            with open(path, 'wb') as out:
                projects.pack(project, files, out)
        except projects.ProjectError as exc:
            path.unlink(missing_ok=True)
            raise ApiError(str(exc), 422, 'project')
        except OSError as exc:
            path.unlink(missing_ok=True)
            raise ApiError(f'The project could not be written: {exc}', 500, 'project')
        with self.lock:
            self._expire_downloads()
            self.downloads[did] = {'path': path, 'name': name, 'until': time.time() + DOWNLOAD_TTL}
        return {'url': f'/download/{did}', 'name': name, 'size': path.stat().st_size}

    def take_download(self, did):
        """The file behind a one-off link (the link is used up)."""
        with self.lock:
            self._expire_downloads()
            d = self.downloads.pop(str(did), None)
        if d is None or not d['path'].is_file():
            raise ApiError('This download link has expired; save again.', 404, 'not_found')
        return d

    def _expire_downloads(self):
        now = time.time()
        for did in [k for k, d in self.downloads.items() if d['until'] < now]:
            self.downloads.pop(did)['path'].unlink(missing_ok=True)

    def open_project(self, name, stream, length):
        """Read an uploaded project: its data files go back into the session (new ids), and the project comes
        back with the file ids replaced, for the page to rebuild every data set from its source."""
        from .. import projects
        if length <= 0:
            raise ApiError('Empty upload.')
        if length > self.max_upload:
            raise ApiError(f'File larger than the limit ({self.max_upload / 1024 ** 3:.0f} GB).', 413)
        tmp = self.session_dir / f'_project_{secrets.token_hex(6)}{projects.EXTENSION}'
        try:
            remaining = length
            with open(tmp, 'wb') as out:
                while remaining > 0:
                    chunk = stream.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
            if remaining:
                raise ApiError('Upload interrupted.')
            try:
                doc, entries = projects.read(tmp, self.max_upload)
            except projects.ProjectError as exc:
                raise ApiError(str(exc), 422, 'project')
            mapping = {}
            for old, fname, entry in entries:
                z, f, size = projects.open_entry(tmp, entry)
                try:
                    mapping[old] = self.add_upload(fname, f, size)['id']
                finally:
                    f.close()
                    z.close()
        finally:
            tmp.unlink(missing_ok=True)
        return {'project': projects.remap(doc, mapping), 'name': Path(name).stem}

    # -------------------------------------------------------------- autosave (autosave.py)
    def autosave_write(self, body):
        """Keep the work on screen on disk (the page sends it when it changes)."""
        from .. import autosave
        project = body.get('project')
        if not isinstance(project, dict) or not project.get('files') and not project.get('main'):
            return {'saved': None}
        with self.lock:
            files = dict(self.files)
            first = not self._autosaved
            self._autosaved = True
        try:
            autosave.save(project, files, first, self.build)
        except OSError as exc:
            raise ApiError(f'Autosave failed: {exc}', 500, 'autosave')
        return {'saved': time.time()}

    def autosave_info(self):
        """The work that can be recovered (not this session's own copy)."""
        from .. import autosave
        return {'items': autosave.info(skip_current=self._autosaved)}

    def autosave_recover(self, body):
        from .. import autosave

        def add_file(name, path):
            with open(path, 'rb') as f:
                return self.add_upload(name, f, path.stat().st_size)['id']
        try:
            project, missing = autosave.recover(str(body.get('slot') or 'current'), add_file)
        except FileNotFoundError as exc:
            raise ApiError(str(exc), 404, 'autosave')
        return {'project': project, 'missing': missing}

    def autosave_discard(self, body):
        from .. import autosave
        autosave.discard(str(body.get('slot') or ''))
        return {'ok': True}
