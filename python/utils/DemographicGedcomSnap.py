"""
-----------------------------------
File: DemographicGedcomSnap.py

Summary: "The Nameless Snap"
         Deterministically merges isolated GEDCOM records by streaming the
         raw 1850-1950 Census databases directly, using demographic signatures
         (Husband's Age + Wife's Age) without relying on exact name matches.
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
    MASTER_100_DB = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"
    MASTER_SAMP_DB = r"D:\Data\Genealogy_Data\MasterVault_ALLs.db"
else:
    CLEAN_TRACER_DB = os.path.expanduser("~/Genealogy_Data/CleanVault_Gedcom.db")
    GEDCOM_DB = os.path.expanduser("~/Genealogy_Data/GedcomVault.db")
    MASTER_100_DB = os.path.expanduser("~/Genealogy_Data/MasterVault_ALL.db")
    MASTER_SAMP_DB = os.path.expanduser("~/Genealogy_Data/MasterVault_ALLs.db")


def demographic_snap():
    print(f"Connecting to databases...")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='90GB'")
    con.execute(f"ATTACH '{CLEAN_TRACER_DB}' AS clean (TYPE SQLITE);")
    con.execute(f"ATTACH '{GEDCOM_DB}' AS gedcom (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{MASTER_100_DB}' AS base (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{MASTER_SAMP_DB}' AS samp (TYPE SQLITE, READ_ONLY);")

    print("Isolating GEDCOM Couples (Husband + Wife)...")

    # Safely extract the exact GEDCOM IDs from the Golden Records
    con.execute("""
                CREATE
                TEMP TABLE clean_anchors AS
                SELECT golden_id,
                       first_name,
                       last_name,
                       TRY_CAST(birth_year AS INTEGER) AS birth_year,
                       vault_pointers,
                       REPLACE(ptr, 'GED_', '')        AS gedcom_id
                FROM (SELECT golden_id,
                             first_name,
                             last_name,
                             birth_year,
                             vault_pointers,
                             UNNEST(string_split(vault_pointers, '|')) AS ptr
                      FROM clean.golden_records
                      WHERE vault_pointers LIKE '%GED_%')
                WHERE ptr LIKE 'GED_%';
                """)

    con.execute("""
                CREATE
                TEMP TABLE gedcom_couples AS
                SELECT h.golden_id              AS husb_golden_id,
                       h.first_name             AS husb_first_name,
                       LOWER(TRIM(h.last_name)) AS husb_last_name,
                       h.birth_year             AS husb_birth_year,
                       h.vault_pointers         AS husb_ptr,
                       w.golden_id              AS wife_golden_id,
                       w.first_name             AS wife_first_name,
                       w.birth_year             AS wife_birth_year,
                       w.vault_pointers         AS wife_ptr
                FROM (SELECT DISTINCT father_gedcom_id, mother_gedcom_id
                      FROM gedcom.gedcom_records
                      WHERE father_gedcom_id IS NOT NULL
                        AND mother_gedcom_id IS NOT NULL) gc
                         JOIN clean_anchors h ON h.gedcom_id = gc.father_gedcom_id
                         JOIN clean_anchors w ON w.gedcom_id = gc.mother_gedcom_id
                WHERE (h.vault_pointers NOT LIKE '%18%' AND h.vault_pointers NOT LIKE '%19%')
                   OR (w.vault_pointers NOT LIKE '%18%' AND w.vault_pointers NOT LIKE '%19%');
                """)

    ged_count = con.execute("SELECT COUNT(*) FROM gedcom_couples").fetchone()[0]
    print(f"  -> Found {ged_count} isolated GEDCOM couples.")

    if ged_count == 0:
        print("No isolated GEDCOM couples found to snap.")
        return

    unique_surnames = con.execute(
        "SELECT DISTINCT husb_last_name FROM gedcom_couples WHERE husb_last_name IS NOT NULL").fetchall()
    in_clause = ", ".join([f"'{s[0].replace(chr(39), chr(39) + chr(39))}'" for s in unique_surnames])

    print("Isolating Candidate Census Couples from Raw Data (This will take 2 to 6 minutes. Do not cancel!)...")

    # 1. Grab matching Heads of Household
    con.execute(f"""
        CREATE TEMP TABLE pop_heads AS
        SELECT composite_id, CAST(year AS INTEGER) AS year, serial, TRY_CAST(age AS INTEGER) as age, 
               LOWER(TRIM(namelast)) AS namelast, LOWER(SUBSTR(TRIM(namefrst), 1, 1)) AS first_init
        FROM base.population
        WHERE LOWER(TRIM(namelast)) IN ({in_clause})
          AND age IS NOT NULL
          AND (related IN ('0100', '100', 'Head') OR related ILIKE '%Head%');
    """)
    con.execute(f"""
        INSERT INTO pop_heads
        SELECT composite_id, CAST(year AS INTEGER) AS year, serial, TRY_CAST(age AS INTEGER) as age, 
               LOWER(TRIM(namelast)) AS namelast, LOWER(SUBSTR(TRIM(namefrst), 1, 1)) AS first_init
        FROM samp.population
        WHERE LOWER(TRIM(namelast)) IN ({in_clause})
          AND age IS NOT NULL
          AND (related IN ('0100', '100', 'Head') OR related ILIKE '%Head%');
    """)

    # 2. Grab their exact spouses living in the same house
    con.execute("""
        CREATE TEMP TABLE head_serials AS
        SELECT DISTINCT year, serial FROM pop_heads;
    """)
    con.execute("""
                CREATE
                TEMP TABLE pop_spouses AS
                SELECT s.composite_id,
                       CAST(s.year AS INTEGER) AS year, s.serial, TRY_CAST(s.age AS INTEGER) as age,
               LOWER(SUBSTR(TRIM(s.namefrst), 1, 1)) AS first_init
                FROM base.population s
                    JOIN head_serials h
                ON s.year = h.year AND s.serial = h.serial
                WHERE s.age IS NOT NULL
                  AND (s.related IN ('0200'
                    , '200'
                    , 'Spouse'
                    , 'Wife')
                   OR s.related ILIKE '%Spouse%'
                   OR s.related ILIKE '%Wife%');
                """)
    con.execute("""
                INSERT INTO pop_spouses
                SELECT s.composite_id,
                       CAST(s.year AS INTEGER) AS year, s.serial, TRY_CAST(s.age AS INTEGER) as age,
               LOWER(SUBSTR(TRIM(s.namefrst), 1, 1)) AS first_init
                FROM samp.population s
                    JOIN head_serials h
                ON s.year = h.year AND s.serial = h.serial
                WHERE s.age IS NOT NULL
                  AND (s.related IN ('0200'
                    , '200'
                    , 'Spouse'
                    , 'Wife')
                   OR s.related ILIKE '%Spouse%'
                   OR s.related ILIKE '%Wife%');
                """)

    # 3. Create the Census Couples
    con.execute("""
        CREATE TEMP TABLE census_couples AS
        SELECT h.composite_id AS husb_comp_id,
               h.year - h.age AS husb_birth_year,
               h.namelast AS husb_last_name,
               h.first_init AS husb_first_init,
               s.composite_id AS wife_comp_id,
               s.year - s.age AS wife_birth_year,
               s.first_init AS wife_first_init
        FROM pop_heads h
        JOIN pop_spouses s ON h.serial = s.serial AND h.year = s.year;
    """)
    cen_count = con.execute("SELECT COUNT(*) FROM census_couples").fetchone()[0]
    print(f"  -> Found {cen_count:,} candidate Census couples living together.")

    print("Executing Nameless Demographic Join (Matching Last Name, First Initials, and Birth Years +/- 5)...")
    con.execute("""
                CREATE
                TEMP TABLE matched_couples AS
                SELECT ged.husb_golden_id AS ged_husb_id,
                       ged.wife_golden_id AS ged_wife_id,
                       cen.husb_comp_id   AS cen_husb_comp_id,
                       cen.wife_comp_id   AS cen_wife_comp_id
                FROM gedcom_couples ged
                         JOIN census_couples cen
                              ON cen.husb_last_name = ged.husb_last_name
                                  AND cen.husb_birth_year BETWEEN ged.husb_birth_year - 5 AND ged.husb_birth_year + 5
                                  AND cen.wife_birth_year BETWEEN ged.wife_birth_year - 5 AND ged.wife_birth_year + 5
         AND (cen.husb_first_init = LOWER(SUBSTR(ged.husb_first_name, 1, 1)) OR ged.husb_first_name IS NULL OR cen.husb_first_init IS NULL)
         AND (cen.wife_first_init = LOWER(SUBSTR(ged.wife_first_name, 1, 1)) OR ged.wife_first_name IS NULL OR cen.wife_first_init IS NULL);
                """)

    # We aggregate all matched decades (e.g. 1880, 1900, 1910) directly onto the GEDCOM record
    con.execute("""
                CREATE
                TEMP TABLE aggregated_matches AS
                SELECT ged_husb_id,
                       ged_wife_id,
                       string_agg(DISTINCT cen_husb_comp_id, '|') AS all_cen_husb_ptrs,
                       string_agg(DISTINCT cen_wife_comp_id, '|') AS all_cen_wife_ptrs
                FROM matched_couples
                GROUP BY ged_husb_id, ged_wife_id;
                """)

    match_count = con.execute("SELECT COUNT(*) FROM aggregated_matches").fetchone()[0]
    print(f"Successfully matched {match_count} Couples ({match_count * 2} Individuals) using pure demographics!")

    if match_count > 0:
        print("Grafting Census pointers into GEDCOM Golden Records...")

        con.execute("""
                    UPDATE clean.golden_records
                    SET vault_pointers = vault_pointers || '|' || (SELECT all_cen_husb_ptrs
                                                                   FROM aggregated_matches m
                                                                   WHERE m.ged_husb_id = golden_records.golden_id),
                        census_count   = 1
                    WHERE golden_id IN (SELECT ged_husb_id FROM aggregated_matches);
                    """)

        con.execute("""
                    UPDATE clean.golden_records
                    SET vault_pointers = vault_pointers || '|' || (SELECT all_cen_wife_ptrs
                                                                   FROM aggregated_matches m
                                                                   WHERE m.ged_wife_id = golden_records.golden_id),
                        census_count   = 1
                    WHERE golden_id IN (SELECT ged_wife_id FROM aggregated_matches);
                    """)

        print("Nameless Snap complete!")
    else:
        print("No unique demographic matches found to snap.")


if __name__ == "__main__":
    demographic_snap()
