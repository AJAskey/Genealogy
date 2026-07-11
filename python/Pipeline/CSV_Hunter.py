"""
File: CSV_Hunter.py
Summary: Pure Python script. Reads a GEDCOM file and matches it against a raw 
         CSV census extract line-by-line. No databases used.
"""

import csv
import os
import re

# --- CONFIGURATION ---
INPUT_GEDCOM = r"E:\Users\Andy\PycharmProjects\Genealogy\output\WilliamAskey_Project.ged"

# Put the path to your actual CSV test file here:
INPUT_CSV = r"C:\tempc\ShortTermCSVfiles\family_rosters_with_hiks.csv"


# LOG_FILE = r"E:\Users\Andy\PycharmProjects\Genealogy\output\CSV_Hunter_Results.txt"


def get_core_location(plac_str):
    """Extracts the state or primary region from a GEDCOM place string."""
    if not plac_str or plac_str == "Unknown": return ""
    parts = [p.strip() for p in plac_str.split(',')]
    if len(parts) >= 2 and parts[-1].upper() in ('USA', 'UNITED STATES', 'UNITED STATES OF AMERICA'):
        return parts[-2]
    return parts[-1] if parts else ""


def parse_advanced_gedcom(filepath):
    """Reads the GEDCOM and extracts demographic fingerprints."""
    if not os.path.exists(filepath):
        print(f"ERROR: Cannot find GEDCOM at {filepath}")
        return []

    print(f"Parsing GEDCOM: {filepath}...")
    individuals = {}
    families = {}
    current_id, current_type, in_birt_block = None, None, False

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line: continue

            parts = line.split(' ', 2)
            level = parts[0]
            tag = parts[1] if len(parts) > 1 else ""
            val = parts[2] if len(parts) > 2 else ""

            if level == '0':
                in_birt_block = False
                if len(parts) == 3 and parts[2] in ('INDI', 'FAM'):
                    current_id, current_type = parts[1], parts[2]
                    if current_type == 'INDI':
                        individuals[current_id] = {'first_name': '', 'last_name': '', 'birthyr': '', 'birthplac': ''}
            elif level == '1' and current_type == 'INDI':
                in_birt_block = False
                if tag == 'NAME':
                    name_match = re.search(r'(.*?) /(.*?)/', val)
                    if name_match:
                        individuals[current_id]['first_name'] = name_match.group(1).strip()
                        individuals[current_id]['last_name'] = name_match.group(2).strip()
                elif tag == 'BIRT':
                    in_birt_block = True
            elif level == '2' and current_type == 'INDI' and in_birt_block:
                if tag == 'DATE':
                    year_match = re.search(r'\b(1[789]\d{2}|20\d{2})\b', val)
                    if year_match:
                        individuals[current_id]['birthyr'] = year_match.group(1)
                elif tag == 'PLAC':
                    individuals[current_id]['birthplac'] = val

    people_to_hunt = []
    for ind_id, ind in individuals.items():
        if ind['birthyr'] and int(ind['birthyr']) <= 1950:
            ind['core_bpl'] = get_core_location(ind['birthplac'])
            people_to_hunt.append(ind)

    print(f"Found {len(people_to_hunt)} valid people in GEDCOM to hunt for.")
    return people_to_hunt


def hunt_in_csv(people, csv_filepath):
    """Reads the CSV row by row and checks for matches."""
    if not os.path.exists(csv_filepath):
        print(f"ERROR: Cannot find CSV at {csv_filepath}")
        return

    print(f"Hunting in CSV: {csv_filepath}...")

    # Open log file to save our matches
    with open(LOG_FILE, 'w', encoding='utf-8') as log:
        log.write(f"--- CSV HUNT RESULTS ---\n")

        with open(csv_filepath, 'r', encoding='utf-8') as csv_file:
            reader = csv.DictReader(csv_file)

            # Print the columns found in the CSV so you have total visibility
            print(f"CSV Columns Found: {reader.fieldnames}")

            row_count = 0
            match_count = 0

            # Process line by line
            for row in reader:
                row_count += 1

                # Extract values from CSV (using get() to prevent crashes if column is missing)
                # Update these string keys if your CSV column names are slightly different!
                csv_age_str = row.get('AGE', '').strip()
                csv_year_str = row.get('YEAR', '').strip()
                csv_fname = row.get('first_name', '').strip()
                csv_lname = row.get('last_name', '').strip()

                if not csv_age_str.isdigit() or not csv_year_str.isdigit():
                    continue  # Skip rows with bad age/year

                csv_year = int(csv_year_str)
                csv_byear = csv_year - int(csv_age_str)

                # Check this CSV row against every person in our GEDCOM
                for p in people:
                    p_byear = int(p['birthyr'])

                    # Check if birth years are within 2 years of each other
                    if abs(csv_byear - p_byear) <= 2:

                        # Since the CSV doesn't have BPL, we will match on Names!
                        # We grab just the first word of the first name to avoid Middle Name mismatches
                        p_fname_first = p['first_name'].split()[0].upper() if p['first_name'] else ""
                        p_lname = p['last_name'].upper()

                        if p_fname_first and p_lname:
                            if p_fname_first in csv_fname.upper() and p_lname in csv_lname.upper():
                                match_count += 1
                                msg = (f"\nMATCH FOUND at CSV Row {row_count}:\n"
                                       f"  GEDCOM Person: {p['first_name']} {p['last_name']} (b. {p_byear})\n"
                                       f"  CSV Record   : {csv_fname} {csv_lname} (Census Year: {csv_year}, b. ~{csv_byear})")

                                print(msg)
                                log.write(msg + "\n")

            print("\n" + "=" * 50)
            print(f"Finished reading {row_count} rows in the CSV.")
            print(f"Found {match_count} total matches.")
            print(f"Results saved to: {LOG_FILE}")


if __name__ == "__main__":
    targets = parse_advanced_gedcom(INPUT_GEDCOM)
    if targets:
        hunt_in_csv(targets, INPUT_CSV)
