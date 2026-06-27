"""
File: ExportCensusToGedcom.py
Summary: Extracts historical census data into a fully compliant GEDCOM file.
         Reads 'resolved_vips' to perfectly merge identical ancestors across decades,
         creating deep, true inter-generational family trees.
"""
import os
import duckdb
import sys
import json

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path: sys.path.insert(0, project_root)
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path: sys.path.insert(0, python_dir)

import gen_logging

try:
    from utils import NameList
except ImportError:
    NameList = None

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

OUTPUT_GEDCOM = os.path.join(project_root, "gedcom_sources", "Census_Export_Askey.ged")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches2.db")
COUNTY_NAMES_JSON = os.path.join(project_root, "JSON", "county_codes_to_names.json")

FAMILY_EXPORT_LIMIT = 20000

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
    47: "District of Columbia", 48: "Maryland", 51: "Kentucky", 52: "Tennessee", 53: "Alabama", 54: "Mississippi",
    61: "Arkansas", 62: "Louisiana", 63: "Oklahoma", 64: "Texas",
    71: "Montana", 72: "Idaho", 73: "Wyoming", 74: "Colorado", 75: "New Mexico", 76: "Arizona", 77: "Utah",
    78: "Nevada",
    81: "Washington", 82: "Oregon", 83: "California", 84: "Alaska", 85: "Hawaii"
}


def decode_bpld(bpld_str):
    if not bpld_str or str(bpld_str).strip() == '': return "Unknown"
    try:
        val = int(float(bpld_str))
        prefix = val // 100 if val >= 1000 else val
        return REVERSE_BPL.get(prefix, "Unknown")
    except (ValueError, TypeError):
        return "Unknown"


