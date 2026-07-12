"""
File: CSV_Gross_Filter.py
Summary: A highly optimized, hardcoded pre-processor to slash massive IPUMS CSVs 
         down to size by extracting ONLY White Males (RACE=1, SEX=1).
"""

import csv
import os

# --- CONFIGURATION ---
# The massive original file
INPUT_CSV = r"C:\tempc\ShortTermCSVfiles\census-1940.csv"

# The new, stripped-down file you will use for your other scripts
OUTPUT_CSV = r"C:\tempc\ShortTermCSVfiles\census-1940_WhiteMales.csv"


def run_gross_filter():
    if not os.path.exists(INPUT_CSV):
        print(f"❌ ERROR: Cannot find the input CSV at {INPUT_CSV}")
        return

    print(f"📂 Reading from: {INPUT_CSV}")
    print("⏳ Running Gross Filter for White Males (RACE=1, SEX=1)...")
    print("   (Optimized for speed. This will stream line-by-line.)\n")

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as infile, \
         open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as outfile:

        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
        writer.writeheader()

        # Find the exact casing of the keys in the header so we don't have to 
        # run .upper() on 44 million rows!
        race_key = next((k for k in reader.fieldnames if k and k.upper() == 'RACE'), 'RACE')
        sex_key = next((k for k in reader.fieldnames if k and k.upper() == 'SEX'), 'SEX')

        row_count = 0
        match_count = 0

        for row in reader:
            row_count += 1

            # Direct, hardcoded, blazing-fast check
            if row.get(race_key, '').strip() == '1' and row.get(sex_key, '').strip() == '1':
                writer.writerow(row)
                match_count += 1

            if row_count % 1000000 == 0:
                print(f"  ...scanned {row_count:,} rows...")

    print("\n" + "=" * 50)
    print(f"✅ Finished scanning {row_count:,} total rows.")
    print(f"✅ Extracted {match_count:,} White Males.")
    print(f"💾 Saved your stripped-down file to: {OUTPUT_CSV}")


if __name__ == "__main__":
    run_gross_filter()