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
from collections import defaultdict

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

# The JSON file you will generate from your GEDCOM script
COUPLES_JSON = os.path.join(project_root, "gedcom_sources", "gedcom_couples.json")


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

    # 2. Iterate Decades
    for filename in os.listdir(NAMED_VAULT_DIR):
        if not (filename.startswith("NamedVault_") and filename.endswith(".db")): continue
        year = filename.replace("NamedVault_", "").replace(".db", "")

        logger.info(f"\n=======================================================")
        logger.info(f"Processing {year} Census Vault")
        logger.info(f"=======================================================")

        db_path = os.path.join(NAMED_VAULT_DIR, filename)
        con.execute(f"ATTACH '{db_path}' AS vault (TYPE SQLITE, READ_ONLY);")

        # 1850, 1860, and 1870 censuses do not have reliable parent birthplaces recorded.
        parent_bpl_filter = ""
        parent_bpl_match = ""
        
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
        con.execute(f"""
            CREATE TEMP TABLE relevant_individuals AS
            SELECT i.*
            FROM vault.individuals i
            JOIN vault.families f ON (i.histid = f.head_histid OR i.histid = f.spouse_histid)
            WHERE f.head_histid IS NOT NULL AND f.spouse_histid IS NOT NULL
              AND i.bpld IS NOT NULL AND i.bpld != ''
              AND (TRY_CAST(i.bpld AS INTEGER) IN ({bpl_filter_str}) OR (TRY_CAST(i.bpld AS INTEGER) // 100) IN ({bpl_filter_str})){parent_bpl_filter};
        """)

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
                                                        AND h.last_name = t.h_last
                                                        AND f.num_kids = t.num_kids
                                                        AND
                                                       (TRY_CAST(h.bpld AS INTEGER) = t.h_bpl OR TRY_CAST(h.bpld AS INTEGER) // 100 = t.h_bpl)
                                                        AND
                                                       (TRY_CAST(s.bpld AS INTEGER) = t.w_bpl OR TRY_CAST(s.bpld AS INTEGER) // 100 = t.w_bpl)
                                                        {parent_bpl_match}
                                      ),
                     highlander AS (SELECT target_idx FROM matched_fams GROUP BY target_idx HAVING COUNT(*) = 1)
                SELECT m.*
                FROM matched_fams m
                         JOIN highlander hl ON m.target_idx = hl.target_idx; \
                """

        matches = con.execute(query).fetchall()
        logger.info(f"  -> SUCCESS: Found {len(matches)} mathematically proven 1-to-1 anchors!")

        con.execute("DROP TABLE relevant_individuals")
        con.execute("DETACH vault")


if __name__ == '__main__':
    main_logger = gen_logging.setup_logging("NAME_OVERLAY_V2")
    run_overlay_v2(main_logger)
