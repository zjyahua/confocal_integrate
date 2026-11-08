"""
Created on Jul 7, 2021

This File is for data processing.

@author: Linjie
"""

import os

import numpy as np
import win32ui
import matplotlib.pyplot as plt
from collections import deque

calculate_loop_limit = 500

# Using win GUI to choose the file
# Set the init path to '..\Cache\Data'

dir_all_data = os.path.join(os.path.dirname("__file__"), os.path.pardir, 'Cache/Data')
dlg = win32ui.CreateFileDialog(1)
dlg.SetOFNInitialDir(dir_all_data)
dlg.DoModal()
# Get the file dir and name
filename = dlg.GetPathName()
path = dlg.GetPathName()

with open(path, 'r') as file_raw_data:
    raw_data = file_raw_data.readlines()
    sig_all = []
    ref_all = []
    time_freq_data_all = []
    loop_all = []
    settings = raw_data[1].split()
    for lines in raw_data[3:]:
        data_arr = lines.split()
        sig_all.append(int(float(data_arr[0])))
        ref_all.append(int(float(data_arr[1])))
        time_freq_data_all.append(float(data_arr[2]))
        loop_all.append(int(float(data_arr[3])))

loop_num = int(settings[2])
point_num = int(settings[6])

modify = []
for i in range(np.size(ref_all)):
    modify.append(sig_all[i]/ref_all[i])

modify_split_by_loop = np.reshape(modify, (loop_num, point_num))

time_freq_one_loop = time_freq_data_all[:point_num]

mod_ave = list(np.average(modify_split_by_loop[:calculate_loop_limit], axis=0))
mod_std = list(np.std(modify_split_by_loop[:calculate_loop_limit], axis=0))


plt.figure(figsize=(15, 10))
# plt.errorbar(x=time_freq_one_loop, y=ref_ave, yerr=ref_std, label='Ref')
# plt.errorbar(x=time_freq_one_loop, y=sig_ave, yerr=sig_std, label='Sig')


plt.plot(time_freq_one_loop, mod_ave, label='Data')
# plt.xlabel('Time(ns)')
plt.xlabel('Freq(MHz)')
plt.ylabel('Counts(Normalized)')
plt.title('CW-ODMR')
plt.legend()
plt.show()
