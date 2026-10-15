"""What every area of the service shares: its limits, the error it answers with, and the helpers for names and JSON."""
import math
from pathlib import Path
import re
from urllib.parse import quote

MAX_JSON = 32 * 1024 * 1024
MAX_BATCH_FILES = 500           # files in one batch analysis
MAX_DATASETS = 200                # kept in memory, least recently used dropped first …
MAX_DATASET_BYTES = 2 * 1024 ** 3  # … also when together they take more than this
MAX_MADE = 1000                   # sources whose data set is remembered (service/files.py)
PREVIEW_ROWS = 200
PREVIEW_COLS = 100      # the table shows the first columns: a wide table would be millions of cells
CHUNK = 1 << 20
DOWNLOAD_TTL = 600            # seconds a one-off download link stays valid


class ApiError(Exception):
    def __init__(self, message, status=400, code='error', **extra):
        super().__init__(message)
        self.status, self.code, self.extra = status, code, extra


def safe_name(name, fallback='data'):
    name = re.sub(r'[^\w.\-]+', '_', Path(str(name)).name, flags=re.UNICODE).strip('._')
    return name[:120] or fallback


def content_disposition(fname):
    """Header value for a download name; HTTP headers are Latin-1, so non-ASCII names go in filename*."""
    ascii_name = fname.encode('ascii', 'replace').decode('ascii').replace('?', '_').replace('"', '_')
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(fname, safe="")}'


def json_safe(v):
    """Make pandas/numpy cell values JSON-serialisable."""
    if v is None:
        return None
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, (str, bool, int)):
        return v
    if hasattr(v, 'isoformat'):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if hasattr(v, 'item'):
        try:
            return json_safe(v.item())
        except Exception:
            pass
    s = str(v)
    return None if s in ('NaT', 'nan', '<NA>') else s
