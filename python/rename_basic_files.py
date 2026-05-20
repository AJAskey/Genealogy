"""
rename_basic_files.py
Finds all .txt files, reads the year from the first line, renames to basic-YYYY.txt
"""

import re
from pathlib import Path

# ── Configuration ──────────────────────
TXT_FOLDER = r"E:\temp\Downloads\basic-all.txt"
DRY_RUN = False  # Start True to preview, then flip to False


# ──────────────────────────────────────────────────────────────────────────


def detect_year(filepath: Path) -> str | None:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        first_line = f.readline()

    # Looking for a 4-digit year in the first line
    # e.g. "Description: 1860 genealogy with samples"
    match = re.search(r"\b(1[89]\d\d|20\d\d)\b", first_line)
    if match:
        return match.group(1)

    print(f"  No year found in first line: {first_line.strip()}")
    return None


def main():
    folder = Path(TXT_FOLDER)
    txt_files = sorted(folder.glob("usa*.txt"))

    if not txt_files:
        print("No .txt files found.")
        return

    print(f"Found {len(txt_files)} .txt file(s)")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n")

    for filepath in txt_files:
        print(f"{filepath.name}")
        year = detect_year(filepath)

        if not year:
            print(f"  Could not detect year -- skipping\n")
            continue

        target = filepath.parent / f"basic-{year}.txt"

        if target.exists() and target != filepath:
            print(f"  SKIP -- basic-{year}.txt already exists\n")
            continue

        print(f"  --> basic-{year}.txt")

        if not DRY_RUN:
            filepath.rename(target)
            print(f"  Renamed.\n")
        else:
            print(f"  (dry run)\n")


if __name__ == "__main__":
    main()
