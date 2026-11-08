"""
This program uses pyuic to transform the "xxx.ui" file into "xxx.py" file.
"""
import subprocess
import os
from os import path

directory = path.dirname(path.abspath(__file__))

source_dir = path.join(directory, "ui_files")
target_dir = path.join(directory, "uipy")

for root, dirs, files in os.walk(source_dir):
    for file in files:
        if file.endswith('.ui'):
            # get the relative path of the .ui file from the source_dir
            relative_path = os.path.relpath(root, source_dir)

            # construct the output directory in the target_dir
            output_dir = os.path.join(target_dir, relative_path)
            os.makedirs(output_dir, exist_ok=True)

            # create __init__.py file
            init_file = os.path.join(output_dir, '__init__.py')
            if not os.path.exists(init_file):
                open(init_file, 'a').close()

            # construct the input and output file paths
            input_file = os.path.join(root, file)
            output_file = os.path.join(output_dir, file.replace('.ui', '.py'))

            # call pyuic5 to generate the .py file
            subprocess.run(['pyuic5', '-x', input_file, '-o', output_file])