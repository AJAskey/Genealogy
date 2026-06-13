"""
-----------------------------------
File: GedcomNameOverlay.py

Summary: The "Label-Maker" for the Census-First Architecture.
         Diagnostic Mode Enabled. Reads the manually cleaned ftm_extracted.csv.
         Targeted to 1900 for deep demographic verification.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0: http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy
"""

import csv
import gc
import os
import shutil
import sqlite3
import sys
from collections import defaultdict

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

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
NAMED_VAULT_DIR = os.path.join(BASE_DATA_DIR, "NamedVaults")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
GEDCOM_INPUT_DIR = os.path.join(project_root, "gedcom_sources")

TARGET_DECADE = "1900"  # Lock exactly to the 1900 database for testing
DEBUG_MODE = True       # Enable detailed match logging


def get_bpl_prefixes(birth_place):
    """Translates a free-text location string into standard IPUMS BPL prefixes."""
    if not birth_place: return None
    bp_lower = birth_place.lower()

    crosswalk = {
        "alabama": ["01", "1"], "alaska": ["02", "2"], "arizona": ["04", "4"], "arkansas": ["05", "5"],
        "california": ["06", "6"], "colorado": ["08", "8"], "connecticut": ["09", "9"],
        "delaware": ["10"], "district of columbia": ["11"], "florida": ["12"],
        "georgia": ["13"], "hawaii": ["15"], "idaho": ["16"], "illinois": ["17"],
        "indiana": ["18"], "iowa": ["19"], "kansas": ["20"], "kentucky": ["21"],
        "louisiana": ["22"], "maine": ["23"], "maryland": ["24"], "massachusetts": ["25"],
        "michigan": ["26"], "minnesota": ["27"], "mississippi": ["28"], "missouri": ["29"],
        "montana": ["30"], "nebraska": ["31"], "nevada": ["32"], "new hampshire": ["33"],
        "new jersey": ["34"], "new mexico": ["35"], "new york": ["36"], "north carolina": ["37"],
        "north dakota": ["38"], "ohio": ["39"], "oklahoma": ["40"], "oregon": ["41"],
        "pennsylvania": ["42", "042"], "rhode island": ["44", "044"], "south carolina": ["45", "045"],
        "south dakota": ["46", "046"], "tennessee": ["47", "047"], "texas": ["48", "048"],
        "utah": ["49", "049"], "vermont": ["50", "050"], "virginia": ["51", "051"],
        "washington": ["53", "053"], "west virginia": ["54", "054"], "wisconsin": ["55", "055"],
        "wyoming": ["56", "056"],
        "england": ["410"], "scotland": ["411"], "wales": ["412"],
        "ireland": ["414"], "northern ireland": ["413"],
        "germany": ["453"], "sweden": ["404"], "norway": ["401"],
        "denmark": ["400"], "netherlands": ["425"], "france": ["421"],
        "switzerland": ["426"], "canada": ["150"], "mexico": ["200"],
        "japan": ["501"], "south korea": ["502"], "korea": ["502"]
    }

    for state, prefixes in crosswalk.items():
        if state in bp_lower:
            return prefixes
    return None


def is_bpl_match(db_val, allowed_prefixes):
    """Safely compares IPUMS detailed codes to general base codes using integer math."""
    if not db_val: return False
    db_str = str(db_val).strip()
    for p in allowed_prefixes:
        p_strip = p.lstrip('0')
        if not p_strip: p_strip = p
        
        # Exact match
        if db_str == p_strip or db_str == p: return True
        
        # Handle trailing zeros (e.g. 4200 starts with 42)
        if db_str.startswith(p_strip):
            remainder = db_str[len(p_strip):]
            if remainder != '' and remainder.replace('0', '') == '':
                return True
            # Foreign countries have 3-digit base codes, allow sub-codes
            if len(p_strip) >= 3:
                return True
    return False


def parse_csv_names_and_dates(filepath):
    """Reads the manually-cleaned Family Tree Maker CSV and extracts target individuals."""
    target_individuals = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            first_name = row.get('first_name', '').strip()
            last_name = row.get('last_name', '').strip()
            sex = row.get('sex', '').strip()
            birth_year = row.get('birth_year', '').strip()

            if '--' in first_name or '--' in last_name or 'Hidden' in first_name or 'Hidden' in last_name:
                continue

            if first_name and last_name and sex and birth_year:
                try:
                    byr_int = int(birth_year)
                    if byr_int < 1850: continue
                    target_individuals.append({
                        'first_name': first_name,
                        'last_name': last_name,
                        'sex': sex,
                        'birthyr': byr_int,
                        'bpld': row.get('birth_place', '').strip(),
                        'fbpl': row.get('father_birth_place', '').strip(),
                        'mbpl': row.get('mother_birth_place', '').strip()
                    })
                except ValueError:
                    pass
    return target_individuals


