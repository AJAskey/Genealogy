"""
census_merge.py
---------------
IPUMS Census Duplicate Merge Script
Andy's Genealogy Project

What this does:
  - Reads each census-YYYY.csv from INPUT_DIR one year at a time
  - Groups records by SERIAL+PERNUM to find duplicates
  - Merges clean duplicates (occurrence_count=2, same person)
  - Passes through unique records unchanged
  - Flags messy records to errata log without touching them
  - Writes one clean output CSV per year
  - Writes a running errata.csv log of all problems found

Merge Rules:
  Rule 1 - Names    : Always take from sample record, never 100% full count
  Rule 2 - Blanks   : If field is blank in full count but populated in sample, take sample value
  Rule 3 - Conflicts: When both records have different values, log to errata, keep both records
  Rule 4 - Count=1  : Clean record, pass straight through unchanged
  Rule 5 - Count=2  : Attempt merge if same person (name+age check), otherwise errata
  Rule 6 - Count=3+ : Too complex to auto-merge, keep all records, log to errata

Identity Check:
  Two records are considered the SAME person if:
    - Names match (or one/both are blank)
    - Age is within AGE_TOLERANCE years
  Otherwise they are flagged as a PERNUM_COLLISION (two different people, IPUMS error)

Run from PyCharm or command line:
  python census_merge.py
"""

import os
from datetime import datetime

import numpy as np
import pandas as pd

# ── CONFIGURE THESE PATHS ─────────────────────────────────────────────────────
INPUT_DIR = r"E:\Census\IPUMS\Original"
OUTPUT_DIR = r"E:\Users\Andy\PycharmProjects\Genealogy\output"
# ─────────────────────────────────────────────────────────────────────────────

# Census years to process
CENSUS_YEARS = [1850]  # , 1860, 1870, 1880, 1900, 1910, 1920, 1930, 1940]
# Note: 1950 excluded until chunked reader is built for memory issues

# How many years difference in age before we consider two records different people
AGE_TOLERANCE = 3

# The 100% full count sample codes by year
# These are the BASE records - sample records get merged INTO these
FULLCOUNT_SAMPLES = {
    1850: 185002,
    1860: 186003,
    1870: 187003,
    1880: 188003,
    1900: 190004,
    1910: 191004,
    1920: 192003,
    1930: 193004,
    1940: 194002,
    1950: 195002,
}

# Name columns - present in some years, not others
NAME_COLS = ["NAMELAST", "NAMEFRST", "NAMEFRST2"]

# Fields where the sample data is preferred over full count when both are populated
# (carefully transcribed oversamples tend to be more accurate on these)
PREFER_SAMPLE_COLS = NAME_COLS + ["BPL", "BPLD", "MTONGUE", "MTONGUED"]

# Errata category codes
CAT_NAME_CONFLICT = "NAME_CONFLICT"  # Same SERIAL+PERNUM, different names, merged anyway
CAT_AGE_CONFLICT = "AGE_CONFLICT"  # Same SERIAL+PERNUM, age differs beyond tolerance
CAT_PERNUM_COLLISION = "PERNUM_COLLISION"  # Clearly two different people, kept both
CAT_FIELD_CONFLICT = "FIELD_CONFLICT"  # Non-name field disagrees between records
CAT_COMPLEX_GROUP = "COMPLEX_GROUP"  # occurrence_count >= 3, kept all records as-is
CAT_NO_FULLCOUNT = "NO_FULLCOUNT"  # Duplicate group has no full count record


def is_blank(value):
    """Return True if a value is blank, null, or a whitespace string."""
    if value is None:
        return True
    if isinstance(value, float) and np.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def names_match(name1, name2):
    """
    Return True if two name values are considered matching.
    Blank names are considered a wildcard match (we can't tell, so don't flag).
    """
    if is_blank(name1) or is_blank(name2):
        return True  # One or both blank - can't confirm mismatch
    return str(name1).strip().upper() == str(name2).strip().upper()


def ages_match(age1, age2, tolerance=AGE_TOLERANCE):
    """Return True if two age values are within tolerance of each other."""
    try:
        return abs(int(age1) - int(age2)) <= tolerance
    except (ValueError, TypeError):
        return True  # Can't compare, don't flag


