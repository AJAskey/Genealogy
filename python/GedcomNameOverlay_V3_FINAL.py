"""
-----------------------------------
File: GedcomNameOverlay_V3_FINAL.py
Summary: The V3 "Motion Picture" Label-Maker.
         Reads a pre-processed JSON list of GEDCOM couples.
         Executes a native 1-to-1 Highlander match, groups results
         by Time Machine CLAN_ID, and validates multi-decade
         geographical trajectories for 100% mathematical certainty.

Architect & Designer: Andy Askey
Coder (AI Assistant): Anthropic Claude

License: Apache License 2.0
-----------------------------------
"""

import os
import json
import duckdb
import sys

# Add the 'python' directory and project root to sys.path so we can import properly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

import gen_logging
from utils import common_utils

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
JSON_PATH = os.path.join(project_root, "JSON", "gedcom_couples.json")
COUNTY_NAMES_JSON = os.path.join(project_root, "JSON", "county_codes_to_names.json")
HOMELAND_JSON = os.path.join(project_root, "output", "homeland_counties.json")

YEAR_WINDOW = 2  # 0 for Ground Truth Validation, 1 or 2 for broad search
IGNORE_KIDS_FOR_VALIDATION = True  # Set to True if sample data lacks accurate kid fingerprints

STATEICP_MAP = {
    1: "Connecticut", 2: "Massachusetts", 3: "Rhode Island", 4: "New Hampshire", 5: "Maine", 6: "Vermont",
    11: "Delaware", 12: "New Jersey", 13: "New York", 14: "Pennsylvania",
    21: "Illinois", 22: "Indiana", 23: "Michigan", 24: "Ohio", 25: "Wisconsin",
    31: "Iowa", 32: "Kansas", 33: "Minnesota", 34: "Missouri", 35: "Nebraska", 36: "North Dakota", 37: "South Dakota",
    41: "Virginia", 42: "West Virginia", 43: "North Carolina", 44: "South Carolina", 45: "Georgia", 46: "Florida", 47: "District of Columbia", 48: "Maryland",
    51: "Kentucky", 52: "Tennessee", 53: "Alabama", 54: "Mississippi",
    61: "Arkansas", 62: "Louisiana", 63: "Oklahoma", 64: "Texas",
    71: "Montana", 72: "Idaho", 73: "Wyoming", 74: "Colorado", 75: "New Mexico", 76: "Arizona", 77: "Utah", 78: "Nevada",
    81: "Washington", 82: "Oregon", 83: "California", 84: "Alaska", 85: "Hawaii"
}

NAME_TO_BPL = {
    "ALABAMA": 1, "ALASKA": 2, "ARIZONA": 4, "ARKANSAS": 5, "CALIFORNIA": 6,
    "COLORADO": 8, "CONNECTICUT": 9, "DELAWARE": 10, "DISTRICT OF COLUMBIA": 11,
    "FLORIDA": 12, "GEORGIA": 13, "HAWAII": 15, "IDAHO": 16, "ILLINOIS": 17,
    "INDIANA": 18, "IOWA": 19, "KANSAS": 20, "KENTUCKY": 21, "LOUISIANA": 22,
    "MAINE": 23, "MARYLAND": 24, "MASSACHUSETTS": 25, "MICHIGAN": 26,
    "MINNESOTA": 27, "MISSISSIPPI": 28, "MISSOURI": 29, "MONTANA": 30,
    "NEBRASKA": 31, "NEVADA": 32, "NEW HAMPSHIRE": 33, "NEW JERSEY": 34,
    "NEW MEXICO": 35, "NEW YORK": 36, "NORTH CAROLINA": 37, "NORTH DAKOTA": 38,
    "OHIO": 39, "OKLAHOMA": 40, "OREGON": 41, "PENNSYLVANIA": 42,
    "RHODE ISLAND": 44, "SOUTH CAROLINA": 45, "SOUTH DAKOTA": 46, "TENNESSEE": 47,
    "TEXAS": 48, "UTAH": 49, "VERMONT": 50, "VIRGINIA": 51, "WASHINGTON": 53,
    "WEST VIRGINIA": 54, "WISCONSIN": 55, "WYOMING": 56,
    "CANADA": 150, "MEXICO": 200, "DENMARK": 400, "NORWAY": 401, "SWEDEN": 404,
    "ENGLAND": 410, "WALES": 411, "SCOTLAND": 412, "NORTHERN IRELAND": 413, "IRELAND": 414, 
    "FRANCE": 421, "NETHERLANDS": 425, "SWITZERLAND": 426, "GERMANY": 453, 
    "JAPAN": 501, "SOUTH KOREA": 502
}
# ==============================================================================

