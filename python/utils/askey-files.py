import argparse
import os
import re

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == '__main__':
    # 1. Get the absolute path of the directory where this specific script lives
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 2. Step up two folder levels ('..') to reach the main project root
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))

    parser = argparse.ArgumentParser(description="Concatenate state archive files for NotebookLLM")
    parser.add_argument("--dir", default=r"E:\Data\Genealogy_Data\Ingestion",
                        help="Input directory to search")
    parser.add_argument("--out", default=os.path.join(project_root, "output", "usgw_archives-askeyerskine.txt"),
                        help="Output file name")
    args = parser.parse_args()

    print(f"Project Root is: {project_root}")

    input_directory = args.dir
    output_file = args.out

    if not os.path.exists(input_directory):
        print(f"ERROR: The input directory '{input_directory}' does not exist!")
        exit(1)

    # Compile the regex pattern once for speed.
    search_pattern = re.compile(r"\b(askey|erskine)\b", re.IGNORECASE)

    # Pattern for filename checking
    filename_pattern = re.compile(r"(askey|erskine)", re.IGNORECASE)

    # Define exclusions as a clean Python list so it's super easy to manage
    excluded_names = [
        r"hazard[\s_]*erskine",
        r"erskine[\s_]*thompson",
        r"erskine[\s_]*hazard",
        r"hazard[\s_]*erskine",
        r"Wrightson[\s_]*erskine",
        r"erskine[\s_]*Tyrone",
        r"Robertson[\s_]*Erskine",
        r"Mansfield[\s_]*Erskine",
        r"HADLOCK[\s_]*Erskine",
        r"john[\s_]*Erskine",
        r"Edgerton[\s_]*Erskine",
        r"ERSKINE W.[\s_]*JOHNSTON",
        r"Johnston,[\s_]*ERSKINE",
        r"MCKINLAY,[\s_]*ERSKINE",
        r"ERSKINE[\s_]*Mansfield"

    ]

    # Automatically join the list with the OR operator (|) and wrap in parentheses
    excl_str = r"(" + r"|".join(excluded_names) + r")"
    exclude_pattern = re.compile(excl_str, re.IGNORECASE)

    matching_txt_files = []
    file_count = 0

    with open(output_file, "w", encoding="utf-8", errors="ignore") as fo:
        fo.write("CONTEXT Match or FULL FILE Match: askey OR erskine\n\n")

        # os.walk automatically and recursively traverses all subdirectories
        for root, _, files in os.walk(input_directory):
            for file in files:
                if file.lower().endswith(".txt"):
                    file_path = os.path.join(root, file)

                    # Dynamically strip the base directory so the output labels are always clean
                    sub_path = file_path.replace(input_directory, "")
                    if sub_path.startswith("\\") or sub_path.startswith("/"):
                        sub_path = sub_path[1:]
                    sub_path_len = len(sub_path) + 3

                    # errors='ignore' prevents crashes if a scraped text file has weird encoding
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f_in:
                            lines = f_in.readlines()

                        # CONDITION 1: Does the filename contain Askey or Erskine?
                        if filename_pattern.search(file) and not exclude_pattern.search(file):
                            print(f"[FULL FILE] {file_path}")

                            header_str = f"\n{'=' * sub_path_len}\n  .{sub_path}\n  (FULL FILE MATCH)\n{'=' * sub_path_len}\n"
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
                                if search_pattern.search(line) and not exclude_pattern.search(line):
                                    match_found = True
                                    # Add previous 3 lines and following 9 lines (context)
                                    start_idx = max(0, i - 3)
                                    end_idx = min(len(lines), i + 10)  # +10 because range is exclusive
                                    for j in range(start_idx, end_idx):
                                        lines_to_print.add(j)

                            # Outdented one tab so it only writes once per file!
                            if match_found:
                                print(f"[CONTEXT]   {file_path}")
                                header_str = f"\n{'=' * sub_path_len}\n  .{sub_path}\n  (CONTEXT MATCH)\n{'=' * sub_path_len}\n"
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
