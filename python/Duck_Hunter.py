"""
File: Duck_Hunter.py
Summary: Reads duck_hunting.json and hunts for the specific families
         in the DuckDB vaults using their exact known residence years!
"""
import os
import json
import duckdb
import csv
from utils import gen_logging

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(project_root, "JSON", "duck_hunting.json")
OUTPUT_CSV = os.path.join(project_root, "output", "Duck_Hunt_Results.csv")

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches2.db")

STATE_TO_ICP = {
    "CONNECTICUT": 1, "MAINE": 5, "MASSACHUSETTS": 2, "NEW HAMPSHIRE": 4, "RHODE ISLAND": 3, "VERMONT": 6,
    "DELAWARE": 11, "NEW JERSEY": 12, "NEW YORK": 13, "PENNSYLVANIA": 14,
    "ILLINOIS": 21, "INDIANA": 22, "MICHIGAN": 23, "OHIO": 24, "WISCONSIN": 25,
    "IOWA": 31, "KANSAS": 32, "MINNESOTA": 33, "MISSOURI": 34, "NEBRASKA": 35, "NORTH DAKOTA": 36, "SOUTH DAKOTA": 37,
    "VIRGINIA": 41, "WEST VIRGINIA": 42, "NORTH CAROLINA": 43, "SOUTH CAROLINA": 44, "GEORGIA": 45, "FLORIDA": 46,
    "DISTRICT OF COLUMBIA": 47, "MARYLAND": 48,
    "KENTUCKY": 51, "TENNESSEE": 52, "ALABAMA": 53, "MISSISSIPPI": 54,
    "ARKANSAS": 61, "LOUISIANA": 62, "OKLAHOMA": 63, "TEXAS": 64,
    "MONTANA": 71, "IDAHO": 72, "WYOMING": 73, "COLORADO": 74, "NEW MEXICO": 75, "ARIZONA": 76, "UTAH": 77,
    "NEVADA": 78,
    "WASHINGTON": 81, "OREGON": 82, "CALIFORNIA": 83, "ALASKA": 84, "HAWAII": 85
}


def get_bpl_code(bpl_str):
    bpl_str = str(bpl_str).upper()
    if "PENNSYLVANIA" in bpl_str or "PENNA" in bpl_str or "PA" in bpl_str.split(): return 42
    if "OHIO" in bpl_str: return 39
    if "NEW YORK" in bpl_str or "NY" in bpl_str.split(): return 36
    if "IOWA" in bpl_str: return 19
    if "ILLINOIS" in bpl_str: return 17
    if "INDIANA" in bpl_str: return 18
    if "KANSAS" in bpl_str: return 20
    if "MISSOURI" in bpl_str: return 29
    if "WISCONSIN" in bpl_str: return 55
    if "MARYLAND" in bpl_str: return 24
    if "NEW JERSEY" in bpl_str: return 34
    if "CALIFORNIA" in bpl_str: return 6
    if "TEXAS" in bpl_str: return 48
    if "NEBRASKA" in bpl_str: return 31
    if "COLORADO" in bpl_str: return 8
    if "MINNESOTA" in bpl_str: return 27
    if "WASHINGTON" in bpl_str: return 53
    if "OREGON" in bpl_str: return 41
    if "IRELAND" in bpl_str: return 414
    if "ENGLAND" in bpl_str: return 410
    if "GERMANY" in bpl_str: return 453
    if "SCOTLAND" in bpl_str: return 412
    if "WALES" in bpl_str: return 411
    if "CANADA" in bpl_str: return 150
    if "SWEDEN" in bpl_str: return 404
    if "DENMARK" in bpl_str: return 400
    return 0


