"""
File: ExportCensusToGedcom.py
Summary: Extracts historical census data into a fully compliant GEDCOM file.
         Bypasses broken Clan logic to treat every household independently.
         Dynamically cross-references GEDCOM JSON targets against the Time Machine
         to find exact Geo-Demographic matches, assigns real names to VIPs,
         fills the remaining tree with placeholder families, and uses NameList
         for realistic synthetic names.
"""
import os
import duckdb
import json
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

import gen_logging
from utils import NameList

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

OUTPUT_GEDCOM = os.path.join(project_root, "gedcom_sources", "Census_Export_Askey.ged")
COUNTY_NAMES_JSON = os.path.join(project_root, "JSON", "county_codes_to_names.json")
JSON_PATH = os.path.join(project_root, "JSON", "gedcom_couples.json")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches2.db")
FAMILY_EXPORT_LIMIT = 20000
YEAR_WINDOW = 1

REVERSE_BPL = {
    1: "Alabama", 2: "Alaska", 4: "Arizona", 5: "Arkansas", 6: "California",
    8: "Colorado", 9: "Connecticut", 10: "Delaware", 11: "District of Columbia",
    12: "Florida", 13: "Georgia", 15: "Hawaii", 16: "Idaho", 17: "Illinois",
    18: "Indiana", 19: "Iowa", 20: "Kansas", 21: "Kentucky", 22: "Louisiana",
    23: "Maine", 24: "Maryland", 25: "Massachusetts", 26: "Michigan",
    27: "Minnesota", 28: "Mississippi", 29: "Missouri", 30: "Montana",
    31: "Nebraska", 32: "Nevada", 33: "New Hampshire", 34: "New Jersey",
    35: "New Mexico", 36: "New York", 37: "North Carolina", 38: "North Dakota",
    39: "Ohio", 40: "Oklahoma", 41: "Oregon", 42: "Pennsylvania",
    44: "Rhode Island", 45: "South Carolina", 46: "South Dakota", 47: "Tennessee",
    48: "Texas", 49: "Utah", 50: "Vermont", 51: "Virginia", 53: "Washington",
    54: "West Virginia", 55: "Wisconsin", 56: "Wyoming",
    150: "Canada", 200: "Mexico", 400: "Denmark", 401: "Norway", 404: "Sweden",
    410: "England", 411: "Wales", 412: "Scotland", 413: "Northern Ireland", 414: "Ireland",
    421: "France", 425: "Netherlands", 426: "Switzerland", 453: "Germany",
    501: "Japan", 502: "South Korea"
}

STATEICP_MAP = {
    1: "Connecticut", 2: "Massachusetts", 3: "Rhode Island", 4: "New Hampshire", 5: "Maine", 6: "Vermont",
    11: "Delaware", 12: "New Jersey", 13: "New York", 14: "Pennsylvania",
    21: "Illinois", 22: "Indiana", 23: "Michigan", 24: "Ohio", 25: "Wisconsin",
    31: "Iowa", 32: "Kansas", 33: "Minnesota", 34: "Missouri", 35: "Nebraska", 36: "North Dakota", 37: "South Dakota",
    41: "Virginia", 42: "West Virginia", 43: "North Carolina", 44: "South Carolina", 45: "Georgia", 46: "Florida",
    47: "District of Columbia", 48: "Maryland",
    51: "Kentucky", 52: "Tennessee", 53: "Alabama", 54: "Mississippi",
    61: "Arkansas", 62: "Louisiana", 63: "Oklahoma", 64: "Texas",
    71: "Montana", 72: "Idaho", 73: "Wyoming", 74: "Colorado", 75: "New Mexico", 76: "Arizona", 77: "Utah",
    78: "Nevada",
    81: "Washington", 82: "Oregon", 83: "California", 84: "Alaska", 85: "Hawaii"
}

NAME_TO_BPL = {k.upper(): v for v, k in REVERSE_BPL.items()}


