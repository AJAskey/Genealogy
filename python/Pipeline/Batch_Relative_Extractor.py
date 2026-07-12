"""
File: Batch_Relative_Extractor.py
Summary: Loops through a dictionary of verified relatives, queries the DuckDB Vault 
         to find every household they ever lived in, and exports them all to a CSV.
"""

import duckdb
import pandas as pd

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"  # Make sure this points to your newly built vault!
OUTPUT_CSV = r"C:\tempc\ShortTermCSVfiles\Verified_Relatives_Households.csv"

# --- YOUR VIP DICTIONARY ---
# Add your verified relatives here. 
# Format is: "Name or Description": "HIK"
TARGET_RELATIVES = {
    "Lawrence Askey (Grandfather)": "7HbCHD5pUfSslqyHea8Jp",
    # "Thomas Askey (Great-Grandfather)": "INSERT_HIK_HERE",
    # "Elizabeth Askey (Great-Grandmother)": "INSERT_HIK_HERE",
}

def extract_batch_relatives():
    print(f"Connecting to Master Vault: {MASTER_VAULT_DB}")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)
    
    all_results = []
    
    print(f"Looping through {len(TARGET_RELATIVES)} verified relatives...\n")
    
    for name, hik in TARGET_RELATIVES.items():
        print(f"-> Hunting for {name} (HIK: {hik})...")
        
        # This query is beautifully simple because the HIK is now baked into your database!
        # It finds every YEAR and SERIAL (Household ID) the relative appears in, 
        # then grabs EVERYONE living in that house.
        query = f"""
            SELECT '{name}' AS Target_Relative, * 
            FROM individuals 
            WHERE (YEAR, SERIAL) IN (
                SELECT YEAR, SERIAL 
                FROM individuals 
                WHERE HIK = '{hik}'
            )
            ORDER BY YEAR ASC, RELATE ASC;
        """
        
        df = con.execute(query).df()
        if not df.empty:
            print(f"   Found {len(df)} household members across their lifetime.")
            all_results.append(df)
        else:
            print(f"   ❌ No records found for {name}. (Double check the HIK!)")
            
    if all_results:
        print(f"\nCombining all records and saving to {OUTPUT_CSV}...")
        final_df = pd.concat(all_results, ignore_index=True)
        final_df.to_csv(OUTPUT_CSV, index=False)
        print("✅ Success! Your batch extraction is complete.")
    else:
        print("\nNo records were found for any of the targets.")

if __name__ == "__main__":
    extract_batch_relatives()