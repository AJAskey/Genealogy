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
OUTPUT_CSV = r"C:\tempc\ShortTermCSVfiles\census-1940_WhiteMales_PA_Counties.csv"

# The maximum number of rows per output file to ensure Excel never corrupts your data
MAX_ROWS_PER_FILE = 990000

# The exact columns you want to keep to reduce file size.
# (Note: I added 'SERIAL' to your list because you need it to group households together in Excel!)
KEEP_COLUMNS = {
    "YEAR", "SERIAL", "NUMPREC", "NUMPERHH", "HHTYPE", "REGION",
    "STATEICP", "STATEFIP", "COUNTYICP", "METAREA", "METAREAD", "CITY",
    "URBAN", "WARD", "FARM", "NMOTHERS", "NFATHERS", "PERNUM", "FAMSIZE",
    "MOMLOC", "POPLOC", "SPLOC", "NCHILD", "NSIBS", "ELDCH", "YNGCH",
    "RELATE", "SEX", "AGE", "MARST", "BIRTHYR", "RACE", "BPL", "MBPL",
    "FBPL", "OCC1950", "IND1950", "INCWAGE", "HISTID"
}

# The exact counties in Pennsylvania you want to filter by
TARGET_COUNTIES = {
    "150", "210", "230", "270", "330", "350", "410", "470", "510", "550", "610", "630", "810",
    # Including padded zero versions just in case IPUMS formatted them differently
    "0150", "0210", "0230", "0270", "0330", "0350", "0410", "0470", "0510", "0550", "0610", "0630", "0810"
}


def run_gross_filter():
    if not os.path.exists(INPUT_CSV):
        print(f"❌ ERROR: Cannot find the input CSV at {INPUT_CSV}")
        return

    print(f"📂 Reading from: {INPUT_CSV}")
    print("⏳ Running Gross Filter for White Males in Target PA Counties (RACE=1, SEX=1, STATEICP=14)...")
    print("   (Optimized for speed. This will stream line-by-line.)\n")

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as infile:
        reader = csv.DictReader(infile)

        # Filter the headers to only include the ones in our KEEP_COLUMNS list
        kept_fieldnames = [col for col in reader.fieldnames if col and col.upper() in KEEP_COLUMNS]

        # Initialize the first chunked file
        file_part = 1
        current_output_csv = OUTPUT_CSV.replace(".csv", f"_part{file_part}.csv")

        outfile = open(current_output_csv, 'w', encoding='utf-8', newline='')
        writer = csv.DictWriter(outfile, fieldnames=kept_fieldnames, extrasaction='ignore')
        writer.writeheader()

        rows_in_current_file = 0
        match_count = 0

        # Find the exact casing of the keys in the header so we don't have to
        # run .upper() on 44 million rows!
        race_key = next((k for k in reader.fieldnames if k and k.upper() == 'RACE'), 'RACE')
        sex_key = next((k for k in reader.fieldnames if k and k.upper() == 'SEX'), 'SEX')
        # Safely grab whatever state column IPUMS gave us (ICP or FIP)
        state_key = next((k for k in reader.fieldnames if k and k.upper() in ('STATEICP', 'STATEFIP', 'STATE')),
                         'STATEICP')
        county_key = next((k for k in reader.fieldnames if k and k.upper() == 'COUNTYICP'), 'COUNTYICP')

        # Safety Check: If columns are entirely missing, crash instantly instead of waiting 10 minutes!
        if race_key not in reader.fieldnames or sex_key not in reader.fieldnames:
            print(f"❌ ERROR: Could not find RACE or SEX columns in the CSV header!")
            print(f"   First few columns found: {reader.fieldnames[:10]}")
            print("   (Is the file tab-separated? You might need to re-download it as comma-separated).")
            return

        row_count = 0
        for row in reader:
            row_count += 1

            # Safely grab values, force to uppercase to handle both Text Labels and Numbers
            race_val = row.get(race_key, '').strip().upper()
            sex_val = row.get(sex_key, '').strip().upper()
            state_val = row.get(state_key, '').strip().upper()
            county_val = row.get(county_key, '').strip()

            # Checks numeric codes (both ICP and FIP) OR text labels!
            if race_val in ('1', '01', 'WHITE') and sex_val in ('1', '01', 'MALE') and state_val in ('14', '014',
                                                                                                     'PENNSYLVANIA') and county_val in TARGET_COUNTIES:
                writer.writerow(row)
                match_count += 1
                rows_in_current_file += 1

                # If we hit the Excel safety limit, close this file and start a new one!
                if rows_in_current_file >= MAX_ROWS_PER_FILE:
                    outfile.close()
                    file_part += 1
                    current_output_csv = OUTPUT_CSV.replace(".csv", f"_part{file_part}.csv")

                    outfile = open(current_output_csv, 'w', encoding='utf-8', newline='')
                    writer = csv.DictWriter(outfile, fieldnames=kept_fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    rows_in_current_file = 0

            if row_count % 1000000 == 0:
                print(f"  ...scanned {row_count:,} rows... (Found {match_count:,} matches so far)")

        outfile.close()

    print("\n" + "=" * 50)
    print(f"✅ Finished scanning {row_count:,} total rows.")
    print(f"✅ Extracted {match_count:,} White Males in Target PA Counties.")
    print(f"💾 Saved your stripped-down files as chunks (e.g., _part1.csv, _part2.csv).")


if __name__ == "__main__":
    run_gross_filter()