def decode_bpld(bpld_str):
    if not bpld_str or str(bpld_str).strip() == '': return "Unknown"
    try:
        val = int(float(bpld_str))
        prefix = val // 100 if val >= 1000 else val
        return REVERSE_BPL.get(prefix, "Unknown")
    except (ValueError, TypeError):
        return "Unknown"


def get_base_code(code_str):
    if not code_str: return 0
    try:
        val = int(float(code_str))
        return val // 100 if val >= 1000 else val
    except (ValueError, TypeError):
        clean_str = str(code_str).strip().upper()
        return NAME_TO_BPL.get(clean_str, 0)


def export_gedcom(logger):
    logger.info("Initializing All-In-One Exporter...")

    if not os.path.exists(MATCH_DB):
        logger.error(f"Could not find Match DB at {MATCH_DB}")
        return

    con = duckdb.connect(MATCH_DB, read_only=True)

    county_names_dict = {}
    if os.path.exists(COUNTY_NAMES_JSON):
        with open(COUNTY_NAMES_JSON, 'r', encoding='utf-8') as f:
            county_names_dict = json.load(f)

    if not os.path.exists(JSON_PATH):
        logger.error(f"Cannot find JSON file at: {JSON_PATH}")
        return

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        gedcom_couples = json.load(f)

    logger.info(f"Loaded {len(gedcom_couples)} target couples from JSON.")

    target_rows = []
    global_bpl_codes = set()

    for idx, g_dict in enumerate(gedcom_couples):
        h_bpl = get_base_code(g_dict.get('h_bpl')) or 0
        w_bpl = get_base_code(g_dict.get('w_bpl')) or 0
        h_fbpl = get_base_code(g_dict.get('h_fbpl')) or 0
        h_mbpl = get_base_code(g_dict.get('h_mbpl')) or 0
        w_fbpl = get_base_code(g_dict.get('w_fbpl')) or 0
        w_mbpl = get_base_code(g_dict.get('w_mbpl')) or 0

        if not g_dict.get('h_byr') or h_bpl == 0 or not g_dict.get('w_byr') or w_bpl == 0:
            continue

        target_rows.append((
            idx,
            int(g_dict.get('h_byr', 0)), h_bpl, h_fbpl, h_mbpl,
            int(g_dict.get('w_byr', 0)), w_bpl, w_fbpl, w_mbpl
        ))
        global_bpl_codes.add(h_bpl)
        global_bpl_codes.add(w_bpl)

    if not target_rows:
        logger.info("No high-quality target couples found to process! Check your JSON.")
        return

    logger.info(f"Dynamically matching {len(target_rows)} elite targets against the Time Machine...")

    con.execute(
        "CREATE TEMP TABLE targets (idx INTEGER, h_byr INTEGER, h_bpl INTEGER, h_fbpl INTEGER, h_mbpl INTEGER, w_byr INTEGER, w_bpl INTEGER, w_fbpl INTEGER, w_mbpl INTEGER)")
    con.executemany("INSERT INTO targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", target_rows)

    bpl_filter_str = ", ".join(map(str, global_bpl_codes))

    con.execute(
        "CREATE TEMP TABLE couple_members AS SELECT head_histid AS histid FROM tm_families UNION SELECT spouse_histid AS histid FROM tm_families WHERE spouse_histid IS NOT NULL")

    con.execute(f"""
        CREATE TEMP TABLE relevant_individuals AS
        WITH parsed_inds AS (
            SELECT i.*,
                   TRY_CAST(i.birthyr AS INTEGER) AS birthyr_int,
                   CASE WHEN TRY_CAST(i.bpld AS INTEGER) >= 1000 THEN TRY_CAST(i.bpld AS INTEGER) // 100 ELSE TRY_CAST(i.bpld AS INTEGER) END AS base_bpl,
                   CASE WHEN TRY_CAST(i.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.fbpl AS INTEGER) // 100 ELSE TRY_CAST(i.fbpl AS INTEGER) END AS base_fbpl,
                   CASE WHEN TRY_CAST(i.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.mbpl AS INTEGER) // 100 ELSE TRY_CAST(i.mbpl AS INTEGER) END AS base_mbpl
            FROM tm_individuals i
            JOIN couple_members cm ON i.histid = cm.histid
            WHERE i.bpld IS NOT NULL AND i.bpld != ''
        )
        SELECT * FROM parsed_inds
        WHERE base_bpl IN ({bpl_filter_str})
          AND (TRY_CAST(year AS INTEGER) IN (1850, 1860, 1870) OR 
               (
                 (fbpl IS NULL OR fbpl = '' OR fbpl = '0' OR base_fbpl IN ({bpl_filter_str}))
                 AND (mbpl IS NULL OR mbpl = '' OR mbpl = '0' OR base_mbpl IN ({bpl_filter_str}))
               )
          );
    """)

    all_matches = con.execute(f"""
        SELECT 
            t.idx, f.family_id, f.year, f.countyicp, f.stateicp, f.head_histid, f.spouse_histid
        FROM tm_families f
        JOIN relevant_individuals h ON f.head_histid = h.histid
        JOIN relevant_individuals s ON f.spouse_histid = s.histid
        JOIN targets t
            ON h.base_bpl = t.h_bpl 
            AND s.base_bpl = t.w_bpl
            AND h.sex = '1' AND s.sex = '2'
            AND h.birthyr_int BETWEEN t.h_byr - {YEAR_WINDOW} AND t.h_byr + {YEAR_WINDOW}
            AND s.birthyr_int BETWEEN t.w_byr - {YEAR_WINDOW} AND t.w_byr + {YEAR_WINDOW}
            AND (TRY_CAST(f.year AS INTEGER) IN (1850, 1860, 1870) OR 
                 (
                    (t.h_fbpl = 0 OR h.fbpl IS NULL OR h.fbpl = '' OR h.fbpl = '0' OR h.base_fbpl = t.h_fbpl)
                    AND (t.h_mbpl = 0 OR h.mbpl IS NULL OR h.mbpl = '' OR h.mbpl = '0' OR h.base_mbpl = t.h_mbpl)
                    AND (t.w_fbpl = 0 OR s.fbpl IS NULL OR s.fbpl = '' OR s.fbpl = '0' OR s.base_fbpl = t.w_fbpl)
                    AND (t.w_mbpl = 0 OR s.mbpl IS NULL OR s.mbpl = '' OR s.mbpl = '0' OR s.base_mbpl = t.w_mbpl)
                 )
            )
    """).fetchall()

    vip_fids = set()
    resolved_names_dict = {}

    for match in all_matches:
        t_idx, fid, yr, cty, st, h_histid, s_histid = match
        g_data = gedcom_couples[t_idx]
        h_res = g_data.get(f'h_res_{yr}', '')

        db_state_name = STATEICP_MAP.get(int(float(st)), "Unknown State") if st is not None else "Unknown State"
        try:
            db_county_code = str(int(float(cty)))
        except (ValueError, TypeError):
            db_county_code = str(cty).strip()
        db_county_name = county_names_dict.get(db_state_name, {}).get(db_county_code, "Unknown County")

        geo_hit = False
        if db_county_name != "Unknown County":
            db_c_clean = db_county_name.upper().replace(" COUNTY", "").strip()
            g_res_clean = h_res.upper().replace(" COUNTY", "").replace(" CO.", "").strip()
            if db_c_clean and db_c_clean in g_res_clean:
                geo_hit = True

        # Geo Check: If the household exactly matches the demographics AND lived in the correct county, it's a VIP!
        if geo_hit:
            vip_fids.add(fid)
            resolved_names_dict[h_histid] = (g_data.get('h_first', ''), g_data.get('h_last', ''))
            resolved_names_dict[s_histid] = (g_data.get('w_first', ''), g_data.get('w_last', ''))

    logger.info(f"  -> Found {len(vip_fids)} perfectly verified Ancestry households.")

    # --- FILL THE REST OF THE LIMIT WITH PLACEHOLDER FAMILIES ---
    remaining_limit = max(0, FAMILY_EXPORT_LIMIT - len(vip_fids))
    if remaining_limit > 0:
        if vip_fids:
            con.execute("CREATE TEMP TABLE vip_tmp AS SELECT unnest(?) AS fid", [list(vip_fids)])
            extra_fids = con.execute(
                f"SELECT family_id FROM tm_families WHERE family_id NOT IN (SELECT fid FROM vip_tmp) LIMIT {remaining_limit}").fetchall()
        else:
            extra_fids = con.execute(f"SELECT family_id FROM tm_families LIMIT {remaining_limit}").fetchall()

        for r in extra_fids:
            vip_fids.add(r[0])

    target_families = list(vip_fids)
    logger.info(f"  -> Extracting {len(target_families):,} total families for GEDCOM export...")

    individuals_data = []
    families_data = []

    if target_families:
        con.execute("CREATE TEMP TABLE target_fids_tmp AS SELECT unnest(?) AS fid", [target_families])

        individuals_data = con.execute("""
                                       SELECT i.histid, i.first_name, i.last_name, i.sex, i.birthyr, i.bpld, i.family_id
                                       FROM tm_individuals i
                                                JOIN target_fids_tmp t ON i.family_id = t.fid
                                       """).fetchall()

        families_data = con.execute("""
                                    SELECT f.family_id, f.head_histid, f.spouse_histid, f.year, f.countyicp, f.stateicp
                                    FROM tm_families f
                                             JOIN target_fids_tmp t ON f.family_id = t.fid
                                    """).fetchall()

    con.close()

    if not individuals_data:
        logger.error(f"No individuals found for the target families in the Time Machine.")
        return

    logger.info(f"Found {len(individuals_data):,} individuals. Building GEDCOM...")

    fam_locs = {}
    histid_to_entity = {}
    clans = {}

    for fam in families_data:
        fid, hid, sid, yr, cty, st = fam
        fam_locs[fid] = (yr, cty, st)
        clans[fid] = {'husb': f"{fid}_H", 'wife': f"{fid}_W", 'children': set()}

        if hid: histid_to_entity[hid] = f"{fid}_H"
        if sid: histid_to_entity[sid] = f"{fid}_W"

    entities = {}

    for ind in individuals_data:
        histid, fname, lname, sex, byr, bpld, fam_id = ind

        # --- REAL NAME INJECTION ---
        is_real = False
        if histid in resolved_names_dict:
            res_f, res_l = resolved_names_dict[histid]
            if res_f: fname = res_f
            if res_l: lname = res_l
            is_real = True

        ent_id = histid_to_entity.get(histid)
        if not ent_id:
            # Child logic: Every child gets a unique ID linked strictly to this household.
            ent_id = f"{fam_id}_C_{histid}"
            histid_to_entity[histid] = ent_id
            clans[fam_id]['children'].add(ent_id)

        entities[ent_id] = {
            'fname': fname, 'lname': lname, 'sex': sex,
            'byr': byr, 'bpld': bpld, 'census': set(),
            'is_real_name': is_real,
            'fam_id': fam_id, 'is_child': '_C_' in ent_id
        }

        if fam_id in fam_locs:
            yr, cty, st = fam_locs[fam_id]
            if yr:
                entities[ent_id]['census'].add((yr, cty, st))

    # --- SYNTHETIC SURNAME PROPAGATION ---
    clan_surnames = {}
    for fid in clans.keys():
        try:
            clan_surnames[fid] = NameList.getNextSurname()
        except AttributeError:
            clan_surnames[fid] = "BosselStink"

    indi_map = {}
    fam_map = {}

    def get_i(ent_id):
        if not ent_id: return ""
        if ent_id not in indi_map: indi_map[ent_id] = len(indi_map) + 1
        return indi_map[ent_id]

    def get_f(fam_id):
        if not fam_id: return ""
        if fam_id not in fam_map: fam_map[fam_id] = len(fam_map) + 1
        return fam_map[fam_id]

    with open(OUTPUT_GEDCOM, 'w', encoding='utf-8') as f:
        f.write("0 HEAD\n1 SOUR Census_Architecture\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n")
        f.write("0 @S1@ SOUR\n1 TITL United States Federal Census\n")

        cnt = 0
        for ent_id, props in entities.items():
            i_seq = get_i(ent_id)
            f.write(f"0 @I{i_seq}@ INDI\n")

            fam_id = props['fam_id']
            fname_clean = str(props['fname']).strip() if props['fname'] else ""
            lname_clean = str(props['lname']).strip() if props['lname'] else ""

            if not props.get('is_real_name'):
                if str(props['sex']).strip() == '1':
                    try:
                        fname_clean = NameList.getNextMale()
                    except AttributeError:
                        fname_clean = ""
                else:
                    try:
                        fname_clean = NameList.getNextFemale()
                    except AttributeError:
                        fname_clean = ""

                if not fname_clean or fname_clean.lower() in ['none', 'unknown']:
                    cnt += 1
                    fname_clean = f"Future {cnt}"

                target_lname = clan_surnames[fam_id]
                if not lname_clean or lname_clean.lower() in ['none', 'unknown', 'bosselstink']:
                    lname_clean = target_lname
            else:
                if not fname_clean: fname_clean = "Unknown"
                if not lname_clean: lname_clean = "Unknown"

            f.write(f"1 NAME {fname_clean} /{lname_clean}/\n")
            sex_val = str(props['sex'])
            f.write(f"1 SEX {'M' if sex_val == '1' else 'F' if sex_val == '2' else 'U'}\n")

            if props['byr']:
                f.write(f"1 BIRT\n2 DATE {props['byr']}\n")
                state_name = decode_bpld(props['bpld'])
                if state_name != "Unknown": f.write(f"2 PLAC {state_name}, USA\n")

            for (yr, cty, st) in sorted(list(props['census']), key=lambda x: x[0]):
                f.write(f"1 RESI\n2 DATE {yr}\n")

                try:
                    st_int = int(float(st))
                except (ValueError, TypeError):
                    st_int = 0
                st_name = STATEICP_MAP.get(st_int, "Unknown")

                if st_name != "Unknown":
                    try:
                        cty_code = str(int(float(cty)))
                    except (ValueError, TypeError):
                        cty_code = str(cty).strip()

                    county_name = county_names_dict.get(st_name, {}).get(cty_code, "")
                    plac_str = f"{county_name}, {st_name}" if county_name else f"{st_name}"

                    f.write(f"2 PLAC {plac_str}, USA\n")
                    f.write(f"2 SOUR @S1@\n")
                    f.write(f"3 PAGE Year: {yr}; Census Place: {plac_str};\n")

            if props['is_child']:
                f.write(f"1 FAMC @F{get_f(fam_id)}@\n")
            else:
                f.write(f"1 FAMS @F{get_f(fam_id)}@\n")

        for fam_id, c_props in clans.items():
            f_seq = get_f(fam_id)
            f.write(f"0 @F{f_seq}@ FAM\n")
            if c_props['husb'] in entities:
                f.write(f"1 HUSB @I{get_i(c_props['husb'])}@\n")
            if c_props['wife'] in entities:
                f.write(f"1 WIFE @I{get_i(c_props['wife'])}@\n")

            for child_id in sorted(list(c_props['children'])):
                if child_id in entities:
                    f.write(f"1 CHIL @I{get_i(child_id)}@\n")

        f.write("0 TRLR\n")

    logger.info(f"SUCCESS! Your Census-Level GEDCOM is ready: {OUTPUT_GEDCOM}")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="EXPORT_GEDCOM")
    export_gedcom(main_logger)
