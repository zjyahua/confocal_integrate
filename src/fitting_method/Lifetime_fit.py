from scipy.optimize import curve_fit
import numpy as np
from scipy.fft import fft, ifft

def Lifetime_fitting(t,I_fluor,init_vals=[1, 0.5, 5, 26, 65.91, 5.202, 0.1]):
    x0 = np.array(init_vals)
    lb = [0, 0, 1, 10, 0, 1, 0]
    ub = [np.inf, 1, 10, 100, 100, 10, np.inf]
    popt, pcov =curve_fit(Lifetime_fitting_model, t, I_fluor, p0=x0,bounds=(lb,ub), maxfev=2000, method='trf')
    y_fit = Lifetime_fitting_model(t, *popt)
    return popt, y_fit

def Lifetime_fitting_model(t, a1, a2, b1, b2, c1, c2, constant):
    return np.real(ifft(fft(lifetime_fun(t, a1, a2, b1, b2, constant))*fft(ideal_response_fun(t, c1, c2))))

def lifetime_fun(t, a1, a2, b1, b2, constant):
    return  constant + a1 * a2 * np.exp(-t / b1) + a1 * (1 - a2) * np.exp(-t / b2)

def ideal_response_fun(t, a1, b1):
    return np.exp(-((t - a1) / b1)**2)