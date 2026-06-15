"""
-----------------------------------
File: LinkFamiliesByDemographics.py

Summary: "The Time Machine"
         Links Relational Families across 10-year census gaps using an unbreakable
         10-variable demographic hash (Sex, BirthYr, BPL, FBPL, MBPL) for the couple.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0: http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sqlite3
import sys
import time

import duckdb

# Add the 'python' directory and project root to sys.path so we can import properly
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [script_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")


def link_households_across_decades(logger):
    logger.info("Initializing DuckDB... Finding demographic household matches across ALL consecutive decades.")

    # DECISION: Remove the automatic deletion of MATCH_DB so we can RESUME if the computer reboots.
    # We will now create tables IF THEY DON'T EXIST and track our progress.
    try:
        if os.path.exists(MATCH_DB):
            with open(MATCH_DB, 'a'):
                pass
    except PermissionError:
        logger.warning(f"CRITICAL: {MATCH_DB} is locked by another program (likely a DB Viewer).")
        logger.warning("Please close any applications using this database and try again.")
        return

    # DECISION: We use DuckDB here instead of standard SQLite because DuckDB is an OLAP 
    # (Online Analytical Processing) engine. It is specifically designed to perform massive, 
    # memory-intensive Cartesian joins across millions of rows in seconds.
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='32GB'")
    con.execute("INSTALL sqlite; LOAD sqlite;")

    logger.info("Attaching Vaults...")
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db (TYPE SQLITE);")

    logger.info("Step 1/3: Extracting Head and Spouse Demographics...")
    step1_start = time.time()
    con.execute("""
                CREATE
                TEMP TABLE hh_features (
            family_id VARCHAR,
            year INTEGER,
            head_histid VARCHAR,
            head_sex VARCHAR,
            head_birthyr INTEGER,
            head_bpld VARCHAR,
            head_fbpl VARCHAR,
            head_mbpl VARCHAR,
            spouse_histid VARCHAR,
            spouse_sex VARCHAR,
            spouse_birthyr INTEGER,
            spouse_bpld VARCHAR,
            spouse_fbpl VARCHAR,
            spouse_mbpl VARCHAR
        )
                """)

    decades = [1850, 1860, 1870, 1880, 1900, 1910, 1920, 1930, 1940, 1950]
    for year in decades:
        db_path = os.path.join(VAULT_DIR, f"YearVault_{year}.db")
        if os.path.exists(db_path):
            logger.info(f"  -> Extracting features from {year}...")
            con.execute(f"ATTACH '{db_path}' AS vault_{year} (TYPE SQLITE, READ_ONLY);")
            con.execute(f"""
                INSERT INTO hh_features
                SELECT 
                    f.family_id, f.year,
                    h.histid, h.sex, h.birthyr, h.bpld, h.fbpl, h.mbpl,
                    s.histid, s.sex, s.birthyr, s.bpld, s.fbpl, s.mbpl
                FROM vault_{year}.families f
                JOIN vault_{year}.individuals h ON f.head_histid = h.histid
                JOIN vault_{year}.individuals s ON f.spouse_histid = s.histid
                WHERE h.birthyr IS NOT NULL AND s.birthyr IS NOT NULL
                  AND f.num_kids > 0;
            """)

    step1_end = time.time()
    feature_cnt = con.execute("SELECT COUNT(*) FROM hh_features").fetchone()[0]
    logger.info(f"  -> Extracted {feature_cnt:,} target couples in {step1_end - step1_start:.2f} seconds.")

    logger.info("Step 2/3: Executing 10-Variable Nationwide Demographic Hash...")
    step2_start = time.time()

    # DECISION: We make raw_links a PERMANENT table inside our SQLite match_db so we don't lose data on reboot.
    # We also create a progress tracker table to checkpoint our chunks.
    # UPDATE: We filter the links IN-MEMORY per chunk, and only save the final unique winners to avoid TBs of data.
    con.execute("""
                CREATE TABLE IF NOT EXISTS match_db.household_links
                (
                    family_id_1
                    TEXT,
                    family_id_2
                    TEXT,
                    year_1
                    INTEGER,
                    year_2
                    INTEGER,
                    head_histid_1
                    TEXT,
                    head_histid_2
                    TEXT,
                    spouse_histid_1
                    TEXT,
                    spouse_histid_2
                    TEXT
                );
                CREATE TABLE IF NOT EXISTS match_db.completed_chunks
                (
                    base_year
                    INTEGER,
                    target_year
                    INTEGER
                );
                """)

    # DECISION: Divide and Conquer. Instead of joining 50M rows against 50M rows dynamically,
    # we explicitly loop through the decades. This forces the database to only compare ~5 million 
    # records at a time, bypassing the query optimizer's "Nested Loop" death spiral.
    # DECISION: Using gaps of 10, 20, and 30 creates overlapping, multi-hop link types. This is intentional 
    # so we can securely bridge the massive missing data gap from the 1890 Census fire.
    decades = [1850, 1860, 1870, 1880, 1900, 1910, 1920, 1930, 1940]
    gaps = [10, 20, 30]

    for base_year in decades:
        for gap in gaps:
            target_year = base_year + gap
            if target_year > 1950:
                continue

            # Check if we already did this chunk before the reboot
            is_done = con.execute(
                f"SELECT COUNT(*) FROM match_db.completed_chunks WHERE base_year = {base_year} AND target_year = {target_year}").fetchone()[
                0]
            if is_done > 0:
                logger.info(f"  -> Skipping {base_year} to {target_year} (Already completed in a previous run)")
                continue

            logger.info(f"  -> Comparing {base_year} to {target_year}...")

            # DECISION: Create the raw matches table first so we can extract debug statistics
            # before we filter and insert the 1-to-1 winners into the permanent database.
            con.execute(f"""
                CREATE TEMP TABLE raw_matches AS 
                WITH y1 AS (SELECT * FROM hh_features WHERE year = {base_year}),
                     y2 AS (SELECT * FROM hh_features WHERE year = {target_year}),
                     raw_matches AS (
                         SELECT 
                             y1.family_id AS family_id_1, y2.family_id AS family_id_2,
                             y1.year AS year_1, y2.year AS year_2,
                             y1.head_histid AS head_histid_1, y2.head_histid AS head_histid_2,
                             y1.spouse_histid AS spouse_histid_1, y2.spouse_histid AS spouse_histid_2
                         FROM y1
                         JOIN y2
                           ON y1.head_sex = y2.head_sex
                          AND y1.spouse_sex = y2.spouse_sex
                          AND y1.head_bpld = y2.head_bpld
                          AND y1.spouse_bpld = y2.spouse_bpld
                          AND y1.head_birthyr = y2.head_birthyr
                          AND y1.spouse_birthyr = y2.spouse_birthyr
                         WHERE (y1.head_fbpl = y2.head_fbpl OR y1.head_fbpl IS NULL OR y2.head_fbpl IS NULL)
                           AND (y1.head_mbpl = y2.head_mbpl OR y1.head_mbpl IS NULL OR y2.head_mbpl IS NULL)
                           AND (y1.spouse_fbpl = y2.spouse_fbpl OR y1.spouse_fbpl IS NULL OR y2.spouse_fbpl IS NULL)
                           AND (y1.spouse_mbpl = y2.spouse_mbpl OR y1.spouse_mbpl IS NULL OR y2.spouse_mbpl IS NULL)
                     )
                SELECT * FROM raw_matches;
            """)

            # TELEMETRY: Calculate how many matches were rejected due to ambiguity
            raw_count = con.execute("SELECT COUNT(*) FROM raw_matches").fetchone()[0]

            con.execute(f"""
                INSERT INTO match_db.household_links
                SELECT family_id_1, family_id_2, 
                       year_1, year_2,
                       head_histid_1, head_histid_2,
                       spouse_histid_1, spouse_histid_2
                FROM raw_matches r1
                WHERE family_id_1 IN (
                    SELECT family_id_1 FROM raw_matches GROUP BY family_id_1 HAVING COUNT(*) = 1
                )
                AND family_id_2 IN (
                    SELECT family_id_2 FROM raw_matches GROUP BY family_id_2 HAVING COUNT(*) = 1
                );
            """)

            inserted_cnt = con.execute(
                f"SELECT COUNT(*) FROM match_db.household_links WHERE year_1={base_year} AND year_2={target_year}").fetchone()[
                0]
            rejected_cnt = raw_count - inserted_cnt
            logger.info(
                f"     -> Linked {inserted_cnt:,} families. (Rejected {rejected_cnt:,} due to duplicate collisions)")

            # TELEMETRY: Log a tiny sample of the matches so the human can see what is happening!
            samples = con.execute(
                f"SELECT family_id_1, family_id_2 FROM match_db.household_links WHERE year_1={base_year} AND year_2={target_year} LIMIT 3").fetchall()
            for s1, s2 in samples:
                logger.info(f"       [SAMPLE] {s1} <---> {s2}")

            con.execute("DROP TABLE raw_matches")

            # Mark chunk as complete
            con.execute(f"INSERT INTO match_db.completed_chunks VALUES ({base_year}, {target_year})")

    step2_end = time.time()
    logger.info(f"  -> Step 2 completed in {step2_end - step2_start:.2f} seconds.")

    logger.info("Step 3/3: Enforcing Unique 1-to-1 Mathematical Matches...")
    # DECISION: Because we now filter IN-MEMORY during Step 2, Step 3 is instantaneous!
    logger.info("  -> Uniqueness was successfully enforced chunk-by-chunk in memory!")

    match_count = con.execute("SELECT COUNT(*) FROM match_db.household_links").fetchone()[0]
    logger.info(f"SUCCESS! Found {match_count:,} perfect multi-decade matches.")

    con.close()

    # --------------------------------------------------------------------------
    # Step 4: Build the Clans
    # --------------------------------------------------------------------------
    logger.info("\nStep 4: Building Time Machine Clans (Connected Components)...")
    with sqlite3.connect(MATCH_DB) as sq_conn:
        sq_cursor = sq_conn.cursor()

        logger.info("  -> Building indices on household_links...")
        sq_cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_famid1 ON household_links(family_id_1);")
        sq_cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_year1 ON household_links(year_1);")

        links = sq_cursor.execute("SELECT family_id_1, family_id_2 FROM household_links").fetchall()

        from collections import defaultdict
        adj = defaultdict(list)
        for u, v in links:
            adj[u].append(v)
            adj[v].append(u)

        visited = set()
        clans = []
        clan_id_counter = 1

        for node in adj.keys():
            if node not in visited:
                stack = [node]
                current_clan = set()
                while stack:
                    curr = stack.pop()
                    if curr not in visited:
                        visited.add(curr)
                        current_clan.add(curr)
                        for neighbor in adj[curr]:
                            if neighbor not in visited:
                                stack.append(neighbor)

                for fam in current_clan:
                    clans.append((fam, f"CLAN_{clan_id_counter}"))
                clan_id_counter += 1

        # TELEMETRY: Check for "Mega-Clans" (If a clan has thousands of members, the logic is broken)
        clan_sizes = defaultdict(int)
        for fam, clan in clans: clan_sizes[clan] += 1
        top_clans = sorted(clan_sizes.items(), key=lambda x: x[1], reverse=True)[:5]

        logger.info(f"  -> Formed {clan_id_counter - 1:,} distinct family timelines.")
        logger.info(f"  -> Top 5 Largest Clans (Safety Check): {top_clans}")

        sq_cursor.execute("DROP TABLE IF EXISTS clan_mapping")
        sq_cursor.execute("CREATE TABLE clan_mapping (family_id TEXT PRIMARY KEY, clan_id TEXT)")
        sq_cursor.executemany("INSERT INTO clan_mapping VALUES (?, ?)", clans)
        sq_cursor.execute("CREATE INDEX IF NOT EXISTS idx_clan_map_fam ON clan_mapping(family_id)")
        sq_conn.commit()

    logger.info(f"SUCCESS! Time Machine saved to: {MATCH_DB}")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="DEMO_LINK")
    link_households_across_decades(main_logger)
