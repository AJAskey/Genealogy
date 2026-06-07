import argparse
import os
import re
import sys


def find1(w1, line):
    ret = False
    m1 = re.compile(w1, re.IGNORECASE)
    f1 = m1.search(line)
    if f1:
        main_logger.debug(f"\t\tfind matched: '{w1}' in line: {line}")
        ret = True
    return ret


def find2(w1, w2, line):
    ret = False
    m1 = re.compile(w1, re.IGNORECASE)
    f1 = m1.search(line)
    if f1:
        m2 = re.compile(w2, re.IGNORECASE)
        f2 = m2.search(line)
        if f2: ret = True
        main_logger.debug(f"\t\tfind matched: '{w1}' and '{w2}' in line: {line}")
    return ret

    # ==============================================================================
    # MAIN
    # ==============================================================================


script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.abspath(os.path.join(script_dir, '..'))
if python_dir not in sys.path:
    sys.path.append(python_dir)

from utils import gen_logging


def main():
    main_logger = gen_logging.setup_logging(logger_name="ASKEYS")

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

    main_logger.info(f"Project Root is: {project_root}")

    input_directory = args.dir
    output_file = args.out

    if not os.path.exists(input_directory):
        main_logger.info(f"ERROR: The input directory '{input_directory}' does not exist!")
        exit(1)

    # Compile the regex pattern once for speed.
    search_pattern = re.compile(r"\b(askey|\baskay|erskine)\b", re.IGNORECASE)

    # Pattern for filename checking
    filename_pattern = re.compile(r"(askey|erskine)", re.IGNORECASE)
    filename_not_pattern = re.compile(r"(caskey|mccaskey)", re.IGNORECASE)

    # Define exclusions as a clean Python list so it's super easy to manage
    name_pairs = [
        ("caskey", "caskey"),
        ("erskine", "abbott"),
        ("erskine", "w."),
        ("erskine", "ruth"),
        ("erskine", "hume"),
        ("erskine", "cruse"),
        ("erskine", "MAXWELL"),
        ("erskine", "baskin"),
        ("erskine", "black"),
        ("erskine", "bynoe"),
        ("erskine", "carlisle"),
        ("erskine", "cittings"),
        ("erskine", "cochran"),
        ("erskine", "davis"),
        ("erskine", "LANDS"),
        ("erskine", "howard"),
        ("erskine", "Trammell"),
        ("erskine", "dean"),
        ("erskine", "Crowe"),
        ("erskine", "Holleman"),
        ("erskine", "young"),
        ("erskine", "gant"),
        ("erskine", "KENNAMER"),
        ("erskine", "ebenezer"),
        ("erskine", "edgerton"),
        ("erskine", "gillock"),
        ("erskine", "gordon"),
        ("erskine", "hadlock"),
        ("erskine", "hamilton"),
        ("erskine", "hazard"),
        ("erskine", "HILYER"),
        ("erskine", "caine"),
        ("erskine", "Davenport"),
        ("erskine", "doss"),
        ("erskine", "mullins"),
        ("erskine", "holt"),
        ("erskine", "russel"),
        ("erskine", "hewitt"),
        ("erskine", "holbert"),
        ("erskine", "johnston"),
        ("erskine", "macoubray"),
        ("erskine", "mansfield"),
        ("erskine", "martin"),
        ("erskine", "mckinlay"),
        ("erskine", "miles"),
        ("erskine", "miller"),
        ("erskine", "rakestraw"),
        ("erskine", "reese"),
        ("erskine", "robertson"),
        ("erskine", "scott"),
        ("erskine", "scott"),
        ("erskine", "solomon"),
        ("erskine", "suber"),
        ("erskine", "thompson"),
        ("erskine", "turner"),
        ("erskine", "tyrone"),
        ("erskine", "wade"),
        ("erskine", "rogers"),
        ("erskine", "mcdaniel"),

        ("erskine", "westinghouse"),
        ("erskine", "wrightson"),
    ]

    matching_txt_files = []
    file_count = 0

    with open(output_file, "w", encoding="utf-8", errors="ignore") as fo:
        fo.write("CONTEXT Match or FULL FILE Match: askey OR askay OR erskine\n\n")

        # os.walk automatically and recursively traverses all subdirectories
        for root, _, files in os.walk(input_directory):
            for file in files:
                main_logger.debug(f"Examining file: {file}")
                if file.lower().endswith(".txt"):
                    file_path = os.path.join(root, file)
                    main_logger.debug(f"\tProcessing file: {file_path}")

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
                        if filename_pattern.search(file) and not filename_notpattern.search(file):
                            main_logger.info(f"[FULL FILE] {file_path}")

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
                                found = False
                                for w1, w2 in name_pairs:
                                    found = find2(w1, w2, line.strip())
                                    if found:
                                        break

                                if search_pattern.search(line) and not found:
                                    match_found = True
                                    # Add previous 3 lines and following 9 lines (context)
                                    start_idx = max(0, i - 3)
                                    end_idx = min(len(lines), i + 10)  # +10 because range is exclusive
                                    for j in range(start_idx, end_idx):
                                        lines_to_print.add(j)

                            # Outdented one tab so it only writes once per file!
                            if match_found:
                                main_logger.info(f"[CONTEXT]   {file_path}")
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
                    except Exception as e:
                        main_logger.error(f"Error processing {file_path}: {e}")

        main_logger.info(
            f"\nSuccess! Concatenated {file_count} files (Askey & Erskine) into {output_file} ready for NotebookLLM.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="ASKEYS")
    main()
