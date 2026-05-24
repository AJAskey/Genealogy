"""
census_recon.py
---------------
IPUMS Census Duplicate Reconnaissance Script
Written for Andy's Genealogy Project

What this does:
  - Reads each census-YYYY.csv from INPUT_DIR
  - Finds all records that share a SERIAL+PERNUM (duplicate candidates)
  - Writes one recon CSV per year to OUTPUT_DIR with all duplicate rows
  - Writes a summary report showing counts and SAMPLE codes found
  - Does NOT modify any source data

Run this from the command line:
  python census_recon.py

Or open it in PyCharm and hit Run.
"""

import os

import pandas as pd

# ── CONFIGURE THESE TWO PATHS ─────────────────────────────────────────────────
INPUT_DIR = r"E:\Census\IPUMS\Original"
OUTPUT_DIR = r"E:\Users\Andy\PycharmProjects\Genealogy\output"
# ─────────────────────────────────────────────────────────────────────────────

# Census years to process - add or remove years as needed
CENSUS_YEARS = [1950]

# Columns we always want to see in the duplicate report
# NAMELAST/NAMEFRST included here - if they don't exist in a file they'll be skipped
PRIORITY_COLS = [
    "YEAR", "SAMPLE", "SERIAL", "PERNUM",
    "NAMELAST", "NAMEFRST",
    "AGE", "SEX", "RACED", "BPLD",
    "RELATED", "STATEICP", "COUNTYICP", "CITY",
    "EMPSTAT", "OCC", "IND",
]


def process_year(year, summary_rows):
    """Process one census year CSV and write a duplicate report."""

    input_file = os.path.join(INPUT_DIR, f"census-{year}.csv")
    output_file = os.path.join(OUTPUT_DIR, f"recon_{year}.csv")

    if not os.path.exists(input_file):
        print(f"  [SKIP] {input_file} not found")
        summary_rows.append({
            "year": year, "status": "FILE NOT FOUND",
            "total_records": 0, "unique_serial_pernum": 0,
            "duplicate_groups": 0, "duplicate_records": 0,
            "samples_found": "", "has_names": ""
        })
        return

    print(f"\n{'=' * 60}")
    print(f"  Processing {year}...")
    print(f"  Reading {input_file}")

    # Read CSV - use low_memory=False because IPUMS files have mixed types
    df = pd.read_csv(input_file, low_memory=False, encoding='latin-1')

    total_records = len(df)
    print(f"  Total records loaded: {total_records:,}")

    # What columns do we actually have?
    available_cols = df.columns.tolist()
    has_names = "NAMELAST" in available_cols or "NAMEFRST" in available_cols

    # What SAMPLE codes are present?
    samples_found = ""
    if "SAMPLE" in available_cols:
        sample_counts = df["SAMPLE"].value_counts().to_dict()
        samples_found = " | ".join([f"{k}:{v:,}" for k, v in sorted(sample_counts.items())])
        print(f"  SAMPLE codes: {samples_found}")

    # ── Find duplicates ───────────────────────────────────────────────────────
    # A duplicate is any SERIAL+PERNUM that appears more than once
    if "SERIAL" not in available_cols or "PERNUM" not in available_cols:
        print(f"  [ERROR] SERIAL or PERNUM column missing - cannot dedup")
        summary_rows.append({
            "year": year, "status": "MISSING KEY COLUMNS",
            "total_records": total_records, "unique_serial_pernum": 0,
            "duplicate_groups": 0, "duplicate_records": 0,
            "samples_found": samples_found, "has_names": has_names
        })
        return

    # Count occurrences of each SERIAL+PERNUM combination
    dup_counts = df.groupby(["SERIAL", "PERNUM"]).size().reset_index(name="occurrence_count")
    unique_combos = len(dup_counts)

    # Pull only the groups that appear more than once
    dup_keys = dup_counts[dup_counts["occurrence_count"] > 1][["SERIAL", "PERNUM"]]
    duplicate_groups = len(dup_keys)

    if duplicate_groups == 0:
        print(f"  No duplicates found in {year}")
        summary_rows.append({
            "year": year, "status": "NO DUPLICATES",
            "total_records": total_records,
            "unique_serial_pernum": unique_combos,
            "duplicate_groups": 0, "duplicate_records": 0,
            "samples_found": samples_found, "has_names": has_names
        })
        return

    # Merge back to get all rows that are part of a duplicate group
    dup_df = df.merge(dup_keys, on=["SERIAL", "PERNUM"], how="inner")
    duplicate_records = len(dup_df)

    print(f"  Unique SERIAL+PERNUM combos : {unique_combos:,}")
    print(f"  Duplicate groups (2+ rows)  : {duplicate_groups:,}")
    print(f"  Total rows in those groups  : {duplicate_records:,}")
    print(f"  Has name columns            : {has_names}")

    # ── Build the output ──────────────────────────────────────────────────────
    # Sort so all rows for the same person are together
    dup_df = dup_df.sort_values(["SERIAL", "PERNUM", "SAMPLE"])

    # Add a column showing how many times this person appears
    dup_df = dup_df.merge(dup_counts[["SERIAL", "PERNUM", "occurrence_count"]],
                          on=["SERIAL", "PERNUM"], how="left")

    # Reorder columns: priority cols first, then everything else
    front_cols = ["occurrence_count"] + \
                 [c for c in PRIORITY_COLS if c in dup_df.columns]
    remaining = [c for c in dup_df.columns if c not in front_cols]
    dup_df = dup_df[front_cols + remaining]

    # Write output
    dup_df.to_csv(output_file, index=False)
    print(f"  Wrote: {output_file}  ({duplicate_records:,} rows)")

    summary_rows.append({
        "year": year, "status": "OK",
        "total_records": total_records,
        "unique_serial_pernum": unique_combos,
        "duplicate_groups": duplicate_groups,
        "duplicate_records": duplicate_records,
        "samples_found": samples_found,
        "has_names": has_names
    })


def main():
    # Make sure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("IPUMS Census Duplicate Reconnaissance")
    print(f"Input  : {INPUT_DIR}")
    print(f"Output : {OUTPUT_DIR}")
    print(f"Years  : {CENSUS_YEARS}")

    summary_rows = []

    for year in CENSUS_YEARS:
        process_year(year, summary_rows)

    # ── Write summary report ──────────────────────────────────────────────────
    summary_df = pd.DataFrame(summary_rows)
    summary_file = os.path.join(OUTPUT_DIR, "recon_summary.csv")
    summary_df.to_csv(summary_file, index=False)

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(summary_df.to_string(index=False))
    print(f"\nSummary written to: {summary_file}")
    print("\nDone. Open the recon_YYYY.csv files in Excel to inspect duplicates.")
    print("Filter by SERIAL to see all rows for a household.")
    print("Filter by occurrence_count=3 to find the most duplicated records.")


if __name__ == "__main__":
    main()
