import os
import json

# Set up paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(project_root, "JSON", "gedcom_couples.json")
SQL_OUT_DIR = os.path.join(project_root, "sql", "debug_queries")

NAME_TO_BPL = {
    "ALABAMA": 1, "ALASKA": 2, "ARIZONA": 4, "ARKANSAS": 5, "CALIFORNIA": 6,
    "COLORADO": 8, "CONNECTICUT": 9, "DELAWARE": 10, "DISTRICT OF COLUMBIA": 11,
    "FLORIDA": 12, "GEORGIA": 13, "HAWAII": 15, "IDAHO": 16, "ILLINOIS": 17,
    "INDIANA": 18, "IOWA": 19, "KANSAS": 20, "KENTUCKY": 21, "LOUISIANA": 22,
    "MAINE": 23, "MARYLAND": 24, "MASSACHUSETTS": 25, "MICHIGAN": 26,
    "MINNESOTA": 27, "MISSISSIPPI": 28, "MISSOURI": 29, "MONTANA": 30,
    "NEBRASKA": 31, "NEVADA": 32, "NEW HAMPSHIRE": 33, "NEW JERSEY": 34,
    "NEW MEXICO": 35, "NEW YORK": 36, "NORTH CAROLINA": 37, "NORTH DAKOTA": 38,
    "OHIO": 39, "OKLAHOMA": 40, "OREGON": 41, "PENNSYLVANIA": 42,
    "RHODE ISLAND": 44, "SOUTH CAROLINA": 45, "SOUTH DAKOTA": 46, "TENNESSEE": 47,
    "TEXAS": 48, "UTAH": 49, "VERMONT": 50, "VIRGINIA": 51, "WASHINGTON": 53,
    "WEST VIRGINIA": 54, "WISCONSIN": 55, "WYOMING": 56,
    "CANADA": 150, "MEXICO": 200, "DENMARK": 400, "NORWAY": 401, "SWEDEN": 404,
    "ENGLAND": 410, "WALES": 411, "SCOTLAND": 412, "NORTHERN IRELAND": 413, "IRELAND": 414,
    "FRANCE": 421, "NETHERLANDS": 425, "SWITZERLAND": 426, "GERMANY": 453,
    "JAPAN": 501, "SOUTH Korea": 502
}

def get_base_code(code_str):
    if not code_str: return 0
    try:
        val = int(float(code_str))
        return val // 100 if val >= 1000 else val
    except (ValueError, TypeError):
        clean_str = str(code_str).strip().upper()
        if clean_str in NAME_TO_BPL:
            return NAME_TO_BPL[clean_str]
        return 0

