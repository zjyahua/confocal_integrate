import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import win32ui
from collections import deque


count_rate = 200
# Using win GUI to choose the file
dlg = win32ui.CreateFileDialog(1)
dlg.SetOFNInitialDir('C:/Users/Desktop')
dlg.DoModal()

# Get the file dir and name
filename = dlg.GetPathName()
path = dlg.GetPathName()
print('File name = ', filename)
print('Path name = ', path)

# Load the data
with open(path, 'r') as file_raw_data:
    raw_data = file_raw_data.readlines()
    x_arr = []
    y_arr = []
    count_arr = []
    for lines in raw_data:
        data_arr = lines.split()
        x_arr.append(round(float(data_arr[0]), 3))
        y_arr.append(round(float(data_arr[1]), 3))
        count_arr.append(float(data_arr[2]))
# The raw data is:
# x_arr
# y_arr
# count_arr
# Split the data based on Y value
diff_y = np.diff(y_arr)
temp = np.where(diff_y)[0]
index_nonzero = temp + np.ones(np.size(temp), dtype=int)
index_nonzero_deq = deque(index_nonzero)
index_nonzero_deq.appendleft(0)

x_2d_arr = []
y_2d_arr = []
counts_2d_arr = []
for i in range(np.size(index_nonzero)):
    x_2d_arr.append(x_arr[index_nonzero_deq[i]:index_nonzero_deq[i + 1]])
    y_2d_arr.append(y_arr[index_nonzero_deq[i]:index_nonzero_deq[i + 1]])
    counts_2d_arr.append(count_arr[index_nonzero_deq[i]:index_nonzero_deq[i + 1]])

# Recreate the counts array
x_max_arr = []
x_min_arr = []
counts_2d_arr_plot = []

# Select and reshape counts in single line
for x_line, counts_line in zip(x_2d_arr, counts_2d_arr):

    x_min = min(x_line)
    x_max = max(x_line)

    x_reshape = np.linspace(x_min, x_max, 101)

    # Select counts based on new x_arr
    counts_arr_plot_line = []
    counts_line_arr = np.array(counts_line)
    for index in range(np.size(x_reshape) - 1):
        selected_counts = counts_line_arr[np.where((x_line >= x_reshape[index]) & (x_line <= x_reshape[index + 1]))]
        if np.size(selected_counts) == 0:
            counts_norm = 0
        else:
            counts_norm = (np.sum(selected_counts) / np.size(selected_counts)) * count_rate
        counts_arr_plot_line.append(counts_norm)

    x_min_arr.append(x_min)
    x_max_arr.append(x_max)
    counts_2d_arr_plot.append(counts_arr_plot_line)

# Create the x_arr used for plot
x_min = np.average(x_min_arr)
x_max = np.average(x_max_arr)

x_arr_plot = np.linspace(x_min, x_max, 100)

# Create the y_arr used for plot
y_arr_plot = np.array(y_2d_arr)[:, 0]

# Change counts_arr into array
counts_2d_arr_plot = np.array(counts_2d_arr_plot)

# Plot
fig = plt.figure(figsize=(12, 10))
plt.pcolormesh(x_arr_plot, y_arr_plot, counts_2d_arr_plot, shading='nearest')
plt.xlim(np.min(x_arr_plot), np.max(x_arr_plot))
plt.ylim(np.min(y_arr_plot), np.max(y_arr_plot))
plt.colorbar()
plt.xlabel('X Axis')
plt.ylabel('Y Axis')
plt.show()

