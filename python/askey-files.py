"""
-----------------------------------
File: askey-files.py

Summary:

Design:

Inputs:

Outputs:

Comments for G:

--------------------------------

"""

import argparse
import os
import re

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Concatenate state archive files for NotebookLLM")
    parser.add_argument("--dir", default=r"E:\Data\Genealogy_Data\Ingestion\usgw_archives_pa",
                        help="Input directory to search")
    parser.add_argument("--out", default=r"../output/pa_archives.out", help="Output file name")
    args = parser.parse_args()

    input_directory = args.dir
    output_file = args.out

    # Compile the regex pattern once for speed.
    # \b(askey|erskine)\b looks for either Askey OR Erskine as a whole word.
    search_pattern = re.compile(r"\b(askey|erskine)\b", re.IGNORECASE)

    # Pattern for filename checking (no word boundaries, in case it's named 'askeyfamily.txt')
    filename_pattern = re.compile(r"(askey|erskine)", re.IGNORECASE)

    matching_txt_files = []
    file_count = 0

    with open(output_file, "w", encoding="utf-8", errors="ignore") as fo:

        fo.write(f"CONTEX Match or FULL FILE Match: askey OR erskine\n\n")

        # os.walk automatically and recursively traverses all subdirectories
        for root, _, files in os.walk(input_directory):
            for file in files:
                if file.lower().endswith(".txt"):
                    file_path = os.path.join(root, file)
                    # errors='ignore' prevents crashes if a scraped text file has weird encoding
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f_in:
                            lines = f_in.readlines()

                        # CONDITION 1: Does the filename contain Askey or Erskine?
                        if filename_pattern.search(file):
                            print(f"[FULL FILE] {file_path}")
                            subpath = file_path[33:]
                            header_str = f"\n{'=' * 60}\n  {subpath}\n  (FULL FILE MATCH)\n{'=' * 60}\n"
                            fo.write(header_str)
                            for line in lines:
                                fo.write(line)
                            fo.write("\n")
                            file_count += 1

                        # CONDITION 2: If not, grep the contents line by line
                        else:
                            lines_to_print = set()
                            match_found = False

                            for i, line in enumerate(lines):
                                if search_pattern.search(line):
                                    match_found = True
                                    # Add previous 3 lines and following 9 lines (context)
                                    start_idx = max(0, i - 3)
                                    end_idx = min(len(lines), i + 10)  # +10 because range is exclusive
                                    for j in range(start_idx, end_idx):
                                        lines_to_print.add(j)

                            # Outdented one tab so it only writes once per file!
                            if match_found:
                                print(f"[CONTEXT]   {file_path}")
                                header_str = f"\n{'=' * 60}\n  {file_path}\n  (CONTEXT MATCH)\n{'=' * 60}\n"
                                fo.write(header_str)

                                sorted_indices = sorted(list(lines_to_print))
                                last_idx = -2
                                for idx in sorted_indices:
                                    # Insert a divider if we skipped lines between matches (like grep's '--')
                                    if last_idx != -2 and idx > last_idx + 1:
                                        fo.write("---\n")
                                    fo.write(lines[idx])
                                    last_idx = idx

                                fo.write("\n")
                                file_count += 1

                    except Exception:
                        pass

    print(f"\nSuccess! Concatenated {file_count} files (Askey & Erskine) into {output_file} ready for NotebookLLM.")