def same_person(row1, row2, available_cols):
    """
    Determine if two records are the same person.
    Checks name match AND age match.
    Returns (is_same, reason_if_not)
    """
    # Check last name
    if "NAMELAST" in available_cols:
        if not names_match(row1.get("NAMELAST"), row2.get("NAMELAST")):
            return False, CAT_PERNUM_COLLISION

    # Check first name
    if "NAMEFRST" in available_cols:
        if not names_match(row1.get("NAMEFRST"), row2.get("NAMEFRST")):
            return False, CAT_PERNUM_COLLISION

    # Check age
    if "AGE" in available_cols:
        if not ages_match(row1.get("AGE"), row2.get("AGE")):
            return False, CAT_AGE_CONFLICT

    return True, None


def merge_two_records(base_row, sample_row, available_cols, errata_rows,
                      year, serial, pernum):
    """
    Merge a full count record (base) with a sample record.
    Returns the merged record as a dict.
    Logs any field conflicts to errata_rows.
    """
    merged = base_row.copy()
    field_conflicts = []

    for col in available_cols:
        base_val = base_row.get(col)
        sample_val = sample_row.get(col)

        base_blank = is_blank(base_val)
        sample_blank = is_blank(sample_val)

        # Rule 1 & preferred cols: always take from sample if available
        if col in PREFER_SAMPLE_COLS:
            if not sample_blank:
                merged[col] = sample_val
            continue

        # Rule 2: fill blanks from sample
        if base_blank and not sample_blank:
            merged[col] = sample_val
            continue

        # Rule 3: both have values - check for conflict
        if not base_blank and not sample_blank:
            if col not in ["SAMPLE", "CLUSTER", "STRATA", "HHWT", "PERWT",
                           "SLPERNUM", "VERSIONHIST"]:
                # These cols are expected to differ between samples - skip them
                try:
                    if str(base_val).strip() != str(sample_val).strip():
                        field_conflicts.append(
                            f"{col}:{base_val}→{sample_val}"
                        )
                except Exception:
                    pass

    # Log field conflicts to errata if any found
    if field_conflicts:
        errata_rows.append({
            "year": year,
            "serial": serial,
            "pernum": pernum,
            "category": CAT_FIELD_CONFLICT,
            "occurrence": 2,
            "sample_codes": f"{base_row.get('SAMPLE')}+{sample_row.get('SAMPLE')}",
            "namelast": base_row.get("NAMELAST", ""),
            "namefrst": base_row.get("NAMEFRST", ""),
            "age": base_row.get("AGE", ""),
            "detail": " | ".join(field_conflicts),
            "disposition": "MERGED_WITH_CONFLICTS"
        })

    return merged