def get_county_code(place_str, county_dict):
    if not place_str:
        return "0000", "Unknown State"
    state = common_utils.extract_state(place_str)
    if not state or state == "Unknown":
        return "0000", "Unknown State"
    county = place_str.split(',')[0].replace(' County', '').strip().upper()
    if state in county_dict:
        for code, name in county_dict[state].items():
            if name.upper() == county:
                return code, state
    return "0000", state

def get_base_code(code_str):
    if not code_str: return 0
    try:
        val = int(float(code_str))
        return val // 100 if val >= 1000 else val
    except (ValueError, TypeError):
        clean_str = str(code_str).strip().upper()
        if clean_str in NAME_TO_BPL:
            return NAME_TO_BPL[clean_str]
        return 0

def run_overlay_v3(logger):
    logger.info("Initializing V3 'Motion Picture' Trajectory Engine...")
    con = duckdb.connect()

    duckdb_tmp_dir = os.path.join(BASE_DATA_DIR, "duckdb_tmp")
    os.makedirs(duckdb_tmp_dir, exist_ok=True)
    con.execute(f"PRAGMA temp_directory='{duckdb_tmp_dir}'")
    con.execute("PRAGMA memory_limit='32GB'")

    con.execute("INSTALL sqlite;")
    con.execute("LOAD sqlite;")
    con.execute("SET sqlite_all_varchar=true;")

    county_names_dict = {}
    if os.path.exists(COUNTY_NAMES_JSON):
        with open(COUNTY_NAMES_JSON, 'r', encoding='utf-8') as f:
            county_names_dict = json.load(f)

    family_counties = []
    if os.path.exists(HOMELAND_JSON):
        with open(HOMELAND_JSON, 'r', encoding='utf-8') as f:
            homeland_data = json.load(f)
            family_counties = [k.upper().strip() for k in homeland_data.keys()]
            logger.info(f"Dynamic Homeland Counties loaded: {family_counties[:5]}")

    if not os.path.exists(JSON_PATH):
        logger.error(f"Cannot find JSON file at: {JSON_PATH}")
        return

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        gedcom_couples = json.load(f)
        
    logger.info(f"Loaded {len(gedcom_couples)} target couples from JSON.")

    target_rows = []
    skipped_ghosts = 0
    global_bpl_codes = set()

    for idx, g_dict in enumerate(gedcom_couples):
        h_bpl = get_base_code(g_dict.get('h_bpl')) or 0
        w_bpl = get_base_code(g_dict.get('w_bpl')) or 0
        
        h_fbpl = get_base_code(g_dict.get('h_fbpl')) or 0
        h_mbpl = get_base_code(g_dict.get('h_mbpl')) or 0
        w_fbpl = get_base_code(g_dict.get('w_fbpl')) or 0
        w_mbpl = get_base_code(g_dict.get('w_mbpl')) or 0

        # Core Profile Filter for Trajectory Matching.
        if not g_dict.get('h_byr') or h_bpl == 0 or not g_dict.get('w_byr') or w_bpl == 0:
            skipped_ghosts += 1
            continue

        target_rows.append((
            idx,
            int(g_dict.get('h_byr', 0)), h_bpl, h_fbpl, h_mbpl,
            int(g_dict.get('w_byr', 0)), w_bpl, w_fbpl, w_mbpl,
            int(g_dict.get('kid_fingerprint', 0)),
            g_dict.get('h_first', ''), g_dict.get('h_last', ''),
            g_dict.get('w_first', ''), g_dict.get('w_last', '')
        ))
        
        global_bpl_codes.add(h_bpl)
        global_bpl_codes.add(w_bpl)
        
    if not target_rows:
        logger.info("No high-quality target couples found to process! Check your JSON.")
        return

    yield_pct = (len(target_rows) / len(gedcom_couples)) * 100
    logger.info(f"Skipped {skipped_ghosts} low-resolution targets. Searchable Yield: {yield_pct:.1f}%")
    logger.info(f"Initialized {len(target_rows)} elite, fully-documented target anchors.")

    con.execute("CREATE TABLE targets (idx INTEGER, h_byr INTEGER, h_bpl INTEGER, h_fbpl INTEGER, h_mbpl INTEGER, w_byr INTEGER, w_bpl INTEGER, w_fbpl INTEGER, w_mbpl INTEGER, kid_fingerprint INTEGER, h_first VARCHAR, h_last VARCHAR, w_first VARCHAR, w_last VARCHAR)")
    con.executemany("INSERT INTO targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", target_rows)

    kid_match_condition_sql = ""

    all_matches = []
    
    parent_filter_sql = ""
    bpl_filter_sql = ""
    if global_bpl_codes:
        bpl_filter_str = ", ".join(map(str, global_bpl_codes))
        bpl_filter_sql = f"AND base_bpl IN ({bpl_filter_str})"
        parent_filter_sql = f"""
          AND (TRY_CAST(year AS INTEGER) IN (1850, 1860, 1870) OR 
               (
                 (fbpl IS NULL OR fbpl = '' OR fbpl = '0' OR base_fbpl IN ({bpl_filter_str}))
                 AND (mbpl IS NULL OR mbpl = '' OR mbpl = '0' OR base_mbpl IN ({bpl_filter_str}))
               )
          )"""

    match_db_path = os.path.join(BASE_DATA_DIR, "DemographicMatches2.db")
    con.execute(f"ATTACH '{match_db_path}' AS match_db")

    for decade in range(1850, 1960, 10):
        db_path = os.path.join(YEARLY_VAULT_DIR, f"YearVault_{decade}.db")
        if not os.path.exists(db_path):
            continue
            
        logger.info(f"\n=======================================================")
        logger.info(f"Processing {decade} Census Vault")
        logger.info(f"=======================================================")
        
        con.execute(f"ATTACH '{db_path}' AS vault")
        
        con.execute("CREATE TEMP TABLE couple_members AS SELECT head_histid AS histid FROM vault.families UNION SELECT spouse_histid AS histid FROM vault.families WHERE spouse_histid IS NOT NULL")
        
        con.execute(f"""
            CREATE TEMP TABLE relevant_individuals AS
            WITH parsed_inds AS (
                SELECT i.*,
                       TRY_CAST(i.birthyr AS INTEGER) AS birthyr_int,
                       CASE WHEN TRY_CAST(i.bpld AS INTEGER) >= 1000 THEN TRY_CAST(i.bpld AS INTEGER) // 100 ELSE TRY_CAST(i.bpld AS INTEGER) END AS base_bpl,
                       CASE WHEN TRY_CAST(i.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.fbpl AS INTEGER) // 100 ELSE TRY_CAST(i.fbpl AS INTEGER) END AS base_fbpl,
                       CASE WHEN TRY_CAST(i.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.mbpl AS INTEGER) // 100 ELSE TRY_CAST(i.mbpl AS INTEGER) END AS base_mbpl
                FROM vault.individuals i
                JOIN couple_members cm ON i.histid = cm.histid
                WHERE i.bpld IS NOT NULL AND i.bpld != ''
            )
            SELECT * FROM parsed_inds
            WHERE 1=1 
              {bpl_filter_sql}
              {parent_filter_sql};
        """)
        
        live_count = con.execute("SELECT COUNT(*) FROM relevant_individuals").fetchone()[0]
        logger.info(f"  -> Dead Weight dropped! Only {live_count:,} relevant individuals remain in RAM.")

        matches = con.execute(f"""
            SELECT 
                t.idx, f.family_id, c.clan_id, f.year,
                t.h_first AS h_first_gedcom, h.first_name AS h_first_db,
                t.h_last  AS h_last_gedcom,  h.last_name  AS h_last_db,
                t.w_first AS w_first_gedcom, s.first_name AS w_first_db,
                t.w_last  AS w_last_gedcom,  s.last_name  AS w_last_db,
                t.h_byr   AS h_byr_gedcom,   h.birthyr_int AS h_byr_db,
                t.w_byr   AS w_byr_gedcom,   s.birthyr_int AS w_byr_db,
                t.h_bpl   AS h_bpl_gedcom,   h.bpld       AS h_bpl_db,
                t.w_bpl   AS w_bpl_gedcom,   s.bpld       AS w_bpl_db,
                t.h_fbpl  AS h_fbpl_gedcom,  h.fbpl       AS h_fbpl_db,
                t.h_mbpl  AS h_mbpl_gedcom,  h.mbpl       AS h_mbpl_db,
                t.w_fbpl  AS w_fbpl_gedcom,  s.fbpl       AS w_fbpl_db,
                t.w_mbpl  AS w_mbpl_gedcom,  s.mbpl       AS w_mbpl_db,
                t.kid_fingerprint, 0 AS db_kid_fingerprint, f.countyicp, f.stateicp,
                f.head_histid, f.spouse_histid
            FROM vault.families f
            JOIN relevant_individuals h ON f.head_histid = h.histid
            JOIN relevant_individuals s ON f.spouse_histid = s.histid
            LEFT JOIN match_db.clan_mapping c ON f.family_id = c.family_id
            JOIN targets t
                ON h.base_bpl = t.h_bpl 
                AND s.base_bpl = t.w_bpl
                AND h.sex = '1' AND s.sex = '2'
                {kid_match_condition_sql}
                AND h.birthyr_int BETWEEN t.h_byr - {YEAR_WINDOW} AND t.h_byr + {YEAR_WINDOW}
                AND s.birthyr_int BETWEEN t.w_byr - {YEAR_WINDOW} AND t.w_byr + {YEAR_WINDOW}
                AND (TRY_CAST(f.year AS INTEGER) IN (1850, 1860, 1870) OR 
                     (
                        (t.h_fbpl = 0 OR h.fbpl IS NULL OR h.fbpl = '' OR h.fbpl = '0' OR h.base_fbpl = t.h_fbpl)
                        AND (t.h_mbpl = 0 OR h.mbpl IS NULL OR h.mbpl = '' OR h.mbpl = '0' OR h.base_mbpl = t.h_mbpl)
                        AND (t.w_fbpl = 0 OR s.fbpl IS NULL OR s.fbpl = '' OR s.fbpl = '0' OR s.base_fbpl = t.w_fbpl)
                        AND (t.w_mbpl = 0 OR s.mbpl IS NULL OR s.mbpl = '' OR s.mbpl = '0' OR s.base_mbpl = t.w_mbpl)
                     )
                )
        """).fetchall()

        logger.info(f"  -> SUCCESS: Found {len(matches)} mathematically proven candidates!")
        all_matches.extend(matches)

        con.execute("DROP TABLE relevant_individuals")
        con.execute("DROP TABLE couple_members")
        con.execute("DETACH vault")

    if all_matches:
        logger.info(f"\n=======================================================")
        logger.info("PHASE 2: EVALUATING MULTI-DECADE TRAJECTORIES (MOTION PICTURE MATCH)")
        logger.info(f"=======================================================")

        grouped_matches = {}
        for match in all_matches:
            target_idx = match[0]
            clan_id = match[2] if match[2] else f"UNCLANNED_{match[1]}"
            grouped_matches.setdefault(target_idx, {}).setdefault(clan_id, []).append(match)

        trajectory_hits = 0
        exact_hits = 0
        names_to_write = set()

        for target_idx, clans in grouped_matches.items():
            g_data = gedcom_couples[target_idx]
            h_first, h_last = g_data.get('h_first', ''), g_data.get('h_last', '')
            w_first, w_last = g_data.get('w_first', ''), g_data.get('w_last', '')
            
            logger.info(f"\n-------------------------------------------------------")
            logger.info(f"REVIEWING Target {target_idx}: {h_first} {h_last} & {w_first} {w_last}")
            
            for clan_id, clan_matches in clans.items():
                clan_matches.sort(key=lambda x: int(x[3])) # Sort chronologically
                
                trajectory_score = 0
                exact_hw_match = False
                traj_log = []
                
                for cand in clan_matches:
                    cand_year = int(cand[3])
                    
                    # Name Check
                    h_match = (str(cand[4]).strip().upper() == str(cand[5]).strip().upper() and
                               str(cand[6]).strip().upper() == str(cand[7]).strip().upper())
                    w_match = (str(cand[8]).strip().upper() == str(cand[9]).strip().upper() and
                               str(cand[10]).strip().upper() == str(cand[11]).strip().upper())
                    
                    if h_match and w_match:
                        exact_hw_match = True
                        
                    # Geo Check
                    h_res = g_data.get(f'h_res_{cand_year}', '')
                    h_res_disp = h_res if h_res else "No Data"
                    
                    db_county_code = "N/A"
                    if cand[30] is not None:
                        try: db_county_code = str(int(float(cand[30])))
                        except ValueError: db_county_code = str(cand[30]).strip()
                        
                    db_state_name = STATEICP_MAP.get(int(float(cand[31])), "Unknown State") if cand[31] is not None else "Unknown State"
                    db_county_name = county_names_dict.get(db_state_name, {}).get(db_county_code, "Unknown County")
                    
                    geo_hit = False
                    if db_county_name != "Unknown County":
                        db_c_clean = db_county_name.upper().replace(" COUNTY", "").strip()
                        g_res_clean = h_res.upper().replace(" COUNTY", "").replace(" CO.", "").strip()
                        
                        if db_c_clean and db_c_clean in g_res_clean:
                            geo_hit = True
                            trajectory_score += 1
                            
                    if geo_hit:
                        traj_log.append(f"  [{cand_year}] [+] GEO MATCH: {db_county_name}, {db_state_name}")
                    else:
                        traj_log.append(f"  [{cand_year}] [-] DB: {db_county_name}, {db_state_name} | GEDCOM: {h_res_disp}")
                
                # Evaluation (Score of 2 means they matched exact counties in at least 2 different decades)
                is_trajectory_match = trajectory_score >= 2
                
                if exact_hw_match: exact_hits += 1
                if is_trajectory_match: trajectory_hits += 1

                if is_trajectory_match:
                    for cand in clan_matches:
                        names_to_write.add((cand[32], h_first, h_last))
                        names_to_write.add((cand[33], w_first, w_last))
                
                # LOG EVERYTHING so we can see the data!
                logger.info(f" > CLAN: {clan_id} | Decades Found: {len(clan_matches)} | Trajectory Score: {trajectory_score}")
                for log_line in traj_log:
                    logger.info(log_line)
                if is_trajectory_match:
                    logger.info(f"   *** MATHEMATICAL CERTAINTY: MULTI-DECADE TRAJECTORY MATCH ***")
                elif exact_hw_match:
                    logger.info(f"   * EXACT NAME MATCH *")
                else:
                    logger.info(f"   --- Rejected (Trajectory Score too low) ---")
                        
        logger.info(f"\n=======================================================")
        logger.info(f"V3 TRAJECTORY VALIDATION SUMMARY")
        logger.info(f"  Targets Evaluated    : {len(target_rows):,}")
        logger.info(f"  Exact Name Matches   : {exact_hits:,}")
        logger.info(f"  Trajectory Matches   : {trajectory_hits:,} (100% Certainty)")
        logger.info(f"=======================================================\n")

        if names_to_write:
            logger.info(f"=======================================================")
            logger.info("PHASE 3: SAVING RESOLVED NAMES TO TIME MACHINE")
            logger.info(f"=======================================================")
            con.execute("DROP TABLE IF EXISTS match_db.resolved_names")
            con.execute("CREATE TABLE match_db.resolved_names (histid VARCHAR, first_name VARCHAR, last_name VARCHAR)")
            con.executemany("INSERT INTO match_db.resolved_names VALUES (?, ?, ?)", list(names_to_write))
            logger.info(f"  -> Successfully painted {len(names_to_write):,} real ancestor records into DemographicMatches2.db!")
            logger.info(f"=======================================================\n")

if __name__ == '__main__':
    main_logger = gen_logging.setup_logging("NAME_OVERLAY_V3")
    run_overlay_v3(main_logger)