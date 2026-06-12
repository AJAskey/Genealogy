"""
-----------------------------------
File: BuildClans.py

Summary: Threads the pairwise demographic matches (e.g., 1850->1860) into
         continuous, multi-generational 100-year timelines.
         It uses Graph Theory (NetworkX) to find all connected families
         and assigns them a single, unified 'clan_id' based on the 
         oldest foundational family (the "Adam").

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sqlite3
import sys
import time

import networkx as nx

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [os.path.join(project_root, 'python'), project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

# --- Configuration ---
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")


def build_clans(logger):
    logger.info(f"Connecting to Match Vault: {MATCH_DB}")

    with sqlite3.connect(MATCH_DB) as conn:
        cursor = conn.cursor()

        logger.info("Step 1/3: Loading pairwise links into memory...")
        start_time = time.time()
        cursor.execute("SELECT family_id_1, family_id_2 FROM household_links")
        pairs = cursor.fetchall()
        logger.info(f"  -> Loaded {len(pairs):,} links in {time.time() - start_time:.2f} seconds.")

        logger.info("Step 2/3: Threading the timelines (Graph Connected Components)...")
        start_time = time.time()

        # We use a Graph to easily trace A -> B -> C into a single chain
        G = nx.Graph()
        G.add_edges_from(pairs)

        # Extract all continuous lineages
        clans = list(nx.connected_components(G))
        logger.info(
            f"  -> Successfully wove {len(clans):,} distinct multi-generational Clans in {time.time() - start_time:.2f} seconds.")

        logger.info("Step 3/3: Assigning the 'Adam' Clan IDs and saving to database...")
        start_time = time.time()

        clan_mappings = []

        for component in clans:
            # Find the oldest chronological family in this chain to act as the "Adam"
            # Since family_ids are formatted as '1850_1234_1', sorting them puts the oldest first
            sorted_families = sorted(list(component))
            adam_family = sorted_families[0]

            # Generate the unified clan ID (e.g., CLAN_1850_1234_1)
            clan_id = f"CLAN_{adam_family}"

            for fam_id in sorted_families:
                clan_mappings.append((fam_id, clan_id))

        # Save the mappings to a new table
        cursor.execute("DROP TABLE IF EXISTS clan_mapping")
        cursor.execute("""
                       CREATE TABLE clan_mapping
                       (
                           family_id TEXT PRIMARY KEY,
                           clan_id   TEXT
                       )
                       """)

        cursor.executemany("INSERT INTO clan_mapping VALUES (?, ?)", clan_mappings)
        logger.info(
            f"  -> Saved {len(clan_mappings):,} family-to-clan mappings in {time.time() - start_time:.2f} seconds.")

        logger.info("\nSUCCESS! The timelines are stitched. The framework is ready for the GEDCOM Name Overlay!")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="BUILD_CLANS")
    build_clans(main_logger)
