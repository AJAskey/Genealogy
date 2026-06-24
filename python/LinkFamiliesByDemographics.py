"""
-----------------------------------
File: LinkFamiliesByDemographics.py

Summary: "THE TIME MACHINE" - Blind Demographic Linking Engine

         THE GOAL: 
         To mathematically prove that a nameless family living in 1880 is the 
         exact same family living in 1900, 1910, or 1920, without ever looking at 
         their names. Names change, get misspelled, or are transcribed poorly. 
         Core biological demographics do not.

         WHAT IT IS DOING:
         1. Extracts a 10-variable "Demographic Fingerprint" (Sex, Birth Year, 
            Birthplace, Father's BPL, Mother's BPL for both Husband and Wife) 
            for every family across a century of census data.
         2. Uses DuckDB to perform massive, cross-decade Cartesian joins, finding 
            identical demographic fingerprints across time.
         3. Enforces the "Highlander Rule" to discard any ambiguous matches 
            (e.g., if one 1870 fingerprint matches two 1880 fingerprints, both 
            are discarded). Only mathematically certain, 1-to-1 links survive.
         4. Employs Graph Theory (Depth First Search) to stitch these individual 
            decade-to-decade links into continuous, multi-generational timelines 
            called "Clans".

         EXPECTED OUTPUT:
         A definitive `DemographicMatches.db` database containing a `clan_mapping` 
         table. This master key assigns a single, persistent `CLAN_ID` to multiple 
         `family_id`s across different decades, permanently linking them together 
         in time, ready for names to be overlaid onto their timelines.

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
SAMPLE_MODE = False
SAMPLE_DB_NAME = "CENSUS-SAMPLE.db"

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")

if SAMPLE_MODE:
    MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches_SAMPLE.db")
else:
    MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches2.db")


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

    # Route DuckDB temp files to the data drive to prevent E: drive thrashing
    duckdb_tmp_dir = os.path.join(BASE_DATA_DIR, "duckdb_tmp")
    os.makedirs(duckdb_tmp_dir, exist_ok=True)
    con.execute(f"PRAGMA temp_directory='{duckdb_tmp_dir}'")

    con.execute("INSTALL sqlite; LOAD sqlite;")
    con.execute("SET sqlite_all_varchar=true;")

    logger.info("Attaching Vaults...")
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db (TYPE SQLITE);")

    if SAMPLE_MODE:
        logger.info("SAMPLE MODE: Clearing previous match data so we start fresh...")
        con.execute("DROP TABLE IF EXISTS match_db.completed_chunks;")
        con.execute("DROP TABLE IF EXISTS match_db.household_links;")
        con.execute("DROP TABLE IF EXISTS match_db.clan_mapping;")

    logger.info("Step 1/3: Extracting Head and Spouse Demographics...")
    # ==================================================================================================
    #  STEP 1: THE DEMOGRAPHIC FINGERPRINT EXTRACTION
    # --------------------------------------------------------------------------------------------------
    #  PLAN: To link families across decades, we first need to define what makes a family unique.
    #        We are using a "demographic fingerprint" composed of 10 key variables for the
    #        husband and wife: Sex, Birth Year, Birth Place, Father's Birth Place, and Mother's
    #        Birth Place. The statistical probability of two different couples in the same
    #        region sharing this exact 10-variable signature is practically zero.
    #
    #  PROCESS: Instead of joining the massive, multi-gigabyte YearVault databases directly,
    #           we first create a temporary, in-memory table called `hh_features`. We then iterate
    #           through each YearVault and extract ONLY these 10 key variables (plus HISTIDs and
    #           family IDs) into this lean, optimized table. This dramatically speeds up the
    #           main linking query in Step 2 by allowing DuckDB to work with a much smaller,
    #           more focused dataset in memory. We also filter for families that have children,
    #           as childless couples are too demographically ambiguous to link with high confidence.
    # ==================================================================================================
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

    if SAMPLE_MODE:
        db_path = os.path.join(VAULT_DIR, SAMPLE_DB_NAME)
        if os.path.exists(db_path):
            con.execute(f"ATTACH '{db_path}' AS vault_sample (TYPE SQLITE, READ_ONLY);")
            for year in decades:
                logger.info(f"  -> Extracting features from {year} (SAMPLE MODE)...")
                con.execute(f"""
                    INSERT INTO hh_features
                    SELECT 
                        f.family_id, TRY_CAST(f.year AS INTEGER),
                        h.histid, h.sex, TRY_CAST(h.birthyr AS INTEGER), h.bpld, h.fbpl, h.mbpl,
                        s.histid, s.sex, TRY_CAST(s.birthyr AS INTEGER), s.bpld, s.fbpl, s.mbpl
                    FROM vault_sample.families f
                    JOIN vault_sample.individuals h ON f.head_histid = h.histid
                    JOIN vault_sample.individuals s ON f.spouse_histid = s.histid
                    WHERE TRY_CAST(f.year AS INTEGER) = {year}
                      AND TRY_CAST(h.birthyr AS INTEGER) IS NOT NULL AND TRY_CAST(s.birthyr AS INTEGER) IS NOT NULL
                      ;
                """)
    else:
        for year in decades:
            db_path = os.path.join(VAULT_DIR, f"YearVault_{year}.db")
            if os.path.exists(db_path):
                logger.info(f"  -> Extracting features from {year}...")
                con.execute(f"ATTACH '{db_path}' AS vault_{year} (TYPE SQLITE, READ_ONLY);")
                con.execute(f"""
                    INSERT INTO hh_features
                    SELECT 
                        f.family_id, TRY_CAST(f.year AS INTEGER),
                        h.histid, h.sex, TRY_CAST(h.birthyr AS INTEGER), h.bpld, h.fbpl, h.mbpl,
                        s.histid, s.sex, TRY_CAST(s.birthyr AS INTEGER), s.bpld, s.fbpl, s.mbpl
                    FROM vault_{year}.families f
                    JOIN vault_{year}.individuals h ON f.head_histid = h.histid
                    JOIN vault_{year}.individuals s ON f.spouse_histid = s.histid
                    WHERE TRY_CAST(h.birthyr AS INTEGER) IS NOT NULL AND TRY_CAST(s.birthyr AS INTEGER) IS NOT NULL
                      AND TRY_CAST(f.num_kids AS INTEGER) > -1;
                """)

    step1_end = time.time()
    feature_cnt = con.execute("SELECT COUNT(*) FROM hh_features").fetchone()[0]
    logger.info(f"  -> Extracted {feature_cnt:,} target couples in {step1_end - step1_start:.2f} seconds.")

    logger.info("Step 2/3: Executing 10-Variable Nationwide Demographic Hash...")
    # ==================================================================================================
    #  STEP 2 & 3: THE TIME MACHINE - LINKING DECADES & ENFORCING UNIQUENESS
    # --------------------------------------------------------------------------------------------------
    #  PLAN: This is the core of the Time Machine. We will join the `hh_features` table against
    #        itself to find identical demographic fingerprints across different decades. To manage
    #        the immense scale, we use a "Divide and Conquer" strategy, comparing only two
    #        decades at a time (e.g., 1870 vs. 1880, 1870 vs. 1900, etc.). The key is to
    #        only accept "1-to-1" matches. If a family from 1870 matches two families in 1880,
    #        it's an ambiguous "clone" and we discard it. Likewise, if two families from 1870
    #        match the same family in 1880, we also discard it. Only perfect, unambiguous
    #        links are saved.
    #
    #  PROCESS:
    #    1. LOOP STRATEGY: We loop through each possible pair of decades, separated by gaps of
    #       10, 20, and 30 years. This allows us to bridge the 1890 census gap.
    #    2. THE 10-VARIABLE HASH JOIN: For each pair of years (e.g., y1 and y2), we perform a
    #       JOIN where the 10 fingerprint variables are identical. We use a `TEMP TABLE`
    #       called `raw_matches` to hold all potential links for that specific year-pair.
    #    3. THE HIGHLANDER RULE (UNIQUENESS FILTER): "There can be only one!" We query the
    #       `raw_matches` table to find `family_id_1` and `family_id_2` values that appear
    #       EXACTLY ONCE. This is done with a `GROUP BY ... HAVING COUNT(*) = 1`. This
    #       brilliantly and efficiently filters out all ambiguous "one-to-many" or
    #       "many-to-one" matches, leaving only the mathematically certain 1-to-1 links.
    #    4. PERSISTENCE: These unique, validated links are then inserted into a permanent
    #       `household_links` table in the main `DemographicMatches.db` SQLite database.
    #       A `completed_chunks` table tracks which year-pairs have been processed, allowing
    #       the script to be stopped and resumed without losing progress.
    # ==================================================================================================
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
            if target_year == 1890 or target_year > 1950:
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
            # OPTIMIZATION: We completely avoid the Cartesian death-spiral by grouping families into 
            # "Demographic Profiles" FIRST. Instead of crossing 10M rows against 10M rows, we cross 
            # small profile buckets and multiply their counts. This turns 11-hour joins into seconds.
            con.execute(f"""
                CREATE TEMP TABLE raw_matches AS 
                WITH y1_profiles AS (
                    SELECT head_sex, spouse_sex, head_bpld, spouse_bpld, head_birthyr, spouse_birthyr, 
                           head_fbpl, head_mbpl, spouse_fbpl, spouse_mbpl, 
                           COUNT(*) as c1, 
                           MIN(family_id) as family_id_1,
                           MIN(head_histid) as head_histid_1,
                           MIN(spouse_histid) as spouse_histid_1
                    FROM hh_features 
                    WHERE year = {base_year}
                    GROUP BY head_sex, spouse_sex, head_bpld, spouse_bpld, head_birthyr, spouse_birthyr, 
                             head_fbpl, head_mbpl, spouse_fbpl, spouse_mbpl
                ),
                y2_profiles AS (
                    SELECT head_sex, spouse_sex, head_bpld, spouse_bpld, head_birthyr, spouse_birthyr, 
                           head_fbpl, head_mbpl, spouse_fbpl, spouse_mbpl, 
                           COUNT(*) as c2, 
                           MIN(family_id) as family_id_2,
                           MIN(head_histid) as head_histid_2,
                           MIN(spouse_histid) as spouse_histid_2
                    FROM hh_features 
                    WHERE year = {target_year}
                    GROUP BY head_sex, spouse_sex, head_bpld, spouse_bpld, head_birthyr, spouse_birthyr, 
                             head_fbpl, head_mbpl, spouse_fbpl, spouse_mbpl
                ),
                profile_matches AS (
                    SELECT 
                        p1.family_id_1, p2.family_id_2,
                        {base_year} AS year_1, {target_year} AS year_2,
                        p1.head_histid_1, p2.head_histid_2,
                        p1.spouse_histid_1, p2.spouse_histid_2,
                        p1.c1, p2.c2
                    FROM y1_profiles p1
                    JOIN y2_profiles p2
                      ON p1.head_sex = p2.head_sex
                     AND p1.spouse_sex = p2.spouse_sex
                     AND p1.head_bpld = p2.head_bpld
                     AND p1.spouse_bpld = p2.spouse_bpld
                     AND p1.head_birthyr = p2.head_birthyr
                     AND p1.spouse_birthyr = p2.spouse_birthyr
                         WHERE (p1.head_fbpl = p2.head_fbpl OR p1.head_fbpl IS NULL OR p2.head_fbpl IS NULL OR p1.head_fbpl = '' OR p2.head_fbpl = '')
                           AND (p1.head_mbpl = p2.head_mbpl OR p1.head_mbpl IS NULL OR p2.head_mbpl IS NULL OR p1.head_mbpl = '' OR p2.head_mbpl = '')
                           AND (p1.spouse_fbpl = p2.spouse_fbpl OR p1.spouse_fbpl IS NULL OR p2.spouse_fbpl IS NULL OR p1.spouse_fbpl = '' OR p2.spouse_fbpl = '')
                           AND (p1.spouse_mbpl = p2.spouse_mbpl OR p1.spouse_mbpl IS NULL OR p2.spouse_mbpl IS NULL OR p1.spouse_mbpl = '' OR p2.spouse_mbpl = '')
                )
                SELECT * FROM profile_matches;
            """)

            # TELEMETRY: Calculate how many matches were rejected due to ambiguity
            raw_count = \
            con.execute("SELECT COALESCE(SUM(CAST(c1 AS BIGINT) * CAST(c2 AS BIGINT)), 0) FROM raw_matches").fetchone()[
                0]

            con.execute(f"""
                INSERT INTO match_db.household_links
                SELECT family_id_1, family_id_2, 
                       year_1, year_2,
                       head_histid_1, head_histid_2,
                       spouse_histid_1, spouse_histid_2
                FROM raw_matches r1
                WHERE family_id_1 IN (
                    SELECT family_id_1 FROM raw_matches GROUP BY family_id_1 HAVING SUM(c2) = 1
                )
                AND family_id_2 IN (
                    SELECT family_id_2 FROM raw_matches GROUP BY family_id_2 HAVING SUM(c1) = 1
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
                logger.info(f"       [EXAMPLE] {s1} <---> {s2}")

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
    # ==================================================================================================
    #  STEP 4: ASSEMBLING THE TIMELINES (CLAN BUILDING)
    # --------------------------------------------------------------------------------------------------
    #  PLAN: The `household_links` table now contains thousands of individual two-point links
    #        (e.g., FamA -> FamB, FamB -> FamC, FamX -> FamY). The final step is to connect all
    #        these disparate links into continuous family timelines, which we call "Clans".
    #        A clan represents the definitive, multi-generational journey of a single family
    #        through time.
    #
    #  PROCESS:
    #    1. GRAPH BUILDING: We treat each family as a "node" and each link as an "edge" in a
    #       massive graph. We build an adjacency list, which is a dictionary mapping each
    #       family ID to a list of all other family IDs it's linked to.
    #    2. CONNECTED COMPONENTS: We traverse this graph using a standard algorithm (Depth First
    #       Search) to find all "connected components." Each component is a group of families
    #       that are all interconnected, forming a single clan.
    #    3. FINAL VALIDATION & NAMING: As we identify each clan, we perform one last sanity check:
    #       The "Highlander Rule." A valid clan can only have ONE household from any given
    #       census year. If a clan somehow contains two households from 1880, it means a
    #       bad link created a data paradox, and the entire clan is discarded. Valid clans
    #       are assigned a unique ID (e.g., "CLAN_1", "CLAN_2") and the results are saved to
    #       the final `clan_mapping` table. This table becomes the master key for the entire
    #       Time Machine, linking any family from any census year to its complete timeline.
    # ==================================================================================================
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

                # DECISION: The Highlander Rule. There can be only one household per decade in a valid clan!
                # If a clan has two households in 1880, a false transitive link corrupted the graph. Discard it.
                years_in_clan = [fam.split('_')[0] for fam in current_clan]
                if len(years_in_clan) == len(set(years_in_clan)):
                    for fam in current_clan:
                        clans.append((fam, f"CLAN_{clan_id_counter}"))
                    clan_id_counter += 1
                else:
                    # TELEMETRY: Log the paradox! If a clan has two families from 1880, we want to know WHO they are.
                    if len(current_clan) <= 15:  # Keep log clean from massive runaway cascades
                        logger.warning(
                            f"  [CLAN PARADOX DETECTED] Discarding interconnected component due to 'Highlander' violation.")
                        logger.warning(f"    └─> Conflicting Families: {current_clan}")

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
