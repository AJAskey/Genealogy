"""
-----------------------------------
File: FamilyTracer.py
Summary: A targeted debugging tool that picks a single family from 1850 
         and traces them through all subsequent census vaults to prove 
         the hashing logic and see how their snapshot hashes evolve.
-----------------------------------
"""

import duckdb
import os
import sys
import json

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")


def attach_databases(con):
    con.execute("INSTALL sqlite; LOAD sqlite; SET sqlite_all_varchar=true;")
    for year in range(1850, 1960, 10):
        db_path = os.path.join(YEARLY_VAULT_DIR, f"YearVault_{year}.db")
        if os.path.exists(db_path):
            con.execute(f"ATTACH '{db_path}' AS vault_{year} (TYPE SQLITE, READ_ONLY);")


def run_trace(con):
    print("\n=======================================================")
    print("  FAMILY TRACER: FOLLOWING ONE FAMILY THROUGH TIME")
    print("=======================================================\n")

    # Step 1: Find a good test subject. 
    # We want a family in 1850 that definitely exists in 1860 so we can see the trace work.
    print("Hunting for an interesting 1850 family to trace...")
    
    target_query = """
        SELECT h50.family_hash
        FROM vault_1850.computed_fam_hashes h50
        JOIN vault_1860.computed_fam_hashes h60 ON h50.family_hash = h60.family_hash
        LIMIT 1;
    """
    
    result = con.execute(target_query).fetchone()
    if not result:
        print("Error: Could not find a family that exists in both 1850 and 1860.")
        return
        
    target_hash = result[0]
    print(f"TARGET ACQUIRED!\nBase Family Hash (Husband/Wife): {target_hash}\n")
    print("Commencing Decade Sweep...\n")

    # Step 2: Sweep the decades and print the hits!
    for year in range(1850, 1960, 10):
        # Check if the vault is attached
        if not con.execute(f"SELECT 1 FROM duckdb_databases() WHERE database_name = 'vault_{year}'").fetchone():
            continue
            
        search_query = f"""
            SELECT f.family_id, f.kids_byr_sum, f.stateicp, f.countyicp, h.snapshot_fam_hash
            FROM vault_{year}.families f
            JOIN vault_{year}.computed_fam_hashes h ON f.family_id = h.family_id
            WHERE h.family_hash = '{target_hash}'
        """
        
        hits = con.execute(search_query).fetchall()
        
        if not hits:
            print(f"[{year}] --- No matches found.")
        else:
            print(f"[{year}] MATCHES FOUND: {len(hits)}")
            for hit in hits:
                fam_id, kids_sum, state, county, snap_hash = hit
                print(f"       Family ID:  {fam_id}")
                print(f"       Location:   State {state}, County {county}")
                print(f"       Exact Hash: {snap_hash}")
                
                # Now let's fetch the actual people in this specific family!
                people_query = f"""
                    SELECT raw_data 
                    FROM vault_{year}.individuals 
                    WHERE family_id = '{fam_id}'
                """
                people = con.execute(people_query).fetchall()
                print(f"       Members ({len(people)}):")
                for person in people:
                    p_data = json.loads(person[0])
                    name = f"{p_data.get('NAMEFRST', '')} {p_data.get('NAMELAST', '')}".strip()
                    age = p_data.get('AGE', 'Unknown')
                    relate = p_data.get('RELATE', 'Unknown')
                    print(f"         - {name} (Age: {age}, Relate: {relate})")
                print("-" * 55)
        print("")


if __name__ == '__main__':
    con = duckdb.connect(database=':memory:')
    attach_databases(con)
    run_trace(con)
    con.close()