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
import duckdb
import pandas as pd

from project_globals import CODEBOOK

# ==============================================================================
# CONFIGURATION
# ==============================================================================
MASTER_100_DB = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"
MASTER_SAMP_DB = r"D:\Data\Genealogy_Data\MasterVault_ALLs.db"
CLEAN_DB = r"D:\Data\Genealogy_Data\CleanVault.db"
OUTPUT_GED = r"E:\Users\Andy\PycharmProjects\Genealogy\output\census_all_export.ged"

# Limit the number of Golden Records to export for testing purposes
EXPORT_LIMIT = 5000


# ==============================================================================
# MAPPING HELPERS
# ==============================================================================
def map_sex(ipums_sex):
    """Map IPUMS SEX to GEDCOM SEX."""
    ipums_sex = str(ipums_sex).strip()
    if ipums_sex == '1':
        return 'M'
    elif ipums_sex == '2':
        return 'F'
    return 'U'  # Unknown


def format_name(first, last):
    """Format name for GEDCOM standard: First /Last/."""
    first = str(first).strip() if pd.notna(first) else ""
    last = str(last).strip() if pd.notna(last) else ""
    if not first and not last:
        return "Unknown"
    return f"{first} /{last}/".strip()


# ==============================================================================
# GEDCOM EXPORTER
# ==============================================================================
def export_to_gedcom(output_path, limit=None, is_test=False):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print("Initializing DuckDB Engine...")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='90GB'")
    con.execute("INSTALL sqlite; LOAD sqlite;")

    if is_test:
        print("*** RUNNING IN TEST MODE ***")
        base_db = r"D:\Data\Genealogy_Data\MasterVault_TEST.db"
        samp_db = r"D:\Data\Genealogy_Data\MasterVault_TEST.db"
    else:
        base_db = MASTER_100_DB
        samp_db = MASTER_SAMP_DB

    print("Attaching Vaults...")
    con.execute(f"ATTACH '{CLEAN_DB}' AS clean (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{base_db}' AS base (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{samp_db}' AS samp (TYPE SQLITE, READ_ONLY);")

    limit_clause = f"LIMIT {limit}" if limit else ""
    
    print("Unpacking St. Joe's IDs and fetching historical timelines...")
    query = f"""
        WITH target_golden AS (
            SELECT * FROM clean.golden_records 
            {limit_clause}
        )
        SELECT 
            g.golden_id, g.first_name, g.last_name, g.birth_year, g.birth_place, g.death_date,
            c.composite_id, c.year, c.age, c.sex, c.serial, c.pernum, c.reel, c.pageno, c.line, c.microseq, c.stateicp
        FROM target_golden g
        CROSS JOIN UNNEST(string_split(g.vault_pointers, '|')) AS t(comp_id)
        JOIN (
            SELECT composite_id, year, age, sex, serial, pernum, reel, pageno, line, microseq, stateicp FROM base.population
            UNION ALL
            SELECT composite_id, year, age, sex, serial, pernum, reel, pageno, line, microseq, stateicp FROM samp.population
        ) c ON t.comp_id = c.composite_id
        ORDER BY g.golden_id, c.year ASC;
    """
    
    df = con.execute(query).df()
    print(f"Loaded {len(df)} historical events. Generating GEDCOM...")
    
    if df.empty:
        print("No records found. Exiting.")
        return
        
    print("Mapping family relationships...")
    exported_ids_tuple = tuple(df['golden_id'].unique())
    if len(exported_ids_tuple) == 1:
        exported_ids_sql = f"('{exported_ids_tuple[0]}')"
    else:
        exported_ids_sql = str(exported_ids_tuple)

    rel_query = f"""
        WITH unnested AS (
            SELECT golden_id, UNNEST(string_split(vault_pointers, '|')) AS comp_id
            FROM clean.golden_records
        )
        SELECT 
            g.golden_id AS child_id,
            f.golden_id AS father_id,
            m.golden_id AS mother_id
        FROM clean.golden_records g
        LEFT JOIN unnested f ON g.father_pointer = f.comp_id
        LEFT JOIN unnested m ON g.mother_pointer = m.comp_id
        WHERE g.golden_id IN {exported_ids_sql}
          AND (f.golden_id IS NOT NULL OR m.golden_id IS NOT NULL)
    """
    rel_df = con.execute(rel_query).df()

    families = {}
    for _, row in rel_df.iterrows():
        child_id = row['child_id']
        father_id = row['father_id'] if pd.notna(row['father_id']) else None
        mother_id = row['mother_id'] if pd.notna(row['mother_id']) else None
        
        if father_id not in exported_ids_tuple: father_id = None
        if mother_id not in exported_ids_tuple: mother_id = None
        
        if not father_id and not mother_id:
            continue
            
        fam_key = (father_id, mother_id)
        if fam_key not in families:
            families[fam_key] = []
        families[fam_key].append(child_id)
        
    fam_id_counter = 1
    indi_links = {}
    fam_records = {}

    for (father_id, mother_id), children in families.items():
        fam_id = f"@F{fam_id_counter}@"
        fam_id_counter += 1
        
        fam_tags = []
        if father_id:
            fam_tags.append(f"1 HUSB @{father_id}@\n")
            indi_links.setdefault(father_id, []).append(f"1 FAMS {fam_id}\n")
        if mother_id:
            fam_tags.append(f"1 WIFE @{mother_id}@\n")
            indi_links.setdefault(mother_id, []).append(f"1 FAMS {fam_id}\n")
            
        for child_id in children:
            fam_tags.append(f"1 CHIL @{child_id}@\n")
            indi_links.setdefault(child_id, []).append(f"1 FAMC {fam_id}\n")
            
        fam_records[fam_id] = fam_tags

    now = datetime.datetime.now()

    with open(output_path, 'w', encoding='utf-8') as f:
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
        f.write("0 @SUBM1@ SUBM\n")
        f.write("1 NAME Andy Askey\n")

        for golden_id, group in df.groupby("golden_id"):
            core = group.iloc[0]
            
            f.write(f"0 @{golden_id}@ INDI\n")
            
            name = format_name(core['first_name'], core['last_name'])
            f.write(f"1 NAME {name}\n")

            sex_val = core.get('sex')
            sex_code = map_sex(sex_val) if pd.notna(sex_val) else 'U'
            f.write(f"1 SEX {sex_code}\n")

            if pd.notna(core['birth_year']) or pd.notna(core['birth_place']):
                f.write("1 BIRT\n")
                if pd.notna(core['birth_year']):
                    f.write(f"2 DATE ABT {int(core['birth_year'])}\n")
                if pd.notna(core['birth_place']):
                    f.write(f"2 PLAC {core['birth_place']}\n")
                    
            if pd.notna(core['death_date']):
                f.write("1 DEAT\n")
                f.write(f"2 DATE {core['death_date']}\n")

            for _, event in group.iterrows():
                year = str(event['year']).strip() if pd.notna(event['year']) else ""
                age = str(event['age']).strip() if pd.notna(event['age']) else ""
                serial = str(event['serial']).strip() if pd.notna(event['serial']) else ""
                pernum = str(event['pernum']).strip() if pd.notna(event['pernum']) else ""
                reel = str(event['reel']).strip() if pd.notna(event['reel']) else ""
                pageno = str(event['pageno']).strip() if pd.notna(event['pageno']) else ""
                line = str(event['line']).strip() if pd.notna(event['line']) else ""
                comp_id = str(event['composite_id']).strip()
                
                state_code = str(event['stateicp']).strip() if pd.notna(event['stateicp']) else ""
                place = CODEBOOK.get_code_value("STATEICP", state_code) or "USA"
                
                f.write("1 CENS\n")
                if year: f.write(f"2 DATE {year}\n")
                if place: f.write(f"2 PLAC {place}\n")
                
                f.write("2 SOUR @S1@\n")
                
                page_parts = [p for p in [f"Serial: {serial}", f"Person: {pernum}", f"Reel: {reel}", f"Page: {pageno}", f"Line: {line}"] if not p.endswith(": ")]
                if page_parts:
                    f.write(f"3 PAGE {', '.join(page_parts)}\n")
                
                if age:
                    f.write("3 DATA\n")
                    f.write(f"4 TEXT Age in census: {age}\n")
                    
                f.write(f"1 REFN {comp_id}\n")
                f.write("2 TYPE ST_JOES_ID\n")

            if golden_id in indi_links:
                for link in indi_links[golden_id]:
                    f.write(link)

        for fam_id, tags in fam_records.items():
            f.write(f"0 {fam_id} FAM\n")
            for tag in tags:
                f.write(tag)

        f.write("0 @S1@ SOUR\n")
        f.write("1 TITL U.S. Federal Census\n")
        f.write("1 PUBL National Archives and Records Administration\n")
        f.write("0 TRLR\n")

    print(f"GEDCOM export complete: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export database to GEDCOM")
    parser.add_argument("--out", default=OUTPUT_GED, help="Output GEDCOM file path")
    parser.add_argument("--limit", type=int, default=EXPORT_LIMIT, help="Max number of Golden Records to export")
    parser.add_argument("--test", action="store_true", help="Run against MasterVault_TEST.db")
    args = parser.parse_args()

    export_to_gedcom(args.out, args.limit, args.test)
