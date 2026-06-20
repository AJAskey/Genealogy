"""
-----------------------------------
File: run_database_analytics.py

Summary: A utility script to run a suite of analytical queries against
         the full set of linked genealogical databases. The output of
         each query is saved to a separate JSON file for analysis.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import glob
import json
import os
import sys

import duckdb

# Add project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging

# --- Configuration ---
if os.path.exists(r"D:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
elif os.path.exists(r"D:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
NAMED_VAULT_DIR = os.path.join(BASE_DATA_DIR, "NamedVaults")
MATCH_DB_PATH = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
ANALYTICS_OUTPUT_DIR = os.path.join(project_root, "analytics_output")


# --- Helper Function ---
def write_query_to_json(con, sql, filename, logger):
    """Executes a SQL query and writes the results to a JSON file."""
    output_path = os.path.join(ANALYTICS_OUTPUT_DIR, filename)
    logger.info(f"  -> Running query for: {filename}...")
    try:
        results = con.execute(sql).fetchall()
        if not results:
            logger.warning(
                f"     [SKIPPED] Query for {filename} returned no results. This may be expected if dependent data is missing.")
            return

        cols = [desc[0] for desc in con.description]
        dict_results = [dict(zip(cols, row)) for row in results]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(dict_results, f, indent=4)

        logger.info(f"     -> SUCCESS: Wrote {len(dict_results):,} records to {output_path}")
    except Exception as e:
        logger.error(f"     [FAILED] Query for {filename} failed: {e}")


# --- Query Functions ---

def query_1_largest_clans(con, logger):
    sql = """
          SELECT clan_id,
                 COUNT(*) AS num_households
          FROM match_db.clan_mapping
          GROUP BY clan_id
          ORDER BY num_households DESC LIMIT 10; \
          """
    write_query_to_json(con, sql, "1_largest_clans.json", logger)


def query_2_longest_lived(con, logger):
    # Note: This query depends on at least one NamedVault existing.
    sql = """
          SELECT h.first_name,
                 h.last_name,
                 COUNT(DISTINCT SUBSTRING(cm.family_id, 1, 4))       AS decades_spanned,
                 MIN(CAST(SUBSTRING(cm.family_id, 1, 4) AS INTEGER)) AS first_seen,
                 MAX(CAST(SUBSTRING(cm.family_id, 1, 4) AS INTEGER)) AS last_seen
          FROM match_db.clan_mapping cm
                   JOIN named_vault_1880.individuals h ON cm.clan_id IN (SELECT clan_id
                                                                         FROM match_db.clan_mapping
                                                                         WHERE family_id = h.family_id)
          WHERE h.pernum = '1' -- Only track heads of household for this example
          GROUP BY h.first_name, h.last_name
          ORDER BY decades_spanned DESC LIMIT 20; \
          """
    write_query_to_json(con, sql, "2_longest_lived.json", logger)


def query_3_migration_superhighways(con, logger):
    sql = """
          WITH pa_clans AS (SELECT DISTINCT clan_id
                            FROM match_db.clan_mapping cm
                                     JOIN yearly_vault_1880.individuals i ON cm.family_id = i.family_id
                            WHERE json_extract_string(i.raw_data, '$.STATEFIP') = '42')
          SELECT json_extract_string(i_1920.raw_data, '$.STATENH') AS destination_state,
                 COUNT(DISTINCT cm.clan_id)                        as num_families
          FROM match_db.clan_mapping cm
                   JOIN yearly_vault_1920.individuals i_1920 ON cm.family_id = i_1920.family_id
          WHERE cm.clan_id IN (SELECT clan_id FROM pa_clans)
            AND json_extract_string(i_1920.raw_data, '$.STATENH') != 'Pennsylvania'
          GROUP BY destination_state
          ORDER BY num_families DESC
              LIMIT 10; \
          """
    write_query_to_json(con, sql, "3_migration_pa_1880_1920.json", logger)


def query_4_occupation_shift(con, logger):
    sql = """
          WITH combined AS (SELECT cm.clan_id,
                                   json_extract_string(i_1880.raw_data, '$.OCCSTR') AS occ_1880,
                                   json_extract_string(i_1920.raw_data, '$.OCCSTR') AS occ_1920
                            FROM match_db.clan_mapping cm
                                     JOIN yearly_vault_1880.families f_1880 ON cm.family_id = f_1880.family_id
                                     JOIN yearly_vault_1920.families f_1920 ON cm.clan_id = (SELECT clan_id
                                                                                             FROM match_db.clan_mapping
                                                                                             WHERE family_id = f_1920.family_id)
                                     JOIN yearly_vault_1880.individuals i_1880 ON f_1880.head_histid = i_1880.histid
                                     JOIN yearly_vault_1920.individuals i_1920 ON f_1920.head_histid = i_1920.histid
                            WHERE f_1880.head_histid = f_1920.head_histid)
          SELECT occ_1880,
                 occ_1920,
                 COUNT(*) as transitions
          FROM combined
          WHERE occ_1880 IS NOT NULL
            AND occ_1920 IS NOT NULL
            AND occ_1880 != occ_1920
          GROUP BY occ_1880, occ_1920
          ORDER BY transitions DESC
              LIMIT 20; \
          """
    write_query_to_json(con, sql, "4_occupation_shift_1880_1920.json", logger)


def query_5_immigrant_settlement(con, logger):
    sql = """
          SELECT json_extract_string(h.raw_data, '$.STATENH') as state,
                 COUNT(DISTINCT f.family_id)                  as first_gen_family_count
          FROM yearly_vault_1900.families f
                   JOIN yearly_vault_1900.individuals h ON f.head_histid = h.histid
                   JOIN yearly_vault_1900.individuals c
                        ON f.family_id = c.family_id AND json_extract_string(c.raw_data, '$.RELATE') = '3'
          WHERE CAST(h.bpld AS INTEGER) > 1000
            AND CAST(c.bpld AS INTEGER) < 1000
          GROUP BY state
          ORDER BY first_gen_family_count DESC LIMIT 20; \
          """
    write_query_to_json(con, sql, "5_immigrant_settlement_1900.json", logger)


def query_6_remarriage(con, logger):
    sql = """
          SELECT h_1880.first_name,
                 h_1880.last_name,
                 h_1880.histid,
                 f_1880.spouse_histid AS spouse_1880_id,
                 f_1900.spouse_histid AS spouse_1900_id
          FROM match_db.clan_mapping cm
                   JOIN named_vault_1880.families f_1880 ON cm.family_id = f_1880.family_id
                   JOIN yearly_vault_1900.families f_1900
                        ON cm.clan_id = (SELECT clan_id FROM match_db.clan_mapping WHERE family_id = f_1900.family_id)
                   JOIN named_vault_1880.individuals h_1880 ON f_1880.head_histid = h_1880.histid
          WHERE f_1880.head_histid = f_1900.head_histid
            AND f_1880.spouse_histid != f_1900.spouse_histid
    LIMIT 20; \
          """
    write_query_to_json(con, sql, "6_remarriage_1880_1900.json", logger)


def query_7_child_mortality_shadows(con, logger):
    sql = """
          SELECT cm.clan_id,
                 f_1880.family_id AS family_1880,
                 f_1900.family_id AS family_1900,
                 f_1880.num_kids  AS kids_1880,
                 f_1900.num_kids  AS kids_1900
          FROM match_db.clan_mapping cm
                   JOIN yearly_vault_1880.families f_1880 ON cm.family_id = f_1880.family_id
                   JOIN yearly_vault_1900.families f_1900
                        ON cm.clan_id = (SELECT clan_id FROM match_db.clan_mapping WHERE family_id = f_1900.family_id)
          WHERE f_1880.head_histid = f_1900.head_histid
            AND f_1880.num_kids > f_1900.num_kids
            AND f_1880.num_kids > 0 LIMIT 20; \
          """
    write_query_to_json(con, sql, "7_child_mortality_shadows.json", logger)


def query_8_empty_nester_age(con, logger):
    sql = """
          WITH transitions AS (SELECT i_1920.age AS head_age_1920
                               FROM match_db.clan_mapping cm
                                        JOIN yearly_vault_1900.families f_1900 ON cm.family_id = f_1900.family_id
                                        JOIN yearly_vault_1920.families f_1920 ON cm.clan_id = (SELECT clan_id
                                                                                                FROM match_db.clan_mapping
                                                                                                WHERE family_id = f_1920.family_id)
                                        JOIN yearly_vault_1920.individuals i_1920 ON f_1920.head_histid = i_1920.histid
                               WHERE f_1900.head_histid = f_1920.head_histid
                                 AND (CAST(f_1900.numprec AS INTEGER) / 2.0) >= CAST(f_1920.numprec AS INTEGER)
                                 AND CAST(f_1900.numprec AS INTEGER) > 2)
          SELECT AVG(head_age_1920) as avg_empty_nester_age
          FROM transitions; \
          """
    write_query_to_json(con, sql, "8_empty_nester_age.json", logger)


def query_9_lost_families(con, logger):
    sql = """
          WITH clan_years AS (SELECT clan_id, SUBSTRING(family_id, 1, 4) as year
          FROM match_db.clan_mapping
              )
          SELECT clan_id
          FROM clan_years
          GROUP BY clan_id
          HAVING MIN(CASE WHEN year = '1880' THEN 1 ELSE 0 END) = 1
             AND MIN(CASE WHEN year = '1920' THEN 1 ELSE 0 END) = 1
             AND MAX(CASE WHEN year = '1900' THEN 1 ELSE 0 END) = 0
             AND MAX(CASE WHEN year = '1910' THEN 1 ELSE 0 END) = 0 LIMIT 20; \
          """
    write_query_to_json(con, sql, "9_lost_families.json", logger)


def query_10_askey_hotspots(con, logger):
    sql = """
          SELECT json_extract_string(raw_data, '$.COUNTYNH') as county,
                 json_extract_string(raw_data, '$.STATENH')  as state,
                 COUNT(*)                                    as name_count
          FROM named_vault_1880.individuals
          WHERE last_name = 'Askey'
          GROUP BY county, state
          ORDER BY name_count DESC LIMIT 10; \
          """
    write_query_to_json(con, sql, "10_askey_hotspots_1880.json", logger)


# --- Main Execution ---
def run_analytics(logger):
    """Main function to connect to databases and run all analytic queries."""
    logger.info("Starting database analytics script...")
    os.makedirs(ANALYTICS_OUTPUT_DIR, exist_ok=True)
    logger.info(f"JSON output will be saved to: {ANALYTICS_OUTPUT_DIR}")

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='96GB'")
    con.execute("INSTALL sqlite; LOAD sqlite;")

    logger.info("Attaching databases...")

    if os.path.exists(MATCH_DB_PATH):
        con.execute(f"ATTACH '{MATCH_DB_PATH}' AS match_db (TYPE SQLITE);")
        logger.info(f"  -> Attached {MATCH_DB_PATH}")
    else:
        logger.error(f"CRITICAL: Match database not found at {MATCH_DB_PATH}. Cannot run most queries.")
        return

    for db_file in glob.glob(os.path.join(VAULT_DIR, "YearlyVault_*.db")):
        alias = f"yearly_vault_{os.path.basename(db_file).replace('YearlyVault_', '').replace('.db', '')}"
        con.execute(f"ATTACH '{db_file}' AS {alias} (TYPE SQLITE, READ_ONLY);")
        logger.info(f"  -> Attached {db_file} as {alias}")

    for db_file in glob.glob(os.path.join(NAMED_VAULT_DIR, "NamedVault_*.db")):
        alias = f"named_vault_{os.path.basename(db_file).replace('NamedVault_', '').replace('.db', '')}"
        con.execute(f"ATTACH '{db_file}' AS {alias} (TYPE SQLITE, READ_ONLY);")
        logger.info(f"  -> Attached {db_file} as {alias}")

    logger.info("\nRunning all analytic queries...")
    query_1_largest_clans(con, logger)
    query_2_longest_lived(con, logger)
    query_3_migration_superhighways(con, logger)
    query_4_occupation_shift(con, logger)
    query_5_immigrant_settlement(con, logger)
    query_6_remarriage(con, logger)
    query_7_child_mortality_shadows(con, logger)
    query_8_empty_nester_age(con, logger)
    query_9_lost_families(con, logger)
    query_10_askey_hotspots(con, logger)

    con.close()
    logger.info("\nAnalytics script finished successfully.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging("DB_ANALYTICS")
    run_analytics(main_logger)