def process_year(year, errata_rows):
    """Process one census year - merge duplicates and write clean output."""

    input_file = os.path.join(INPUT_DIR, f"census-{year}.csv")
    output_file = os.path.join(OUTPUT_DIR, f"clean_{year}.csv")

    if not os.path.exists(input_file):
        print(f"  [SKIP] {input_file} not found")
        return

    print(f"\n{'=' * 60}")
    print(f"  Processing {year}...")

    df = pd.read_csv(input_file, low_memory=False, encoding='latin-1')
    total_in = len(df)
    print(f"  Loaded {total_in:,} records")

    available_cols = df.columns.tolist()
    fullcount_code = FULLCOUNT_SAMPLES.get(year)

    # Convert to dict of lists for faster processing
    # Group by SERIAL+PERNUM
    groups = df.groupby(["SERIAL", "PERNUM"])

    output_records = []
    count_passthrough = 0
    count_merged = 0
    count_collision = 0
    count_complex = 0

    for (serial, pernum), group in groups:
        rows = group.to_dict("records")
        n = len(rows)

        # ── Case 1: Only one record - clean passthrough ───────────────────────
        if n == 1:
            output_records.append(rows[0])
            count_passthrough += 1
            continue

        # ── Case 2: Three or more - too complex, keep all, log to errata ─────
        if n >= 3:
            for r in rows:
                output_records.append(r)
            count_complex += 1
            sample_codes = "+".join([str(r.get("SAMPLE", "?")) for r in rows])
            errata_rows.append({
                "year": year,
                "serial": serial,
                "pernum": pernum,
                "category": CAT_COMPLEX_GROUP,
                "occurrence": n,
                "sample_codes": sample_codes,
                "namelast": rows[0].get("NAMELAST", ""),
                "namefrst": rows[0].get("NAMEFRST", ""),
                "age": rows[0].get("AGE", ""),
                "detail": f"{n} records for same SERIAL+PERNUM",
                "disposition": "KEPT_ALL"
            })
            continue

        # ── Case 3: Exactly two records ───────────────────────────────────────
        # Identify which is the full count and which is the sample
        if fullcount_code:
            base_rows = [r for r in rows if r.get("SAMPLE") == fullcount_code]
            sample_rows = [r for r in rows if r.get("SAMPLE") != fullcount_code]
        else:
            base_rows = [rows[0]]
            sample_rows = [rows[1]]

        if not base_rows:
            # No full count record in this pair - unusual, log it
            for r in rows:
                output_records.append(r)
            sample_codes = "+".join([str(r.get("SAMPLE", "?")) for r in rows])
            errata_rows.append({
                "year": year,
                "serial": serial,
                "pernum": pernum,
                "category": CAT_NO_FULLCOUNT,
                "occurrence": 2,
                "sample_codes": sample_codes,
                "namelast": rows[0].get("NAMELAST", ""),
                "namefrst": rows[0].get("NAMEFRST", ""),
                "age": rows[0].get("AGE", ""),
                "detail": "No full count record found in duplicate pair",
                "disposition": "KEPT_ALL"
            })
            continue

        base_row = base_rows[0]
        sample_row = sample_rows[0]

        # Check if these are actually the same person
        is_same, reason = same_person(base_row, sample_row, available_cols)

        if not is_same:
            # Different people with same SERIAL+PERNUM - IPUMS error
            # Keep both records, log to errata
            output_records.append(base_row)
            output_records.append(sample_row)
            count_collision += 1
            errata_rows.append({
                "year": year,
                "serial": serial,
                "pernum": pernum,
                "category": reason,
                "occurrence": 2,
                "sample_codes": f"{base_row.get('SAMPLE')}+{sample_row.get('SAMPLE')}",
                "namelast": f"{base_row.get('NAMELAST', '')} vs {sample_row.get('NAMELAST', '')}",
                "namefrst": f"{base_row.get('NAMEFRST', '')} vs {sample_row.get('NAMEFRST', '')}",
                "age": f"{base_row.get('AGE', '')} vs {sample_row.get('AGE', '')}",
                "detail": "Different people assigned same SERIAL+PERNUM",
                "disposition": "KEPT_BOTH"
            })
            continue

        # Same person - merge them
        merged = merge_two_records(base_row, sample_row, available_cols,
                                   errata_rows, year, serial, pernum)
        output_records.append(merged)
        count_merged += 1

    # ── Write clean output ────────────────────────────────────────────────────
    out_df = pd.DataFrame(output_records, columns=available_cols)
    out_df.to_csv(output_file, index=False, encoding='latin-1')

    total_out = len(out_df)
    print(f"  Passthroughs (unique)  : {count_passthrough:,}")
    print(f"  Merged (clean dupes)   : {count_merged:,}")
    print(f"  Collisions (kept both) : {count_collision:,}")
    print(f"  Complex groups (3+)    : {count_complex:,}")
    print(f"  Records in             : {total_in:,}")
    print(f"  Records out            : {total_out:,}")
    print(f"  Reduction              : {total_in - total_out:,}")
    print(f"  Wrote: {output_file}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("IPUMS Census Merge Script")
    print(f"Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Input   : {INPUT_DIR}")
    print(f"Output  : {OUTPUT_DIR}")
    print(f"Years   : {CENSUS_YEARS}")

    errata_rows = []

    for year in CENSUS_YEARS:
        process_year(year, errata_rows)

        # Write errata after each year so you have it even if script crashes
        if errata_rows:
            errata_df = pd.DataFrame(errata_rows)
            errata_file = os.path.join(OUTPUT_DIR, "errata.csv")
            errata_df.to_csv(errata_file, index=False, encoding='latin-1')
            print(f"  Errata log updated: {len(errata_rows):,} entries")

    print(f"\n{'=' * 60}")
    print(f"DONE")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Clean CSVs written to: {OUTPUT_DIR}")
    print(f"Errata log: {os.path.join(OUTPUT_DIR, 'errata.csv')}")
    print(f"Total errata entries: {len(errata_rows):,}")


if __name__ == "__main__":
    main()
