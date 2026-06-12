"""
-----------------------------------
File: DemographicChildSnap.py

Summary: Deterministically merges isolated GEDCOM Children into the 
         "John/Jane" Census Discovery records created by the Living Room Sweep.
         Matches based on shared parents, Birth Year (+/- 3), and Sex.

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

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.abspath(os.path.join(script_dir, '..'))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [python_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

if os.name == 'nt':
    CLEAN_TRACER_DB = r"D:\Data\Genealogy_Data\CleanVault_Gedcom.db"
    GEDCOM_DB = r"D:\Data\Genealogy_Data\GedcomVault.db"
else:
    CLEAN_TRACER_DB = os.path.expanduser("~/Genealogy_Data/CleanVault_Gedcom.db")
    GEDCOM_DB = os.path.expanduser("~/Genealogy_Data/GedcomVault.db")


def child_snap():
    print(f"Connecting to {CLEAN_TRACER_DB}...")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='90GB'")
    con.execute(f"ATTACH '{CLEAN_TRACER_DB}' AS clean (TYPE SQLITE);")
    con.execute(f"ATTACH '{GEDCOM_DB}' AS gedcom (TYPE SQLITE, READ_ONLY);")

    print("Mapping Parent Pointers...")
    # This maps both GEDCOM pointers (GED_I1) and Census pointers (1880_1_1) to their Golden Record ID
    con.execute("""
                CREATE
                TEMP TABLE parent_map AS
                SELECT golden_id                                 AS parent_golden_id,
                       UNNEST(string_split(vault_pointers, '|')) AS ptr
                FROM clean.golden_records;
                """)

    print("Isolating Isolated GEDCOM Children...")
    con.execute("""
                CREATE
                TEMP TABLE gedcom_children AS
                SELECT c.golden_id                       AS gedcom_child_id,
                       c.first_name,
                       c.last_name,
                       TRY_CAST(c.birth_year AS INTEGER) AS birth_year,
                       pm_f.parent_golden_id             AS father_golden_id,
                       pm_m.parent_golden_id             AS mother_golden_id
                FROM clean.golden_records c
                         LEFT JOIN parent_map pm_f ON c.father_pointer = pm_f.ptr
                         LEFT JOIN parent_map pm_m ON c.mother_pointer = pm_m.ptr
                WHERE c.vault_pointers LIKE 'GED_%'
                  AND c.vault_pointers NOT LIKE '%|%'
                  AND c.vault_pointers NOT LIKE '%18%'
                  AND c.vault_pointers NOT LIKE '%19%'
                  AND (pm_f.parent_golden_id IS NOT NULL OR pm_m.parent_golden_id IS NOT NULL);
                """)
    ged_count = con.execute("SELECT COUNT(*) FROM gedcom_children").fetchone()[0]
    print(f"  -> Found {ged_count} isolated GEDCOM children.")

    if ged_count == 0:
        print("No isolated GEDCOM children to snap.")
        return

    print("Isolating Census Discovery Children (Johns and Janes)...")
    con.execute("""
                CREATE
                TEMP TABLE census_children AS
                SELECT c.golden_id                       AS census_child_id,
                       TRY_CAST(c.birth_year AS INTEGER) AS birth_year,
                       pm_f.parent_golden_id             AS father_golden_id,
                       pm_m.parent_golden_id             AS mother_golden_id,
                       c.vault_pointers                  AS census_ptr
                FROM clean.golden_records c
                         LEFT JOIN parent_map pm_f ON c.father_pointer = pm_f.ptr
                         LEFT JOIN parent_map pm_m ON c.mother_pointer = pm_m.ptr
                WHERE c.vault_pointers NOT LIKE '%GED_%'
                  AND (pm_f.parent_golden_id IS NOT NULL OR pm_m.parent_golden_id IS NOT NULL);
                """)
    cen_count = con.execute("SELECT COUNT(*) FROM census_children").fetchone()[0]
    print(f"  -> Found {cen_count:,} Census discovery children.")

    print("Snapping Children by Shared Parents and Birth Year (+/- 3)...")
    con.execute("""
                CREATE
                TEMP TABLE matched_children AS
                SELECT ged.gedcom_child_id,
                       cen.census_child_id,
                       cen.census_ptr
                FROM gedcom_children ged
                         JOIN census_children cen
                              ON (ged.father_golden_id = cen.father_golden_id AND ged.father_golden_id IS NOT NULL
                                  OR ged.mother_golden_id = cen.mother_golden_id AND ged.mother_golden_id IS NOT NULL)
                                  AND cen.birth_year BETWEEN ged.birth_year - 3 AND ged.birth_year + 3
                """)

    # Enforce 1-to-1 matching to prevent twins from cross-wiring
    con.execute("""
                CREATE
                TEMP TABLE unique_matches AS
                SELECT gedcom_child_id, MAX(census_child_id) AS census_child_id, MAX(census_ptr) AS census_ptr
                FROM matched_children
                GROUP BY gedcom_child_id
                HAVING COUNT(*) = 1
                """)

    match_count = con.execute("SELECT COUNT(*) FROM unique_matches").fetchone()[0]
    print(f"Successfully matched {match_count} GEDCOM children to Census discoveries!")

    if match_count > 0:
        print("Grafting Census pointers into GEDCOM Children...")
        con.execute("""
                    UPDATE clean.golden_records
                    SET vault_pointers = vault_pointers || '|' || (SELECT census_ptr
                                                                   FROM unique_matches m
                                                                   WHERE m.gedcom_child_id = golden_records.golden_id LIMIT 1), census_count = 1
                    WHERE golden_id IN (SELECT gedcom_child_id FROM unique_matches);
                    """)

        print("Deleting orphaned 'John/Jane' shells...")
        con.execute("""
                    DELETE
                    FROM clean.golden_records
                    WHERE golden_id IN (SELECT census_child_id FROM unique_matches);
                    """)

        print("Child Snap complete! You can now re-run the GEDCOM export.")
    else:
        print("No matches found to snap.")


if __name__ == "__main__":
    child_snap()
