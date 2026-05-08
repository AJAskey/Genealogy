"""
rename_census_files.py
Reads IPUMS csv files, detects year from YEAR column, renames to census-YYYY.csv
"""

import csv
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
CSV_FOLDER = r"E:\Census\IPUMS\Downloads"
DRY_RUN    = False   # Start True to preview, then change to False to rename
# ──────────────────────────────────────────────────────────────────────────


def detect_year(filepath: Path) -> str | None:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return None
        year_col = next(
            (c for c in reader.fieldnames if c.strip().upper() == "YEAR"), None
        )
        if not year_col:
            print(f"  No YEAR column found. Columns: {reader.fieldnames[:8]}")
            return None
        for row in reader:
            val = row.get(year_col, "").strip()
            if val.isdigit() and len(val) == 4:
                return val
    return None


def main():
    folder = Path(CSV_FOLDER)
    files  = sorted(folder.glob("*.csv"))
    print(f"Found {len(files)} CSV files")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n")

    for filepath in files:
        print(f"{filepath.name}")
        year = detect_year(filepath)
        if not year:
            print(f"  Could not detect year -- skipping\n")
            continue

        target = filepath.parent / f"census-{year}.csv"

        if target.exists() and target != filepath:
            print(f"  SKIP -- census-{year}.csv already exists\n")
            continue

        print(f"  --> census-{year}.csv")
        if not DRY_RUN:
            filepath.rename(target)
            print(f"  Renamed.\n")
        else:
            print(f"  (dry run)\n")


if __name__ == "__main__":
    main()