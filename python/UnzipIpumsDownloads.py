"""
-----------------------------------
File: UnzipIpumsDownloads.py

Summary:

Design:

Inputs:

Outputs:

Comments for G:

--------------------------------

"""
import zipfile

# Path to the zip file and the target directory
zip_file_path = 'example.zip'
target_directory = 'extracted_folder'

# Using a context manager ensures the file is closed automatically
with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
    zip_ref.extractall(target_directory)

# save as UTF-8
with open(input_csv, mode='r', errors='replace') as infile:
    reader = csv.DictReader(infile, delimiter=',')

    for row in reader:
        continue