def main():
    os.makedirs(SQL_OUT_DIR, exist_ok=True)
    
    if not os.path.exists(JSON_PATH):
        print(f"Cannot find JSON at {JSON_PATH}")
        return
        
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    files_created = 0
    
    for couple in data:
        h_first, h_last = couple.get('h_first', 'Unknown'), couple.get('h_last', 'Unknown')
        w_first, w_last = couple.get('w_first', 'Unknown'), couple.get('w_last', 'Unknown')
        
        h_byr = couple.get('h_byr')
        w_byr = couple.get('w_byr')
        if not h_byr or not w_byr or not str(h_byr).isnumeric() or not str(w_byr).isnumeric():
            continue
            
        h_byr_int, w_byr_int = int(h_byr), int(w_byr)
        
        h_bpl = get_base_code(couple.get('h_bpl'))
        w_bpl = get_base_code(couple.get('w_bpl'))
        h_fbpl = get_base_code(couple.get('h_fbpl'))
        h_mbpl = get_base_code(couple.get('h_mbpl'))
        w_fbpl = get_base_code(couple.get('w_fbpl'))
        w_mbpl = get_base_code(couple.get('w_mbpl'))
        
        # Only generate queries for fully-documented people to match the Time Machine logic
        if 0 in (h_bpl, w_bpl, h_fbpl, h_mbpl, w_fbpl, w_mbpl):
            continue
            
        clean_h_first = "".join([c for c in h_first if c.isalpha()]).strip()
        filename = f"{clean_h_first}_{h_last}_{h_byr_int}.sql"
        filepath = os.path.join(SQL_OUT_DIR, filename)
        
        sql_content = f"""-- =========================================================================
-- TARGET: {h_first} {h_last} (b.{h_byr_int}) & {w_first} {w_last} (b.{w_byr_int})
-- =========================================================================

-- 1. THE EXACT COUPLE QUERY (This is what the Time Machine searches for)
SELECT 
    f.year, f.family_id,
    h.first_name AS Husb_First, h.last_name AS Husb_Last, h.birthyr AS Husb_Yr, h.bpld AS Husb_BPL, h.fbpl AS Husb_FBPL, h.mbpl AS Husb_MBPL,
    s.first_name AS Wife_First, s.last_name AS Wife_Last, s.birthyr AS Wife_Yr, s.bpld AS Wife_BPL, s.fbpl AS Wife_FBPL, s.mbpl AS Wife_MBPL
FROM families f
JOIN individuals h ON f.head_histid = h.histid
JOIN individuals s ON f.spouse_histid = s.histid
WHERE h.sex = '1' AND s.sex = '2'
  AND CAST(h.birthyr AS INTEGER) BETWEEN {h_byr_int - 5} AND {h_byr_int + 5}
  AND CAST(s.birthyr AS INTEGER) BETWEEN {w_byr_int - 5} AND {w_byr_int + 5}
  AND (CASE WHEN CAST(h.bpld AS INTEGER) >= 1000 THEN CAST(h.bpld AS INTEGER) / 100 ELSE CAST(h.bpld AS INTEGER) END) = {h_bpl}
  AND (CASE WHEN CAST(s.bpld AS INTEGER) >= 1000 THEN CAST(s.bpld AS INTEGER) / 100 ELSE CAST(s.bpld AS INTEGER) END) = {w_bpl}
  AND (CASE WHEN CAST(h.fbpl AS INTEGER) >= 1000 THEN CAST(h.fbpl AS INTEGER) / 100 ELSE CAST(h.fbpl AS INTEGER) END) = {h_fbpl}
  AND (CASE WHEN CAST(h.mbpl AS INTEGER) >= 1000 THEN CAST(h.mbpl AS INTEGER) / 100 ELSE CAST(h.mbpl AS INTEGER) END) = {h_mbpl}
  AND (CASE WHEN CAST(s.fbpl AS INTEGER) >= 1000 THEN CAST(s.fbpl AS INTEGER) / 100 ELSE CAST(s.fbpl AS INTEGER) END) = {w_fbpl}
  AND (CASE WHEN CAST(s.mbpl AS INTEGER) >= 1000 THEN CAST(s.mbpl AS INTEGER) / 100 ELSE CAST(s.mbpl AS INTEGER) END) = {w_mbpl};

-- 2. HUSBAND ONLY (If the couple query fails, highlight and run this to see if the husband exists without his wife)
SELECT histid, first_name, last_name, sex, birthyr, bpld, fbpl, mbpl
FROM individuals
WHERE sex = '1' AND CAST(birthyr AS INTEGER) BETWEEN {h_byr_int - 5} AND {h_byr_int + 5}
  AND (CASE WHEN CAST(bpld AS INTEGER) >= 1000 THEN CAST(bpld AS INTEGER) / 100 ELSE CAST(bpld AS INTEGER) END) = {h_bpl}
  AND (CASE WHEN CAST(fbpl AS INTEGER) >= 1000 THEN CAST(fbpl AS INTEGER) / 100 ELSE CAST(fbpl AS INTEGER) END) = {h_fbpl}
  AND (CASE WHEN CAST(mbpl AS INTEGER) >= 1000 THEN CAST(mbpl AS INTEGER) / 100 ELSE CAST(mbpl AS INTEGER) END) = {h_mbpl};
"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(sql_content)
        files_created += 1
        
    print(f"Generated {files_created} diagnostic SQL files in {SQL_OUT_DIR}!")

if __name__ == "__main__":
    main()