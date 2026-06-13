"""
-----------------------------------
File: GedcomNameOverlay.py

Summary: The "Label-Maker" for the Census-First Architecture.
         Diagnostic Mode Enabled. Reads the flattened ftm_couples.csv.
         Targeted to 1900 for deep demographic verification using the
         unbreakable 10-Variable Couple Anchor.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0: http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy
-----------------------------------
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

# ==============================================================================
# DIAGNOSTIC MODE SETTINGS
# ==============================================================================
TARGET_DECADE = "1900"  # Lock exactly to the 1900 database for testing
DEBUG_MODE = True  # Enable highly detailed match logging


# ==============================================================================

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
    """Reads the flattened Couples CSV and extracts target families."""
    target_couples = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            h_first = row.get('h_first', '').strip()
            w_first = row.get('w_first', '').strip()

            if '--' in h_first or '--' in w_first or 'Hidden' in h_first or 'Hidden' in w_first or '[' in h_first or '[' in w_first:
                continue

            h_byr_str = row.get('h_byr', '').strip()
            w_byr_str = row.get('w_byr', '').strip()

            if not h_byr_str or not w_byr_str:
                continue

            try:
                target_couples.append({
                    'h_first': h_first,
                    'h_last': row.get('h_last', '').strip(),
                    'h_byr': int(h_byr_str) if h_byr_str.isdigit() else None,
                    'h_bpl': row.get('h_bpl', '').strip(),
                    'h_fbpl': row.get('h_fbpl', '').strip(),
                    'h_mbpl': row.get('h_mbpl', '').strip(),

                    'w_first': w_first,
                    'w_last': row.get('w_last', '').strip(),
                    'w_byr': int(w_byr_str) if w_byr_str.isdigit() else None,
                    'w_bpl': row.get('w_bpl', '').strip(),
                    'w_fbpl': row.get('w_fbpl', '').strip(),
                    'w_mbpl': row.get('w_mbpl', '').strip(),

                    'num_children': int(row.get('num_children', 0) or 0)
                })
            except ValueError:
                pass
    return target_couples


def apply_gedcom_names(logger):
    logger.info("Step 1/4: Preparing the 'Named' Database Vaults...")
    os.makedirs(NAMED_VAULT_DIR, exist_ok=True)

    for filename in os.listdir(VAULT_DIR):
        if filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename:
            # Diagnostic mode: Only process the target decade
            if TARGET_DECADE and TARGET_DECADE not in filename:
                continue

            src = os.path.join(VAULT_DIR, filename)
            dst = os.path.join(NAMED_VAULT_DIR, filename.replace("YearVault_", "NamedVault_"))

            if not os.path.exists(dst):
                logger.info(f"  -> Copying {filename} to Named Vaults to protect raw data...")
                shutil.copy2(src, dst)
            else:
                logger.info(f"  -> {filename} already copied.")

    logger.info(f"\nStep 2/4: Scanning for CSV files in: {GEDCOM_INPUT_DIR}")
    csv_files = [f for f in os.listdir(GEDCOM_INPUT_DIR) if f.lower() == 'ftm_couples.csv']
    if not csv_files:
        logger.warning("  -> ftm_couples.csv not found! Please run ftm_report_to_csv.py first.")
        return

    all_target_couples = []
    for file in csv_files:
        filepath = os.path.join(GEDCOM_INPUT_DIR, file)
        couples = parse_csv_names_and_dates(filepath)
        all_target_couples.extend(couples)
        logger.info(f"  -> Extracted {len(couples)} target couples for 10-Variable Anchoring from {file}")

    logger.info("\nStep 3/4: Searching for nameless couples in the Named Vaults...")

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
            'fam': fam,
            'results': [],
            'clans': set(),
            'unclanned': set(),
            'too_many': False,

            'h_sex': '1',  # Male
            'h_byr': fam['h_byr'],
            'h_bpl_pref': get_bpl_prefixes(fam['h_bpl']),
            'h_fbpl_pref': get_bpl_prefixes(fam['h_fbpl']),
            'h_mbpl_pref': get_bpl_prefixes(fam['h_mbpl']),

            'w_sex': '2',  # Female
            'w_byr': fam['w_byr'],
            'w_bpl_pref': get_bpl_prefixes(fam['w_bpl']),
            'w_fbpl_pref': get_bpl_prefixes(fam['w_fbpl']),
            'w_mbpl_pref': get_bpl_prefixes(fam['w_mbpl']),

            'num_children': fam.get('num_children', 0)
        } for i, fam in enumerate(all_target_couples)
    }

    # Loop through the decades ONE AT A TIME
    for filename in os.listdir(NAMED_VAULT_DIR):
        if not (filename.startswith("NamedVault_") and filename.endswith(".db")):
            continue

        if TARGET_DECADE and TARGET_DECADE not in filename:
            continue

        db_path = os.path.join(NAMED_VAULT_DIR, filename)
        logger.info(f"  -> Loading nameless couples from {filename} into memory...")
        with sqlite3.connect(db_path) as conn:
            bosselstinks = conn.execute("""
                                        SELECT f.family_id,
                                               h.histid,
                                               h.sex,
                                               h.birthyr,
                                               h.bpld,
                                               h.fbpl,
                                               h.mbpl,
                                               s.histid,
                                               s.sex,
                                               s.birthyr,
                                               s.bpld,
                                               s.fbpl,
                                               s.mbpl
                                        FROM families f
                                                 JOIN individuals h ON f.head_histid = h.histid
                                                 JOIN individuals s ON f.spouse_histid = s.histid
                                        WHERE h.last_name = 'Bosselstink'
                                          AND h.first_name = 'Future'
                                          AND h.birthyr IS NOT NULL
                                          AND s.birthyr IS NOT NULL
                                        """).fetchall()

        logger.info(f"     Building memory index for {len(bosselstinks):,} couples...")
        mem_index = defaultdict(list)
        for row in bosselstinks:
            mem_index[(row[3], row[9])].append(row)  # Index by H_BYR, W_BYR

        logger.info(f"     Matching targets against {filename}...")

        for i, match_data in target_matches.items():
            if match_data['too_many'] or not match_data['h_byr'] or not match_data['w_byr']:
                continue

            # Print diagnostic info for the first 50 people
            debug_print = DEBUG_MODE and i < 50

            if debug_print:
                h_name = f"{match_data['fam']['h_first']} {match_data['fam']['h_last']}"
                w_name = f"{match_data['fam']['w_first']} {match_data['fam']['w_last']}"
                logger.info(
                    f"\n[SEARCHING] Couple: {h_name} (b. {match_data['h_byr']}) & {w_name} (b. {match_data['w_byr']}) | Kids: {match_data['num_children']}")
                logger.info(
                    f"   HUSB Needs -> BPL: {match_data['h_bpl_pref']} | FBPL: {match_data['h_fbpl_pref']} | MBPL: {match_data['h_mbpl_pref']}")
                logger.info(
                    f"   WIFE Needs -> BPL: {match_data['w_bpl_pref']} | FBPL: {match_data['w_fbpl_pref']} | MBPL: {match_data['w_mbpl_pref']}")

            matches_this_decade = 0

            # DECISION: Two-Pass Age Strategy. Try exact birth years first.
            # If no match is found, expand to a +/- 2 year window.
            pass_configs = [
                [(0, 0)],
                [(h, w) for h in range(-2, 3) for w in range(-2, 3) if not (h == 0 and w == 0)]
            ]

            for offsets in pass_configs:
                if matches_this_decade > 0:
                    break
                
                for h_off, w_off in offsets:
                    key = (match_data['h_byr'] + h_off, match_data['w_byr'] + w_off)
                    if key in mem_index:
                        for db_row in mem_index[key]:
                            db_h_bpld, db_h_fbpl, db_h_mbpl = db_row[4], db_row[5], db_row[6]
                            db_w_bpld, db_w_fbpl, db_w_mbpl = db_row[10], db_row[11], db_row[12]

                            # Check Sex
                            if match_data['h_sex'] and db_row[2] != match_data['h_sex']: continue
                            if match_data['w_sex'] and db_row[8] != match_data['w_sex']: continue

                            # Check BPLs for Husband
                            if match_data['h_bpl_pref'] and not is_bpl_match(db_h_bpld,
                                                                             match_data['h_bpl_pref']): continue
                            if match_data['h_fbpl_pref'] and not is_bpl_match(db_h_fbpl,
                                                                              match_data['h_fbpl_pref']): continue
                            if match_data['h_mbpl_pref'] and not is_bpl_match(db_h_mbpl,
                                                                              match_data['h_mbpl_pref']): continue

                            # Check BPLs for Wife
                            if match_data['w_bpl_pref'] and not is_bpl_match(db_w_bpld,
                                                                             match_data['w_bpl_pref']): continue
                            if match_data['w_fbpl_pref'] and not is_bpl_match(db_w_fbpl,
                                                                              match_data['w_fbpl_pref']): continue
                            if match_data['w_mbpl_pref'] and not is_bpl_match(db_w_mbpl,
                                                                              match_data['w_mbpl_pref']): continue

                            fam_id = db_row[0]
                            clan_id = clan_map.get(fam_id)

                            if clan_id:
                                match_data['clans'].add(clan_id)
                            else:
                                match_data['unclanned'].add(fam_id)

                            match_data['results'].append(db_row)
                            matches_this_decade += 1

                            if debug_print and matches_this_decade <= 5:
                                logger.info(f"   [MATCH FOUND] H_BYR={db_row[3]} W_BYR={db_row[9]} | FamID: {fam_id}")

            if debug_print and matches_this_decade > 5:
                logger.info(f"   ... and {matches_this_decade - 5} more matches found in this decade.")
            elif debug_print and matches_this_decade == 0:
                logger.info(f"   [NO MATCH FOUND] Zero records matched these demographics in {filename}.")

            # Enforce the cap immediately
            total_entities = len(match_data['clans']) + len(match_data['unclanned'])
            if total_entities > 20:
                match_data['too_many'] = True
                match_data['results'] = []  # Dump the array from RAM
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
    flagged_multiples = set()

    for match_data in target_matches.values():
        fam = match_data['fam']
        h_name = f"{fam['h_first']} {fam['h_last']}"
        w_name = f"{fam['w_first']} {fam['w_last']}"

        if match_data['too_many'] or not match_data['h_byr'] or not match_data['w_byr']:
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
            logger.warning(
                f"  [MULTIPLE] Found {total_unique_entities} distinct families for Couple: {h_name} & {w_name}. Flagging as 'Multiple'.")
            multiple_count += 1
            for db_row in match_data['results']:
                histid_h, histid_w, fam_id = db_row[1], db_row[7], db_row[0]
                if histid_h not in flagged_multiples:
                    update_queue_by_year[fam_id.split('_')[0]].append(('Multiple', 'Bosselstink', histid_h))
                    flagged_multiples.add(histid_h)
                if histid_w not in flagged_multiples:
                    update_queue_by_year[fam_id.split('_')[0]].append(('Multiple', 'Bosselstink', histid_w))
                    flagged_multiples.add(histid_w)
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
                                    WHERE i.last_name = 'Bosselstink'
                                      AND i.first_name = 'Future'
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
