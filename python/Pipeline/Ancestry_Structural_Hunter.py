"""
File: Ancestry_Structural_Hunter.py
Summary: Reads a CSV of structural facts gathered from Ancestry.com
         (Census Year, Birth Year, Locations). Searches the Master Vault
         (without relying on names) and returns the full household structures
         of any matches so you can visually verify the family.
"""

import duckdb
import os
import csv

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"
TARGETS_CSV = r"C:\tempc\ShortTermCSVfiles\Ancestry_Targets.csv"


def create_template_csv():
    """Creates the input CSV with headers and an example row if it doesn't exist."""
    with open(TARGETS_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Search_Label', 'Census_Year', 'Birth_Year', 'BPL_Code', 'State_ICP_Code', 'County_ICP_Code'])
        writer.writerow(['Example: Grandfather 1940', '1940', '1909', '42', '14', '810'])
    print(f"Created a blank input file for you at: {TARGETS_CSV}")
    print("Open it, add your Ancestry facts, save it, and run this script again!")


def run_structural_hunter():
    if not os.path.exists(TARGETS_CSV):
        create_template_csv()
        return

    print(f"Connecting to Master Vault: {MASTER_VAULT_DB}")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    with open(TARGETS_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = row.get('Search_Label', 'Unknown')
            cyear = row.get('Census_Year', '').strip()
            byear = row.get('Birth_Year', '').strip()
            bpl = row.get('BPL_Code', '').strip()
            state = row.get('State_ICP_Code', '').strip()
            county = row.get('County_ICP_Code', '').strip()

            if not cyear or not byear:
                continue

            print("\n" + "=" * 80)
            print(f"🎯 Hunting for: {label}")
            print(f"   Census: {cyear} | Target Birth: ~{byear} | BPL: {bpl} | State (ICP): {state}")
            print("=" * 80)

            # Build the query purely on structure - completely ignoring names!
            # Handles the Ancestry "ABT" (About) by adding a 2-year buffer.
            query = f"""
                SELECT DISTINCT SERIAL, HISTID, HIK, AGE, BIRTHYR
                FROM individuals
                WHERE YEAR = {cyear}
                  AND TRY_CAST(BIRTHYR AS INTEGER) BETWEEN {int(byear) - 2} AND {int(byear) + 2}
            """

            if bpl: query += f" AND TRY_CAST(BPL AS INTEGER) = {bpl}\n"
            if state: query += f" AND TRY_CAST(STATEICP AS INTEGER) = {state}\n"
            if county: query += f" AND TRY_CAST(COUNTYICP AS INTEGER) = {county}\n"

            query += " LIMIT 5"  # Cap at 5 households so we don't flood the terminal

            matches = con.execute(query).df()

            if matches.empty:
                print("❌ No matching records found for this structural fingerprint.")
                continue

            print(f"✅ Found {len(matches)} potential households. Pulling their family structures...\n")

            # For every candidate, pull out the entire household so you can verify it
            for index, match in matches.iterrows():
                serial = match['SERIAL']
                target_hik = match['HIK']

                print(f"--- Candidate Household {index + 1} (Target HIK: {target_hik}) ---")
                hh_query = f"""
                    SELECT RELATE AS Role, SEX, AGE, BIRTHYR, BPL, HIK
                    FROM individuals
                    WHERE YEAR = {cyear} AND SERIAL = {serial}
                    ORDER BY TRY_CAST(AGE AS INTEGER) DESC NULLS LAST
                """
                hh_df = con.execute(hh_query).df()
                print(hh_df.to_string(index=False))
                print("-" * 60 + "\n")


if __name__ == "__main__":
    run_structural_hunter()
