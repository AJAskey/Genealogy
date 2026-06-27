"""
File: Database_Sleuth.py
Summary: A diagnostic tool that loads decades into native DuckDB RAM, loops through
         your JSON file instantly, tests the EXACT V3 Strict Query, and uses fuzzy
         matching to explain any rejections!
"""
import duckdb
import os
import json

# Set this to your base data directory
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(PROJECT_ROOT, "JSON", "gedcom_couples.json")
TARGET_SURNAME = "ASKEY"  # Set to "" to search everyone, or "ASKEY" to filter!

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


def run_json_sleuth():
    if not os.path.exists(JSON_PATH):
        print(f"Cannot find JSON at: {JSON_PATH}")
        return

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"Loaded {len(data)} couples from JSON.")
    print("Initializing DuckDB for lightning-fast sleuthing...")

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='32GB'")
    con.execute("INSTALL sqlite; LOAD sqlite; SET sqlite_all_varchar=true;")

    # Dictionary to hold the print logs so we can output them grouped by couple at the end!
    couple_logs = {idx: [] for idx in range(len(data))}
    skipped_couples = set()  # Explicitly track who we've already logged as skipped

    valid_years = [1880, 1900, 1910, 1920, 1930, 1940]
    for year in valid_years:
        db_path = os.path.join(YEARLY_VAULT_DIR, f"YearVault_{year}.db")
        if not os.path.exists(db_path):
            print(f"[-] Cannot find database vault for {year} at: {db_path}")
            continue

        print(f"\n=====================================================================")
        print(f" LOADING {year} VAULT INTO RAM FOR LIGHTNING FAST SEARCH...")
        print(f"=====================================================================")

        con.execute(f"ATTACH '{db_path}' AS vault_{year} (TYPE SQLITE, READ_ONLY);")

        con.execute("DROP TABLE IF EXISTS mem_fams")
        con.execute("DROP TABLE IF EXISTS mem_inds")

        # Load the relevant columns into native DuckDB memory to avoid SQLite bottlenecks
        con.execute(f"""
            CREATE TABLE mem_fams AS 
            SELECT family_id, head_histid, spouse_histid, countyicp, stateicp 
            FROM vault_{year}.families 
            WHERE spouse_histid IS NOT NULL AND spouse_histid != ''
        """)

        con.execute(f"""
            CREATE TABLE mem_inds AS 
            SELECT histid, first_name, last_name, sex, 
                   TRY_CAST(birthyr AS INTEGER) AS birthyr_int,
                   CASE WHEN TRY_CAST(bpld AS INTEGER) >= 1000 THEN TRY_CAST(bpld AS INTEGER)//100 ELSE TRY_CAST(bpld AS INTEGER) END AS base_bpl,
                   CASE WHEN TRY_CAST(fbpl AS INTEGER) >= 1000 THEN TRY_CAST(fbpl AS INTEGER)//100 ELSE TRY_CAST(fbpl AS INTEGER) END AS base_fbpl,
                   CASE WHEN TRY_CAST(mbpl AS INTEGER) >= 1000 THEN TRY_CAST(mbpl AS INTEGER)//100 ELSE TRY_CAST(mbpl AS INTEGER) END AS base_mbpl
            FROM vault_{year}.individuals
            WHERE first_name IS NOT NULL AND first_name != ''
        """)

        print(f" -> {year} loaded! Sleuthing {len(data)} targets...")

        for idx, couple in enumerate(data):
            h_f = couple.get('h_first', '')
            h_l = couple.get('h_last', '')
            w_f = couple.get('w_first', '')
            h_byr = couple.get('h_byr', '')
            w_byr = couple.get('w_byr', '')

            if TARGET_SURNAME and TARGET_SURNAME.upper() not in h_l.upper():
                continue

            if not h_byr or not w_byr or not str(h_byr).isnumeric() or not str(w_byr).isnumeric():
                continue

            h_byr_int = int(h_byr)
            w_byr_int = int(w_byr)

            h_bpl = get_base_code(couple.get('h_bpl'))
            w_bpl = get_base_code(couple.get('w_bpl'))
            h_fbpl = get_base_code(couple.get('h_fbpl'))
            h_mbpl = get_base_code(couple.get('h_mbpl'))
            w_fbpl = get_base_code(couple.get('w_fbpl'))
            w_mbpl = get_base_code(couple.get('w_mbpl'))

            # Skip if they have a missing required birthplace
            if 0 in (h_bpl, w_bpl, h_fbpl, h_mbpl, w_fbpl, w_mbpl):
                if idx not in skipped_couples:
                    couple_logs[idx].append(
                        f" [!] SKIPPED: {h_f} {h_l} & {w_f} - Missing one or more required birthplaces in GEDCOM.")
                    skipped_couples.add(idx)
                continue

            # --- ACTUAL V3 STRICT QUERY ---
            v3_query = '''
                       SELECT h.histid, h.first_name, h.last_name, s.first_name, s.last_name
                       FROM mem_fams f
                                JOIN mem_inds h ON f.head_histid = h.histid
                                JOIN mem_inds s ON f.spouse_histid = s.histid
                       WHERE h.birthyr_int BETWEEN ? AND ?
                         AND s.birthyr_int BETWEEN ? AND ?
                         AND h.sex = '1'
                         AND s.sex = '2'
                         AND h.base_bpl = ?
                         AND s.base_bpl = ?
                         AND (? = 0 OR h.base_fbpl IS NULL OR h.base_fbpl = 0 OR h.base_fbpl = ?)
                         AND (? = 0 OR h.base_mbpl IS NULL OR h.base_mbpl = 0 OR h.base_mbpl = ?)
                         AND (? = 0 OR s.base_fbpl IS NULL OR s.base_fbpl = 0 OR s.base_fbpl = ?)
                         AND (? = 0 OR s.base_mbpl IS NULL OR s.base_mbpl = 0 OR s.base_mbpl = ?) \
                       '''
            year_win = 5
            v3_params = (
                h_byr_int - year_win, h_byr_int + year_win,
                w_byr_int - year_win, w_byr_int + year_win,
                h_bpl, w_bpl,
                h_fbpl, h_fbpl,
                h_mbpl, h_mbpl,
                w_fbpl, w_fbpl,
                w_mbpl, w_mbpl
            )

            if not couple_logs[idx]:
                couple_logs[idx].append(f"  STRICT QUERY PARAMETERS:")
                couple_logs[idx].append(
                    f"    -> Husband : Age {h_byr_int - year_win}-{h_byr_int + year_win} | BPL: {h_bpl} | FBPL: {h_fbpl} | MBPL: {h_mbpl}")
                couple_logs[idx].append(
                    f"    -> Wife    : Age {w_byr_int - year_win}-{w_byr_int + year_win} | BPL: {w_bpl} | FBPL: {w_fbpl} | MBPL: {w_mbpl}")

            con.execute(v3_query, v3_params)
            strict_rows = con.fetchall()

            if strict_rows:
                couple_logs[idx].append(
                    f"  [{year}] SUCCESS! V3 Strict Query matched ({len(strict_rows)} demographic hits in database).")
                continue

            # --- FUZZY QUERY ---
            fuzzy_query = """
                          SELECT h.histid, \
                                 h.first_name, \
                                 h.last_name, \
                                 h.sex, \
                                 h.birthyr_int, \
                                 h.base_bpl, \
                                 h.base_fbpl, \
                                 h.base_mbpl,
                                 s.first_name, \
                                 s.last_name, \
                                 s.sex, \
                                 s.birthyr_int, \
                                 s.base_bpl, \
                                 s.base_fbpl, \
                                 s.base_mbpl,
                                 f.countyicp, \
                                 f.stateicp
                          FROM mem_fams f
                                   JOIN mem_inds h ON f.head_histid = h.histid
                                   JOIN mem_inds s ON f.spouse_histid = s.histid
                          WHERE h.birthyr_int BETWEEN ? AND ?
                            AND s.birthyr_int BETWEEN ? AND ?
                            AND h.base_bpl = ?
                            AND s.base_bpl = ?
                            AND h.sex = '1'
                            AND s.sex = '2' \
                          """
            con.execute(fuzzy_query, (
                h_byr_int - 5, h_byr_int + 5,
                w_byr_int - 5, w_byr_int + 5,
                h_bpl, w_bpl
            ))
            rows = con.fetchall()
            matches_found = 0

            for r in rows:
                h_id, h_fn, h_ln, h_sex, h_b, db_h_bpl, db_h_fbpl, db_h_mbpl, w_fn, w_ln, w_sex, w_b, db_w_bpl, db_w_fbpl, db_w_mbpl, cty, st = r

                # Check if the first 2 letters of last name match to keep logs clean
                if len(h_l) >= 2 and h_ln and h_ln.upper().startswith(h_l[:2].upper()):
                    matches_found += 1
                    if matches_found <= 5:
                        couple_logs[idx].append(f"  [{year}] FAILED V3 STRICT MATCH. Found fuzzy candidate:")
                        couple_logs[idx].append(
                            f"    -> Census Husband : {h_fn} {h_ln} (b.{h_b}) | FBPL: {db_h_fbpl}, MBPL: {db_h_mbpl}")
                        couple_logs[idx].append(
                            f"    -> Census Wife    : {w_fn} {w_ln} (b.{w_b}) | FBPL: {db_w_fbpl}, MBPL: {db_w_mbpl}")

                        errs = []
                        if h_b is None:
                            errs.append(f"H_BYR (Missing/Null)")
                        elif abs(h_b - h_byr_int) > 2:
                            errs.append(f"H_BYR ({h_b} vs {h_byr_int})")

                        if w_b is None:
                            errs.append(f"W_BYR (Missing/Null)")
                        elif abs(w_b - w_byr_int) > 2:
                            errs.append(f"W_BYR ({w_b} vs {w_byr_int})")

                        if h_fbpl != 0 and db_h_fbpl != 0 and db_h_fbpl != h_fbpl: errs.append(
                            f"H_FBPL ({db_h_fbpl} vs {h_fbpl})")
                        if h_mbpl != 0 and db_h_mbpl != 0 and db_h_mbpl != h_mbpl: errs.append(
                            f"H_MBPL ({db_h_mbpl} vs {h_mbpl})")
                        if w_fbpl != 0 and db_w_fbpl != 0 and db_w_fbpl != w_fbpl: errs.append(
                            f"W_FBPL ({db_w_fbpl} vs {w_fbpl})")
                        if w_mbpl != 0 and db_w_mbpl != 0 and db_w_mbpl != w_mbpl: errs.append(
                            f"W_MBPL ({db_w_mbpl} vs {w_mbpl})")

                        if errs:
                            couple_logs[idx].append(f"    [!] REASONS FOR REJECTION: {', '.join(errs)}")
                        else:
                            couple_logs[idx].append(f"    [?] No strict mismatches found. V3 might drop in Phase 2.")
                        couple_logs[idx].append(f"    -------------------------------------------------")

            if matches_found > 5:
                couple_logs[idx].append(f"    ... and {matches_found - 5} more fuzzy demographic matches omitted.")

            if matches_found == 0:
                couple_logs[idx].append(f"  [{year}] No matches found for this couple in this census year.")

        con.execute("DROP TABLE mem_fams")
        con.execute("DROP TABLE mem_inds")
        con.execute(f"DETACH vault_{year}")

    # --- PRINT OUT THE FINAL DIAGNOSTIC REPORT ---
    print(f"\n=====================================================================")
    print(f" FINAL DIAGNOSTIC REPORT")
    print(f"=====================================================================\n")

    for idx, couple in enumerate(data):
        h_f = couple.get('h_first', '')
        h_l = couple.get('h_last', '')
        w_f = couple.get('w_first', '')
        h_byr = couple.get('h_byr', '')
        w_byr = couple.get('w_byr', '')

        if TARGET_SURNAME and TARGET_SURNAME.upper() not in h_l.upper():
            continue

        if not h_byr or not w_byr or not str(h_byr).isnumeric() or not str(w_byr).isnumeric():
            continue

        print(f" Analyzing GEDCOM Target: {h_f} {h_l} (b.{h_byr}) & {w_f} (b.{w_byr})")
        for log_line in couple_logs[idx]:
            print(log_line)
        print("=====================================================================")


if __name__ == "__main__":
    run_json_sleuth()