def apply_gedcom_names(logger):
    logger.info("Step 1/4: Preparing the 'Named' Database Vaults...")
    os.makedirs(NAMED_VAULT_DIR, exist_ok=True)

    for filename in os.listdir(VAULT_DIR):
        if filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename:
            src = os.path.join(VAULT_DIR, filename)
            dst = os.path.join(NAMED_VAULT_DIR, filename.replace("YearVault_", "NamedVault_"))
            if not os.path.exists(dst):
                logger.info(f"  -> Copying {filename} to Named Vaults to protect raw data...")
                shutil.copy2(src, dst)
            else:
                logger.info(f"  -> {filename} already copied.")

    logger.info(f"\nStep 2/4: Scanning for CSV files in: {GEDCOM_INPUT_DIR}")
    csv_files = [f for f in os.listdir(GEDCOM_INPUT_DIR) if f.lower().endswith('.csv')]
    if not csv_files:
        logger.warning("  -> No .csv files found! Please drop your exported CSVs in the folder and rerun.")
        return
        
    all_target_individuals = []
    for file in csv_files:
        filepath = os.path.join(GEDCOM_INPUT_DIR, file)
        individuals = parse_csv_names_and_dates(filepath)
        all_target_individuals.extend(individuals)
        logger.info(f"  -> Extracted {len(individuals)} individuals with complete demographics from {file}")

    logger.info("\nStep 3/4: Searching for nameless individuals in the Named Vaults...")

    logger.info("  -> Loading Clan Mappings from the Time Machine...")
    try:
        with sqlite3.connect(MATCH_DB) as sq_conn:
            clan_map = {row[0]: row[1] for row in
                        sq_conn.execute("SELECT family_id, clan_id FROM clan_mapping").fetchall()}
        logger.info(f"  -> Loaded {len(clan_map):,} family-to-clan links.")
    except sqlite3.OperationalError:
        logger.warning("  -> MATCH_DB not found! Clan consolidation disabled.")
        clan_map = {}

    target_matches = {
        i: {
            'ind': ind,
            'results': [],
            'clans': set(),
            'unclanned': set(),
            'too_many': False,
            'target_sex': ind['sex'],
            'target_byr': ind['birthyr'],
            'bpl_prefixes': get_bpl_prefixes(ind['bpld']),
            'fbpl_prefixes': get_bpl_prefixes(ind['fbpl']),
            'mbpl_prefixes': get_bpl_prefixes(ind['mbpl'])
        } for i, ind in enumerate(all_target_individuals)
    }

    # Loop through the decades ONE AT A TIME
    for filename in os.listdir(NAMED_VAULT_DIR):
        if not (filename.startswith("NamedVault_") and filename.endswith(".db")):
            continue
            
        if TARGET_DECADE and TARGET_DECADE not in filename:
            continue

        db_path = os.path.join(NAMED_VAULT_DIR, filename)
        logger.info(f"  -> Loading nameless individuals from {filename} into memory...")
        with sqlite3.connect(db_path) as conn:
            bosselstinks = conn.execute("""
                SELECT histid, family_id, sex, birthyr, bpld, fbpl, mbpl
                FROM individuals
                WHERE last_name = 'Bosselstink'
                  AND first_name = 'Future'
                  AND birthyr IS NOT NULL
            """).fetchall()

        logger.info(f"     Building memory index for {len(bosselstinks):,} records...")
        mem_index = defaultdict(list)
        for row in bosselstinks:
            mem_index[(row[2], row[3])].append(row)

        logger.info(f"     Matching targets against {filename}...")
        for i, match_data in target_matches.items():
            if match_data['too_many']:
                continue

            ind = match_data['ind']
            t_sex = match_data['target_sex']
            t_byr = match_data['target_byr']
            bpl_pref = match_data['bpl_prefixes']
            fbpl_pref = match_data['fbpl_prefixes']
            mbpl_pref = match_data['mbpl_prefixes']

            debug_print = DEBUG_MODE and i < 50
            
            if debug_print:
                logger.info(f"\n[SEARCHING] {ind['first_name']} {ind['last_name']} (b. {ind['birthyr']})")
                logger.info(f"   Target Needs -> Sex: {t_sex} | BYR: {t_byr} (+/-2) | BPL: {bpl_pref} | FBPL: {fbpl_pref} | MBPL: {mbpl_pref}")

            matches_this_decade = 0
            
            for offset in range(-2, 3):
                key = (t_sex, t_byr + offset)
                if key in mem_index:
                    for db_row in mem_index[key]:
                        db_bpld, db_fbpl, db_mbpl = db_row[4], db_row[5], db_row[6]
                        
                        if bpl_pref:
                            if not is_bpl_match(db_bpld, bpl_pref): continue
                        if fbpl_pref:
                            if not is_bpl_match(db_fbpl, fbpl_pref): continue
                        if mbpl_pref:
                            if not is_bpl_match(db_mbpl, mbpl_pref): continue

                        histid, fam_id = db_row[0], db_row[1]
                        clan_id = clan_map.get(fam_id)
                        if clan_id:
                            match_data['clans'].add(clan_id)
                        else:
                            match_data['unclanned'].add((histid, fam_id))

                        match_data['results'].append(db_row)
                        matches_this_decade += 1
                        
                        if debug_print and matches_this_decade <= 5:
                            bpl_stat = "Math Match" if bpl_pref else "Wildcard (CSV Blank)"
                            fbpl_stat = "Math Match" if fbpl_pref else "Wildcard (CSV Blank)"
                            mbpl_stat = "Math Match" if mbpl_pref else "Wildcard (CSV Blank)"
                            logger.info(f"   [MATCH FOUND] DB_BYR: {db_row[3]} | DB_BPL: {db_bpld} [{bpl_stat}] | DB_FBPL: {db_fbpl} [{fbpl_stat}] | DB_MBPL: {db_mbpl} [{mbpl_stat}]")

            if debug_print and matches_this_decade > 5:
                logger.info(f"   ... and {matches_this_decade - 5} more matches found in this decade.")
            elif debug_print and matches_this_decade == 0:
                logger.info(f"   [NO MATCH FOUND] Zero records matched these demographics in {filename}.")

            # Enforce the cap immediately
            total_entities = len(match_data['clans']) + len(match_data['unclanned'])
            if total_entities > 20:
                match_data['too_many'] = True
                match_data['results'] = []
                match_data['clans'].clear()
                match_data['unclanned'].clear()
                if debug_print:
                    logger.warning(f"   [ABORTED] Surpassed 20 matches. Flagged as 'Too Many'.")

        del bosselstinks
        del mem_index
        gc.collect()

    logger.info("\n  -> Evaluating Final Couple Matches Across All Decades...")
    update_queue_by_year = defaultdict(list)
    multiple_count = 0
    too_many_count = 0
    zero_count = 0
    success_count = 0

    clans_to_update = {}
    unclanned_to_update = {}

    for match_data in target_matches.values():
        fam = match_data['fam']
        h_name = f"{fam['h_first']} {fam['h_last']}"
        w_name = f"{fam['w_first']} {fam['w_last']}"

        if match_data['too_many']:
            too_many_count += 1
            continue

        total_unique_entities = len(match_data['clans']) + len(match_data['unclanned'])

        if total_unique_entities == 1:
            success_count += 1
            if len(match_data['clans']) == 1:
                clans_to_update[list(match_data['clans'])[0]] = fam
            else:
                unclanned_to_update[list(match_data['unclanned'])[0]] = fam

        elif total_unique_entities > 1:
            logger.warning(f"  [MULTIPLE] Found {total_unique_entities} distinct families for Couple: {h_name} & {w_name}. Flagging as 'Multiple'.")
            multiple_count += 1
        else:
            zero_count += 1

    logger.info(f"\nLookup Complete:")
    logger.info(f"  -> Perfect Unique Anchors Found: {success_count:,}")
    logger.info(f"  -> Multiple Matches Flagged (<20): {multiple_count:,}")
    logger.info(f"  -> Too Many Matches (Skipped): {too_many_count:,}")
    logger.info(f"  -> Zero Matches (Skipped): {zero_count:,}")

    # DECISION: The Living Room Sweep
    if clans_to_update or unclanned_to_update:
        logger.info("\n  -> Resolving 'Time Machine Echoes' & Sweeping Living Rooms...")
        for filename in os.listdir(NAMED_VAULT_DIR):
            if not (filename.startswith("NamedVault_") and filename.endswith(".db")): continue
            year_prefix = filename.replace("NamedVault_", "").replace(".db", "")
            
            if TARGET_DECADE and TARGET_DECADE != year_prefix: continue

            with sqlite3.connect(os.path.join(NAMED_VAULT_DIR, filename)) as conn:
                rows = conn.execute("""
                    SELECT i.histid, f.family_id, i.sex, i.birthyr, f.head_histid, f.spouse_histid
                    FROM individuals i
                    JOIN families f ON i.family_id = f.family_id
                    WHERE i.last_name = 'Bosselstink' AND i.first_name = 'Future'
                """).fetchall()

                for histid, fam_id, sex, byr, head_id, spouse_id in rows:
                    t_fam = None
                    c_id = clan_map.get(fam_id)
                    if c_id and c_id in clans_to_update:
                        t_fam = clans_to_update[c_id]
                    elif fam_id in unclanned_to_update:
                        t_fam = unclanned_to_update[fam_id]
                        
                    if t_fam:
                        if histid == head_id:
                            update_queue_by_year[year_prefix].append((t_fam['h_first'], t_fam['h_last'], histid))
                        elif histid == spouse_id:
                            update_queue_by_year[year_prefix].append((t_fam['w_first'], t_fam['w_last'], histid))

    logger.info(f"\nStep 4/4: Applying historical names to the census records...")
    for year, q in update_queue_by_year.items():
        if not q: continue
        db_path = os.path.join(NAMED_VAULT_DIR, f"NamedVault_{year}.db")
        if os.path.exists(db_path):
            logger.info(f"  -> Executing {len(q):,} updates in {year}...")
            with sqlite3.connect(db_path) as sqlite_conn:
                sqlite_conn.execute("PRAGMA journal_mode=WAL")
                sqlite_conn.executemany("UPDATE individuals SET first_name = ?, last_name = ? WHERE histid = ?", q)
                sqlite_conn.commit()

    logger.info("\nSUCCESS! CSV Name Overlay complete.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="NAME_OVERLAY")
    apply_gedcom_names(main_logger)
