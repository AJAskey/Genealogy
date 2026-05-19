"""
-----------------------------------
File: export_gedcom.py

Summary: Exports census data from the SQLite vault into a GEDCOM 7.0.18 
         compliant file, grouping individuals by household/family.

Design:
  - Adheres to GEDCOM 7.0.18 spec (UTF-8 encoding).
  - Creates INDI records for individuals and FAM records for relationships.
  - Groups people into FAM records based on their shared SERIAL and FAMUNIT.
  - Maps variables like SEX, AGE, and BPL based on the IPUMS standard.
  - Uses simple sequential IDs (@I1@, @F1@) to prevent Family Tree Maker 
    from rejecting XREFs that exceed 22 characters.

Inputs:  SQLite database file (e.g. MasterVault_1900.db)
Outputs: .ged file encoded in UTF-8
--------------------------------
"""

import argparse
import datetime
import os
import sqlite3

from python.project_globals import CODEBOOK

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DEFAULT_DB = r"D:\Data\Genealogy_Data\MasterVault_1920.db"
OUTPUT_GED = r"E:\Users\Andy\PycharmProjects\Genealogy\output\census_export.ged"


# ==============================================================================
# MAPPING HELPERS
# ==============================================================================
def map_sex(ipums_sex):
    """Map IPUMS SEX to GEDCOM SEX."""
    if ipums_sex == '1':
        return 'M'
    elif ipums_sex == '2':
        return 'F'
    return 'U'  # Unknown


def format_name(first, last):
    """Format name for GEDCOM standard: First /Last/."""
    first = first.strip() if first else ""
    last = last.strip() if last else ""
    if not first and not last:
        return "Unknown"
    return f"{first} /{last}/".strip()


