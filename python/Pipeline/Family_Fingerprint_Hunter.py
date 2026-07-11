"""
File: Family_Fingerprint_Hunter.py
Summary: Takes a known family structure from a census record (a "fingerprint")
         and searches the master CSV to find a definitive match, returning the
         HIKs for the entire verified family unit.
"""

import csv
import os
from collections import defaultdict

# The massive CSV containing all records
MASTER_CSV = r"C:\tempc\ShortTermCSVfiles\family_rosters_with_hiks.csv"

# --- TARGET FINGERPRINT (from your 1940 Census Record) ---
# SOURCE CITATION:
# Year: 1940; Census Place: Williamsport, Lycoming, Pennsylvania; 
# Roll: m-t0627-03567; Page: 7B; Enumeration District: 41-92
# Title: 1940 United States Federal Census
# Publisher: Ancestry.com Operations, Inc. (2012)

TARGET_YEAR = 1940
TARGET_HEAD = {
    "first_name": "Lawrence",
    "last_name": "Askey",
    "age": 31
}
TARGET_SPOUSE = {
    "first_name": "Joye",
    "age": 28
}
# The ages of the children present in the 1940 household
TARGET_CHILDREN_AGES = {7, 5, 4}  # Using a set for easy comparison


def find_family_by_fingerprint():
    """
    Reads the master CSV, groups it by household, and then searches for a
    household that perfectly matches the family fingerprint provided above.
    """
    if not os.path.exists(MASTER_CSV):
        print(f"ERROR: Cannot find Master CSV at {MASTER_CSV}")
        return

    # 1. Read the entire CSV into a household dictionary for efficiency
    households = defaultdict(list)
    print(f"Reading master CSV into memory: {MASTER_CSV}")
    with open(MASTER_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = row.get('YEAR', '').strip()
            hh_id = row.get('household_id', '').strip()
            if year and hh_id:
                households[(year, hh_id)].append(row)
    print(f"Finished reading. Found {len(households)} unique households.")

    # 2. Iterate through households from the target year to find a match
    print(f"\nSearching for a family matching the {TARGET_YEAR} fingerprint...")
    found_match = False
    for (year, hh_id), members in households.items():
        if year != str(TARGET_YEAR):
            continue

        # Find the head of this household
        head = next((m for m in members if m.get('role') == 'Head'), None)
        if not head:
            continue

        # Check if the head matches Lawrence's profile (allowing 2-year age variance)
        head_age = int(head.get('age', -1))
        if (TARGET_HEAD['first_name'].upper() in head.get('first_name', '').upper() and
                TARGET_HEAD['last_name'].upper() in head.get('last_name', '').upper() and
                abs(head_age - TARGET_HEAD['age']) <= 2):

            # Potential match! Now check the rest of the family.
            spouse = next((m for m in members if m.get('role') == 'Spouse'), None)
            children_ages = {int(m['age']) for m in members if m.get('role') == 'Child' and m.get('age', '').isdigit()}

            # Check spouse
            spouse_match = False
            if spouse:
                spouse_age = int(spouse.get('age', -1))
                if (TARGET_SPOUSE['first_name'].upper() in spouse.get('first_name', '').upper() and
                        abs(spouse_age - TARGET_SPOUSE['age']) <= 2):
                    spouse_match = True

            # Check if the set of children's ages is identical
            children_match = (children_ages == TARGET_CHILDREN_AGES)

            if spouse_match and children_match:
                # We found a definitive match!
                found_match = True
                print("\n" + "=" * 80)
                print("✅ SUCCESS! Found a definitive family match in the CSV!")
                print(f"   Household ID: {hh_id} in Year: {year}")
                print("=" * 80)
                print(f"{'Role':<10} {'First Name':<15} {'Last Name':<15} {'Age':<5} {'PERSON_HIK'}")
                print("-" * 80)

                for member in sorted(members, key=lambda x: (x.get('role') != 'Head', x.get('role') != 'Spouse', int(x.get('age', 0)))):
                    print(f"{member.get('role', ''):<10} {member.get('first_name', ''):<15} {member.get('last_name', ''):<15} {member.get('age', ''):<5} {member.get('person_hik', 'NOT FOUND')}")
                print("=" * 80)
                print("\nUse the HIKs above to build your Golden Dataset!")
                break  # Stop after finding the first perfect match

    if not found_match:
        print("\n❌ No definitive match found. The CSV might not contain this exact family,")
        print("   or the names/ages in the CSV are different from the census record.")


if __name__ == "__main__":
    find_family_by_fingerprint()