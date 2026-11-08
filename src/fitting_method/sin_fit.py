from scipy.optimize import curve_fit
import numpy as np
from scipy.fft import fft, ifft

"""
input parameter unit
time ns
frequency kHz
"""
def sin_fun(t, f, a1, a2, b1, constant):
    return  a1 * t + constant + a2 * np.sin(2 * np.pi * f * t * 1e-6 + b1 / 180 * np.pi)

def sin_fit(t, I_fluor, f, init_vals=[100, 0, 40, 0, 100]):
    x0 = np.array(init_vals)
    lb = [f - 1,-np.inf, 0, -180, 0]
    ub = [f + 1,np.inf, np.inf, 180, np.inf]
    popt, pcov = curve_fit(sin_fun, t, I_fluor, p0=x0, bounds=(lb, ub), maxfev=5000, method='trf')
    y_fit = sin_fun(t, *popt)
    return popt, y_fit