def main():
    logger.info("--- Starting The Duck Hunter ---")
    if not os.path.exists(JSON_PATH):
        print(f"Error: Could not find {JSON_PATH}")
        return

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        targets = json.load(f)

    logger.info(f"Loaded {len(targets)} targets for the hunt.")
    con = duckdb.connect()

    # Attach the high-speed Time Machine instead of the slow raw SQLite vaults!
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db")
    attached_years = [y for y in range(1850, 1950, 10) if y != 1890]

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Target_Name", "Census_Year", "State_Searched", "DB_Family_ID", "DB_H_Name", "DB_W_Name",
                         "County_ICP", "Kid_Fingerprint", "Match_Type", "DB_Kids"])
        logger.info('"Target_Name", "Census_Year", "State_Searched", "DB_Family_ID", "DB_H_Name", "DB_W_Name", \
                         "County_ICP", "Kid_Fingerprint", "Match_Type", "DB_Kids"]')

        for t in targets:
            h_first, h_last = t.get('h_first', ''), t.get('h_last', '')
            w_first, w_last = t.get('w_first', ''), t.get('w_last', '')

            # Temporary filter for testing!
            if "FOSTER EDGAR" not in h_first.upper() and "WILLIAM FRANCIS" not in h_first.upper():
                continue

            target_name = f"{h_first} {h_last} & {w_first} {w_last}"
            h_byr = int(t.get('h_byr', 0)) if str(t.get('h_byr', '')).isnumeric() else 0
            w_byr = int(t.get('w_byr', 0)) if str(t.get('w_byr', '')).isnumeric() else 0
            if h_byr == 0 or w_byr == 0: continue

            h_bpl = get_bpl_code(t.get('h_bpl', ''))
            w_bpl = get_bpl_code(t.get('w_bpl', ''))
            h_fbpl = get_bpl_code(t.get('h_fbpl', ''))
            h_mbpl = get_bpl_code(t.get('h_mbpl', ''))
            w_fbpl = get_bpl_code(t.get('w_fbpl', ''))
            w_mbpl = get_bpl_code(t.get('w_mbpl', ''))
            kfp = t.get('kid_fingerprint', '')

            logger.info(
                f"h_bpl : {h_bpl}  w_bpl:{w_bpl}  h_fbpl:{h_fbpl}  h_mbpl:{h_mbpl}  w_fbpl:{w_fbpl}  w_mbpl:{w_mbpl}  kfp:{kfp}")

            # k_print = int(t.get('kid_fingerprint', 0)) if str(t.get('kid_fingerprint', '')).isnumeric() else 0
            # logger.info(f"k_print:{k_print}")

            logger.info(f"Hunting: {target_name}...")

            for year in attached_years:
                res_state = str(t.get(f'h_rsst_{year}', '')).upper().strip()
                if not res_state: res_state = str(t.get(f'w_rsst_{year}', '')).upper().strip()

                state_filter_sql = ""
                search_location = "ALL STATES (Missing in GEDCOM)"

                if res_state and res_state in STATE_TO_ICP:
                    state_filter_sql = f"f.stateicp = {STATE_TO_ICP[res_state]} AND "
                    search_location = res_state

                sql = f"SELECT f.family_id, h.first_name, h.last_name, s.first_name, s.last_name, f.countyicp, f.kids_byr_sum, f.head_histid, f.spouse_histid FROM match_db.tm_families f JOIN match_db.tm_individuals h ON f.head_histid = h.histid JOIN match_db.tm_individuals s ON f.spouse_histid = s.histid WHERE f.year = {year} AND {state_filter_sql}h.sex = '1' AND s.sex = '2' AND TRY_CAST(h.birthyr AS INTEGER) BETWEEN {h_byr - 2} AND {h_byr + 2} AND TRY_CAST(s.birthyr AS INTEGER) BETWEEN {w_byr - 2} AND {w_byr + 2}"
                if h_bpl > 0: sql += f" AND (CASE WHEN TRY_CAST(h.bpld AS INTEGER) >= 1000 THEN TRY_CAST(h.bpld AS INTEGER) // 100 ELSE TRY_CAST(h.bpld AS INTEGER) END) = {h_bpl}"
                if w_bpl > 0: sql += f" AND (CASE WHEN TRY_CAST(s.bpld AS INTEGER) >= 1000 THEN TRY_CAST(s.bpld AS INTEGER) // 100 ELSE TRY_CAST(s.bpld AS INTEGER) END) = {w_bpl}"
                if h_fbpl > 0: sql += f" AND (CASE WHEN TRY_CAST(h.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(h.fbpl AS INTEGER) // 100 ELSE TRY_CAST(h.fbpl AS INTEGER) END) = {h_fbpl}"
                if h_mbpl > 0: sql += f" AND (CASE WHEN TRY_CAST(h.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(h.mbpl AS INTEGER) // 100 ELSE TRY_CAST(h.mbpl AS INTEGER) END) = {h_mbpl}"
                if w_fbpl > 0: sql += f" AND (CASE WHEN TRY_CAST(s.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(s.fbpl AS INTEGER) // 100 ELSE TRY_CAST(s.fbpl AS INTEGER) END) = {w_fbpl}"
                if w_mbpl > 0: sql += f" AND (CASE WHEN TRY_CAST(s.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(s.mbpl AS INTEGER) // 100 ELSE TRY_CAST(s.mbpl AS INTEGER) END) = {w_mbpl}"

                # REMOVED: We cannot use the GEDCOM lifetime fingerprint to search a point-in-time census snapshot!

                k_print = int(t.get('kid_fingerprint', 0)) if str(t.get('kid_fingerprint', '')).isnumeric() else 0
                if k_print > 0:
                    sql += f" AND f.kids_byr_sum = {k_print}"

                wcnt = 0
                for r in con.execute(sql).fetchall():
                    logger.info(f"len(r) = {len(r)}   -->  k_print = {k_print}")

                    fam_id, head_id, spouse_id = r[0], r[7], r[8]

                    # Fetch the kids from the Time Machine
                    kids_sql = f"SELECT first_name, birthyr FROM match_db.tm_individuals WHERE family_id = '{fam_id}' AND histid != '{head_id}' AND histid != '{spouse_id}' ORDER BY birthyr"
                    kids = con.execute(kids_sql).fetchall()
                    kids_str = ", ".join([f"{k[0]} (b.{k[1]})" for k in kids]) if kids else "None"

                    writer.writerow(
                        [target_name, year, search_location, fam_id, f"{r[1]} {r[2]}", f"{r[3]} {r[4]}", r[5], r[6],
                         "Exact Fingerprint" if k_print > 0 else "Demographic", kids_str])
                    if wcnt < 100:
                        wcnt += 1
                        logger.info([wcnt, target_name, year, search_location, fam_id, f"{r[1]} {r[2]}",
                                     f"{r[3]} {r[4]}", r[5],
                                     r[6],
                                     "Exact Fingerprint" if k_print > 0 else "Demographic", kids_str])

    logger.info(f"\nDone! Results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    logger = gen_logging.setup_logging(logger_name="Duck_Hunting")
    main()