# ==============================================================================
# GEDCOM EXPORTER
# ==============================================================================
def export_to_gedcom(db_path, output_path, limit=None):
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Get a list of unique household serials
    print("Fetching unique household serials...")
    cursor.execute("SELECT DISTINCT serial FROM population")
    all_serials = [row['serial'] for row in cursor.fetchall()]

    # 2. Limit the number of households to process
    if limit:
        serials_to_process = all_serials[:limit]
        print(f"Limiting to first {limit} households.")
    else:
        serials_to_process = all_serials

    # 3. Fetch all rows for those selected households
    print(f"Fetching all records for {len(serials_to_process)} households...")
    placeholders = ','.join('?' for _ in serials_to_process)
    query = f"SELECT * FROM population WHERE serial IN ({placeholders})"
    cursor.execute(query, serials_to_process)
    rows = cursor.fetchall()

    print(f"Loaded {len(rows)} records. Generating GEDCOM...")

    # Organize into families
    # Key: (year, sample, serial, famunit)
    families = {}
    individuals = []

    # Map long database IDs to short GEDCOM sequential IDs to avoid FTM 22-char limits
    indi_id_map = {}
    fam_id_map = {}
    indi_counter = 1
    fam_counter = 1

    for row in rows:
        individuals.append(row)

        comp_id_safe = str(row['composite_id']).strip().replace(" ", "_")
        if comp_id_safe not in indi_id_map:
            indi_id_map[comp_id_safe] = f"@I{indi_counter}@"
            indi_counter += 1

        fam_unit_safe = str(row['famunit']).strip() if row['famunit'] else "1"
        fam_key = (row['year'], row['sample'], row['serial'], fam_unit_safe)

        if fam_key not in families:
            families[fam_key] = []
        families[fam_key].append(row)

    # Map Family Keys to short GEDCOM IDs
    for fam_key in families.keys():
        if fam_key not in fam_id_map:
            fam_id_map[fam_key] = f"@F{fam_counter}@"
            fam_counter += 1

    # --- PRE-CALCULATE ALL BIDIRECTIONAL LINKS ---
    indi_links = {}
    fam_records = {}

    for fam_key, members in families.items():
        short_fam_id = fam_id_map[fam_key]
        fam_records[short_fam_id] = []
        has_husb = False
        has_wife = False

        for row in members:
            comp_id_safe = str(row['composite_id']).strip().replace(" ", "_")
            short_indi_id = indi_id_map[comp_id_safe]

            relate = str(row['related']).strip() if row['related'] else ""
            sex = map_sex(row['sex'])

            if short_indi_id not in indi_links:
                indi_links[short_indi_id] = []

            if (relate.startswith('1') or relate == '0100') and not has_husb:
                if sex == 'M':
                    fam_records[short_fam_id].append(f"1 HUSB {short_indi_id}\n")
                    indi_links[short_indi_id].append(f"1 FAMS {short_fam_id}\n")
                    has_husb = True
                elif not has_wife:
                    fam_records[short_fam_id].append(f"1 WIFE {short_indi_id}\n")
                    indi_links[short_indi_id].append(f"1 FAMS {short_fam_id}\n")
                    has_wife = True

            elif (relate.startswith('2') or relate == '0200') and not has_wife:
                if sex == 'F':
                    fam_records[short_fam_id].append(f"1 WIFE {short_indi_id}\n")
                    indi_links[short_indi_id].append(f"1 FAMS {short_fam_id}\n")
                    has_wife = True
                elif not has_husb:
                    fam_records[short_fam_id].append(f"1 HUSB {short_indi_id}\n")
                    indi_links[short_indi_id].append(f"1 FAMS {short_fam_id}\n")
                    has_husb = True

            elif relate.startswith('3') or relate == '0300':
                state = CODEBOOK.get_code_value("RELATED", relate)
                fam_records[short_fam_id].append(f"1 CHIL {short_indi_id}\n")
                indi_links[short_indi_id].append(f"1 FAMC {short_fam_id}\n")
            else:
                pass

    now = datetime.datetime.now()

    with open(output_path, 'w', encoding='utf-8') as f:
        # -----------------------------
        # HEAD RECORD
        # -----------------------------
        f.write("0 HEAD\n")
        f.write("1 SOUR GENEALOGY_PIPELINE\n")
        f.write("2 VERS 1.0\n")
        f.write("2 NAME Genealogy Census Exporter\n")
        f.write("1 DEST ANY\n")
        f.write(f"1 DATE {now.strftime('%d %b %Y').upper()}\n")
        f.write(f"2 TIME {now.strftime('%H:%M:%S')}\n")
        f.write("1 SUBM @SUBM1@\n")
        f.write("1 COPR Copyright 2026\n")
        f.write("1 GEDC\n")
        f.write("2 VERS 7.0.18\n")

        # In GEDCOM 7, standard extensions need to point to a URI.
        # Custom internal tags should be structured specifically under a URI we control.
        # But an even safer way that complies fully with the standard and avoids schema errors
        # is to simply use the standard `REFN` (Reference Number) tag or a `NOTE`.

        # Let's remove the SCHMA block and use REFN in the INDI block instead.

        # -----------------------------
        # SUBMITTER RECORD
        # -----------------------------
        f.write("0 @SUBM1@ SUBM\n")
        f.write("1 NAME Andy Askey\n")

        # -----------------------------
        # INDIVIDUAL (INDI) RECORDS
        # -----------------------------
        for row in individuals:
            comp_id_safe = str(row['composite_id']).strip().replace(" ", "_")
            short_indi_id = indi_id_map[comp_id_safe]
            f.write(f"0 {short_indi_id} INDI\n")

            name = format_name(row['namefrst'], row['namelast'])
            f.write(f"1 NAME {name}\n")

            sex = map_sex(row['sex'])
            f.write(f"1 SEX {sex}\n")

            if row['age'] or row['birthyr'] or row['bpld']:
                f.write("1 BIRT\n")
                if row['birthyr']:
                    f.write(f"2 DATE {row['birthyr']}\n")
                if row['bpld']:
                    f.write(f"2 PLAC {row['bpld']}\n")

            if row['age']:
                f.write(f"1 NOTE Age in census: {row['age']}\n")

            # Instead of a custom tag, we use the universally compliant REFN tag
            # REFN means "Reference Number" - exactly what a database ID is.
            f.write(f"1 REFN {comp_id_safe}\n")
            f.write(f"2 TYPE IPUMS_COMPOSITE_ID\n")

            if short_indi_id in indi_links:
                for link in indi_links[short_indi_id]:
                    f.write(link)

        # -----------------------------
        # FAMILY (FAM) RECORDS
        # -----------------------------
        for fam_key, short_fam_id in fam_id_map.items():
            roles = fam_records.get(short_fam_id, [])
            if len(roles) > 0:
                f.write(f"0 {short_fam_id} FAM\n")
                for role in roles:
                    f.write(role)

        # -----------------------------
        # TRAILER
        # -----------------------------
        f.write("0 TRLR\n")

    print(f"GEDCOM export complete: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export database to GEDCOM")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    parser.add_argument("--out", default=OUTPUT_GED, help="Output GEDCOM file path")
    parser.add_argument("--limit", type=int, default=100, help="Max number of HOUSEHOLDS to export for testing")
    args = parser.parse_args()

    export_to_gedcom(args.db, args.out, args.limit)
