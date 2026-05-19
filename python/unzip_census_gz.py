"""
unzip_census_gz.py
Finds all .csv.gz files and extracts them to .csv in the same folder.
"""

import gzip
import shutil
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────
GZ_FOLDER = r"E:\Census\IPUMS\Downloads"
DELETE_GZ = False  # True = delete the .gz after successful extract
DRY_RUN = False  # Start True to preview, then flip to False


# ──────────────────────────────────────────────────────────────────────────


def main():
    folder = Path(GZ_FOLDER)
    gz_files = sorted(folder.glob("*.gz"))

    if not gz_files:
        print("No .gz files found.")
        return

    print(f"Found {len(gz_files)} .gz file(s)")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n")

    for gz_path in gz_files:
        # Strip the .gz to get the output name  e.g. usa_00066.csv.gz --> usa_00066.csv
        out_path = gz_path.with_suffix("")

        print(f"{gz_path.name}")
        print(f"  --> {out_path.name}")

        if out_path.exists():
            print(f"  SKIP -- {out_path.name} already exists\n")
            continue

        if DRY_RUN:
            print(f"  (dry run)\n")
            continue

        # Extract
        with gzip.open(gz_path, "rb") as f_in:
            with open(out_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        print(f"  Extracted OK  ({out_path.stat().st_size / 1_073_741_824:.1f} GB)")

        if DELETE_GZ:
            gz_path.unlink()
            print(f"  Deleted {gz_path.name}")

        print()


if __name__ == "__main__":
    main()
