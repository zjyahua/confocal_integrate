"""Timestamped experiment logs.

Every run appends to one file per category, so a day of experiments leaves a
handful of readable logs instead of dozens of folders:

    <data root>/<YYYY.MM.DD>/logs/scan.log
    <data root>/<YYYY.MM.DD>/logs/track.log
    <data root>/<YYYY.MM.DD>/logs/point.log
    <data root>/<YYYY.MM.DD>/logs/misc.log

Each line starts with the local time, so the log shows what happened when.
"""

from __future__ import annotations

import json
import os
import time

from src.api import paths


def _timestamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _compact(payload, max_length=400):
    """Small one-line JSON for parameters and results."""
    if payload is None:
        return ""

    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return ""

    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return text


def write(kind, message, payload=None):
    """Append one timestamped line to the log of that kind."""
    path = paths.log_path(kind)
    line = "[%s] %s" % (_timestamp(), message)

    extra = _compact(payload)
    if extra:
        line += "  " + extra

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:  # logging must never break a run
        print("log write failed: %s" % exc)

    return path
