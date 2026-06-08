"""
-----------------------------------
File: DemographicIndividualSnap.py

Summary: A straight-up SQL lookup.
         Takes isolated GEDCOM individuals and queries the 5% named Census Sample
         directly using Sex, First Initial, Last Name, and Birth Year.
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
    MASTER_SAMP_DB = r"D:\Data\Genealogy_Data\MasterVault_ALLs.db"
else:
    CLEAN_TRACER_DB = os.path.expanduser("~/Genealogy_Data/CleanVault_Gedcom.db")
    MASTER_SAMP_DB = os.path.expanduser("~/Genealogy_Data/MasterVault_ALLs.db")

def individual_snap():
    print(f"Connecting to databases...")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='90GB'")
    con.execute(f"ATTACH '{CLEAN_TRACER_DB}' AS clean (TYPE SQLITE);")
    con.execute(f"ATTACH '{MASTER_SAMP_DB}' AS samp (TYPE SQLITE, READ_ONLY);")

    print("Isolating remaining isolated GEDCOM individuals...")
    con.execute("""
        CREATE TEMP TABLE isolated_gedcom AS
        SELECT golden_id, 
               first_name, 
               LOWER(TRIM(last_name)) AS last_name, 
               LOWER(SUBSTR(first_name, 1, 1)) AS first_init,
               TRY_CAST(birth_year AS INTEGER) AS birth_year,
               sex
        FROM clean.golden_records
        WHERE vault_pointers LIKE 'GED_%'
          AND vault_pointers NOT LIKE '%18%'
          AND vault_pointers NOT LIKE '%19%'
          AND birth_year IS NOT NULL
          AND last_name IS NOT NULL
          AND first_name IS NOT NULL;
    """)
    
    ged_count = con.execute("SELECT COUNT(*) FROM isolated_gedcom").fetchone()[0]
    print(f"  -> Found {ged_count} isolated GEDCOM individuals.")
    
    if ged_count == 0:
        print("No isolated GEDCOM individuals left to snap.")
        return
        
    unique_surnames = con.execute("SELECT DISTINCT last_name FROM isolated_gedcom").fetchall()
    in_clause = ", ".join([f"'{s[0].replace(chr(39), chr(39)+chr(39))}'" for s in unique_surnames])
    
    print("Running straight-up SQL lookup against the Census Sample (takes ~10 seconds)...")
    
    # Map IPUMS sex to GEDCOM sex for direct comparison
    con.execute(f"""
        CREATE TEMP TABLE matched_individuals AS
        SELECT g.golden_id AS gedcom_id,
               s.composite_id AS census_ptr
        FROM isolated_gedcom g
        JOIN samp.population s
          ON LOWER(TRIM(s.namelast)) = g.last_name
         AND LOWER(SUBSTR(TRIM(s.namefrst), 1, 1)) = g.first_init
         AND (s.year - TRY_CAST(s.age AS INTEGER)) BETWEEN g.birth_year - 3 AND g.birth_year + 3
         AND CASE 
                WHEN s.sex = '1' THEN 'M' 
                WHEN s.sex = '2' THEN 'F' 
                ELSE 'U' 
             END = g.sex
        WHERE LOWER(TRIM(s.namelast)) IN ({in_clause})
          AND s.age IS NOT NULL;
    """)
    
    # Ensure we only snap if the SQL lookup finds exactly one logical historical match 
    # across the entire country (to prevent merging John Smith into the wrong John Smith)
    con.execute("""
        CREATE TEMP TABLE unique_matches AS
        SELECT gedcom_id, string_agg(DISTINCT census_ptr, '|') AS all_census_ptrs
        FROM matched_individuals
        GROUP BY gedcom_id
        HAVING COUNT(DISTINCT SPLIT_PART(census_ptr, '_', 1)) = 1; 
    """)
    
    match_count = con.execute("SELECT COUNT(*) FROM unique_matches").fetchone()[0]
    print(f"Successfully matched {match_count} individuals using direct SQL lookup!")
    
    if match_count > 0:
        print("Grafting Census pointers directly into GEDCOM records...")
        con.execute("""
            UPDATE clean.golden_records
            SET vault_pointers = vault_pointers || '|' || (SELECT all_census_ptrs FROM unique_matches m WHERE m.gedcom_id = golden_records.golden_id LIMIT 1),
                census_count = 1
            WHERE golden_id IN (SELECT gedcom_id FROM unique_matches);
        """)
        print("Individual Snap complete! You can now re-run the GEDCOM export.")
    else:
        print("No unique matches found to snap.")

if __name__ == "__main__":
    individual_snap()