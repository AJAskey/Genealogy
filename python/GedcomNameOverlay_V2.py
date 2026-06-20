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
TEST_VAULT_DIR = os.path.join(BASE_DATA_DIR, "TestVaults")

COUPLES_JSON = os.path.join(project_root, "gedcom_sources", "gedcom_couples.json")
COUNTY_JSON = os.path.join(project_root, "JSON", "county_names_to_codes.json")
COUNTY_NAMES_JSON = os.path.join(project_root, "JSON", "county_codes_to_names.json")

IPUMS_STATES = {
    1: "Alabama", 2: "Alaska", 4: "Arizona", 5: "Arkansas", 6: "California",
    8: "Colorado", 9: "Connecticut", 10: "Delaware", 11: "District of Columbia",
    12: "Florida", 13: "Georgia", 15: "Hawaii", 16: "Idaho", 17: "Illinois",
    18: "Indiana", 19: "Iowa", 20: "Kansas", 21: "Kentucky", 22: "Louisiana",
    23: "Maine", 24: "Maryland", 25: "Massachusetts", 26: "Michigan",
    27: "Minnesota", 28: "Mississippi", 29: "Missouri", 30: "Montana",
    31: "Nebraska", 32: "Nevada", 33: "New Hampshire", 34: "New Jersey",
    35: "New Mexico", 36: "New York", 37: "North Carolina", 38: "North Dakota",
    39: "Ohio", 40: "Oklahoma", 41: "Oregon", 42: "Pennsylvania",
    44: "Rhode Island", 45: "South Carolina", 46: "South Dakota", 47: "Tennessee",
    48: "Texas", 49: "Utah", 50: "Vermont", 51: "Virginia", 53: "Washington",
    54: "West Virginia", 55: "Wisconsin", 56: "Wyoming"
}

# --- Test Mode Configuration ---
TEST_MODE = False
TEST_H_LAST = "ASKEY"  # Replace this with the last name of the 6th/7th gen family you want to test
VALIDATION_MODE = True
SAMPLE_DB_NAME = "CENSUS-SAMPLE.db"
YEAR_WINDOW = 0  # 0 for Ground Truth Validation, 1 or 2 for broad search
IGNORE_KIDS_FOR_VALIDATION = True  # Set to True if sample data lacks accurate kid fingerprints

if VALIDATION_MODE:
    MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches_SAMPLE.db")
