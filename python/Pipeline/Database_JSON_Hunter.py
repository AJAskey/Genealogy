"""
File: Database_JSON_Hunter.py
Summary: Reads a family fingerprint from a JSON file and queries the Master DuckDB Vault
         to find the exact matching household. Returns the same results as the CSV Extractor, 
         but directly from the database!
"""

import duckdb
import json
import os
import pandas as pd
from markdown_it.parser_block import LOGGER

import gen_logging

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"
JSON_FILE = r"E:\Users\Andy\PycharmProjects\Genealogy\JSON\lawrence_askey.json"

# Set to 0 for an exact digital-to-digital match (matching your CSV Extractor logic)
AGE_TOLERANCE = 0


def run_database_hunter():
    if not os.path.exists(MASTER_VAULT_DB):
        logger.info(f"❌ ERROR: Cannot find Master Vault at {MASTER_VAULT_DB}")
        return
    if not os.path.exists(JSON_FILE):
        logger.info(f"❌ ERROR: Cannot find JSON file at {JSON_FILE}")
        return

    # --- PARSE THE JSON FILE ---
    logger.info(f"📂 Loading search criteria from JSON: {JSON_FILE}")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        target_data = json.load(f)

    global_criteria = {}
    if "CENSUSYR" in target_data: global_criteria["YEAR"] = str(target_data["CENSUSYR"])
    if "countyicp" in target_data: global_criteria["COUNTYICP"] = str(target_data["countyicp"])
    if "stateicp" in target_data: global_criteria["STATEICP"] = str(target_data["stateicp"])

    search_profiles = []
    for person in target_data.get("family", []):
        profile = global_criteria.copy()
        if "byr" in person: profile["BIRTHYR"] = str(person["byr"])
        if "age" in person: profile["AGE"] = str(person["age"])
        if "sex" in person: profile["SEX"] = str(person["sex"])

        if person.get("role") == "father":
            if "income" in target_data: profile["INCWAGE"] = str(target_data["income"])
            if "eldch" in target_data: profile["ELDCH"] = str(target_data["eldch"])
            if "yngch" in target_data: profile["YNGCH"] = str(target_data["yngch"])
            if "famsize" in target_data: profile["FAMSIZE"] = str(target_data["famsize"])

        if profile:
            search_profiles.append(profile)

    # --- QUERY THE DATABASE ---
    logger.info(f"🚀 Connecting to Vault and hunting for matching household...")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    # We build a fast SQL query using our global criteria to instantly narrow down the database
    where_clauses = []
    for k, v in global_criteria.items():
        where_clauses.append(f"TRY_CAST({k} AS INTEGER) = {v}")
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    query = f"SELECT * FROM individuals WHERE {where_sql}"
    df = con.execute(query).df()

    logger.info(f"   -> Query returned {len(df):,} individuals from that region. Evaluating households...")

    # --- APPLY THE EXACT SAME RADAR FENCE LOGIC AS THE CSV SCRIPT ---
    match_count = 0

    # We will log the exact reason our known target household fails (if it does!)
    DEBUG_SERIAL = "29978924"

    for serial, group in df.groupby('SERIAL'):
        is_debug = str(serial).replace('.0', '') == DEBUG_SERIAL
        if is_debug:
            print(f"\n[🔍 DEBUG] Found Target Household {serial} with {len(group)} members. Evaluating...")

        matched_profiles = set()
        buffer = group.to_dict('records')

        for r_idx, r in enumerate(buffer):
            row_data = {}
            for k, v in r.items():
                if not k: continue
                if pd.isna(v):
                    row_data[str(k).upper()] = ""
                else:
                    row_data[str(k).upper()] = str(v).strip()

            for i, profile in enumerate(search_profiles):
                if i in matched_profiles: continue

                profile_match = True
                fail_reasons = []

                for col, target_val in profile.items():
                    row_val = row_data.get(col.upper(), "")
                    target_str = str(target_val).strip()

                    try:
                        r_float = float(row_val)
                        t_float = float(target_str)

                        if col.upper() in ('BIRTHYR', 'AGE'):
                            if abs(r_float - t_float) > AGE_TOLERANCE:
                                profile_match = False
                                fail_reasons.append(f"{col} ({r_float} != {t_float})")
                        elif r_float != t_float:
                            profile_match = False
                            fail_reasons.append(f"{col} ({r_float} != {t_float})")
                    except ValueError:
                        if row_val.upper() != target_str.upper():
                            profile_match = False
                            fail_reasons.append(f"{col} ('{row_val}' != '{target_str}')")

                if is_debug:
                    if profile_match:
                        print(f"  -> Row {r_idx} (b.{row_data.get('BIRTHYR')}) MATCHED Profile {i}!")
                    elif len(fail_reasons) > 0:
                        # Only print the first failure reason to keep the console clean
                        print(
                            f"  -> Row {r_idx} (b.{row_data.get('BIRTHYR')}) failed Profile {i} on: {fail_reasons[0]}")

                if profile_match:
                    matched_profiles.add(i)
                    break  # Move to the next row once a match is found

        if is_debug:
            logger.info(f"  -> Total Profiles Matched: {len(matched_profiles)} out of {len(search_profiles)}")

        if len(matched_profiles) == len(search_profiles):
            match_count += 1
            logger.info(f"\n✅ PERFECT MATCH FOUND! Household SERIAL: {serial}")
            cols_to_print = ['YEAR', 'SERIAL', 'RELATE', 'SEX', 'AGE', 'BIRTHYR', 'INCWAGE', 'HISTID', 'HIK']
            logger.info(group[[c for c in cols_to_print if c in group.columns]].to_string(index=False))

    logger.info("\n" + "=" * 60)
    logger.info(f"Total Households Matched: {match_count}")


if __name__ == "__main__":
    logger = gen_logging.setup_logging('DuckTestDDuckHunterr')
    logger.info("=====================================================================")
    logger.info("  DUCKDB Duck Haunter ")
    logger.info("=====================================================================")
    run_database_hunter()
