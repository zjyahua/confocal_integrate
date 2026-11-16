"""Where experiment output goes.

Runs are written outside the source tree, under the lab data folder:

    C:/zjh/experiment data/<YYYY.MM.DD>/api/<YYmmdd-HHMMSS>/

Override with the CONFOCAL_DATA_ROOT environment variable (useful for tests
or when the data disk moves).
"""

from __future__ import annotations

import os
import time

DEFAULT_DATA_ROOT = r"C:\zjh\experiment data"

DATA_ROOT = os.environ.get("CONFOCAL_DATA_ROOT") or DEFAULT_DATA_ROOT


def default_out_dir(prefix="api"):
    """<data root>/<YYYY.MM.DD>/<prefix>/<stamp>"""
    now = time.localtime()
    day = time.strftime("%Y.%m.%d", now)
    stamp = time.strftime("%Y%m%d-%H%M%S", now)
    return os.path.join(DATA_ROOT, day, prefix, stamp)
