"""
File: Golden_Extractor.py
Summary: Creates a "Golden Dataset". Takes a verified HIK, finds every household 
         they ever lived in across all decades, and extracts the entire family 
         unit into a small, verified test CSV.
"""

import csv
import os

# --- CONFIGURATION ---
# Put the exact, verified HIK (the crosswalk ID) of your grandfather here.
# You can add as many as you want to this list.
TARGET_HIKS = [
    "PUT_YOUR_GRANDFATHERS_VERIFIED_HIK_HERE",
]

# The massive CSV containing all records
MASTER_CSV = r"C:\tempc\ShortTermCSVfiles\family_rosters_with_hiks.csv"

# The small, verified CSV this script will create
OUTPUT_CSV = r"C:\tempc\ShortTermCSVfiles\Golden_Family.csv"


def build_golden_dataset():
    if not os.path.exists(MASTER_CSV):
        print(f"ERROR: Cannot find Master CSV at {MASTER_CSV}")
        return

    target_households = set()

    print(f"Pass 1: Searching for {len(TARGET_HIKS)} verified HIKs to find their exact households...")
    with open(MASTER_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            person_hik = row.get('person_hik', '').strip()
            if person_hik in TARGET_HIKS:
                year = row.get('YEAR', '').strip()
                hh_id = row.get('household_id', '').strip()
                if year and hh_id:
                    target_households.add((year, hh_id))

    if not target_households:
        print("Could not find any of those HIKs in the CSV. Double check your IDs and column names!")
        return

    print(f"Found {len(target_households)} different census households.")
    print(f"Pass 2: Extracting all parents, spouses, and children in those households...")
    
    golden_records = []
    with open(MASTER_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            year = row.get('YEAR', '').strip()
            hh_id = row.get('household_id', '').strip()
            if (year, hh_id) in target_households:
                golden_records.append(row)

    print(f"Writing {len(golden_records)} family records to {OUTPUT_CSV}...")
    with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(golden_records)

    print("Success! Your Golden Dataset is ready for testing.")

if __name__ == "__main__":
    build_golden_dataset()