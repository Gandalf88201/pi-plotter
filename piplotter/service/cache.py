"""Clearing the cache: the session starts from zero.

What the service keeps only to be quicker, or only for the work on screen, is dropped: the data sets in memory and
the sources they were made from, the 3D views, the copies of the files opened in this session, the projects waiting
to be downloaded, the console's variables, the analyses loaded, and on disk the list of module versions read from
PyPI and the import checks (made again in the background). What cannot be made again stays: saved projects, the
files on the user's disk, the user's plugins, the installed modules and their list. The autosaved copies of the last
work are deleted only when asked (autosave=True): otherwise the work cleared stays recoverable."""
import shutil
from pathlib import Path


class CacheArea:
    def clear_cache(self, body):
        autosave = body.get('autosave') is True
        with self.lock:
            datasets, made, files = len(self.datasets), len(self.made), len(self.files)
            self.datasets.clear()
            self.made.clear()
            self.views3d.clear()
            self._overlay_alias = {}
            self._extra_refs = []
            for info in self.files.values():
                folder = Path(info['path']).parent
                if folder.parent == self.session_dir:             # a copy of an opened file, never anything else
                    shutil.rmtree(folder, ignore_errors=True)
            self.files = {}
            self._save_files()
            for d in self.downloads.values():
                Path(d['path']).unlink(missing_ok=True)
            self.downloads = {}
            self._plugins = None                                  # the analyses are read again on next use
            # Keeping the autosave: the next work of this session moves the cleared work to previous/ first,
            # instead of writing over it.
            self._autosaved = False
        if self._console is not None:
            self._console.reset()
        self.modules.clear_caches()
        if autosave:
            from .. import autosave as kept
            for slot in kept.SLOTS:
                kept.discard(slot)
        return {'ok': True, 'datasets': datasets, 'sources': made, 'files': files, 'autosave': autosave}
