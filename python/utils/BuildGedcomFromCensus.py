"""
-----------------------------------
File: BuildGedcomFromCensus.py
Summary: Extracts the mathematically linked "Clans" from the Time Machine
         and formats them into a standard GEDCOM 5.5 file.
-----------------------------------
"""

import os
import sqlite3

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
SAMPLE_DB = os.path.join(VAULT_DIR, "CENSUS-SAMPLE.db")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches_SAMPLE.db")
OUT_GED = os.path.join(BASE_DATA_DIR, "Census_Ground_Truth.ged")


def build_gedcom():
    print(f"Connecting to databases...")
    con = sqlite3.connect(SAMPLE_DB)
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db")
    cursor = con.cursor()

    print("Fetching Clan Data... (This may take a moment)")
    # DECISION: We grab the MOST RECENT census record for each clan to use as the base for the GEDCOM names.
    cursor.execute("""
                   WITH RankedFamilies AS (SELECT c.clan_id,
                                                  f.family_id,
                                                  f.year,
                                                  f.head_histid,
                                                  f.spouse_histid,
                                                  ROW_NUMBER() OVER(PARTITION BY c.clan_id ORDER BY f.year DESC) as rn
                                           FROM match_db.clan_mapping c
                                                    JOIN families f ON c.family_id = f.family_id)
                   SELECT clan_id, family_id, year, head_histid, spouse_histid
                   FROM RankedFamilies
                   WHERE rn = 1
                   """)

    clans = cursor.fetchall()
    print(f"Found {len(clans):,} unique family timelines. Generating GEDCOM...")

    with open(OUT_GED, 'w', encoding='utf-8') as f:
        # Standard GEDCOM Header
        f.write("0 HEAD\n1 SOUR CENSUS_TIME_MACHINE\n1 GEDC\n2 VERS 5.5\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n")

        for clan_id, fam_id, year, head_histid, spouse_histid in clans:

            # Fetch all individuals living in this specific household
            cursor.execute("""
                           SELECT histid, first_name, last_name, sex, birthyr, bpld
                           FROM individuals
                           WHERE family_id = ?
                           """, (fam_id,))

            members = cursor.fetchall()
            child_ids = []

            for mem in members:
                histid, fname, lname, sex, byr, bpl = mem

                if histid != head_histid and histid != spouse_histid:
                    child_ids.append(histid)

                f.write(f"0 @I_{histid}@ INDI\n")
                f.write(f"1 NAME {fname} /{lname}/\n")

                ged_sex = "M" if str(sex) == "1" else "F" if str(sex) == "2" else "U"
                f.write(f"1 SEX {ged_sex}\n")

                if byr:
                    f.write(f"1 BIRT\n2 DATE ABT {byr}\n")

            # Build the Family (FAM) Block
            f.write(f"0 @F_{clan_id}@ FAM\n")
            if head_histid:   f.write(f"1 HUSB @I_{head_histid}@\n")
            if spouse_histid: f.write(f"1 WIFE @I_{spouse_histid}@\n")
            for cid in child_ids:
                f.write(f"1 CHIL @I_{cid}@\n")

        f.write("0 TRLR\n")

    print(f"SUCCESS! Saved to: {OUT_GED}")


if __name__ == "__main__":
    build_gedcom()
