"""
File: debug_database_classes.py

Summary: A reusable wrapper script that queries the raw SQLite database,
         instantiates the OOP 'Individual' and 'Family' classes, maps the
         relational pointers in memory, and logs them out for debugging.
"""

import os
import sqlite3
import sys

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [script_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging
from genealogy_classes import Individual, Family

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")

# ==============================================================================
# TUNING KNOBS
# ==============================================================================
TARGET_DB = "MiniVault_1900.db"  # Change this to "YearVault_1900.db" or "MiniVault_1900.db"


def test_classes_from_db(logger):
    db_path = os.path.join(VAULT_DIR, TARGET_DB)
    if not os.path.exists(db_path):
        logger.error(f"Cannot find database: {db_path}")
        return

    logger.info(f"Connecting to {db_path} to populate Genealogy Classes...")

    with sqlite3.connect(db_path) as conn:
        # This allows us to access SQL columns by name instead of index!
        conn.row_factory = sqlite3.Row

        # Fetch a sample of 25 complete families to test with
        logger.info("Querying 25 Family Households...")
        fam_rows = conn.execute("SELECT * FROM families LIMIT 25").fetchall()

        families = {}
        target_fam_ids = []

        for row in fam_rows:
            fam_id = row['family_id']
            target_fam_ids.append(fam_id)

            # Instantiate the Family Class
            fam = Family(family_id=fam_id)
            fam.husband_id = row['head_histid']
            fam.wife_id = row['spouse_histid']
            families[fam_id] = fam

        # Now fetch all the individuals that belong ONLY to those 25 families
        placeholders = ",".join("?" * len(target_fam_ids))
        ind_rows = conn.execute(f"SELECT * FROM individuals WHERE family_id IN ({placeholders})",
                                target_fam_ids).fetchall()

        individuals = {}
        logger.info(f"Querying {len(ind_rows)} Individuals to map into the Families...")

        for row in ind_rows:
            histid = row['histid']

            # Instantiate the Individual Class (Using HISTID as the temporary St. Joes ID)
            indi = Individual(st_joes_id=histid, raw_composite_id=histid, fam_id=row['family_id'])

            # Populate the attributes from the database directly into the Object
            for attr in ['first_name', 'last_name', 'birthyr', 'birthmo', 'sex', 'bpld', 'fbpl', 'mbpl',
                         'father_histid', 'mother_histid', 'marrnoyrs']:
                if attr in row.keys():
                    setattr(indi,
                            attr if attr not in ('father_histid', 'mother_histid') else attr.replace('_histid', '_id'),
                            row[attr])

            individuals[histid] = indi

            # logger.info(inspect(indi))

            # Map the children into the Family Class Array!
            fam = families.get(row['family_id'])
            if fam and histid != fam.husband_id and histid != fam.wife_id:
                fam.add_child(histid)

        logger.info("Population Complete! Logging Class Outputs:\n")

        # Print them all out beautifully
        for fam in families.values():
            logger.info("=" * 60)
            logger.info(f"FAMILY OBJECT: {fam.family_id}")

            if fam.husband_id in individuals:
                individuals[fam.husband_id].status = "HUSBAND"
                gen_logging.log_obj(logger, individuals[fam.husband_id], "[HUSBAND]")

            if fam.wife_id in individuals:
                individuals[fam.wife_id].status = "SPOUSE"
                gen_logging.log_obj(logger, individuals[fam.wife_id], "[SPOUSE]")

            for child_id in fam.children_ids:
                if child_id in individuals:
                    individuals[child_id].status = "CHILD"
                    gen_logging.log_obj(logger, individuals[child_id], "[CHILD]")

        logger.info("=" * 60)
        logger.info("Classes successfully populated and logged!")


if __name__ == '__main__':
    main_logger = gen_logging.setup_logging("CLASS_DEBUGGER")
    test_classes_from_db(main_logger)
