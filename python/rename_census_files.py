"""
rename_census_files.py
Reads IPUMS csv files, detects year from YEAR column, renames to census-YYYY.csv
"""

import csv
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
CSV_FOLDER = r"D:\Data\Genealogy_Data\CSV"
DRY_RUN = False  # Start True to preview, then change to False to rename


# ──────────────────────────────────────────────────────────────────────────


def detect_year(filepath: Path) -> str | None:
    """
    Reads the header of a CSV file to find the 'YEAR' column, 
    and returns the first valid 4-digit year found in the data rows.
    """
    # Open the file with utf-8 encoding, replacing any invalid characters
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)

        # If the file is empty or has no headers, return None
        if not reader.fieldnames:
            return None

        # Case-insensitive search for a column named 'YEAR'
        year_col = next(
            (c for c in reader.fieldnames if c.strip().upper() == "YEAR"), None
        )

        # If no 'YEAR' column is found, log a message and return None
        if not year_col:
            print(f"  No YEAR column found. Columns: {reader.fieldnames[:8]}")
            return None

        # Iterate through the rows to find the first valid 4-digit year
        for row in reader:
            val = row.get(year_col, "").strip()
            if val.isdigit() and len(val) == 4:
                return val

    return None


def main():
    """
    Main execution function. Scans the configured folder for CSV files,
    detects the year for each, and renames them accordingly.
    """
    folder = Path(CSV_FOLDER)

    # Get a sorted list of all CSV files in the folder
    files = sorted(folder.glob("usa*.csv"))
    print(f"Found {len(files)} CSV files")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n")

    # Process each CSV file
    for filepath in files:
        print(f"{filepath.name}")

        # Attempt to detect the year from the file's contents
        year = detect_year(filepath)
        if not year:
            print(f"  Could not detect year -- skipping\n")
            continue

        # Construct the new filename based on the detected year
        target = filepath.parent / f"census-{year}.csv"

        # Prevent overwriting an existing file
        if target.exists() and target != filepath:
            print(f"  SKIP -- census-{year}.csv already exists\n")
            continue

        print(f"  --> census-{year}.csv")

        # Perform the rename if not in dry run mode
        if not DRY_RUN:
            filepath.rename(target)
            print(f"  Renamed.\n")
        else:
            print(f"  (dry run)\n")


if __name__ == "__main__":
    main()
