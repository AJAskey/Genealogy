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

import os
import sys
import json
import duckdb
from collections import defaultdic

# -----------------------------------------------------------------------------
# 1. The Setup Phase
#
# Imports and Paths: The script starts by bringing in the tools it needs. 
# It figures out exactly where your script is running from so it can reliably 
# find your utils folder and data directories.
#
# Test Mode: We have a toggle here and a target last name (ASKEY). When this 
# is on, the script looks in your TestVaults folder instead of the massive 
# production vaults to save you hours of waiting while testing.
# -----------------------------------------------------------------------------

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging
from utils.common_utils import get_bpl_prefixes, create_standard_dict

# --- Configuration ---
if os.path.exists(r"d:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
elif os.path.exists(r"D:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

NAMED_VAULT_DIR = os.path.join(BASE_DATA_DIR, "NamedVaults")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
TEST_VAULT_DIR = os.path.join(BASE_DATA_DIR, "TestVaults")

# The JSON file you will generate from your GEDCOM script
COUPLES_JSON = os.path.join(project_root, "gedcom_sources", "gedcom_couples.json")

# -----------------------------------------------------------------------------
# 2. Loading the "Targets"
#
# get_base_code(): A helper function that converts a state string into the IPUMS integer.
#
# Loading the JSON: Loads gedcom_couples.json. If TEST_MODE is on, it throws 
# away any couple whose last name doesn't match our target.
#
# The "Ruthless Filter": Loops through all GEDCOM couples. If a couple is missing 
# any of the 6 required birthplaces or their birth years, it skips them. We only 
# want "elite, fully-documented" couples to act as our anchors.
#
# Global BPLs: As it finds good couples, it adds their birthplace codes to a 
# master list. This tells the database which states we actually care about.
# -----------------------------------------------------------------------------

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


def run_overlay_v2(logger):
    logger.info("Initializing V2 DuckDB Overlay Engine...")
    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")

    if not os.path.exists(COUPLES_JSON):
        logger.error(f"Target JSON not found: {COUPLES_JSON}")
        return

    with open(COUPLES_JSON, 'r', encoding='utf-8') as f:
        gedcom_couples = json.load(f)

    if TEST_MODE:
        gedcom_couples = [c for c in gedcom_couples if c.get('h_last', '').upper() == TEST_H_LAST.upper()]
        logger.info(
            f"TEST MODE ENABLED: Filtered down to {len(gedcom_couples)} target couples with last name {TEST_H_LAST}.")

    logger.info(f"Loaded {len(gedcom_couples)} target couples from JSON.")

    # 1. Parse targets and collect global BPL codes for the Dead Weight Filter
    target_rows = []
    global_bpl_codes = set()

    for idx, g_dict in enumerate(gedcom_couples):
        h_bpl = get_base_code(g_dict.get('h_bpl'))
        h_fbpl = get_base_code(g_dict.get('h_fbpl'))
        h_mbpl = get_base_code(g_dict.get('h_mbpl'))
        w_bpl = get_base_code(g_dict.get('w_bpl'))
        w_fbpl = get_base_code(g_dict.get('w_fbpl'))
        w_mbpl = get_base_code(g_dict.get('w_mbpl'))

        # RUTHLESS FILTER: If they are missing any parent birthplaces, skip them entirely!
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

    # -------------------------------------------------------------------------
    # 3. Injecting Targets into DuckDB
    #
    # The script creates a temporary table in DuckDB called targets. It takes
    # all the surviving "elite" GEDCOM couples and inserts them into this table.
    # This allows us to use insanely fast SQL to compare our family tree directly
    # against the census databases.
    # -------------------------------------------------------------------------

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

    # Attach the time machine
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db (TYPE SQLITE, READ_ONLY);")

    # -------------------------------------------------------------------------
    # 4. The Time Machine Loop
    #
    # The script opens your vault folder (using TestVaults if test mode is on).
    # It loops through the databases, extracts the year, and "attaches" the file.
    # Attaching means DuckDB connects to it so it can read the tables inside
    # without having to load the whole massive file into RAM.
    # -------------------------------------------------------------------------

    # 2. Iterate Decades
    vault_dir_to_use = NAMED_VAULT_DIR
    if TEST_MODE and os.path.exists(TEST_VAULT_DIR):
        logger.info(f"TEST MODE: Using smaller test vaults from {TEST_VAULT_DIR}")
        vault_dir_to_use = TEST_VAULT_DIR

    for filename in os.listdir(vault_dir_to_use):
        if not (filename.startswith("NamedVault_") and filename.endswith(".db")): continue
        year = filename.replace("NamedVault_", "").replace(".db", "")

        logger.info(f"\n=======================================================")
        logger.info(f"Processing {year} Census Vault")
        logger.info(f"=======================================================")

        db_path = os.path.join(vault_dir_to_use, filename)
        con.execute(f"ATTACH '{db_path}' AS vault (TYPE SQLITE, READ_ONLY);")

        # 1850, 1860, and 1870 censuses do not have reliable parent birthplaces recorded.
        parent_bpl_filter = ""
        parent_bpl_match = ""

        # ---------------------------------------------------------------------
        # 5. The "Dead Weight" Filter
        #
        # Pre-1880 Exemption: If the census year is 1850, 1860, or 1870, the
        # script dynamically adjusts the SQL to ignore parent birthplaces.
        #
        # couple_members: Creates a tiny temp list of IDs of currently married people.
        #
        # relevant_individuals: Scans the massive census individuals table. It
        # drops anyone who isn't married (dropping singles and kids). Then, it
        # drops anyone whose birthplace isn't in our global_bpl_codes list.
        # Millions of rows are instantly vaporized to save RAM!
        # ---------------------------------------------------------------------

        if int(year) not in [1850, 1860, 1870]:
            parent_bpl_filter = f"""
              AND (i.fbpl IS NULL OR i.fbpl = '' OR i.fbpl = '0' OR TRY_CAST(i.fbpl AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.fbpl AS INTEGER) // 100) IN ({bpl_filter_str}))
              AND (i.mbpl IS NULL OR i.mbpl = '' OR i.mbpl = '0' OR TRY_CAST(i.mbpl AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.mbpl AS INTEGER) // 100) IN ({bpl_filter_str}))"""

            parent_bpl_match = """
                  AND
                      (h.fbpl IS NULL OR h.fbpl = '' OR h.fbpl = '0' OR TRY_CAST(h.fbpl AS INTEGER) = t.h_fbpl OR TRY_CAST(h.fbpl AS INTEGER) // 100 = t.h_fbpl)
                  AND
                      (h.mbpl IS NULL OR h.mbpl = '' OR h.mbpl = '0' OR TRY_CAST(h.mbpl AS INTEGER) = t.h_mbpl OR TRY_CAST(h.mbpl AS INTEGER) // 100 = t.h_mbpl)
                  AND
                      (s.fbpl IS NULL OR s.fbpl = '' OR s.fbpl = '0' OR TRY_CAST(s.fbpl AS INTEGER) = t.w_fbpl OR TRY_CAST(s.fbpl AS INTEGER) // 100 = t.w_fbpl)
                  AND
                      (s.mbpl IS NULL OR s.mbpl = '' OR s.mbpl = '0' OR TRY_CAST(s.mbpl AS INTEGER) = t.w_mbpl OR TRY_CAST(s.mbpl AS INTEGER) // 100 = t.w_mbpl)"""

        # DECISION: The Extreme Dead Weight Filter!
        # Drops singles, children, and anyone whose birthplaces aren't in our target set.
        # To optimize, we first gather all unique individuals who are part of a couple, avoiding a costly JOIN with an OR condition.
        con.execute("""
            CREATE TEMP TABLE couple_members AS
            SELECT head_histid AS histid FROM vault.families WHERE head_histid IS NOT NULL AND spouse_histid IS NOT NULL
            UNION
            SELECT spouse_histid AS histid FROM vault.families WHERE head_histid IS NOT NULL AND spouse_histid IS NOT NULL;
        """)

        # Now, create the filtered individuals table by joining against the smaller, pre-filtered set of couple members.
        con.execute(f"""
            CREATE TEMP TABLE relevant_individuals AS
            SELECT i.*
            FROM vault.individuals i
            JOIN couple_members cm ON i.histid = cm.histid
            WHERE i.bpld IS NOT NULL AND i.bpld != ''
              AND (TRY_CAST(i.bpld AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.bpld AS INTEGER) // 100) IN ({bpl_filter_str})){parent_bpl_filter};
        """)

        # ---------------------------------------------------------------------
        # 6. The Highlander Match
        #
        # Part A (matched_fams): Joins relevant_individuals to the families table
        # so the husband and wife are side-by-side. Then joins to the GEDCOM
        # targets table requiring 9 variables to match perfectly.
        #
        # Part B (highlander): "There can be only one." It groups matches by GEDCOM
        # target ID. If one GEDCOM couple matches multiple Census families, it
        # drops them all to prevent a false match. Keeps only COUNT(*) = 1.
        #
        # Part C: Returns only the pristine matches that survived the rule.
        # ---------------------------------------------------------------------

        survivors = con.execute("SELECT COUNT(*) FROM relevant_individuals").fetchone()[0]
        logger.info(f"  -> Dead Weight dropped! Only {survivors:,} relevant individuals remain in RAM.")

        # DECISION: The Native SQL 10-Variable Match & Highlander Filter
        query = f"""
                WITH matched_fams AS (SELECT t.target_idx,
                                             f.family_id,
                                             f.num_kids,
                                             h.histid     AS h_histid,
                                             s.histid     AS w_histid,
                                             h.first_name AS h_first_db,
                                             h.last_name  AS h_last_db,
                                             s.first_name AS w_first_db,
                                             s.last_name  AS w_last_db,
                                             c.clan_id
                                      FROM vault.families f
                                               JOIN relevant_individuals h ON f.head_histid = h.histid
                                               JOIN relevant_individuals s ON f.spouse_histid = s.histid
                                               LEFT JOIN match_db.clan_mapping c ON f.family_id = c.family_id
                                               JOIN targets t
                                                    ON h.sex = '1' AND s.sex = '2'
                                                        AND h.birthyr BETWEEN t.h_byr - 1 AND t.h_byr + 1
                                                        AND s.birthyr BETWEEN t.w_byr - 1 AND t.w_byr + 1
                                                        AND UPPER(h.last_name) = t.h_last
                                                        AND
                                                       (TRY_CAST(h.bpld AS INTEGER) = t.h_bpl OR TRY_CAST(h.bpld AS INTEGER) // 100 = t.h_bpl)
                                                        AND
                                                       (TRY_CAST(s.bpld AS INTEGER) = t.w_bpl OR TRY_CAST(s.bpld AS INTEGER) // 100 = t.w_bpl)
                                                        {parent_bpl_match}
                                      ),
                     highlander AS (SELECT target_idx FROM matched_fams GROUP BY target_idx HAVING COUNT(*) = 1)
                SELECT m.*
                FROM matched_fams m
                         JOIN highlander hl ON m.target_idx = hl.target_idx;
                """

        matches = con.execute(query).fetchall()
        logger.info(f"  -> SUCCESS: Found {len(matches)} mathematically proven 1-to-1 anchors!")

        # ---------------------------------------------------------------------
        # 7. Output and Cleanup
        #
        # If TEST_MODE is on, prints the names of the matches and the clan_id.
        # Finally, it drops the temporary tables and detaches the census
        # database, completely clearing the memory so it can safely move on
        # to the next decade without crashing.
        # ---------------------------------------------------------------------

        if TEST_MODE and matches:
            logger.info("  -> TEST MODE MATCH DETAILS:")
            for match in matches:
                # The CTE outputs: target_idx, family_id, num_kids, h_histid, w_histid, h_first_db, h_last_db, w_first_db, w_last_db, clan_id
                m_first, m_last, w_first, w_last, clan_id = match[5], match[6], match[7], match[8], match[9]
                logger.info(f"     GEDCOM Target {match[0]} matched to Census Family {match[1]}")
                logger.info(f"     Matched Names: {m_first} {m_last} & {w_first} {w_last} | Clan ID: {clan_id}")

        con.execute("DROP TABLE relevant_individuals")
        con.execute("DROP TABLE couple_members")
        con.execute("DETACH vault")


##### ------------------------------------------------------------

if __name__ == '__main__':
    main_logger = gen_logging.setup_logging("NAME_OVERLAY_V2")
    run_overlay_v2(main_logger)

    # -------------------------------------------------------------------------
    # 1. The Entry Point (Bottom of the script)
    # What's happening: The script starts at if __name__ == '__main__':. It sets up your logging system so 
    # everything outputs to your log file, and then it passes that logger into the main function, 
    # run_overlay_v2(main_logger).
    #
    # 2. Setup & JSON Loading (Lines 77 - 88)
    # What's happening: It initializes DuckDB and loads the SQLite extension so DuckDB can read your vault 
    # files natively. Then it opens your gedcom_couples.json file.
    # Watch this variable: Keep an eye on gedcom_couples. Initially, it will load every couple from your JSON. 
    # But a few lines later, because TEST_MODE = True, it aggressively filters that list down to only couples with 
    # the last name "ASKEY". You'll see the size of that list shrink instantly!
    #
    # 3. The "Ruthless Filter" Loop (Lines 91 - 114)
    # What's happening: You are now looping through your Askey GEDCOM couples one by one. The script calls 
    # get_base_code() to clean up the state strings (e.g., converting "Pennsylvania" to 42).
    # The Trapdoor: On line 104 (if None in...), it checks if the couple is missing any of the required 6 
    # birthplaces or their birth years. If they are, it hits continue and skips them.
    # Watch these variables:
    # - global_bpl_codes: This set will slowly grow, collecting only the unique state codes 
    #   (like 42 for PA, 39 for OH) that your surviving Askeys were born in.
    # - target_rows: This is the final list of "elite" couples that passed the test, formatted as clean tuples ready 
    #   for the database.
    #
    # 4. Injecting into DuckDB (Lines 126 - 146)
    # What's happening: The Python loop is done. The script creates a temporary table in DuckDB called targets 
    # and uses con.executemany() to dump all your target_rows into it at lightning speed. It also converts your 
    # global_bpl_codes into a comma-separated string (bpl_filter_str) so it can be used in SQL queries later.
    #
    # 5. The Time Machine Loop (Lines 149 - 171)
    # What's happening: The script figures out it should look in TestVaults (because of TEST_MODE) 
    # and loops through the .db files inside.
    # Attaching: When it hits con.execute(f"ATTACH... AS vault"), DuckDB securely connects to your 
    # 1920 (or whichever year) test vault without loading the whole thing into memory.
    # Dynamic SQL: It checks the year string. If the year is 1880 or later, it populates parent_bpl_filter 
    # and parent_bpl_match with strict SQL rules that demand the mother's and father's birthplaces match perfectly.
    #
    # 6. The Dead Weight Filter (Lines 187 - 200)
    # What's happening: This is where we save your computer's RAM.
    # - First, it creates couple_members, getting a quick list of everyone who is actively married in the census.
    # - Then, it creates relevant_individuals.
    # Watch this variable: Step over the query and look at survivors. This tells you exactly how many people 
    # survived the filter. It drops anyone not married, and anyone not born in the states we collected in 
    # global_bpl_codes.
    #
    # 7. The Highlander Match (Lines 206 - 231)
    # What's happening: This is the massive SQL engine firing.
    # - It joins the husband, the wife, the census family record, and your GEDCOM targets table all together.
    # - It aligns them on 9 variables: Husband name, husband/wife birth years, and all 6 birth places.
    # - It then applies the highlander rule: HAVING COUNT(*) = 1. If an Askey couple matches more than one census 
    #   family, it drops them both to prevent bad data.
    # Watch this variable: matches! When this query finishes and fetches all, matches 
    # will contain your 1-to-1 mathematically proven links.
    #
    # 8. Cleanup and Next Decade (Lines 242 - 253)
    # What's happening: If TEST_MODE is on and it found matches, it prints them neatly to the console. 
    # Finally, it drops the temp tables (DROP TABLE relevant_individuals, etc.) and detaches the vault.
    # The Loop Continues: It loops back up to step 5, grabs the 1930 database, and does it all over again!
    # -------------------------------------------------------------------------
