"""
-----------------------------------
File: MergeGedcomToCleanVault.py

Summary: Deterministically merges the names from your GedcomVault.db 
         directly into the census databases and mints Golden Records.
         It creates a brand new Clean Vault database focused entirely 
         on the people in your family tree, making Ancestry uploads 
         clean, named, and highly targeted.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sys

import duckdb

# Ensure we can import from the utils directory
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.append(project_root)
if script_dir not in sys.path:
    sys.path.append(script_dir)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    CENSUS_100_DB = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"
    CENSUS_SAMP_DB = r"D:\Data\Genealogy_Data\MasterVault_ALLs.db"
    GEDCOM_DB = r"D:\Data\Genealogy_Data\GedcomVault.db"
    # We create a brand new database so we don't pollute your main clean vault!
    NEW_CLEAN_DB = r"D:\Data\Genealogy_Data\CleanVault_Gedcom.db"
else:
    CENSUS_100_DB = os.path.expanduser("~/Genealogy_Data/MasterVault_ALL.db")
    CENSUS_SAMP_DB = os.path.expanduser("~/Genealogy_Data/MasterVault_ALLs.db")
    GEDCOM_DB = os.path.expanduser("~/Genealogy_Data/GedcomVault.db")
    NEW_CLEAN_DB = os.path.expanduser("~/Genealogy_Data/CleanVault_Gedcom.db")


def merge_gedcom(logger):
    logger.info("Initializing DuckDB Engine...")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='90GB'")
    con.execute("INSTALL sqlite; LOAD sqlite;")

    logger.info(f"Creating new Clean Vault for GEDCOM Merge at: {NEW_CLEAN_DB}")
    os.makedirs(os.path.dirname(NEW_CLEAN_DB), exist_ok=True)

    con.execute(f"ATTACH '{NEW_CLEAN_DB}' AS clean (TYPE SQLITE);")

    logger.info("Attaching NVMe Source Vaults...")
    con.execute(f"ATTACH '{CENSUS_100_DB}' AS census100 (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{CENSUS_SAMP_DB}' AS samples (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{GEDCOM_DB}' AS gedcom (TYPE SQLITE, READ_ONLY);")

    logger.info("Initializing Golden Records table...")
    con.execute("""
                CREATE TABLE IF NOT EXISTS clean.golden_records
                (
                    golden_id
                    VARCHAR
                    PRIMARY
                    KEY,
                    first_name
                    VARCHAR,
                    last_name
                    VARCHAR,
                    birth_year
                    INTEGER,
                    birth_place
                    VARCHAR,
                    state
                    VARCHAR,
                    death_date
                    VARCHAR,
                    census_years
                    VARCHAR,
                    record_count
                    INTEGER,
                    census_count
                    INTEGER,
                    death_record_count
                    INTEGER,
                    gedcom_count
                    INTEGER,
                    vault_pointers
                    VARCHAR,
                    father_pointer
                    VARCHAR,
                    mother_pointer
                    VARCHAR,
                    st_joes_patrilineal_id
                    VARCHAR,
                    st_joes_matrilineal_id
                    VARCHAR
                );
                DELETE
                FROM clean.golden_records;
                """)

    logger.info("Executing Deterministic Merge: GEDCOM names to Census 1850-1950...")

    # Match on first 3 letters of first name (to catch 'William' vs 'Wm') 
    # and exact match on last name + birth year (+/- 2).
    query = """
            WITH squashed_census AS (SELECT base.composite_id                                                   AS unique_id,
                                            COALESCE(samp.namefrst, base.namefrst)                              AS first_name,
                                            COALESCE(samp.namelast, base.namelast)                              AS last_name,
                                            NULLIF(CAST(COALESCE(samp.birthyr, base.birthyr) AS INTEGER),
                                                   9999)                                                        AS birth_year,
                                            COALESCE(samp.bpld, base.bpld)                                      AS birth_place
                                     FROM census100.population base
                                              LEFT JOIN samples.population samp
                                                        ON base.year = samp.year AND base.serial = samp.serial AND
                                                           base.pernum = samp.pernum
                                     -- Pre-filter to only names existing in the GEDCOM for performance
                                     WHERE LOWER(COALESCE(samp.namelast, base.namelast)) IN
                                           (SELECT DISTINCT LOWER(last_name) FROM gedcom.gedcom_records)),
                 matches AS (SELECT g.gedcom_id,
                                    g.first_name,
                                    g.last_name,
                                    g.birth_year,
                                    g.birth_place,
                                    g.death_date,
                                    g.father_gedcom_id,
                                    g.mother_gedcom_id,
                                    string_agg(c.unique_id, '|') AS census_ids,
                                    count(c.unique_id)           AS census_cnt
                             FROM gedcom.gedcom_records g
                                      LEFT JOIN squashed_census c
                                                ON LOWER(SUBSTR(g.first_name, 1, 3)) = LOWER(SUBSTR(c.first_name, 1, 3))
                                                    AND LOWER(g.last_name) = LOWER(c.last_name)
                                                    AND c.birth_year BETWEEN g.birth_year - 2 AND g.birth_year + 2
                             GROUP BY g.gedcom_id, g.first_name, g.last_name, g.birth_year, g.birth_place, g.death_date,
                                      g.father_gedcom_id, g.mother_gedcom_id)
            INSERT
            INTO clean.golden_records
            SELECT 'SJ_GED_' || m.gedcom_id                                                                 AS golden_id,
                   m.first_name,
                   m.last_name,
                   m.birth_year,
                   m.birth_place,
                   CAST(NULL AS VARCHAR)                                                                    AS state,
                   m.death_date,
                   CAST(NULL AS VARCHAR)                                                                    AS census_years,
                   m.census_cnt + 1                                                                         AS record_count,
                   m.census_cnt                                                                             AS census_count,
                   0                                                                                        AS death_record_count,
                   1                                                                                        AS gedcom_count,
                   'GED_' || m.gedcom_id || CASE
                                                WHEN m.census_cnt > 0 THEN '|' || m.census_ids
                                                ELSE '' END                                                 AS vault_pointers,
                   CASE
                       WHEN m.father_gedcom_id IS NOT NULL THEN 'GED_' || m.father_gedcom_id
                       ELSE NULL END                                                                        AS father_pointer,
                   CASE
                       WHEN m.mother_gedcom_id IS NOT NULL THEN 'GED_' || m.mother_gedcom_id
                       ELSE NULL END                                                                        AS mother_pointer,
                   CAST(NULL AS VARCHAR)                                                                    AS st_joes_patrilineal_id,
                   CAST(NULL AS VARCHAR)                                                                    AS st_joes_matrilineal_id
            FROM matches m; \
            """

    con.execute(query)

    row_count = con.execute("SELECT COUNT(*) FROM clean.golden_records;").fetchone()[0]
    linked_count = con.execute("SELECT COUNT(*) FROM clean.golden_records WHERE census_count > 0;").fetchone()[0]

    logger.info(f"Merge Complete! {row_count:,} Golden Records created in the new Clean Vault.")
    logger.info(f"Successfully linked {linked_count:,} of them directly to raw census data.")
    logger.info("You can now run 'ExpandHouseholds.py' against this vault, or export it.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="MERGE_GEDCOM")
    merge_gedcom(main_logger)
