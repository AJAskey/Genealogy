"""
-----------------------------------
File: ExpandHouseholds.py

Summary: Post-processing graph traversal script.
         Finds named Golden Records in the Clean Vault, traverses back to the
         raw IPUMS databases, and uses POPLOC/MOMLOC intra-household pointers
         to find un-named children/dependents.

         It mints new Golden Records for these un-named dependents, infers
         their last name from the parent, and inserts them into the Clean Vault.
-----------------------------------
"""

import argparse
import os
import uuid

import duckdb
import pandas as pd

from python.utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    MASTER_100_DB = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"
    MASTER_SAMP_DB = r"D:\Data\Genealogy_Data\MasterVault_ALLs.db"
    DEFAULT_CLEAN_DB = r"D:\Data\Genealogy_Data\CleanVault.db"
else:
    MASTER_100_DB = os.path.expanduser("~/Genealogy_Data/MasterVault_ALL.db")
    MASTER_SAMP_DB = os.path.expanduser("~/Genealogy_Data/MasterVault_ALLs.db")
    DEFAULT_CLEAN_DB = os.path.expanduser("~/Genealogy_Data/CleanVault.db")


def expand_households(logger, clean_db_path=DEFAULT_CLEAN_DB):
    """
    Executes the POPLOC/MOMLOC graph traversal to discover un-named children
    and insert them into the Clean Vault.
    """
    logger.info("Initializing DuckDB Engine for Household Expansion...")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='90GB'")
    con.execute("INSTALL sqlite; LOAD sqlite;")

    logger.info("Attaching Vaults...")
    # Clean DB needs to be writable so we can insert the new records
    con.execute(f"ATTACH '{clean_db_path}' AS clean (TYPE SQLITE);")
    con.execute(f"ATTACH '{MASTER_100_DB}' AS base (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{MASTER_SAMP_DB}' AS samp (TYPE SQLITE, READ_ONLY);")

    logger.info("Running POPLOC/MOMLOC graph traversal across all known Golden Records...")

    query = """
            WITH parsed_golden AS (SELECT golden_id                                 AS parent_golden_id, \
                                          last_name                                 AS parent_last_name, \
                                          UNNEST(string_split(vault_pointers, '|')) AS comp_id \
                                   FROM clean.golden_records),
                 expanded_golden AS (SELECT parent_golden_id, \
                                            parent_last_name, \
                                            comp_id, \
                                            SPLIT_PART(comp_id, '_', 1) AS sample_id, \
                                            SPLIT_PART(comp_id, '_', 2) AS serial, \
                                            SPLIT_PART(comp_id, '_', 3) AS pernum \
                                     FROM parsed_golden),
                 raw_pop \
                     AS (SELECT composite_id, CAST(year AS INTEGER) AS year, TRY_CAST(age AS INTEGER) AS age, sex, bpld, poploc, momloc, stateicp
            FROM base.population
            UNION ALL
            SELECT composite_id, CAST(year AS INTEGER) AS year, TRY_CAST(age AS INTEGER) AS age, sex, bpld, poploc, momloc, stateicp
            FROM samp.population
                )
            SELECT g.parent_golden_id, \
                   g.parent_last_name, \
                   g.comp_id                     AS parent_comp_id, \
                   CAST(g.pernum AS INTEGER)     AS parent_pernum, \
                   r.composite_id                AS child_comp_id, \
                   r.year, \
                   r.age, \
                   r.sex, \
                   r.bpld, \
                   r.stateicp, \
                   TRY_CAST(r.poploc AS INTEGER) AS poploc, \
                   TRY_CAST(r.momloc AS INTEGER) AS momloc
            FROM expanded_golden g
                     JOIN raw_pop r
                          ON SPLIT_PART(r.composite_id, '_', 1) = g.sample_id
                              AND SPLIT_PART(r.composite_id, '_', 2) = g.serial
            WHERE (TRY_CAST(r.poploc AS INTEGER) = CAST(g.pernum AS INTEGER)
                OR TRY_CAST(r.momloc AS INTEGER) = CAST(g.pernum AS INTEGER)) \
            """

    df = con.execute(query).df()
    logger.info(f"Found {len(df):,} potential child/dependent records via graph traversal.")

    if df.empty:
        logger.info("No dependents found. Exiting.")
        return

    logger.info("Filtering out dependents that already exist in the Clean Vault...")
    existing_pointers_df = con.execute("""
                                       SELECT DISTINCT UNNEST(string_split(vault_pointers, '|')) AS comp_id
                                       FROM clean.golden_records
                                       """).df()

    existing_set = set(existing_pointers_df['comp_id'])
    new_children_df = df[~df['child_comp_id'].isin(existing_set)].copy()

    logger.info(f"Filtered down to {len(new_children_df):,} brand NEW un-named dependents.")

    if new_children_df.empty:
        logger.info("No new dependents to add. Exiting.")
        return

    logger.info("Minting Golden Records for un-named dependents...")
    new_golden_records = []

    for child_comp_id, group in new_children_df.groupby('child_comp_id'):
        core = group.iloc[0]

        first_name = "John" if str(core.get('sex')).strip() == '1' else "Jane" if str(
            core.get('sex')).strip() == '2' else "Unknown"
        birth_year = int(core['year']) - int(core['age']) if pd.notna(core['year']) and pd.notna(core['age']) else None

        # Safely extract father/mother pointers before creating the dictionary
        father_ptr = None
        mother_ptr = None
        for _, r in group.iterrows():
            if pd.notna(r['poploc']) and r['poploc'] == r['parent_pernum']:
                father_ptr = r['parent_comp_id']
            if pd.notna(r['momloc']) and r['momloc'] == r['parent_pernum']:
                mother_ptr = r['parent_comp_id']

        golden = {
            "golden_id": f"SJ_AUTO_{uuid.uuid4().hex[:16].upper()}",
            "first_name": first_name,
            "last_name": core['parent_last_name'],
            "birth_year": birth_year,
            "birth_place": core['bpld'],
            "state": core['stateicp'],
            "death_date": None,
            "census_years": str(int(core['year'])) if pd.notna(core['year']) else None,
            "record_count": 1,
            "census_count": 1,
            "death_record_count": 0,
            "gedcom_count": 0,
            "vault_pointers": child_comp_id,
            "father_pointer": father_ptr,
            "mother_pointer": mother_ptr,
            "st_joes_patrilineal_id": None,
            "st_joes_matrilineal_id": None
        }
        new_golden_records.append(golden)

    insert_df = pd.DataFrame(new_golden_records)
    logger.info(f"Writing {len(insert_df):,} new Golden Records into CleanVault.db...")
    con.register("insert_df", insert_df)
    con.execute("INSERT INTO clean.golden_records SELECT * FROM insert_df;")
    logger.info("Expansion complete! Un-named dependents successfully grafted into the Clean Vault.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Expand households from Golden Records")
    parser.add_argument("--vault", default=DEFAULT_CLEAN_DB, help="Specific CleanVault database to read/write from")
    args = parser.parse_args()
    logger = gen_logging.setup_logging(logger_name="EXPANDER")
    expand_households(logger, args.vault)
