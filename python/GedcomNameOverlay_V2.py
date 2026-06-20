"""
-----------------------------------
File: GedcomNameOverlay_V2.py
Summary: The V2 "Label-Maker" for the Census-First Architecture.
         Reads a pre-processed JSON list of GEDCOM couples.
         Uses DuckDB to enforce a strict "Dead Weight" filter,
         dropping millions of unmarried/irrelevant records before
         executing a native 1-to-1 Highlander match.
Architect & Designer: Andy Askey
Coders (AI Assistants): Gemini Code Assist
-----------------------------------
"""

import json
import os
import sys
import duckdb

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging
from utils.common_utils import get_bpl_prefixes

# --- Configuration ---
if os.path.exists(r"d:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
elif os.path.exists(r"D:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

NAMED_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
TEST_VAULT_DIR = os.path.join(BASE_DATA_DIR, "TestVaults")

COUPLES_JSON = os.path.join(project_root, "gedcom_sources", "gedcom_couples.json")
COUNTY_JSON = os.path.join(project_root, "JSON", "county_names_to_codes.json")
COUNTY_NAMES_JSON = os.path.join(project_root, "JSON", "county_codes_to_names.json")

# --- Test Mode Configuration ---
TEST_MODE = True
TEST_H_LAST = "ASKEY"  # Replace this with the last name of the 6th/7th gen family you want to test


def get_base_code(state_str):
    """Takes a state string (e.g. 'Pennsylvania'), gets the IPUMS prefix, and returns the base integer."""
    if not state_str: return None
    prefixes = get_bpl_prefixes(state_str)
    if not prefixes: return None
    p = str(prefixes[0]).strip().lstrip('0')
    if not p: return None
    return int(p)


def get_county_code(res_str, county_dict):
    """Parses a GEDCOM residence string and returns the matching IPUMS County Code and State Name."""
    if not res_str: return "N/A", "Unknown State"
    res_upper = res_str.upper()

    # 1. Find the state to avoid cross-state county name collisions (e.g., Washington County)
    matched_state = None
    for state in county_dict.keys():
        if state.upper() in res_upper:
            matched_state = state
            break

    if not matched_state:
        return "N/A", "Unknown State"

    # 2. Find the county within that state
    for county, code in county_dict[matched_state].items():
        # Handle slashed names in the JSON (e.g., "Chilton/Baker")
        for c_name in county.split('/'):
            if c_name.strip().upper() in res_upper:
                return str(code), matched_state

    return "N/A", matched_state


def run_overlay_v2(logger):
    logger.info("Initializing V2 DuckDB Overlay Engine...")
    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")
    con.execute("SET sqlite_all_varchar=true;")

    if not os.path.exists(COUPLES_JSON):
        logger.error(f"Target JSON not found: {COUPLES_JSON}")
        return

    with open(COUPLES_JSON, 'r', encoding='utf-8') as f:
        gedcom_couples = json.load(f)

    # Load the national county mappings
    county_codes_dict = {}
    if os.path.exists(COUNTY_JSON):
        with open(COUNTY_JSON, 'r', encoding='utf-8') as f:
            county_codes_dict = json.load(f)
    else:
        logger.warning(f"National County JSON not found at {COUNTY_JSON}")

    county_names_dict = {}
    if os.path.exists(COUNTY_NAMES_JSON):
        with open(COUNTY_NAMES_JSON, 'r', encoding='utf-8') as f:
            county_names_dict = json.load(f)
    else:
        logger.warning(f"Reverse National County JSON not found at {COUNTY_NAMES_JSON}")

    if TEST_MODE:
        gedcom_couples = [c for c in gedcom_couples if c.get('h_last', '').upper() == TEST_H_LAST.upper()]
        logger.info(
            f"TEST MODE ENABLED: Filtered down to {len(gedcom_couples)} target couples with last name {TEST_H_LAST}.")

    logger.info(f"Loaded {len(gedcom_couples)} target couples from JSON.")

    target_rows = []
    global_bpl_codes = set()

    for idx, g_dict in enumerate(gedcom_couples):
        h_bpl = get_base_code(g_dict.get('h_bpl'))
        h_fbpl = get_base_code(g_dict.get('h_fbpl'))
        h_mbpl = get_base_code(g_dict.get('h_mbpl'))
        w_bpl = get_base_code(g_dict.get('w_bpl'))
        w_fbpl = get_base_code(g_dict.get('w_fbpl'))
        w_mbpl = get_base_code(g_dict.get('w_mbpl'))

        if None in (h_bpl, h_fbpl, h_mbpl, w_bpl, w_fbpl, w_mbpl) or not g_dict.get('h_byr') or not g_dict.get('w_byr'):
            continue

        global_bpl_codes.update([h_bpl, h_fbpl, h_mbpl, w_bpl, w_fbpl, w_mbpl])

        target_rows.append((
            idx,
            g_dict.get('h_first', '').upper(),
            g_dict.get('h_last', '').upper(),
            int(g_dict['h_byr']), h_bpl, h_fbpl, h_mbpl,
            g_dict.get('w_first', '').upper(),
            g_dict.get('w_last', '').upper(),
            int(g_dict['w_byr']), w_bpl, w_fbpl, w_mbpl,
            int(g_dict.get('num_children', 0)),
            g_dict.get('kid_fingerprint', '')
        ))

    logger.info(f"Filtered down to {len(target_rows)} elite, fully-documented target anchors.")

    con.execute("""
                CREATE TABLE targets
                (
                    target_idx INTEGER,
                    h_first    VARCHAR,
                    h_last     VARCHAR,
                    h_byr      INTEGER,
                    h_bpl      INTEGER,
                    h_fbpl     INTEGER,
                    h_mbpl     INTEGER,
                    w_first    VARCHAR,
                    w_last     VARCHAR,
                    w_byr      INTEGER,
                    w_bpl      INTEGER,
                    w_fbpl     INTEGER,
                    w_mbpl     INTEGER,
                    num_kids   INTEGER,
                    kid_fp     VARCHAR
                )
                """)
    con.executemany("INSERT INTO targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", target_rows)

    bpl_filter_str = ", ".join(map(str, global_bpl_codes))

    con.execute(f"ATTACH '{MATCH_DB}' AS match_db (TYPE SQLITE, READ_ONLY);")

    vault_dir_to_use = NAMED_VAULT_DIR
    if TEST_MODE:
        logger.info(f"TEST MODE: Using full production vaults from {NAMED_VAULT_DIR}")

    for filename in os.listdir(vault_dir_to_use):
        if not filename.endswith(".db"): continue
        if not (filename.startswith("YearVault_") or filename.startswith("PA_1900_Couples_")): continue
        year = filename.replace("PA_1900_Couples_", "").replace("YearVault_", "").replace("NamedVault_", "").replace(
            ".db", "")

        logger.info(f"\n=======================================================")
        logger.info(f"Processing {year} Census Vault")
        logger.info(f"=======================================================")

        db_path = os.path.join(vault_dir_to_use, filename)
        con.execute(f"ATTACH '{db_path}' AS vault (TYPE SQLITE, READ_ONLY);")

        parent_bpl_filter = ""
        parent_bpl_match = ""

        if int(year) not in [1850, 1860, 1870]:
            parent_bpl_filter = f"""
              AND (i.fbpl IS NULL OR i.fbpl = '' OR i.fbpl = '0' OR TRY_CAST(i.fbpl AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.fbpl AS INTEGER) // 100) IN ({bpl_filter_str}))
              AND (i.mbpl IS NULL OR i.mbpl = '' OR i.mbpl = '0' OR TRY_CAST(i.mbpl AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.mbpl AS INTEGER) // 100) IN ({bpl_filter_str}))"""

            parent_bpl_match = """
                  AND (h.fbpl IS NULL OR h.fbpl = '' OR h.fbpl = '0' OR TRY_CAST(h.fbpl AS INTEGER) = t.h_fbpl OR TRY_CAST(h.fbpl AS INTEGER) // 100 = t.h_fbpl)
                  AND (h.mbpl IS NULL OR h.mbpl = '' OR h.mbpl = '0' OR TRY_CAST(h.mbpl AS INTEGER) = t.h_mbpl OR TRY_CAST(h.mbpl AS INTEGER) // 100 = t.h_mbpl)
                  AND (s.fbpl IS NULL OR s.fbpl = '' OR s.fbpl = '0' OR TRY_CAST(s.fbpl AS INTEGER) = t.w_fbpl OR TRY_CAST(s.fbpl AS INTEGER) // 100 = t.w_fbpl)
                  AND (s.mbpl IS NULL OR s.mbpl = '' OR s.mbpl = '0' OR TRY_CAST(s.mbpl AS INTEGER) = t.w_mbpl OR TRY_CAST(s.mbpl AS INTEGER) // 100 = t.w_mbpl)"""

        con.execute("""
            CREATE TEMP TABLE couple_members AS
            SELECT head_histid AS histid FROM vault.families WHERE head_histid IS NOT NULL AND spouse_histid IS NOT NULL
            UNION
            SELECT spouse_histid AS histid FROM vault.families WHERE head_histid IS NOT NULL AND spouse_histid IS NOT NULL;
        """)

        con.execute(f"""
            CREATE TEMP TABLE relevant_individuals AS
            SELECT i.*
            FROM vault.individuals i
            JOIN couple_members cm ON i.histid = cm.histid
            WHERE i.bpld IS NOT NULL AND i.bpld != ''
              AND (TRY_CAST(i.bpld AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.bpld AS INTEGER) // 100) IN ({bpl_filter_str})){parent_bpl_filter};
        """)

        survivors = con.execute("SELECT COUNT(*) FROM relevant_individuals").fetchone()[0]
        logger.info(f"  -> Dead Weight dropped! Only {survivors:,} relevant individuals remain in RAM.")

        query = f"""
            WITH matched_fams AS (
                SELECT 
                    t.target_idx,
                    f.family_id,
                    c.clan_id,
                    -- 3 to 10: NAMES
                    t.h_first AS h_first_gedcom, h.first_name AS h_first_db,
                    t.h_last  AS h_last_gedcom,  h.last_name  AS h_last_db,
                    t.w_first AS w_first_gedcom, s.first_name AS w_first_db,
                    t.w_last  AS w_last_gedcom,  s.last_name  AS w_last_db,
                    -- 11 to 14: BIRTH YEARS
                    t.h_byr   AS h_byr_gedcom,   TRY_CAST(h.birthyr AS INTEGER) AS h_byr_db,
                    t.w_byr   AS w_byr_gedcom,   TRY_CAST(s.birthyr AS INTEGER) AS w_byr_db,
                    -- 15 to 18: BIRTHPLACES
                    t.h_bpl   AS h_bpl_gedcom,   h.bpld       AS h_bpl_db,
                    t.w_bpl   AS w_bpl_gedcom,   s.bpld       AS w_bpl_db,
                    -- 19 to 26: PARENT BIRTHPLACES
                    t.h_fbpl  AS h_fbpl_gedcom,  h.fbpl       AS h_fbpl_db,
                    t.h_mbpl  AS h_mbpl_gedcom,  h.mbpl       AS h_mbpl_db,
                    t.w_fbpl  AS w_fbpl_gedcom,  s.fbpl       AS w_fbpl_db,
                    t.w_mbpl  AS w_mbpl_gedcom,  s.mbpl       AS w_mbpl_db,
                    -- 27 to 28: KIDS
                    t.num_kids AS num_kids_gedcom, f.num_kids AS num_kids_db,
                    -- 29 to 30: KID FINGERPRINTS
                    t.kid_fp AS kid_fp_gedcom, f.kids_byr_sum AS kids_byr_sum_db,
                    -- 31: COUNTY
                    f.countyicp AS county_db
                FROM vault.families f
                JOIN relevant_individuals h ON f.head_histid = h.histid
                JOIN relevant_individuals s ON f.spouse_histid = s.histid
                LEFT JOIN match_db.clan_mapping c ON f.family_id = c.family_id
                JOIN targets t
                    ON h.sex = '1' AND s.sex = '2'
                    AND TRY_CAST(f.num_kids AS INTEGER) > 0
                    AND TRY_CAST(h.birthyr AS INTEGER) BETWEEN t.h_byr - 2 AND t.h_byr + 2
                    AND TRY_CAST(s.birthyr AS INTEGER) BETWEEN t.w_byr - 2 AND t.w_byr + 2
                    AND (TRY_CAST(h.bpld AS INTEGER) = t.h_bpl OR TRY_CAST(h.bpld AS INTEGER) // 100 = t.h_bpl)
                    AND (TRY_CAST(s.bpld AS INTEGER) = t.w_bpl OR TRY_CAST(s.bpld AS INTEGER) // 100 = t.w_bpl)
                    {parent_bpl_match}
            ),
            match_counts AS (
                SELECT target_idx, COUNT(*) as cnt 
                FROM matched_fams 
                GROUP BY target_idx
            ),
            refined_fams AS (
                SELECT m.*
                FROM matched_fams m
                JOIN match_counts mc ON m.target_idx = mc.target_idx
                WHERE mc.cnt <= 25
                   OR (mc.cnt > 25 AND (m.kid_fp_gedcom IS NULL OR m.kid_fp_gedcom = '' OR TRY_CAST(m.kids_byr_sum_db AS VARCHAR) = m.kid_fp_gedcom))
            )
            SELECT m.*
            FROM refined_fams m;
        """

        matches = con.execute(query).fetchall()
        logger.info(f"  -> SUCCESS: Found {len(matches)} mathematically proven candidates!")

        if TEST_MODE and matches:
            logger.info("  -> COLLISION REVIEW MODE:")

            grouped_matches = {}
            for match in matches:
                target_idx = match[0]
                grouped_matches.setdefault(target_idx, []).append(match)

            for target_idx, candidates in grouped_matches.items():
                if len(candidates) > 1:
                    logger.info(f"\n=======================================================")
                    logger.info(
                        f"COLLISION DETECTED: GEDCOM Target {target_idx} has {len(candidates)} competing Census Families!")

                    original_json_data = gedcom_couples[target_idx]
                    h_res = original_json_data.get(f'h_res_{year}', '')
                    w_res = original_json_data.get(f'w_res_{year}', '')
                    h_res_code, h_res_state = get_county_code(h_res, county_codes_dict)
                    w_res_code, w_res_state = get_county_code(w_res, county_codes_dict)
                    
                    # We'll use the GEDCOM state to translate the Database's county code
                    lookup_state = h_res_state if h_res_state != "Unknown State" else w_res_state
                    
                    h_res_disp = h_res if h_res else "No Data"
                    w_res_disp = w_res if w_res else "No Data"
                    residences = f"Husb: {h_res_disp} (Code: {h_res_code}) | Wife: {w_res_disp} (Code: {w_res_code})"

                    base = candidates[0]
                    logger.info(f"--- GEDCOM BASELINE ---")
                    logger.info(
                        f"Husband: {base[3]} {base[5]} (Born: {base[11]}, BPL: {base[15]}, FBPL: {base[19]}, MBPL: {base[21]})")
                    logger.info(
                        f"Wife   : {base[7]} {base[9]} (Born: {base[13]}, BPL: {base[17]}, FBPL: {base[23]}, MBPL: {base[25]})")
                    logger.info(f"Kids   : Count={base[27]} (Fingerprint: {base[29]})")
                    logger.info(f"Residences: {residences}")
                    logger.info(f"-------------------------------------------------------")

                    # Print out competing Database families (capped at 10 to save log space)
                    limit = 10
                    for i, cand in enumerate(candidates[:limit], 1):
                        logger.info(f"  [Candidate {i}] Census Family ID: {cand[1]}")
                        logger.info(
                            f"    DB Husband : {cand[4]} {cand[6]} (Born: {cand[12]}, BPL: {cand[16]}, FBPL: {cand[20]}, MBPL: {cand[22]})")
                        logger.info(
                            f"    DB Wife    : {cand[8]} {cand[10]} (Born: {cand[14]}, BPL: {cand[18]}, FBPL: {cand[24]}, MBPL: {cand[26]})")
                        logger.info(f"    DB Kids    : Count={cand[28]} (Fingerprint: {cand[30]})")
                        
                        if cand[31] is not None:
                            try:
                                db_county_code = str(int(float(cand[31])))
                            except ValueError:
                                db_county_code = str(cand[31]).strip()
                        else:
                            db_county_code = "N/A"
                            
                        db_county_name = "Unknown County"
                        if lookup_state != "Unknown State" and db_county_code != "N/A":
                            db_county_name = county_names_dict.get(lookup_state, {}).get(db_county_code, "Unknown County")
                            
                        logger.info(f"    DB County  : {db_county_name}, {lookup_state} (Code: {db_county_code})")
                        logger.info(f"  - - - - - - - - - - - - - - - - - - - - - - - - -")

                    if len(candidates) > limit:
                        logger.info(
                            f"  ... and {len(candidates) - limit} more competing families hidden to save log space.")

        con.execute("DROP TABLE relevant_individuals")
        con.execute("DROP TABLE couple_members")
        con.execute("DETACH vault")


if __name__ == '__main__':
    main_logger = gen_logging.setup_logging("NAME_OVERLAY_V2")
    run_overlay_v2(main_logger)
