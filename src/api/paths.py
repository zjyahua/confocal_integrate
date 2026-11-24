"""Where experiment data and logs go.

One day folder holds four things:

    C:/zjh/experiment data/<YYYY.MM.DD>/
    ├── logs/                 one timestamped log per kind (scan/track/point/misc)
    ├── scan/                 confocal image scans, one folder per run
    ├── track/                tracking runs, one folder per run
    └── point/                single point experiments, one folder per run

Small commands (goto / where / demo) do not create data folders; they only
write to the log.

Override the root with the CONFOCAL_DATA_ROOT environment variable.
"""

from __future__ import annotations

import os
import time
import uuid

DEFAULT_DATA_ROOT = r"C:\zjh\experiment data"

DATA_ROOT = os.environ.get("CONFOCAL_DATA_ROOT") or DEFAULT_DATA_ROOT

# job kind -> (data folder name, log file category)
CATEGORY = {
    "confocal_scan": ("scan", "scan"),
    "point_scan": ("point", "point"),
    "track": ("track", "track"),
    "goto": (None, "misc"),
    "where": (None, "misc"),
    "demo": (None, "misc"),
}

DATA_KINDS = ("confocal_scan", "point_scan", "track")


def is_data_kind(kind):
    """Only these kinds own an output folder."""
    return kind in DATA_KINDS


def category_of(kind):
    """Return (data_folder, log_category); data_folder is None for small commands."""
    return CATEGORY.get(kind, ("misc", "misc"))


def day_dir(stamp=None):
    day = stamp or time.strftime("%Y.%m.%d")
    return os.path.join(DATA_ROOT, day)


def logs_dir(stamp=None):
    return os.path.join(day_dir(stamp), "logs")


def log_path(kind, stamp=None):
    _, log_category = category_of(kind)
    return os.path.join(logs_dir(stamp), log_category + ".log")


def default_out_dir(kind="confocal_scan", stamp=None):
    """<data root>/<day>/<category>/<HHMMSS> for kinds that own data."""
    data_folder, _ = category_of(kind)

    if data_folder is None:
        raise ValueError("%r does not create an output folder" % kind)

    day = stamp or time.strftime("%Y.%m.%d")
    # a short suffix keeps two runs that start in the same second apart
    run_stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:3]

    return os.path.join(DATA_ROOT, day, data_folder, run_stamp)
