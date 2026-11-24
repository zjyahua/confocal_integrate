"""PNG rendering with matplotlib's Agg backend (no Qt, no window).

Every figure the agent shows in chat is produced here, so the plotting
style stays consistent no matter whether the Qt GUI is open or not.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

STYLE = {
    "figsize": (7.2, 5.0),
    "dpi": 140,
    "grid_alpha": 0.3,
}


def _save(fig, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=STYLE["dpi"])
    plt.close(fig)
    return path


def render_map(map2d, path, title="", xlabel="x", ylabel="y", unit="", extent=None):
    """2D intensity / lifetime image."""
    data = np.asarray(map2d, dtype=float)
    fig, ax = plt.subplots(figsize=STYLE["figsize"])

    image = ax.imshow(
        data,
        origin="lower",
        aspect="auto",
        cmap="inferno",
        interpolation="nearest",
        extent=extent,
    )
    fig.colorbar(image, ax=ax, label="counts" if not unit else unit)

    ax.set_title(title or "scan")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    return _save(fig, path)


def render_sweep(
    x, sig, ref=None, path="sweep.png", title="", xlabel="", ylabel="", xscale="linear"
):
    """Point measurement: signal (and optionally reference) versus the sweep."""
    x = np.asarray(x, dtype=float)
    sig = np.asarray(sig, dtype=float)

    fig, ax = plt.subplots(figsize=STYLE["figsize"])
    ax.plot(x, sig, "o-", ms=3, lw=1.2, label="signal")

    if ref is not None:
        ref = np.asarray(ref, dtype=float)
        ax.plot(x, ref, "s--", ms=3, lw=1.0, label="reference")
        if np.all(ref != 0):
            ax2 = ax.twinx()
            ax2.plot(x, sig / ref, "-", lw=1.6, color="tab:red", label="sig/ref")
            ax2.set_ylabel("signal / reference")

    ax.set_xscale(xscale)
    ax.set_title(title or "point sweep")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=STYLE["grid_alpha"])
    ax.legend(loc="best")
    return _save(fig, path)


def render_histogram(counts, path="hist.png", title="", xlabel="time (ns)", x=None):
    """Histogram / FLIM trace of a single pixel (x is the time axis in ns)."""
    counts = np.asarray(counts, dtype=float)

    if x is None:
        x = np.arange(counts.size)
    else:
        x = np.asarray(x, dtype=float)

    fig, ax = plt.subplots(figsize=STYLE["figsize"])

    # same style as the GUI histogram window: a line through the data points,
    # not a filled bar chart (bars hide the shape and look like a solid block)
    if counts.size <= 200:
        ax.plot(x, counts, "o-", ms=3.5, lw=1.0)
    else:
        ax.plot(x, counts, ".-", ms=2.0, lw=0.6)

    ax.set_title(title or "histogram")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("counts")
    ax.grid(alpha=STYLE["grid_alpha"])
    return _save(fig, path)


def render_progress(packets, path, title="", xlabel="", ylabel=""):
    """Live figure from the accumulated point-scan packets."""
    from collections import defaultdict

    table = defaultdict(lambda: {"sig": 0.0, "ref": 0.0, "n": 0})
    for packet in packets:
        key = packet.get("frequency")
        if key is None:
            key = packet.get("time_point")
        entry = table[key]
        entry["sig"] += float(packet.get("sig", 0))
        entry["ref"] += float(packet.get("ref", 0))
        entry["n"] += 1

    if not table:
        return None

    xs = sorted(table)
    sig = [table[k]["sig"] / max(table[k]["n"], 1) for k in xs]
    ref = [table[k]["ref"] / max(table[k]["n"], 1) for k in xs]
    return render_sweep(xs, sig, ref, path=path, title=title, xlabel=xlabel, ylabel=ylabel)


def demo(out_dir):
    """Render fake data, to check the visual style without hardware."""
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(7)

    yy, xx = np.mgrid[0:100, 0:100]
    blob = 3000 * np.exp(-(((xx - 50) ** 2) + ((yy - 45) ** 2)) / (2 * 9.0 ** 2))
    map2d = rng.normal(20, 4, size=(100, 100)) + blob

    x = np.linspace(2800, 2940, 141)
    sig = 10000 + rng.normal(0, 40, x.size)
    ref = 10000 + rng.normal(0, 40, x.size)
    for centre, fwhm, depth in ((2836.4, 31.3, 280.0), (2904.3, 28.3, 290.0)):
        sig -= depth / (1 + ((x - centre) / (fwhm / 2)) ** 2)
    ratio_sig = sig / 1.0

    files = [
        render_map(map2d, os.path.join(out_dir, "demo_map.png"), title="demo scan"),
        render_sweep(x, ratio_sig / ref, None, path=os.path.join(out_dir, "demo_sweep.png"),
                     title="demo ODMR (sig/ref)", xlabel="frequency (MHz)"),
    ]
    return files

def render_track(pos_lists, cts_lists, origins, finals, path="track.png", title=""):
    """Three panels: counts versus position for X, Y and Z."""
    names = ["X", "Y", "Z"]

    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.6))

    for i, ax in enumerate(axes):
        pos = np.asarray(pos_lists[i], dtype=float)
        cts = np.asarray(cts_lists[i], dtype=float)

        ax.plot(pos, cts, "o-", ms=4, lw=1.2, color="tab:blue")

        ax.axvline(
            float(origins[i]), color="tab:gray", ls="--", lw=1.0, label="origin"
        )
        ax.axvline(
            float(finals[i]), color="tab:red", ls="-", lw=1.2, label="final"
        )

        ax.set_title(names[i])
        ax.set_xlabel("%s position" % names[i])
        ax.set_ylabel("counts")
        ax.grid(True, alpha=STYLE["grid_alpha"])

        if i == 0:
            ax.legend(fontsize=8)

    if title:
        fig.suptitle(title, fontsize=11)

    return _save(fig, path)

def render_fit(
    x, y, y_fit, path="fit.png", title="", xlabel="", annotation="", xscale="linear"
):
    """Measured points with the fitted curve on top."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    y_fit = np.asarray(y_fit, dtype=float)

    fig, ax = plt.subplots(figsize=STYLE["figsize"])

    ax.plot(x, y, "o", ms=3.5, color="tab:blue", label="data")
    ax.plot(x, y_fit, "-", lw=1.6, color="tab:red", label="fit")

    ax.set_xscale(xscale)
    ax.set_title(title or "fit")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("signal")
    ax.grid(True, alpha=STYLE["grid_alpha"])
    ax.legend(fontsize=8)

    if annotation:
        ax.text(
            0.02,
            0.98,
            annotation,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=8,
            family="monospace",
            bbox=dict(boxstyle="round", fc="white", ec="0.7", alpha=0.85),
        )

    return _save(fig, path)