def export_gedcom(logger):
    logger.info("Initializing The Tree Weaver Exporter...")
    if not os.path.exists(MATCH_DB):
        logger.error(f"Could not find Match DB at {MATCH_DB}")
        return

    con = duckdb.connect(MATCH_DB, read_only=True)

    county_names_dict = {}
    if os.path.exists(COUNTY_NAMES_JSON):
        with open(COUNTY_NAMES_JSON, 'r', encoding='utf-8') as f:
            county_names_dict = json.load(f)

    logger.info("Reading VIP targets from Time Machine...")
    try:
        vips_raw = con.execute("SELECT histid, target_idx, role, first_name, last_name FROM resolved_vips").fetchall()
    except duckdb.CatalogException:
        vips_raw = []

    if not vips_raw:
        logger.error("No VIPs found. Run GedcomNameOverlay_V3_FINAL.py first!")
        return

    # Map histids to their Target IDs so we can merge them across decades
    histid_to_vip = {}
    for r in vips_raw:
        histid_to_vip[r[0]] = {'t_idx': r[1], 'role': r[2], 'fname': r[3], 'lname': r[4]}

    # Pull the exact households that belong to our VIP targets
    vip_histids = list(histid_to_vip.keys())
    con.execute("CREATE TEMP TABLE vip_ids AS SELECT unnest(?) AS hid", [vip_histids])

    logger.info("Pulling family records...")
    families_data = con.execute("""
                                SELECT family_id, head_histid, spouse_histid, year, countyicp, stateicp
                                FROM tm_families
                                WHERE head_histid IN (SELECT hid FROM vip_ids)
                                   OR spouse_histid IN (SELECT hid FROM vip_ids)
                                """).fetchall()

    vip_fids = [f[0] for f in families_data]

    # --- FILL THE REST OF THE LIMIT WITH PLACEHOLDER FAMILIES ---
    remaining_limit = max(0, FAMILY_EXPORT_LIMIT - len(vip_fids))
    vip_fids_set = set(vip_fids)

    if remaining_limit > 0:
        if vip_fids:
            con.execute("CREATE TEMP TABLE vip_fids_tmp AS SELECT unnest(?) AS fid", [list(vip_fids_set)])
            extra_fids = con.execute(
                f"SELECT family_id FROM tm_families WHERE family_id NOT IN (SELECT fid FROM vip_fids_tmp) LIMIT {remaining_limit}").fetchall()
        else:
            extra_fids = con.execute(f"SELECT family_id FROM tm_families LIMIT {remaining_limit}").fetchall()

        for r in extra_fids:
            vip_fids_set.add(r[0])

    target_families = list(vip_fids_set)
    logger.info(f"  -> Extracting {len(target_families):,} total families for GEDCOM export...")

    con.execute("CREATE TEMP TABLE fam_ids AS SELECT unnest(?) AS fid", [target_families])

    logger.info("Pulling individual records...")
    individuals_data = con.execute("""
                                   SELECT histid, first_name, last_name, sex, birthyr, bpld, family_id
                                   FROM tm_individuals
                                   WHERE family_id IN (SELECT fid FROM fam_ids)
                                   """).fetchall()
    con.close()

    logger.info(f"Found {len(individuals_data):,} individuals. Weaving inter-generational GEDCOM tree...")

    entities = {}  # Holds INDI records
    families = {}  # Holds FAM records
    fam_locs = {}

    # Build families. If they belong to a target, group them by Target ID to merge across decades!
    for fam in families_data:
        fid, hid, sid, yr, cty, st = fam
        fam_locs[fid] = (yr, cty, st)

        t_idx = None
        if hid in histid_to_vip:
            t_idx = histid_to_vip[hid]['t_idx']
        elif sid in histid_to_vip:
            t_idx = histid_to_vip[sid]['t_idx']

        fam_key = f"T_{t_idx}" if t_idx is not None else f"F_{fid}"

        if fam_key not in families:
            families[fam_key] = {'husb': None, 'wife': None, 'children': set()}

        h_ent = f"T_{t_idx}_H" if t_idx is not None else f"I_{hid}" if hid else None
        w_ent = f"T_{t_idx}_W" if t_idx is not None else f"I_{sid}" if sid else None

        if h_ent: families[fam_key]['husb'] = h_ent
        if w_ent: families[fam_key]['wife'] = w_ent

    # Process individuals
    for ind in individuals_data:
        histid, fname, lname, sex, byr, bpld, fam_id = ind

        t_idx = None
        if histid in histid_to_vip:
            vip = histid_to_vip[histid]
            t_idx = vip['t_idx']
            ent_id = f"T_{t_idx}_{vip['role']}"
        else:
            ent_id = f"I_{histid}"

        fam_key = f"T_{t_idx}" if t_idx is not None else f"F_{fam_id}"

        # Assign child to the merged family unit
        if ent_id != families[fam_key].get('husb') and ent_id != families[fam_key].get('wife'):
            families[fam_key]['children'].add(ent_id)

        if ent_id not in entities:
            entities[ent_id] = {'fname': fname, 'lname': lname, 'sex': sex, 'byr': byr, 'bpld': bpld, 'census': set(),
                                'fams': set(), 'famc': set()}

        if histid in histid_to_vip:
            entities[ent_id]['fname'] = histid_to_vip[histid]['fname']
            entities[ent_id]['lname'] = histid_to_vip[histid]['lname']
            entities[ent_id]['is_real_name'] = True

        if fam_id in fam_locs:
            entities[ent_id]['census'].add(fam_locs[fam_id])

        if ent_id == families[fam_key].get('husb') or ent_id == families[fam_key].get('wife'):
            entities[ent_id]['fams'].add(fam_key)
        else:
            entities[ent_id]['famc'].add(fam_key)

    # --- SYNTHETIC SURNAME PROPAGATION ---
    clan_surnames = {}
    for fid in families.keys():
        try:
            clan_surnames[fid] = NameList.getNextSurname() if NameList else "BosselStink"
        except AttributeError:
            clan_surnames[fid] = "BosselStink"

    # Write GEDCOM
    indi_map = {}
    fam_map = {}

    def get_i(ent_id):
        if ent_id not in indi_map: indi_map[ent_id] = len(indi_map) + 1
        return indi_map[ent_id]

    def get_f(fam_id):
        if fam_id not in fam_map: fam_map[fam_id] = len(fam_map) + 1
        return fam_map[fam_id]

    with open(OUTPUT_GEDCOM, 'w', encoding='utf-8') as f:
        f.write("0 HEAD\n1 SOUR Census_Architecture\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n")
        f.write("0 @S1@ SOUR\n1 TITL United States Federal Census\n")

        cnt = 0
        for ent_id, props in entities.items():
            f.write(f"0 @I{get_i(ent_id)}@ INDI\n")

            # Determine synthetic name or real name
            fname_clean = str(props['fname']).strip() if props['fname'] else ""
            lname_clean = str(props['lname']).strip() if props['lname'] else ""

            if not props.get('is_real_name'):
                fam_id = sorted(list(props['fams']))[0] if props['fams'] else sorted(list(props['famc']))[0] if props[
                    'famc'] else None
                if str(props['sex']).strip() == '1':
                    try:
                        fname_clean = NameList.getNextMale() if NameList else "Unknown"
                    except AttributeError:
                        fname_clean = "Unknown"
                else:
                    try:
                        fname_clean = NameList.getNextFemale() if NameList else "Unknown"
                    except AttributeError:
                        fname_clean = "Unknown"

                if not fname_clean or fname_clean.lower() in ['none', 'unknown']:
                    cnt += 1
                    fname_clean = f"Future {cnt}"

                target_lname = clan_surnames.get(fam_id, "BosselStink")
                if not lname_clean or lname_clean.lower() in ['none', 'unknown', 'bosselstink']:
                    lname_clean = target_lname
            else:
                if not fname_clean: fname_clean = "Unknown"
                if not lname_clean: lname_clean = "Unknown"

            f.write(f"1 NAME {fname_clean} /{lname_clean}/\n")
            sex_val = str(props['sex'])
            f.write(f"1 SEX {'M' if sex_val == '1' else 'F' if sex_val == '2' else 'U'}\n")
            if props['byr']: f.write(f"1 BIRT\n2 DATE {props['byr']}\n")

            state_name = decode_bpld(props['bpld'])
            if state_name != "Unknown": f.write(f"2 PLAC {state_name}, USA\n")

            for (yr, cty, st) in sorted(list(props['census']), key=lambda x: x[0]):
                f.write(f"1 RESI\n2 DATE {yr}\n2 SOUR @S1@\n")
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
                    f.write(f"3 PAGE Year: {yr}; Census Place: {plac_str};\n")

            for cid in sorted(list(props['famc'])): f.write(f"1 FAMC @F{get_f(cid)}@\n")
            for cid in sorted(list(props['fams'])): f.write(f"1 FAMS @F{get_f(cid)}@\n")

        for fam_id, c_props in families.items():
            f.write(f"0 @F{get_f(fam_id)}@ FAM\n")
            if c_props['husb'] in entities: f.write(f"1 HUSB @I{get_i(c_props['husb'])}@\n")
            if c_props['wife'] in entities: f.write(f"1 WIFE @I{get_i(c_props['wife'])}@\n")
            for child_id in sorted(list(c_props['children'])):
                if child_id in entities: f.write(f"1 CHIL @I{get_i(child_id)}@\n")

        f.write("0 TRLR\n")

    logger.info(f"SUCCESS! Your Inter-Generational GEDCOM is ready: {OUTPUT_GEDCOM}")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="EXPORT_GEDCOM")
    export_gedcom(main_logger)
