"""Curve fitting for point-scan data.

The models are the ones from confocal/data_processing/Fitting_methods, rewritten
so they return values instead of printing and so the initial guesses are made
from the data itself:

    lorentz  ODMR dips / peaks        sum of Lorentzians + background
    rabi     Rabi oscillation         A sin(2 pi f t + phi) exp(-t/T2) + b t + C
    t1       T1 relaxation            A exp(-t/T1) + C
    t2       T2 relaxation            A exp(-(t/T2)^beta) + C
    fid      Ramsey / FID             (A cos(2 pi f t + phi) + C1) exp(-(t/T2*)^n) + b t + C2

x is in the units of the sweep (MHz for ODMR, ns for time scans), so the time
constants come back in ns and the frequencies in 1/ns (= GHz).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

FIT_KINDS = ("none", "lorentz", "rabi", "t1", "t2", "fid")


# --------------------------------------------------------------------- models
def lorentz_sum(x, *params):
    """params = [a1, w1, c1, a2, w2, c2, ..., background] (w = FWHM)."""
    x = np.asarray(x, dtype=float)
    y = np.full_like(x, float(params[-1]))

    for i in range((len(params) - 1) // 3):
        amplitude, width, center = params[3 * i], params[3 * i + 1], params[3 * i + 2]
        y = y + 2.0 * amplitude / np.pi * width / (4.0 * (x - center) ** 2 + width ** 2)

    return y


def rabi_model(x, amplitude, omega, phi, t2, b, constant):
    return amplitude * np.sin(2 * np.pi * omega * x + phi) * np.exp(-x / t2) + b * x + constant


def t1_model(x, amplitude, t1, constant):
    return amplitude * np.exp(-x / t1) + constant


def t2_model(x, amplitude, t2, beta, constant):
    return amplitude * np.exp(-((x / t2) ** beta)) + constant


def fid_model(x, amplitude, omega, phi, c1, t2_star, n, b, c2):
    return (amplitude * np.cos(2 * np.pi * omega * x + phi) + c1) * np.exp(
        -((x / t2_star) ** n)
    ) + b * x + c2


# ------------------------------------------------------------------- helpers
def _r2(y, y_fit):
    y = np.asarray(y, dtype=float)
    y_fit = np.asarray(y_fit, dtype=float)

    ss_res = float(np.sum((y - y_fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))

    if ss_tot <= 0:
        return 0.0

    return 1.0 - ss_res / ss_tot


def _baseline(y, k=6):
    y = np.asarray(y, dtype=float)
    k = max(2, min(int(k), max(1, len(y) // 2)))

    return float(np.mean([np.mean(y[:k]), np.mean(y[-k:])]))


def _smooth(y, window):
    """Moving average that leaves the ends untouched."""
    y = np.asarray(y, dtype=float)
    half = int(window) // 2

    if window < 3 or half < 1 or y.size <= 2 * half:
        return y

    smoothed = np.convolve(y, np.ones(int(window)) / float(window), mode="same")
    smoothed[:half] = y[:half]
    smoothed[-half:] = y[-half:]

    return smoothed


def _peak_centers(x, y, max_peaks=8):
    """Peak positions (either sign of excursion, dips are the usual ODMR case)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.size < 8:
        return []

    # smooth first: raw counts turn every noise bump into a peak
    window = max(3, (x.size // 40) * 2 + 1)
    smoothed = _smooth(y, window)

    deviation = smoothed - np.median(smoothed)
    work = -deviation if (-deviation.min()) > deviation.max() else deviation

    level = float(np.median(work))
    span = float(np.max(work) - level)

    if span <= 0:
        return []

    # noise level from consecutive differences: the slow signal does not
    # contribute there, unlike a plain MAD over the whole trace
    if smoothed.size > 2:
        noise = 1.4826 * float(np.median(np.abs(np.diff(smoothed)))) / np.sqrt(2.0)
    else:
        noise = 0.0

    distance = max(2, int(x.size // 20))
    indices, props = find_peaks(
        work,
        height=level + 0.35 * span,
        prominence=max(0.35 * span, 4.0 * noise),
        distance=distance,
    )

    prominences = props["prominences"] if indices.size else np.array([])

    # drop peaks sitting on the first/last samples (edge artefacts) and keep
    # only the peaks that are comparable to the strongest one
    if indices.size:
        margin = 2
        inside = (indices > margin) & (indices < x.size - 1 - margin)
        indices, prominences = indices[inside], prominences[inside]

    if indices.size == 0:
        # no convincing peak: use the strongest deviation as the single seed
        return [float(x[int(np.argmax(work))])]

    strongest = float(np.max(prominences))
    keep = prominences >= 0.5 * strongest
    indices, prominences = indices[keep], prominences[keep]

    order = np.argsort(prominences)[::-1][: int(max_peaks)]

    return [float(x[i]) for i in sorted(indices[order])]


def _dominant_period(x, y, default):
    """Period of the strongest oscillation, used as the initial guess."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.size < 8 or x[0] == x[-1]:
        return float(default)

    dx = float(np.median(np.diff(x)))

    if dx <= 0:
        return float(default)

    detrended = y - np.polyval(np.polyfit(x, y, 1), x)
    spectrum = np.abs(np.fft.rfft(detrended))
    freqs = np.fft.rfftfreq(detrended.size, d=dx)

    if spectrum.size < 3:
        return float(default)

    k = int(np.argmax(spectrum[1:]) + 1)

    if freqs[k] <= 0:
        return float(default)

    return float(1.0 / freqs[k])


def _fit(model, x, y, p0):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    popt, _ = curve_fit(model, x, y, p0=p0, maxfev=400000)

    return popt, model(x, *popt)


# --------------------------------------------------------------------- fitters
def lorentz_fit(x, y, peaks=None):
    """peaks=None detects the peaks, an int keeps the N strongest ones."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.size < 8:
        raise ValueError("need at least 8 points for a Lorentzian fit")

    baseline = _baseline(y)
    centers = _peak_centers(x, y)

    if peaks is not None:
        centers = centers[: int(peaks)]

    if not centers:
        raise RuntimeError("no peak could be located")

    p0 = []

    for center in centers:
        index = int(np.argmin(np.abs(x - center)))
        amplitude = float(y[index] - baseline)

        if abs(amplitude) < 1e-12:
            amplitude = float(np.max(y) - baseline)

        p0 += [amplitude, 12.0, float(x[index])]

    p0.append(baseline)

    popt, y_fit = _fit(lorentz_sum, x, y, p0)

    peaks_out = []

    for i in range((len(popt) - 1) // 3):
        amplitude, width, center = popt[3 * i], popt[3 * i + 1], popt[3 * i + 2]
        peaks_out.append(
            {
                "center": round(float(center), 4),
                "fwhm": round(abs(float(width)), 4),
                "amplitude": round(float(amplitude), 6),
            }
        )

    peaks_out.sort(key=lambda item: item["center"])

    result = {
        "kind": "lorentz",
        "params": {
            "peaks": peaks_out,
            "background": round(float(popt[-1]), 6),
        },
        "r2": round(_r2(y, y_fit), 4),
    }

    return result, y_fit


def rabi_fit(x, y, period=None):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.size < 8:
        raise ValueError("need at least 8 points for a Rabi fit")

    span = float(np.max(x) - np.min(x))

    if period is None:
        period = _dominant_period(x, y, span / 2 if span > 0 else 1.0)

    amplitude = 0.5 * float(np.max(y) - np.min(y))
    p0 = [amplitude, 1.0 / period, -np.pi / 2, span / 2, 0.0, float(np.mean(y))]

    popt, y_fit = _fit(rabi_model, x, y, p0)
    amplitude, omega, phi, t2, b, constant = popt

    result = {
        "kind": "rabi",
        "params": {
            "amplitude": round(float(amplitude), 6),
            "frequency_mhz": round(float(omega) * 1000.0, 4),
            "period_ns": round(float(1.0 / omega), 3) if omega else None,
            "phase": round(float(phi), 4),
            "t2_ns": round(float(t2), 2),
            "linear": round(float(b), 8),
            "offset": round(float(constant), 6),
        },
        "r2": round(_r2(y, y_fit), 4),
    }

    return result, y_fit


def t1_fit(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.size < 5:
        raise ValueError("need at least 5 points for a T1 fit")

    span = float(np.max(x) - np.min(x))
    p0 = [float(y[0] - y[-1]), max(span / 3.0, 1.0), float(y[-1])]

    popt, y_fit = _fit(t1_model, x, y, p0)
    amplitude, t1, constant = popt

    result = {
        "kind": "t1",
        "params": {
            "amplitude": round(float(amplitude), 6),
            "t1_ns": round(abs(float(t1)), 2),
            "offset": round(float(constant), 6),
        },
        "r2": round(_r2(y, y_fit), 4),
    }

    return result, y_fit


def t2_fit(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.size < 5:
        raise ValueError("need at least 5 points for a T2 fit")

    span = float(np.max(x) - np.min(x))
    p0 = [float(y[0] - y[-1]), max(span / 3.0, 1.0), 1.0, float(y[-1])]

    popt, y_fit = _fit(t2_model, x, y, p0)
    amplitude, t2, beta, constant = popt

    result = {
        "kind": "t2",
        "params": {
            "amplitude": round(float(amplitude), 6),
            "t2_ns": round(abs(float(t2)), 2),
            "beta": round(float(beta), 4),
            "offset": round(float(constant), 6),
        },
        "r2": round(_r2(y, y_fit), 4),
    }

    return result, y_fit


def fid_fit(x, y, period=None):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.size < 10:
        raise ValueError("need at least 10 points for a FID fit")

    span = float(np.max(x) - np.min(x))

    if period is None:
        period = _dominant_period(x, y, span / 2 if span > 0 else 1.0)

    amplitude = 0.5 * float(np.max(y) - np.min(y))
    p0 = [amplitude, 1.0 / period, 0.0, 0.0, span / 2, 2.0, 0.0, float(np.mean(y))]

    popt, y_fit = _fit(fid_model, x, y, p0)
    amplitude, omega, phi, c1, t2_star, n, b, c2 = popt

    result = {
        "kind": "fid",
        "params": {
            "amplitude": round(float(amplitude), 6),
            "frequency_mhz": round(float(omega) * 1000.0, 4),
            "period_ns": round(float(1.0 / omega), 3) if omega else None,
            "phase": round(float(phi), 4),
            "t2_star_ns": round(abs(float(t2_star)), 2),
            "n": round(float(n), 4),
            "linear": round(float(b), 8),
            "offset": round(float(c2), 6),
        },
        "r2": round(_r2(y, y_fit), 4),
    }

    return result, y_fit


FITTERS = {
    "lorentz": lorentz_fit,
    "rabi": rabi_fit,
    "t1": t1_fit,
    "t2": t2_fit,
    "fid": fid_fit,
}


def fit_curve(kind, x, y, **options):
    """
    Fit one curve.

    Returns (result, y_fit); result is a plain dict with kind, params and r2.
    """
    kind = (kind or "none").lower()

    if kind not in FITTERS:
        raise ValueError("unknown fit %r, use one of %s" % (kind, ", ".join(FITTERS)))

    fitter = FITTERS[kind]
    result, y_fit = fitter(x, y, **options)

    result["ok"] = True
    result["n_points"] = int(len(np.asarray(x)))

    return result, y_fit


def describe(result):
    """Short multi-line text summary of a fit result, drawn on the figure."""
    if not result.get("ok"):
        return "fit failed: %s" % result.get("error", "")

    lines = ["%s   r2 = %.4f" % (result.get("kind", "?"), result.get("r2", 0.0))]
    params = result.get("params") or {}
    peaks = params.get("peaks")

    if isinstance(peaks, list):
        for index, peak in enumerate(peaks, 1):
            lines.append(
                "peak%d  c = %-9.5g fwhm = %.4g"
                % (index, peak.get("center", 0.0), peak.get("fwhm", 0.0))
            )
        lines.append("background = %.4g" % params.get("background", 0.0))
    else:
        for key, value in params.items():
            if isinstance(value, (int, float)):
                lines.append("%s = %.4g" % (key, value))

    return "\n".join(lines)
