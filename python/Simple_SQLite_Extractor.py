"""
File: Simple_SQLite_Extractor.py
Summary: The "Go Small" MVP Extractor.
         Connects to a single SQLite Census Vault, finds exact demographic 
         matches for GEDCOM targets, and exports them directly to a CSV.
"""
import os
import json
import sqlite3
import csv

# --- CONFIGURATION ---
TARGET_YEAR = 1880  # Change this to whatever decade you want to search!
YEAR_WINDOW = 1     # +/- 1 year for age drift

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(project_root, "JSON", "gedcom_couples.json")
OUTPUT_CSV = os.path.join(project_root, "output", f"Simple_Matches_{TARGET_YEAR}.csv")

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

DB_PATH = os.path.join(BASE_DATA_DIR, "YearlyVaults", f"YearVault_{TARGET_YEAR}.db")

NAME_TO_BPL = {
    "PENNSYLVANIA": 42, "NEW YORK": 36, "OHIO": 39, "MARYLAND": 24, "NEW JERSEY": 34,
    "IRELAND": 414, "ENGLAND": 410, "GERMANY": 453, "SCOTLAND": 412
    # Add more as needed, or keep it focused on your core states for speed!
}

def get_base_code(code_str):
    if not code_str: return 0
    try:
        val = int(float(code_str))
        return val // 100 if val >= 1000 else val
    except (ValueError, TypeError):
        return NAME_TO_BPL.get(str(code_str).strip().upper(), 0)

def main():
    print(f"--- Starting Simple Extractor for {TARGET_YEAR} ---")
    
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Cannot find database at {DB_PATH}")
        return
        
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        gedcom_couples = json.load(f)
        
    print(f"Loaded {len(gedcom_couples)} targets from JSON.")
    
    # Prepare the CSV file
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    csv_file = open(OUTPUT_CSV, 'w', newline='', encoding='utf-8')
    writer = csv.writer(csv_file)
    writer.writerow(["Target_ID", "Ancestry_H_Name", "Ancestry_W_Name", 
                     "DB_Family_ID", "DB_H_BirthYr", "DB_W_BirthYr", "County_ICP", "Kid_Fingerprint"])

    # Connect to standard SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    matches_found = 0

    for idx, g_dict in enumerate(gedcom_couples):
        h_first, h_last = g_dict.get('h_first', ''), g_dict.get('h_last', '')
        w_first, w_last = g_dict.get('w_first', ''), g_dict.get('w_last', '')
        
        h_bpl = get_base_code(g_dict.get('h_bpl'))
        w_bpl = get_base_code(g_dict.get('w_bpl'))
        h_fbpl = get_base_code(g_dict.get('h_fbpl'))
        h_mbpl = get_base_code(g_dict.get('h_mbpl'))
        w_fbpl = get_base_code(g_dict.get('w_fbpl'))
        w_mbpl = get_base_code(g_dict.get('w_mbpl'))
        
        h_byr = int(g_dict.get('h_byr', 0)) if str(g_dict.get('h_byr', 0)).isnumeric() else 0
        w_byr = int(g_dict.get('w_byr', 0)) if str(g_dict.get('w_byr', 0)).isnumeric() else 0
        
        kid_fingerprint = int(g_dict.get('kid_fingerprint', 0))
        
        if h_byr == 0 or w_byr == 0 or h_bpl == 0 or w_bpl == 0:
            continue # Skip incomplete records

        # A standard, simple SQLite query
        sql = f"""
            SELECT f.family_id, h.birthyr, s.birthyr, f.countyicp
            FROM families f
            JOIN individuals h ON f.head_histid = h.histid
            JOIN individuals s ON f.spouse_histid = s.histid
            WHERE h.sex = '1' AND s.sex = '2'
              AND CAST(h.birthyr AS INTEGER) BETWEEN {h_byr - YEAR_WINDOW} AND {h_byr + YEAR_WINDOW}
              AND CAST(s.birthyr AS INTEGER) BETWEEN {w_byr - YEAR_WINDOW} AND {w_byr + YEAR_WINDOW}
              AND (CASE WHEN CAST(h.bpld AS INTEGER) >= 1000 THEN CAST(h.bpld AS INTEGER) / 100 ELSE CAST(h.bpld AS INTEGER) END) = {h_bpl}
              AND (CASE WHEN CAST(s.bpld AS INTEGER) >= 1000 THEN CAST(s.bpld AS INTEGER) / 100 ELSE CAST(s.bpld AS INTEGER) END) = {w_bpl}
              AND (CASE WHEN CAST(h.fbpl AS INTEGER) >= 1000 THEN CAST(h.fbpl AS INTEGER) / 100 ELSE CAST(h.fbpl AS INTEGER) END) = {h_fbpl}
              AND (CASE WHEN CAST(h.mbpl AS INTEGER) >= 1000 THEN CAST(h.mbpl AS INTEGER) / 100 ELSE CAST(h.mbpl AS INTEGER) END) = {h_mbpl}
              AND (CASE WHEN CAST(s.fbpl AS INTEGER) >= 1000 THEN CAST(s.fbpl AS INTEGER) / 100 ELSE CAST(s.fbpl AS INTEGER) END) = {w_fbpl}
              AND (CASE WHEN CAST(s.mbpl AS INTEGER) >= 1000 THEN CAST(s.mbpl AS INTEGER) / 100 ELSE CAST(s.mbpl AS INTEGER) END) = {w_mbpl}
        """
        
        if kid_fingerprint > 0:
            sql += f"              AND f.kids_byr_sum = {kid_fingerprint}\n"
            
        results = cursor.execute(sql).fetchall()
        
        for row in results:
            # row: (family_id, h_birthyr, s_birthyr, countyicp, kids_byr_sum)
            writer.writerow([idx, f"{h_first} {h_last}", f"{w_first} {w_last}", row[0], row[1], row[2], row[3], kid_fingerprint])
            matches_found += 1

    conn.close()
    csv_file.close()
    
    print(f"Done! Found {matches_found} matching families. Results saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()