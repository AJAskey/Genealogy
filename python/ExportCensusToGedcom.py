"""
-----------------------------------
File: ExportCensusToGedcom.py

Summary: Generates a standard .ged family tree file directly from the 
         relational census data in the Named Vaults.
         It automatically propagates the father's last name to his children 
         before exporting, then generates "Census-level" GEDCOM structures.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0: http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sqlite3
import sys

# Add the 'python' directory and project root to sys.path so we can import properly
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [script_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

NAMED_VAULT_DIR = os.path.join(BASE_DATA_DIR, "NamedVaults")
OUTPUT_GEDCOM = os.path.join(project_root, "gedcom_sources", "Census_Export_Askey.ged")
TARGET_LAST_NAME = 'Askey'

REVERSE_BPL = {
    1: "Alabama", 2: "Alaska", 4: "Arizona", 5: "Arkansas", 6: "California",
    8: "Colorado", 9: "Connecticut", 10: "Delaware", 11: "District of Columbia",
    12: "Florida", 13: "Georgia", 15: "Hawaii", 16: "Idaho", 17: "Illinois",
    18: "Indiana", 19: "Iowa", 20: "Kansas", 21: "Kentucky", 22: "Louisiana",
    23: "Maine", 24: "Maryland", 25: "Massachusetts", 26: "Michigan",
    27: "Minnesota", 28: "Mississippi", 29: "Missouri", 30: "Montana",
    31: "Nebraska", 32: "Nevada", 33: "New Hampshire", 34: "New Jersey",
    35: "New Mexico", 36: "New York", 37: "North Carolina", 38: "North Dakota",
    39: "Ohio", 40: "Oklahoma", 41: "Oregon", 42: "Pennsylvania", 44: "Rhode Island",
    45: "South Carolina", 46: "South Dakota", 47: "Tennessee", 48: "Texas",
    49: "Utah", 50: "Vermont", 51: "Virginia", 53: "Washington", 54: "West Virginia",
    55: "Wisconsin", 56: "Wyoming", 410: "England", 411: "Scotland", 412: "Wales",
    414: "Ireland", 413: "Northern Ireland", 453: "Germany", 404: "Sweden", 401: "Norway",
    400: "Denmark", 425: "Netherlands", 421: "France", 426: "Switzerland", 150: "Canada",
    200: "Mexico", 501: "Japan", 502: "South Korea"
}


def decode_bpld(bpld_str):
    if not bpld_str or str(bpld_str).strip() == '': return "Unknown"
    try:
        val = int(bpld_str)
        prefix = val // 100 if val >= 1000 else val
        return REVERSE_BPL.get(prefix, str(val))
    except ValueError:
        return str(bpld_str)


def export_gedcom(logger):
    logger.info(f"Extracting '{TARGET_LAST_NAME}' lineage from the Decade Vaults...")

    individuals_data = []
    families_data = []

    for filename in os.listdir(NAMED_VAULT_DIR):
        if filename.startswith("NamedVault_") and filename.endswith(".db"):
            db_path = os.path.join(NAMED_VAULT_DIR, filename)
            logger.info(f"  -> Processing {filename}...")
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # Step 1: Ripple
                cursor.execute("""
                               UPDATE individuals
                               SET last_name = (SELECT p.last_name
                                                FROM individuals p
                                                WHERE p.histid = individuals.father_histid)
                               WHERE last_name = 'Bosselstink'
                                 AND father_histid IS NOT NULL
                                 AND (SELECT p.last_name
                                      FROM individuals p
                                      WHERE p.histid = individuals.father_histid) != 'Bosselstink';
                               """)
                conn.commit()

                # Step 2: Fetch Targets
                cursor.execute(
                    f"SELECT DISTINCT family_id FROM individuals WHERE last_name COLLATE NOCASE = '{TARGET_LAST_NAME}' AND family_id IS NOT NULL")
                target_families = [r[0] for r in cursor.fetchall()]

                if target_families:
                    fam_placeholders = ','.join(['?'] * len(target_families))
                    cursor.execute(
                        f"SELECT histid, first_name, last_name, sex, birthyr, bpld, family_id, father_histid, mother_histid FROM individuals WHERE family_id IN ({fam_placeholders})",
                        target_families)
                    individuals_data.extend(cursor.fetchall())

                    cursor.execute(
                        f"SELECT family_id, head_histid, spouse_histid FROM families WHERE family_id IN ({fam_placeholders})",
                        target_families)
                    families_data.extend(cursor.fetchall())

    if not individuals_data:
        logger.warning("No families found to export!")
        return

    logger.info(f"Found {len(individuals_data):,} individuals across all decades. Building GEDCOM...")

    children_by_fam = {}
    for ind in individuals_data:
        histid, _, _, _, _, _, fam_id, f_id, m_id = ind
        if f_id or m_id:
            if fam_id not in children_by_fam: children_by_fam[fam_id] = []
            children_by_fam[fam_id].append(histid)

    with open(OUTPUT_GEDCOM, 'w', encoding='utf-8') as f:
        f.write("0 HEAD\n1 SOUR Census_Architecture\n1 GEDC\n2 VERS 5.5\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n")

        for ind in individuals_data:
            histid, fname, lname, sex, byr, bpld, fam_id, f_id, m_id = ind
            f.write(f"0 @I{histid}@ INDI\n")

            if fname == 'Future' and lname == 'Bosselstink':
                f.write("1 NAME Unknown /Unknown/\n")
            else:
                f.write(f"1 NAME {fname} /{lname}/\n")

            f.write(f"1 SEX {'M' if sex == '1' else 'F' if sex == '2' else 'U'}\n")

            if byr:
                f.write(f"1 BIRT\n2 DATE {byr}\n")
                state_name = decode_bpld(bpld)
                if state_name != "Unknown": f.write(f"2 PLAC {state_name}, USA\n")

            if f_id or m_id:
                f.write(f"1 FAMC @F{fam_id}@\n")
            else:
                f.write(f"1 FAMS @F{fam_id}@\n")

        for fam in families_data:
            fam_id, head_id, spouse_id = fam
            f.write(f"0 @F{fam_id}@ FAM\n")
            if head_id: f.write(f"1 HUSB @I{head_id}@\n")
            if spouse_id: f.write(f"1 WIFE @I{spouse_id}@\n")
            for child_id in children_by_fam.get(fam_id, []):
                f.write(f"1 CHIL @I{child_id}@\n")

        f.write("0 TRLR\n")

    logger.info(f"\nSUCCESS! Your Census-Level GEDCOM is ready: {OUTPUT_GEDCOM}")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="EXPORT_GEDCOM")
    export_gedcom(main_logger)
