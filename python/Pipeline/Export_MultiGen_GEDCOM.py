"""
File: Export_MultiGen_GEDCOM.py

Summary: Uses the IPUMS Crosswalk to stitch individuals together across 
         multiple decades. Outputs a multi-generational GEDCOM 5.5.1 file.
"""

import duckdb
import os

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Test_DuckDB_Vault.db"
CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"
OUTPUT_GEDCOM = r"C:\tempc\ShortTermCSVfiles\multigen_census.ged"

STATE_MAP = {
    "42": "Pennsylvania, USA", "39": "Ohio, USA", "36": "New York, USA",
    "17": "Illinois, USA", "18": "Indiana, USA", "34": "New Jersey, USA",
    "24": "Maryland, USA", "54": "West Virginia, USA", "51": "Virginia, USA",
    "25": "Massachusetts, USA"
}

def main():
    print(f"Connecting to Test Vault: {MASTER_VAULT_DB}...")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)
    
    print(f"Attaching Crosswalk Time Machine...")
    con.execute(f"ATTACH '{CROSSWALK_DB}' AS cw (READ_ONLY);")

    print("Mapping all HISTIDs to their eternal Crosswalk IDs (HIK)...")
    con.execute("""
        CREATE TEMP TABLE vault_hiks AS
        WITH all_histids AS (
            SELECT DISTINCT HISTID FROM individuals
        ),
        cw_unpivoted AS (
            SELECT TRIM(histid_1850) AS histid, HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1850)) > 5
            UNION ALL SELECT TRIM(histid_1860), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1860)) > 5
            UNION ALL SELECT TRIM(histid_1870), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1870)) > 5
            UNION ALL SELECT TRIM(histid_1880), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1880)) > 5
            UNION ALL SELECT TRIM(histid_1900), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1900)) > 5
            UNION ALL SELECT TRIM(histid_1910), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1910)) > 5
            UNION ALL SELECT TRIM(histid_1920), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1920)) > 5
            UNION ALL SELECT TRIM(histid_1930), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1930)) > 5
            UNION ALL SELECT TRIM(histid_1940), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1940)) > 5
            UNION ALL SELECT TRIM(histid_1950), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1950)) > 5
        )
        SELECT a.HISTID, COALESCE(c.HIK, a.HISTID) AS HIK
        FROM all_histids a
        LEFT JOIN cw_unpivoted c ON UPPER(TRIM(a.HISTID)) = UPPER(c.histid);
    """)

    print("Extracting Unified Individuals across all decades...")
    inds = con.execute("""
        SELECT 
            v.HIK, 
            MAX(i.first_name) AS first_name, 
            MAX(i.last_name) AS last_name, 
            MAX(i.SEX) AS SEX, 
            MIN(i.BIRTHYR) AS BIRTHYR, 
            MAX(i.BPL) AS BPL
        FROM individuals i
        JOIN vault_hiks v ON i.HISTID = v.HISTID
        GROUP BY v.HIK
    """).fetchall()

    print("Extracting Families across all decades...")
    fams = con.execute("""
        SELECT 
            f.YEAR || '_' || f.SERIAL AS fam_id,
            vh.HIK AS head_hik,
            vs.HIK AS spouse_hik
        FROM families f
        LEFT JOIN vault_hiks vh ON f.head_histid = vh.HISTID
        LEFT JOIN vault_hiks vs ON f.spouse_histid = vs.HISTID
    """).fetchall()

    print("Mapping children to multi-generational families...")
    children = con.execute("""
        SELECT 
            i.YEAR || '_' || i.SERIAL AS fam_id,
            v.HIK AS child_hik
        FROM individuals i
        JOIN vault_hiks v ON i.HISTID = v.HISTID
        WHERE i.RELATE IN ('03', '3', 'Child')
    """).fetchall()

    # Build linking dictionaries
    fam_children = {}
    ind_fams = {}  # Families where this person is a spouse/head
    ind_famc = {}  # Families where this person is a child

    for child in children:
        fam_id, child_hik = child
        fam_children.setdefault(fam_id, []).append(child_hik)
        ind_famc.setdefault(child_hik, []).append(fam_id)

    for fam in fams:
        fam_id, head_hik, spouse_hik = fam
        if head_hik:
            ind_fams.setdefault(head_hik, []).append(fam_id)
        if spouse_hik:
            ind_fams.setdefault(spouse_hik, []).append(fam_id)

    # Create simple 22-character limit GEDCOM IDs
    ind_map = {ind[0]: f"I{i}" for i, ind in enumerate(inds, 1)}
    fam_map = {fam[0]: f"F{i}" for i, fam in enumerate(fams, 1)}

    print(f"Writing Multi-Generational GEDCOM to {OUTPUT_GEDCOM}...")
    with open(OUTPUT_GEDCOM, 'w', encoding='utf-8') as f:
        # --- 1. GEDCOM HEADER ---
        f.write("0 HEAD\n")
        f.write("1 SOUR DuckDB_Pipeline\n")
        f.write("1 SUBM @U1@\n")
        f.write("1 GEDC\n")
        f.write("2 VERS 5.5.1\n")
        f.write("2 FORM LINEAGE-LINKED\n")
        f.write("1 CHAR UTF-8\n")
        
        f.write("0 @U1@ SUBM\n")
        f.write("1 NAME Andy Askey\n")

        # --- 2. INDIVIDUALS (INDI) ---
        for ind in inds:
            hik, first_name, last_name, sex_code, birthyr, bpl_code = ind
            mapped_hik = ind_map.get(hik)

            first_name = first_name if first_name else "Unknown"
            last_name = last_name if last_name else "Unknown"
            sex = 'M' if str(sex_code).strip() == '1' else 'F'

            clean_bpl = str(bpl_code).strip()
            if len(clean_bpl) > 2 and clean_bpl.endswith("00"):
                clean_bpl = clean_bpl[:-2]
            birth_place = STATE_MAP.get(clean_bpl, f"Code {clean_bpl}")

            f.write(f"0 @{mapped_hik}@ INDI\n")
            f.write(f"1 NAME {first_name} /{last_name}/\n")
            f.write(f"1 SEX {sex}\n")

            if birthyr:
                f.write("1 BIRT\n")
                f.write(f"2 DATE {birthyr}\n")
                if birth_place:
                    f.write(f"2 PLAC {birth_place}\n")

            # Add the HIK as a searchable Reference Number in the GEDCOM
            f.write(f"1 REFN {hik}\n")

            # Link to Spouse Families
            if hik in ind_fams:
                for fam_id in set(ind_fams[hik]):
                    f.write(f"1 FAMS @{fam_map.get(fam_id)}@\n")
            
            # Link to Child Families (The Grandparent Link!)
            if hik in ind_famc:
                for fam_id in set(ind_famc[hik]):
                    f.write(f"1 FAMC @{fam_map.get(fam_id)}@\n")

        # --- 3. FAMILIES (FAM) ---
        for fam in fams:
            fam_id, head_hik, spouse_hik = fam
            mapped_fam = fam_map.get(fam_id)
            
            f.write(f"0 @{mapped_fam}@ FAM\n")
            if head_hik:
                f.write(f"1 HUSB @{ind_map.get(head_hik)}@\n")
            if spouse_hik:
                f.write(f"1 WIFE @{ind_map.get(spouse_hik)}@\n")

            if fam_id in fam_children:
                for child_hik in set(fam_children[fam_id]):
                    f.write(f"1 CHIL @{ind_map.get(child_hik)}@\n")

        # --- 4. GEDCOM TRAILER ---
        f.write("0 TRLR\n")

    print("SUCCESS! Multi-Generational GEDCOM ready for Ancestry.")

if __name__ == "__main__":
    main()