else:
    MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")


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
    skipped_ghosts = 0

    for idx, g_dict in enumerate(gedcom_couples):
        h_bpl = get_base_code(g_dict.get('h_bpl')) or 0
        h_fbpl = get_base_code(g_dict.get('h_fbpl')) or 0
        h_mbpl = get_base_code(g_dict.get('h_mbpl')) or 0
        w_bpl = get_base_code(g_dict.get('w_bpl')) or 0
        w_fbpl = get_base_code(g_dict.get('w_fbpl')) or 0
        w_mbpl = get_base_code(g_dict.get('w_mbpl')) or 0

        # Only process high-quality anchors (Husband MUST have a known personal birthplace)
        if not g_dict.get('h_byr') or not g_dict.get('w_byr') or h_bpl == 0:
            skipped_ghosts += 1
            continue

        global_bpl_codes.update([b for b in [h_bpl, h_fbpl, h_mbpl, w_bpl, w_fbpl, w_mbpl] if b != 0])

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

    if not target_rows:
        logger.warning("No target couples found to process! Check your JSON or TEST_MODE filters.")
        return

    total_couples = len(target_rows) + skipped_ghosts
    if skipped_ghosts > 0:
        yield_pct = (len(target_rows) / total_couples) * 100
        logger.info(f"Skipped {skipped_ghosts:,} 'ghost' targets. Searchable Yield: {yield_pct:.1f}%")

    logger.info(f"Initialized {len(target_rows):,} elite, fully-documented target anchors.")

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

    bpl_filter_sql = ""
    parent_filter_sql = ""
    if global_bpl_codes:
        bpl_filter_str = ", ".join(map(str, global_bpl_codes))
        bpl_filter_sql = f"AND (TRY_CAST(i.bpld AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.bpld AS INTEGER) // 100) IN ({bpl_filter_str}))"
        parent_filter_sql = f"""
          AND (TRY_CAST(i.year AS INTEGER) IN (1850, 1860, 1870) OR 
               (
                 (i.fbpl IS NULL OR i.fbpl = '' OR i.fbpl = '0' OR TRY_CAST(i.fbpl AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.fbpl AS INTEGER) // 100) IN ({bpl_filter_str}))
                 AND (i.mbpl IS NULL OR i.mbpl = '' OR i.mbpl = '0' OR TRY_CAST(i.mbpl AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.mbpl AS INTEGER) // 100) IN ({bpl_filter_str}))
               )
          )"""

    con.execute(f"ATTACH '{MATCH_DB}' AS match_db (TYPE SQLITE, READ_ONLY);")

    vault_dir_to_use = NAMED_VAULT_DIR
    if TEST_MODE:
        logger.info(f"TEST MODE: Using full production vaults from {NAMED_VAULT_DIR}")

    for filename in os.listdir(vault_dir_to_use):
        if not filename.endswith(".db"): continue

        if VALIDATION_MODE:
            if filename != SAMPLE_DB_NAME: continue
            year_label = "ALL SAMPLE YEARS"
        else:
            if not (filename.startswith("YearVault_") or filename.startswith("PA_1900_Couples_")): continue
            year_label = filename.replace("PA_1900_Couples_", "").replace("YearVault_", "").replace("NamedVault_",
                                                                                                    "").replace(".db",
                                                                                                                "")

        logger.info(f"\n=======================================================")
        logger.info(f"Processing {year_label} Census Vault")
        logger.info(f"=======================================================")

        db_path = os.path.join(vault_dir_to_use, filename)
        con.execute(f"ATTACH '{db_path}' AS vault (TYPE SQLITE, READ_ONLY);")

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
              {bpl_filter_sql}
              {parent_filter_sql};
        """)

        survivors = con.execute("SELECT COUNT(*) FROM relevant_individuals").fetchone()[0]
        logger.info(f"  -> Dead Weight dropped! Only {survivors:,} relevant individuals remain in RAM.")

        kid_match_condition_sql = ""
        if not IGNORE_KIDS_FOR_VALIDATION:
            kid_match_condition_sql = """
                    AND (t.num_kids = 0 OR TRY_CAST(f.num_kids AS INTEGER) > 0) -- If GEDCOM has kids, DB must have kids
                    AND (t.kid_fp = '' OR TRY_CAST(f.kids_byr_sum AS VARCHAR) = t.kid_fp) -- If GEDCOM has fingerprint, DB must match
            """
        query = f"""
            WITH matched_fams AS (
                SELECT 
                    t.target_idx, f.family_id, c.clan_id, TRY_CAST(f.year AS INTEGER) AS match_year,

                    t.h_first AS h_first_gedcom, h.first_name AS h_first_db,
                    t.h_last  AS h_last_gedcom,  h.last_name  AS h_last_db,
                    t.w_first AS w_first_gedcom, s.first_name AS w_first_db,
                    t.w_last  AS w_last_gedcom,  s.last_name  AS w_last_db,

                    t.h_byr   AS h_byr_gedcom,   TRY_CAST(h.birthyr AS INTEGER) AS h_byr_db,
                    t.w_byr   AS w_byr_gedcom,   TRY_CAST(s.birthyr AS INTEGER) AS w_byr_db,

                    t.h_bpl   AS h_bpl_gedcom,   h.bpld       AS h_bpl_db,
                    t.w_bpl   AS w_bpl_gedcom,   s.bpld       AS w_bpl_db,

                    t.h_fbpl  AS h_fbpl_gedcom,  h.fbpl       AS h_fbpl_db,
                    t.h_mbpl  AS h_mbpl_gedcom,  h.mbpl       AS h_mbpl_db,
                    t.w_fbpl  AS w_fbpl_gedcom,  s.fbpl       AS w_fbpl_db,
                    t.w_mbpl  AS w_mbpl_gedcom,  s.mbpl       AS w_mbpl_db,

                    t.num_kids AS num_kids_gedcom, f.num_kids AS num_kids_db,
                    t.kid_fp AS kid_fp_gedcom, f.kids_byr_sum AS kids_byr_sum_db,

                    f.countyicp AS county_db,
                    f.stateicp AS state_db
                FROM vault.families f
                JOIN relevant_individuals h ON f.head_histid = h.histid
                JOIN relevant_individuals s ON f.spouse_histid = s.histid
                LEFT JOIN match_db.clan_mapping c ON f.family_id = c.family_id
                JOIN targets t
                    ON h.sex = '1' AND s.sex = '2'
                    {kid_match_condition_sql}
                    AND TRY_CAST(h.birthyr AS INTEGER) BETWEEN t.h_byr - {YEAR_WINDOW} AND t.h_byr + {YEAR_WINDOW}
                    AND TRY_CAST(s.birthyr AS INTEGER) BETWEEN t.w_byr - {YEAR_WINDOW} AND t.w_byr + {YEAR_WINDOW}
                    AND (TRY_CAST(h.bpld AS INTEGER) = t.h_bpl OR TRY_CAST(h.bpld AS INTEGER) // 100 = t.h_bpl)
                    AND (t.w_bpl = 0 OR TRY_CAST(s.bpld AS INTEGER) = t.w_bpl OR TRY_CAST(s.bpld AS INTEGER) // 100 = t.w_bpl)
                    AND (TRY_CAST(f.year AS INTEGER) IN (1850, 1860, 1870) OR 
                         (
                            (t.h_fbpl = 0 OR h.fbpl IS NULL OR h.fbpl = '' OR h.fbpl = '0' OR TRY_CAST(h.fbpl AS INTEGER) = t.h_fbpl OR TRY_CAST(h.fbpl AS INTEGER) // 100 = t.h_fbpl)
                            AND (t.h_mbpl = 0 OR h.mbpl IS NULL OR h.mbpl = '' OR h.mbpl = '0' OR TRY_CAST(h.mbpl AS INTEGER) = t.h_mbpl OR TRY_CAST(h.mbpl AS INTEGER) // 100 = t.h_mbpl)
                            AND (t.w_fbpl = 0 OR s.fbpl IS NULL OR s.fbpl = '' OR s.fbpl = '0' OR TRY_CAST(s.fbpl AS INTEGER) = t.w_fbpl OR TRY_CAST(s.fbpl AS INTEGER) // 100 = t.w_fbpl)
                            AND (t.w_mbpl = 0 OR s.mbpl IS NULL OR s.mbpl = '' OR s.mbpl = '0' OR TRY_CAST(s.mbpl AS INTEGER) = t.w_mbpl OR TRY_CAST(s.mbpl AS INTEGER) // 100 = t.w_mbpl)
                         )
                    )
            )
            SELECT m.*
            FROM matched_fams m;
        """

        matches = con.execute(query).fetchall()
        logger.info(f"  -> SUCCESS: Found {len(matches)} mathematically proven candidates!")

        if matches:
            logger.info("  -> COLLISION REVIEW MODE:")

            grouped_matches = {}
            for match in matches:
                target_idx = match[0]
                grouped_matches.setdefault(target_idx, []).append(match)

            for target_idx, candidates in grouped_matches.items():
                if len(candidates) > 0:  # Allow viewing all matches, including collisions
                    logger.info(f"\n=======================================================")
                    logger.info(
                        f"REVIEWING: GEDCOM Target {target_idx} has {len(candidates)} competing Census Families! (Birth Year Window: ±{YEAR_WINDOW})")

                    original_json_data = gedcom_couples[target_idx]
                    base = candidates[0]
                    match_year = base[3]  # Dynamically pull the exact year this census record belongs to!

                    h_res = original_json_data.get(f'h_res_{match_year}', '')
                    w_res = original_json_data.get(f'w_res_{match_year}', '')

                    h_res_code, h_res_state = get_county_code(h_res, county_codes_dict)
                    w_res_code, w_res_state = get_county_code(w_res, county_codes_dict)

                    # We'll use the GEDCOM state to translate the Database's county code
                    lookup_state = h_res_state if h_res_state != "Unknown State" else w_res_state

                    h_res_disp = h_res if h_res else "No Data"
                    w_res_disp = w_res if w_res else "No Data"

                    residences = f"Husb: {h_res_disp} (Code: {h_res_code}) | Wife: {w_res_disp} (Code: {w_res_code})"

                    logger.info(f"--- GEDCOM BASELINE ---")
                    logger.info(
                        f"Husband: {base[4]} {base[6]} (Born: {base[12]}, BPL: {base[16]}, FBPL: {base[20]}, MBPL: {base[22]})")
                    logger.info(
                        f"Wife   : {base[8]} {base[10]} (Born: {base[14]}, BPL: {base[18]}, FBPL: {base[24]}, MBPL: {base[26]})")
                    logger.info(f"Kids   : Count={base[28]} (Fingerprint: {base[30]})")
                    logger.info(f"Residences: {residences}")
                    logger.info(f"-------------------------------------------------------")

                    # Print out competing Database families (capped at 10 to save log space)
                    limit = 50
                    exact_hw_match = False
                    for i, cand in enumerate(candidates[:limit], 1):
                        h_match = (str(cand[4]).strip().upper() == str(cand[5]).strip().upper() and
                                   str(cand[6]).strip().upper() == str(cand[7]).strip().upper())
                        w_match = (str(cand[8]).strip().upper() == str(cand[9]).strip().upper() and
                                   str(cand[10]).strip().upper() == str(cand[11]).strip().upper())

                        match_tag = ""
                        if h_match and w_match:
                            match_tag = "  *** EXACT HUSBAND & WIFE NAME MATCH ***"
                            exact_hw_match = True
                        elif h_match:
                            match_tag = "  * (Exact Husband Name Match)"
                        elif w_match:
                            match_tag = "  * (Exact Wife Name Match)"

                        logger.info(f"  [Candidate {i}] Census Family ID: {cand[1]} | YEAR: {cand[3]}{match_tag}")
                        logger.info(
                            f"    DB Husband : {cand[5]} {cand[7]} (Born: {cand[13]}, BPL: {cand[17]}, FBPL: {cand[21]}, MBPL: {cand[23]})")
                        logger.info(
                            f"    DB Wife    : {cand[9]} {cand[11]} (Born: {cand[15]}, BPL: {cand[19]}, FBPL: {cand[25]}, MBPL: {cand[27]})")
                        logger.info(f"    DB Kids    : Count={cand[29]} (Fingerprint: {cand[31]})")

                        if cand[32] is not None:
                            try:
                                db_county_code = str(int(float(cand[32])))
                            except ValueError:
                                db_county_code = str(cand[32]).strip()
                        else:
                            db_county_code = "N/A"

                        db_state_name = "Unknown State"
                        if cand[33] is not None:
                            try:
                                db_state_name = IPUMS_STATES.get(int(float(cand[33])), "Unknown State")
                            except ValueError:
                                pass

                        db_county_name = "Unknown County"
                        if db_state_name != "Unknown State" and db_county_code != "N/A":
                            db_county_name = county_names_dict.get(db_state_name, {}).get(db_county_code,
                                                                                          "Unknown County")

                        logger.info(f"    DB County  : {db_county_name}, {db_state_name} (Code: {db_county_code})")
                        logger.info(f"  - - - - - - - - - - - - - - - - - - - - - - - - -")

                    if len(candidates) > limit:
                        logger.info(
                            f"  ... and {len(candidates) - limit} more competing families hidden to save log space.")
                    logger.info(f"EXACT HUSBAND-WIFE MATCH : {exact_hw_match}  ")

        con.execute("DROP TABLE relevant_individuals")
        con.execute("DROP TABLE couple_members")
        con.execute("DETACH vault")


if __name__ == '__main__':
    main_logger = gen_logging.setup_logging("NAME_OVERLAY_V2")
    run_overlay_v2(main_logger)
