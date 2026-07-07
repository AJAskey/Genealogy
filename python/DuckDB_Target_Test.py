"""
File: DuckDB_Target_Test.py
Summary: The "Prove It" Stress Test.
         Uses DuckDB to connect to ALL yearly vaults simultaneously, 
         hunts specifically for Foster Edgar and William Francis, 
         and exports the exact matches across all decades to a CSV.
"""
import os
import json
import duckdb
import csv

# --- CONFIGURATION ---
YEAR_WINDOW = 1  # +/- 1 year for age drift

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(project_root, "JSON", "duck_hunting.json")
OUTPUT_CSV = os.path.join(project_root, "output", "DuckDB_Target_Test_Results.csv")

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")

NAME_TO_BPL = {
    "PENNSYLVANIA": 42, "NEW YORK": 36, "OHIO": 39, "MARYLAND": 24, "NEW JERSEY": 34,
    "IRELAND": 414, "ENGLAND": 410, "GERMANY": 453, "SCOTLAND": 412
}


def get_base_code(code_str):
    if not code_str: return 0
    try:
        val = int(float(code_str))
        return val // 100 if val >= 1000 else val
    except (ValueError, TypeError):
        return NAME_TO_BPL.get(str(code_str).strip().upper(), 0)


def main():
    print("--- Starting DuckDB Cross-Decade Target Test ---")

    con = duckdb.connect()
    attached_years = []

    # Attach all available yearly databases!
    for year in range(1850, 1950, 10):
        if year == 1890: continue
        db_path = os.path.join(YEARLY_VAULT_DIR, f"YearVault_{year}.db")
        if os.path.exists(db_path):
            con.execute(f"ATTACH '{db_path}' AS vault_{year} (TYPE SQLITE, READ_ONLY);")
            attached_years.append(year)
            print(f"Attached vault_{year}")

    if not attached_years:
        print("No databases found in YearlyVaults!")
        return

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        ducks = json.load(f)

    # Filter the JSON down to JUST Foster Edgar and William Francis
    test_targets = []
    for idx, couple in enumerate(ducks):
        h_first = str(couple.get('h_first', '')).upper()
        if "FOSTER EDGAR" in h_first or "WILLIAM FRANCIS" in h_first:
            test_targets.append((idx, couple))

    print(f"Found {len(test_targets)} test targets matching requested names in the JSON.")

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            ["Target_Name", "Census_Year", "DB_Family_ID", "DB_H_Name", "DB_W_Name", "H_BirthYr", "W_BirthYr",
             "County_ICP", "Kid_Fingerprint"])

        for idx, g_dict in test_targets:
            h_first, h_last = g_dict.get('h_first', ''), g_dict.get('h_last', '')
            w_first, w_last = g_dict.get('w_first', ''), g_dict.get('w_last', '')
            target_name = f"{h_first} {h_last} & {w_first} {w_last}"
            print(f"Querying across all decades for: {target_name}")

            h_bpl = get_base_code(g_dict.get('h_bpl'))
            w_bpl = get_base_code(g_dict.get('w_bpl'))
            h_fbpl = get_base_code(g_dict.get('h_fbpl'))
            h_mbpl = get_base_code(g_dict.get('h_mbpl'))
            w_fbpl = get_base_code(g_dict.get('w_fbpl'))
            w_mbpl = get_base_code(g_dict.get('w_mbpl'))

            h_byr = int(g_dict.get('h_byr', 0)) if str(g_dict.get('h_byr', 0)).isnumeric() else 0
            w_byr = int(g_dict.get('w_byr', 0)) if str(g_dict.get('w_byr', 0)).isnumeric() else 0
            kid_fingerprint = int(g_dict.get('kid_fingerprint', 0))

            union_queries = []
            for year in attached_years:
                # Notice DuckDB uses // for integer division instead of / !
                sql = f"""
                    SELECT {year} AS census_year, f.family_id, h.first_name, h.last_name, s.first_name, s.last_name, h.birthyr, s.birthyr, f.countyicp, f.kids_byr_sum
                    FROM vault_{year}.families f
                    JOIN vault_{year}.individuals h ON f.head_histid = h.histid
                    JOIN vault_{year}.individuals s ON f.spouse_histid = s.histid
                    WHERE h.sex = '1' AND s.sex = '2'
                      AND TRY_CAST(h.birthyr AS INTEGER) BETWEEN {h_byr - YEAR_WINDOW} AND {h_byr + YEAR_WINDOW}
                      AND TRY_CAST(s.birthyr AS INTEGER) BETWEEN {w_byr - YEAR_WINDOW} AND {w_byr + YEAR_WINDOW}
                      AND (CASE WHEN TRY_CAST(h.bpld AS INTEGER) >= 1000 THEN TRY_CAST(h.bpld AS INTEGER) // 100 ELSE TRY_CAST(h.bpld AS INTEGER) END) = {h_bpl}
                      AND (CASE WHEN TRY_CAST(s.bpld AS INTEGER) >= 1000 THEN TRY_CAST(s.bpld AS INTEGER) // 100 ELSE TRY_CAST(s.bpld AS INTEGER) END) = {w_bpl}
                """

                # Add parent BPLs if they exist in the target data
                if h_fbpl > 0: sql += f" AND (CASE WHEN TRY_CAST(h.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(h.fbpl AS INTEGER) // 100 ELSE TRY_CAST(h.fbpl AS INTEGER) END) = {h_fbpl}"
                if h_mbpl > 0: sql += f" AND (CASE WHEN TRY_CAST(h.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(h.mbpl AS INTEGER) // 100 ELSE TRY_CAST(h.mbpl AS INTEGER) END) = {h_mbpl}"
                if w_fbpl > 0: sql += f" AND (CASE WHEN TRY_CAST(s.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(s.fbpl AS INTEGER) // 100 ELSE TRY_CAST(s.fbpl AS INTEGER) END) = {w_fbpl}"
                if w_mbpl > 0: sql += f" AND (CASE WHEN TRY_CAST(s.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(s.mbpl AS INTEGER) // 100 ELSE TRY_CAST(s.mbpl AS INTEGER) END) = {w_mbpl}"

                if kid_fingerprint > 0:
                    sql += f" AND f.kids_byr_sum = {kid_fingerprint}"

                union_queries.append(sql)

            # Combine all the yearly queries into one massive cross-decade search
            full_query = "\nUNION ALL\n".join(union_queries)

            results = con.execute(full_query).fetchall()
            for row in results:
                writer.writerow(
                    [target_name, row[0], row[1], f"{row[2]} {row[3]}", f"{row[4]} {row[5]}", row[6], row[7], row[8],
                     row[9]])

    print(f"Done! Check {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
