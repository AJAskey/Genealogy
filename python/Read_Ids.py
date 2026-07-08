import csv
import duckdb

MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"
OUTPUT_CSV = r"C:\tempc\ShortTermCSVfiles\test_census_subset.csv"

# Distinct recognizable names to assign to the key players and their clans
FAKE_SURNAMES = ["Appleseed", "Baggins", "Corleone", "Dracula", "Einstein", "Farnsworth", "Gatsby", "Houdini", "Ivanhoe", "Jekyll"]
FAKE_FIRSTS = ["Arthur", "Betty", "Charles", "Diana", "Edward", "Fiona", "George", "Helen", "Ian", "Jane"]

# --- GEOGRAPHIC FILTER ---
# State: 42 = Pennsylvania
# Counties: 0270 = Centre County, 0330 = Clearfield County
TARGET_STATE = '42'
TARGET_COUNTIES = ['0270', '0330', '027', '033']  # Included the 3-digit variants just in case

if __name__ == '__main__':

    csv_file = r"E:\Working\Census Linkage\topids.csv"
    target_histids = []
    name_mappings = []
    
    print(f"Reading target IDs from {csv_file}...")
    with open(csv_file, mode='r') as infile:
        reader = csv.DictReader(infile, delimiter=',')

        for idx, raw_row in enumerate(reader):
            # Generate a distinct fake name based on the row index
            fake_last = FAKE_SURNAMES[idx % len(FAKE_SURNAMES)]
            if idx >= len(FAKE_SURNAMES):
                fake_last += f"_{idx}"  # In case there are more than 10 targets
            fake_first = FAKE_FIRSTS[idx % len(FAKE_FIRSTS)]

            for k, v in raw_row.items():
                val = str(v).strip()
                # Grab any valid HISTID from this person across ANY decade
                if val and str(k).upper().startswith('HISTID'):
                    target_histids.append(val)
                    name_mappings.append((val, fake_first, fake_last))
                    
    print(f"Found {len(target_histids)} unique HISTIDs.")
    
    if target_histids:
        print(f"Connecting to Master Vault: {MASTER_VAULT_DB}...")
        con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)
        
        # Load the fake names into a temporary lookup table in DuckDB
        con.execute("CREATE TEMP TABLE fake_names (HISTID VARCHAR, FAKE_FIRST VARCHAR, FAKE_LAST VARCHAR)")
        con.executemany("INSERT INTO fake_names VALUES (?, ?, ?)", name_mappings)
        
        county_sql = ", ".join([f"'{c}'" for c in TARGET_COUNTIES])
        
        # Quick check: How many households match our geographic filter?
        print("Scanning Master Vault for geographic matches...")
        count_query = f"""
            SELECT COUNT(DISTINCT i.SERIAL || i.YEAR) 
            FROM individuals i
            JOIN fake_names fn ON i.HISTID = fn.HISTID
            WHERE i.STATEICP = '{TARGET_STATE}' AND i.COUNTYICP IN ({county_sql})
        """
        matched_households = con.execute(count_query).fetchone()[0]
        print(f"-> Found {matched_households} households in Centre/Clearfield County for the key players.")

        # This query finds the households of your targets, then selects EVERYONE in those households
        query = f"""
            COPY (
                WITH target_households AS (
                    SELECT i.YEAR, i.SERIAL, MAX(fn.FAKE_LAST) AS FAKE_LAST
                    FROM individuals i
                    JOIN fake_names fn ON i.HISTID = fn.HISTID
                    WHERE i.STATEICP = '{TARGET_STATE}' AND i.COUNTYICP IN ({county_sql})
                    GROUP BY i.YEAR, i.SERIAL
                )
                SELECT 
                    i.* EXCLUDE (NAMEFRST, NAMELAST),
                    COALESCE(fn.FAKE_FIRST, i.NAMEFRST) AS NAMEFRST,
                    COALESCE(th.FAKE_LAST, i.NAMELAST) AS NAMELAST
                FROM individuals i
                INNER JOIN target_households t 
                    ON i.YEAR = t.YEAR AND i.SERIAL = t.SERIAL
                LEFT JOIN fake_names fn 
                    ON i.HISTID = fn.HISTID
                -- Keep ONLY the core nuclear family (Head, Spouse, Child) to keep the test file clean
                WHERE i.RELATE IN ('01', '1', 'Head/householder', '02', '2', 'Spouse', '03', '3', 'Child')
            ) TO '{OUTPUT_CSV}' (HEADER, DELIMITER ',');
        """
        con.execute(query)
        print(f"SUCCESS! Golden Test Dataset created at: {OUTPUT_CSV}")
