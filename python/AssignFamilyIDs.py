"""
-----------------------------------
File: AssignFamilyIDs.py

Summary: Uses a Union-Find (Disjoint Set) graph algorithm to group every 
         single census record (named and unnamed) into universal Family IDs.
         
         It uses IPUMS Household structures (SERIAL, FAMUNIT) to group people 
         within a decade, and uses the CleanVault's vault_pointers to link 
         those households across decades.
-----------------------------------
"""

import os

import duckdb
import pandas as pd
import sys

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
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MASTER_100_DB = os.path.join(BASE_DATA_DIR, "MasterVault_ALL.db")
MASTER_SAMP_DB = os.path.join(BASE_DATA_DIR, "MasterVault_ALLs.db")
CLEAN_DB = os.path.join(BASE_DATA_DIR, "CleanVault.db")


class UnionFind:
    """Blazing fast memory-efficient graph clustering."""

    def __init__(self):
        self.parent = {}

    def find(self, i):
        # 1. Find the root of the tree iteratively
        root = i
        while self.parent.setdefault(root, root) != root:
            root = self.parent[root]

        # 2. Path compression: point all traversed nodes directly to the root
        curr = i
        while curr != root:
            nxt = self.parent[curr]
            self.parent[curr] = root
            curr = nxt

        return root

    def union(self, i, j):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j


def assign_global_families(logger):
    """
    Extracts edges from DuckDB, computes connected components, 
    and writes the universal Family IDs back to the Clean Vault.
    """
    logger.info("Initializing DuckDB Engine for Graph Traversal...")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='90GB'")
    con.execute("INSTALL sqlite; LOAD sqlite;")

    logger.info("Attaching Vaults...")
    con.execute(f"ATTACH '{CLEAN_DB}' AS clean (TYPE SQLITE);")
    con.execute(f"ATTACH '{MASTER_100_DB}' AS base (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{MASTER_SAMP_DB}' AS samp (TYPE SQLITE, READ_ONLY);")

    uf = UnionFind()

    # ---------------------------------------------------------
    # EDGE TYPE 1: Intra-Household (No Names Required)
    # ---------------------------------------------------------
    logger.info("Isolating target households from Golden Records...")
    con.execute("""
                CREATE
                TEMP TABLE target_hhs AS
                SELECT DISTINCT SPLIT_PART(comp_id, '_', 1) AS sample,
                                SPLIT_PART(comp_id, '_', 2) AS serial
                FROM (SELECT UNNEST(string_split(vault_pointers, '|')) AS comp_id
                      FROM clean.golden_records);
                """)

    logger.info("Extracting household structures (The Intra-Decade Glue)...")
    query_households = """
                       SELECT p.composite_id,
                              p.sample || '_' || p.serial || '_' || COALESCE(p.famunit, '1') AS household_id
                       FROM base.population p
                                JOIN target_hhs t ON p.sample = t.sample AND p.serial = t.serial
                       UNION ALL
                       SELECT p.composite_id,
                              p.sample || '_' || p.serial || '_' || COALESCE(p.famunit, '1') AS household_id
                       FROM samp.population p
                                JOIN target_hhs t ON p.sample = t.sample AND p.serial = t.serial; \
                       """

    # Stream the results in manageable chunks to prevent Python memory thrashing
    cursor = con.execute(query_households)
    chunk_size = 5_000_000
    processed_count = 0

    while True:
        chunk = cursor.fetchmany(chunk_size)
        if not chunk:
            break  # No more rows to fetch

        for comp_id, household_id in chunk:
            uf.union(comp_id, f"HH_{household_id}")

        processed_count += len(chunk)
        logger.info(f"  -> Processed {processed_count:,} household edges into the graph...")

    # ---------------------------------------------------------
    # EDGE TYPE 2: Cross-Decade (The 25% Bridges)
    # ---------------------------------------------------------
    logger.info("Extracting Golden Record pointers (The Cross-Decade Glue)...")
    query_pointers = "SELECT vault_pointers FROM clean.golden_records WHERE record_count > 1;"
    pointers = con.execute(query_pointers).fetchall()

    logger.info(f"Applying {len(pointers):,} multi-decade bridges to the graph...")
    for (ptr_str,) in pointers:
        parts = ptr_str.split('|')
        if len(parts) > 1:
            anchor = parts[0]
            for other_ptr in parts[1:]:
                uf.union(anchor, other_ptr)

    # ---------------------------------------------------------
    # ASSIGN FAMILY IDs
    # ---------------------------------------------------------
    logger.info("Calculating Universal Family IDs...")
    # Group everything by its root node
    family_map = []

    # We only care about saving the actual people (composite_ids), not our temporary HH_ nodes
    for node in uf.parent.keys():
        if not str(node).startswith("HH_"):
            root = uf.find(node)
            # Clean up the root string to act as the permanent Family ID
            family_id = f"FAM_{str(root).replace('HH_', '')}"
            family_map.append((node, family_id))

    df_families = pd.DataFrame(family_map, columns=['composite_id', 'family_id'])

    logger.info(f"Saving {len(df_families):,} Family assignments to the Clean Vault...")
    con.register("df_families", df_families)

    con.execute("DROP TABLE IF EXISTS clean.universal_families;")
    con.execute("""
                CREATE TABLE clean.universal_families
                (
                    composite_id VARCHAR PRIMARY KEY,
                    family_id    VARCHAR
                );
                """)
    con.execute("INSERT INTO clean.universal_families SELECT * FROM df_families;")
    logger.info("Complete! Every record now belongs to a Universal Family ID.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="FAM_GRAPH")
    assign_global_families(main_logger)
