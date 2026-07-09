"""
File: Export_GEDCOM.py

Summary: Extracts a specific census year from the Test Vault and formats
         it into a strictly compliant GEDCOM 5.5.1 file for Ancestry.com.
"""

import duckdb
import os

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Test_DuckDB_Vault.db"
OUTPUT_GEDCOM = r"C:\tempc\ShortTermCSVfiles\test_census.ged"

# The specific census year to extract as our test snapshot
ANCHOR_YEAR = 1900

# Basic map to turn IPUMS BPL codes into readable text for Ancestry
STATE_MAP = {
    "42": "Pennsylvania, USA",
    "39": "Ohio, USA",
    "36": "New York, USA",
    "17": "Illinois, USA",
    "18": "Indiana, USA",
    "34": "New Jersey, USA",
    "24": "Maryland, USA",
    "54": "West Virginia, USA",
    "51": "Virginia, USA",
    "25": "Massachusetts, USA"
}


def main():
    print(f"Connecting to Test Vault: {MASTER_VAULT_DB}...")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    print(f"Extracting Individuals for {ANCHOR_YEAR}...")
    inds = con.execute(f"""
        SELECT HISTID, first_name, last_name, SEX, BIRTHYR, BPL, RELATE, SERIAL
        FROM individuals
        WHERE YEAR = {ANCHOR_YEAR}
    """).fetchall()

    print(f"Extracting Families for {ANCHOR_YEAR}...")
    fams = con.execute(f"""
        SELECT SERIAL, head_histid, spouse_histid
        FROM families
        WHERE YEAR = {ANCHOR_YEAR}
    """).fetchall()

    # Build a quick Python dictionary to map children to their family's SERIAL
    fam_children = {}
    for ind in inds:
        histid, _, _, _, _, _, relate, serial = ind
        rel_code = str(relate).strip()
        if rel_code in ('03', '3', 'Child'):
            if serial not in fam_children:
                fam_children[serial] = []
            fam_children[serial].append(histid)

    # --- GEDCOM COMPLIANCE FIXES ---
    # Ancestry strictly enforces a 22-character limit on IDs. UUIDs are 36 characters.
    # We build a quick map to assign simple, standard IDs (e.g., I1, I2, F1, F2)
    ind_map = {}
    fam_map = {}
    
    for i, ind in enumerate(inds, 1):
        ind_map[ind[0]] = f"I{i}"
        
    for i, fam in enumerate(fams, 1):
        fam_map[fam[0]] = f"F{i}"

    print(f"Writing strict GEDCOM format to {OUTPUT_GEDCOM}...")
    with open(OUTPUT_GEDCOM, 'w', encoding='utf-8') as f:
        # --- 1. GEDCOM HEADER ---
        f.write("0 HEAD\n")
        f.write("1 SOUR DuckDB_Pipeline\n")
        f.write("1 SUBM @U1@\n")  # Must point to a valid SUBM record
        f.write("1 GEDC\n")
        f.write("2 VERS 5.5.1\n")
        f.write("2 FORM LINEAGE-LINKED\n")
        f.write("1 CHAR UTF-8\n")
        
        # The required Submitter Record
        f.write("0 @U1@ SUBM\n")
        f.write("1 NAME Andy Askey\n")

        # --- 2. INDIVIDUALS (INDI) ---
        for ind in inds:
            histid, first_name, last_name, sex_code, birthyr, bpl_code, relate, serial = ind
            
            mapped_histid = ind_map.get(histid)
            mapped_serial = fam_map.get(serial)

            first_name = first_name if first_name else "Unknown"
            last_name = last_name if last_name else "Unknown"
            sex = 'M' if str(sex_code).strip() == '1' else 'F'

            # Clean the BPL code (IPUMS adds trailing zeros like '4200' for PA)
            clean_bpl = str(bpl_code).strip()
            if len(clean_bpl) > 2 and clean_bpl.endswith("00"):
                clean_bpl = clean_bpl[:-2]
            birth_place = STATE_MAP.get(clean_bpl, f"Code {clean_bpl}")

            rel_code = str(relate).strip()

            f.write(f"0 @{mapped_histid}@ INDI\n")
            f.write(f"1 NAME {first_name} /{last_name}/\n")
            f.write(f"1 SEX {sex}\n")

            if birthyr:
                f.write("1 BIRT\n")
                f.write(f"2 DATE {birthyr}\n")
                if birth_place:
                    f.write(f"2 PLAC {birth_place}\n")

            # Link the individual to the Family record
            if rel_code in ('01', '1', 'Head/householder', '02', '2', 'Spouse'):
                if mapped_serial:
                    f.write(f"1 FAMS @{mapped_serial}@\n")
            elif rel_code in ('03', '3', 'Child'):
                if mapped_serial:
                    f.write(f"1 FAMC @{mapped_serial}@\n")

        # --- 3. FAMILIES (FAM) ---
        for fam in fams:
            serial, head_histid, spouse_histid = fam
            mapped_serial = fam_map.get(serial)
            
            f.write(f"0 @{mapped_serial}@ FAM\n")
            if head_histid:
                f.write(f"1 HUSB @{ind_map.get(head_histid)}@\n")
            if spouse_histid:
                f.write(f"1 WIFE @{ind_map.get(spouse_histid)}@\n")

            if serial in fam_children:
                for child_id in fam_children[serial]:
                    mapped_child_id = ind_map.get(child_id)
                    f.write(f"1 CHIL @{mapped_child_id}@\n")

        # --- 4. GEDCOM TRAILER ---
        f.write("0 TRLR\n")

    print("SUCCESS! GEDCOM ready for Ancestry.")


if __name__ == "__main__":
    main()
