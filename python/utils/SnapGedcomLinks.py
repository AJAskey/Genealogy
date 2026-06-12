"""
-----------------------------------
File: SnapGedcomLinks.py

Summary: Deterministically merges isolated GEDCOM Golden Records into
         their corresponding Census Golden Records inside CleanVault_Gedcom.db.
         Includes aggressive matching and verbose debugging.
-----------------------------------
"""

import os
import sys

import duckdb

script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.abspath(os.path.join(script_dir, '..'))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [python_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

CLEAN_TRACER_DB = r"D:\Data\Genealogy_Data\CleanVault_Gedcom.db"
GEDCOM_DB = r"D:\Data\Genealogy_Data\GedcomVault.db"


def snap_links():
    print(f"Connecting to {CLEAN_TRACER_DB}...")
    con = duckdb.connect()
    con.execute(f"ATTACH '{CLEAN_TRACER_DB}' AS clean (TYPE SQLITE);")
    con.execute(f"ATTACH '{GEDCOM_DB}' AS gedcom (TYPE SQLITE, READ_ONLY);")

    print("Finding isolated GEDCOM records...")
    con.execute("""
                CREATE
                TEMP TABLE gedcom_recs AS
                SELECT c.golden_id, g.first_name, g.last_name, TRY_CAST(g.birth_year AS INTEGER) AS birth_year, c.vault_pointers
                FROM clean.golden_records c
                JOIN gedcom.gedcom_records g ON g.gedcom_id = REPLACE(c.vault_pointers, 'GED_', '')
                WHERE c.vault_pointers LIKE 'GED_%'
                  AND c.vault_pointers NOT LIKE '%|%'
                  AND c.vault_pointers NOT LIKE '%18%'
                  AND c.vault_pointers NOT LIKE '%19%';
                """)

    ged_count = con.execute("SELECT COUNT(*) FROM gedcom_recs").fetchone()[0]
    print(f"  -> Found {ged_count} isolated GEDCOM records.")

    if ged_count == 0:
        print("No isolated GEDCOM records found! They may have already been snapped.")
        return

    print("Finding candidate Census records...")
    con.execute("""
                CREATE
                TEMP TABLE census_recs AS
                SELECT golden_id, first_name, last_name, TRY_CAST(birth_year AS INTEGER) AS birth_year, vault_pointers
                FROM clean.golden_records
                WHERE (vault_pointers LIKE '%18%' OR vault_pointers LIKE '%19%');
                """)
    cen_count = con.execute("SELECT COUNT(*) FROM census_recs").fetchone()[0]
    print(f"  -> Found {cen_count:,} candidate Census records.")

    print("Deterministically matching on Last Name (exact), Birth Year (+/- 5), and First Initial...")
    con.execute("""
                CREATE
                TEMP TABLE matched AS
                SELECT c.golden_id      AS census_golden_id,
                       g.golden_id      AS gedcom_golden_id,
                       g.vault_pointers AS gedcom_ptr
                FROM gedcom_recs g
                         JOIN census_recs c
                              ON LOWER(TRIM(g.last_name)) = LOWER(TRIM(c.last_name))
                                  AND c.birth_year BETWEEN g.birth_year - 5 AND g.birth_year + 5
                                  AND LOWER(SUBSTR(g.first_name, 1, 1)) = LOWER(SUBSTR(c.first_name, 1, 1))
                WHERE g.last_name IS NOT NULL
                  AND c.last_name IS NOT NULL
                  AND g.birth_year IS NOT NULL
                  AND c.birth_year IS NOT NULL
                """)

    con.execute("""
                CREATE
                TEMP TABLE best_matches AS
                SELECT census_golden_id, gedcom_golden_id, gedcom_ptr
                FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY gedcom_golden_id ORDER BY census_golden_id) as rn
                      FROM matched)
                WHERE rn = 1;
                """)

    match_count = con.execute("SELECT COUNT(*) FROM best_matches").fetchone()[0]
    print(f"Successfully matched {match_count} GEDCOM records to Census Golden Records!")

    if match_count == 0:
        print("\n--- DIAGNOSTIC DUMP ---")
        print("Why did 0 records match? Here are 3 of your isolated GEDCOM records:")
        print(con.execute("SELECT * FROM gedcom_recs LIMIT 3").df().to_string())
        print("\nHere are 3 candidate Census records with the SAME last name (if any exist):")
        print(con.execute("""
                          SELECT c.golden_id, c.first_name, c.last_name, c.birth_year, c.vault_pointers
                          FROM census_recs c
                                   JOIN gedcom_recs g ON LOWER(TRIM(c.last_name)) = LOWER(TRIM(g.last_name)) LIMIT 3
                          """).df().to_string())
        print("-----------------------\n")
        print("No matches found to snap. Review the diagnostic dump above.")
        return

    print("Grafting GEDCOM pointers into Census Golden Records...")
    con.execute("""
                UPDATE clean.golden_records
                SET vault_pointers = vault_pointers || '|' || (SELECT gedcom_ptr
                                                               FROM best_matches m
                                                               WHERE m.census_golden_id = golden_records.golden_id LIMIT 1), gedcom_count = 1
                WHERE golden_id IN (SELECT census_golden_id FROM best_matches);
                """)

    print("Deleting orphaned GEDCOM shells...")
    con.execute("""
                DELETE
                FROM clean.golden_records
                WHERE golden_id IN (SELECT gedcom_golden_id FROM best_matches);
                """)

    print("Snap complete! You can now re-run the GEDCOM export.")


if __name__ == "__main__":
    snap_links()
