"""
File: Audit_HIK.py

Summary: A debugging tool for Full Traceability. Paste an HIK,
         and this script will crawl the Master Vault to find them, 
         their children, grandchildren, and all descendants, 
         printing a generational report.
"""

import duckdb

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"

# Paste the Reference Number (HIK) here!
TARGET_HIK = "uB001TMrJhvM5I_JOkGvM]"


def main():
    if not TARGET_HIK:
        print("Please enter a TARGET_HIK at the top of the script!")
        return

    print(f"Connecting to Master Vault and Auditing Descendants for HIK: {TARGET_HIK}\n")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    # Check if target exists
    check_query = f"SELECT MODE(BIRTHYR), MODE(SEX) FROM individuals WHERE HIK = '{TARGET_HIK}'"
    target_info = con.execute(check_query).fetchone()
    if not target_info or not target_info[0]:
        print("❌ Target HIK not found in the database!")
        return

    generations = {0: {TARGET_HIK}}
    all_found_hiks = {TARGET_HIK}

    print("Crawling down the family tree to find all descendants...\n")

    current_gen = 0
    while True:
        current_hiks = generations[current_gen]
        if not current_hiks:
            break

        hiks_str = ", ".join([f"'{h}'" for h in current_hiks])

        # Find all children of the current generation.
        # A person is a parent if they are Head (1) or Spouse (2) in a household.
        # Their children are RELATE = '3' in that same household.
        query = f"""
            SELECT DISTINCT c.HIK
            FROM individuals p
            JOIN individuals c ON p.YEAR = c.YEAR AND p.SERIAL = c.SERIAL
            WHERE p.HIK IN ({hiks_str})
              AND p.RELATE IN ('1', '2') 
              AND c.RELATE = '3'         
              AND c.HIK IS NOT NULL
        """
        children = con.execute(query).fetchall()

        # Filter out people we've already seen to prevent infinite loops
        new_children_hiks = {row[0] for row in children} - all_found_hiks

        if not new_children_hiks:
            break

        current_gen += 1
        generations[current_gen] = new_children_hiks
        all_found_hiks.update(new_children_hiks)

    print(f"✅ Crawl Complete! Found {len(all_found_hiks) - 1} total descendants across {current_gen} generations.\n")

    # Fetch demographics for everyone found
    all_hiks_str = ", ".join([f"'{h}'" for h in all_found_hiks])
    profile_query = f"""
        SELECT 
            HIK, 
            MODE(SEX) as sex, 
            MODE(BIRTHYR) as birthyr, 
            MODE(BPL) as bpl
        FROM individuals
        WHERE HIK IN ({all_hiks_str})
        GROUP BY HIK
    """
    profiles_df = con.execute(profile_query).df()

    # Convert to dictionary for easy lookup
    profiles = {}
    for _, row in profiles_df.iterrows():
        sex_str = 'M' if str(row['sex']).strip() == '1' else 'F'
        profiles[row['HIK']] = f"b. ~{row['birthyr']} | Sex: {sex_str} | BPL: {row['bpl']}"

    # Print the generational report
    print("=" * 60)
    print(" GENERATIONAL DESCENDANT AUDIT")
    print("=" * 60)

    for gen in range(current_gen + 1):
        if gen == 0:
            print(f"GENERATION 0 (Target Ancestor):")
        else:
            print(f"\nGENERATION {gen} ({len(generations[gen])} Descendants):")

        for hik in generations[gen]:
            info = profiles.get(hik, "Unknown Demographics")
            print(f"  -> HIK: {hik} | {info}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
