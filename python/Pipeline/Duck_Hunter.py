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
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatchesTest.db")

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
    logger.info(f"MATCH_DB : {MATCH_DB}")

    if not os.path.exists(JSON_PATH):
        logger.warning(f"Error: Could not find {JSON_PATH}")
        return

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        targets = json.load(f)

    logger.info(f"Loaded {len(targets)} targets for the hunt.")
    con = duckdb.connect()

    # Attach the high-speed Time Machine instead of the slow raw SQLite vaults!
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db (READ_ONLY)")
    attached_years = [y for y in range(1850, 1950, 10) if y != 1890]

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            ["Target_Name", "Census_Year", "Score", "Match_Reasons", "DB_Family_ID", "DB_H_Name", "DB_W_Name",
             "DB_State_ICP", "DB_County_ICP", "Target_KFP", "DB_Snapshot_KFP", "DB_Lifetime_KFP", "DB_Kids"])

        stats = {
            "total_targets": len(targets),
            "exact_kfp_found": 0,
            "near_miss_kfp_found": 0,
            "no_match_found": 0
        }

        for t in targets:

            h_first, h_last = t.get('h_first', ''), t.get('h_last', '')
            w_first, w_last = t.get('w_first', ''), t.get('w_last', '')

            # Temporary filter for testing!
            # if "FOSTER EDGAR" not in h_first.upper() and "WILLIAM FRANCIS" not in h_first.upper():
            #     continue

            h_bpl = get_bpl_code(t.get('h_bpl', ''))
            w_bpl = get_bpl_code(t.get('w_bpl', ''))
            h_fbpl = get_bpl_code(t.get('h_fbpl', ''))
            h_mbpl = get_bpl_code(t.get('h_mbpl', ''))
            w_fbpl = get_bpl_code(t.get('w_fbpl', ''))
            w_mbpl = get_bpl_code(t.get('w_mbpl', ''))
            kfp = t.get('kid_fingerprint', '')

            target_name = f"{h_first} {h_last} & {w_first} {w_last}"
            h_byr = int(t.get('h_byr', 0)) if str(t.get('h_byr', '')).isnumeric() else 0
            w_byr = int(t.get('w_byr', 0)) if str(t.get('w_byr', '')).isnumeric() else 0

            if h_byr == 0 or w_byr == 0 or h_bpl == 0 or w_bpl == 0: continue
            if h_fbpl == 0 or h_mbpl == 0: continue

            best_target_drift = None
            num_kids = int(t.get('num_children', 0)) if str(t.get('num_children', '')).isnumeric() else 0

            logger.info("***************************************************")
            logger.info(f"Hunting: {target_name}...")
            logger.info(
                f"h_bpl : {h_bpl}  w_bpl:{w_bpl}  h_fbpl:{h_fbpl}  h_mbpl:{h_mbpl}  w_fbpl:{w_fbpl}  w_mbpl:{w_mbpl}  kfp:{kfp}")
            gen_logging.log_dict(logger, t, "target data")

            for year in attached_years:
                search_location = "ALL STATES"

                sql = f"SELECT f.family_id, h.first_name, h.last_name, s.first_name, s.last_name, f.stateicp, f.countyicp, f.kids_byr_sum, f.head_histid, f.spouse_histid, COALESCE(cd.lifetime_kfp, 0) AS lifetime_kfp FROM match_db.tm_families f JOIN match_db.tm_individuals h ON f.head_histid = h.histid JOIN match_db.tm_individuals s ON f.spouse_histid = s.histid LEFT JOIN match_db.clan_mapping cm ON f.family_id = cm.family_id LEFT JOIN match_db.clan_details cd ON cm.clan_id = cd.clan_id WHERE f.year = {year} AND h.sex = '1' AND s.sex = '2' AND h.byr_int = {h_byr} AND s.byr_int = {w_byr}"

                if h_bpl > 0: sql += f" AND h.bpl_int = {h_bpl}"
                if w_bpl > 0: sql += f" AND s.bpl_int = {w_bpl}"
                if h_fbpl > 0: sql += f" AND h.fbpl_int = {h_fbpl}"
                if h_mbpl > 0: sql += f" AND h.mbpl_int = {h_mbpl}"
                if w_fbpl > 0: sql += f" AND s.fbpl_int = {w_fbpl}"
                if w_mbpl > 0: sql += f" AND s.mbpl_int = {w_mbpl}"

                logger.info(f"SQL : {sql}")

                # REMOVED: We cannot use the GEDCOM lifetime fingerprint to search a point-in-time census snapshot!

                k_print = int(t.get('kid_fingerprint', 0)) if str(t.get('kid_fingerprint', '')).isnumeric() else 0
                # if k_print > 0:
                #     sql += f" AND f.kids_byr_sum = {k_print}"

                results = con.execute(sql).fetchall()
                logger.info(f"Found {len(results)} candidate families for {year}")

                scored_results = []
                wcnt = 0
                for r in results:

                    fam_id = r[0]
                    db_stateicp = r[5]
                    db_countyicp = r[6]
                    db_snapshot_kfp = r[7]
                    db_lifetime_kfp = r[10]

                    score = 0
                    reasons = []

                    # Check 1: Did they live in the expected state?
                    target_state = str(t.get(f'h_rsst_{year}', '')).upper().strip()
                    if not target_state: target_state = str(t.get(f'w_rsst_{year}', '')).upper().strip()

                    if target_state and target_state in STATE_TO_ICP:
                        if db_stateicp == STATE_TO_ICP[target_state]:
                            score += 5
                            reasons.append("State Match")

                    # Check 2: Exact Match with Telemetry for Near Misses (1% drift allowance)
                    if k_print > 0:
                        drift = abs(int(db_snapshot_kfp) - int(k_print))
                        if drift == 0:
                            score += 100
                            reasons.append("Exact Snapshot KFP")
                            best_target_drift = 0
                        elif num_kids > 0 and drift <= num_kids:
                            # Allow a maximum of 1 year of drift per kid (Very tight "1% off" rule)
                            score += 75
                            reasons.append(f"Near Snapshot KFP (Off by {drift})")
                            if best_target_drift is None or drift < best_target_drift:
                                best_target_drift = drift

                    kids_sql = f"SELECT first_name, byr_int FROM match_db.tm_individuals WHERE family_id = '{fam_id}' AND histid != '{r[8]}' AND histid != '{r[9]}' ORDER BY byr_int"
                    kids = con.execute(kids_sql).fetchall()
                    kids_str = ", ".join([f"{k[0]} (b.{k[1]})" for k in kids]) if kids else "None"

                    scored_results.append({
                        'row': [target_name, year, score, " + ".join(reasons) if reasons else "Demographics Only",
                                fam_id, f"{r[1]} {r[2]}", f"{r[3]} {r[4]}", db_stateicp, db_countyicp, k_print,
                                db_snapshot_kfp, db_lifetime_kfp, kids_str],
                        'score': score
                    })

                # Sort results by score (highest first) so your true ancestor is always at the top!
                scored_results.sort(key=lambda x: x['score'], reverse=True)

                # Only write the top 3 highest-scoring candidates to the CSV!
                for sr in scored_results[:333]:
                    writer.writerow(sr['row'])

            # Tally the statistics for this target across all decades
            if best_target_drift == 0:
                stats["exact_kfp_found"] += 1
            elif best_target_drift is not None:
                stats["near_miss_kfp_found"] += 1
            else:
                stats["no_match_found"] += 1

    # Print the Final Telemetry Report
    logger.info("\n=====================================================================")
    logger.info("HUNTING STATISTICS & KFP DRIFT REPORT")
    logger.info("=====================================================================")
    logger.info(f"Total Targets Hunted : {stats['total_targets']}")
    if stats['total_targets'] > 0:
        logger.info(
            f"Exact KFP Matches    : {stats['exact_kfp_found']} ({(stats['exact_kfp_found'] / stats['total_targets']) * 100:.1f}%)")
        logger.info(
            f"Near Miss KFP Matches: {stats['near_miss_kfp_found']} ({(stats['near_miss_kfp_found'] / stats['total_targets']) * 100:.1f}%)")
        logger.info(
            f"No KFP Match Found   : {stats['no_match_found']} ({(stats['no_match_found'] / stats['total_targets']) * 100:.1f}%)")
    else:
        logger.info("No targets were processed, so percentages cannot be calculated.")
    logger.info("=====================================================================")

    logger.info(f"\nDone! Results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    logger = gen_logging.setup_logging(logger_name="Duck_Hunting")
    main()
