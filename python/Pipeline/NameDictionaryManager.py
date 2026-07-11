"""
File: NameDictionaryManager.py

Summary: Creates and manages a persistent Lookup Table inside the 
         Master Vault to permanently map HISTIDs to First and Last Names.
"""

import duckdb

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"

def initialize_name_table(con):
    """Creates the lookup table if it doesn't already exist."""
    print("Initializing 'histid_names' table in Master Vault...")
    con.execute("""
        CREATE TABLE IF NOT EXISTS histid_names (
            HISTID VARCHAR PRIMARY KEY,
            first_name VARCHAR,
            last_name VARCHAR
        );
    """)
    print("Table ready!")

def add_names_to_dictionary(con, name_mappings):
    """
    Inserts or updates names in the dictionary.
    name_mappings should be a list of tuples: [('HISTID1', 'John', 'Smith'), ...]
    """
    print(f"Adding {len(name_mappings)} names to the dictionary...")
    # We use INSERT OR REPLACE so if we update a name later, it just overwrites the old one
    con.executemany("""
        INSERT OR REPLACE INTO histid_names (HISTID, first_name, last_name) 
        VALUES (?, ?, ?);
    """, name_mappings)
    print("Names successfully saved!")

def load_names_from_csv(con, csv_file_path):
    """
    Reads a CSV file containing (HISTID, first_name, last_name)
    and permanently saves them into the lookup dictionary.
    """
    print(f"Loading names from {csv_file_path} into the Master Vault...")
    con.execute(f"""
        INSERT OR REPLACE INTO histid_names (HISTID, first_name, last_name)
        SELECT HISTID, first_name, last_name FROM read_csv_auto('{csv_file_path}');
    """)
    print("CSV names successfully merged into the database!")

def main():
    con = duckdb.connect(database=MASTER_VAULT_DB)
    
    initialize_name_table(con)
    
    # --- EXAMPLE USAGE ---
    # You can pass your generated names or GEDCOM names right here!
    sample_names = [
        ('8B06C466-9999-42CC-94DC-4AEF9B05316A', 'Foster', 'Askey'),
        ('0C53F1D0-C511-4CAC-BAC1-44D2710EF2AE', 'Mary', 'Askey')
    ]
    
    add_names_to_dictionary(con, sample_names)
    
    # --- BULK CSV IMPORT ---
    # When your realistic names CSV is ready, just uncomment this line!
    # load_names_from_csv(con, r"C:\tempc\ShortTermCSVfiles\my_generated_names.csv")

if __name__ == '__main__':
    main()