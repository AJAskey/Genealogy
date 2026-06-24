"""
-----------------------------------
File: ExportCensusToGedcom.py

Summary: Generates a standard .ged family tree file directly from the
         relational census data in the Named Vaults.
         It automatically propagates the father's last name to his children
         before exporting, then generates "Census-level" GEDCOM structures.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0: http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sqlite3
import json
import sys
from utils import NameList

# Add the 'python' directory and project root to sys.path so we can import properly
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [script_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
TEST_VAULT_DIR = os.path.join(BASE_DATA_DIR, "TestVaults")
OUTPUT_GEDCOM = os.path.join(project_root, "gedcom_sources", "Census_Export_Askey.ged")
COUNTY_NAMES_JSON = os.path.join(project_root, "JSON", "county_codes_to_names.json")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
TARGET_LAST_NAME = 'Bosselstink'
CLAN_EXPORT_LIMIT = 20000  # Adjust this to safely control the size of your Ancestry upload

REVERSE_BPL = {
    1: "Alabama", 2: "Alaska", 4: "Arizona", 5: "Arkansas", 6: "California",
    8: "Colorado", 9: "Connecticut", 10: "Delaware", 11: "District of Columbia",
    12: "Florida", 13: "Georgia", 15: "Hawaii", 16: "Idaho", 17: "Illinois",
    18: "Indiana", 19: "Iowa", 20: "Kansas", 21: "Kentucky", 22: "Louisiana",
    23: "Maine", 24: "Maryland", 25: "Massachusetts", 26: "Michigan",
    27: "Minnesota", 28: "Mississippi", 29: "Missouri", 30: "Montana",
    31: "Nebraska", 32: "Nevada", 33: "New Hampshire", 34: "New Jersey",
    35: "New Mexico", 36: "New York", 37: "North Carolina", 38: "North Dakota",
    39: "Ohio", 40: "Oklahoma", 41: "Oregon", 42: "Pennsylvania", 44: "Rhode Island",
    45: "South Carolina", 46: "South Dakota", 47: "Tennessee", 48: "Texas",
    49: "Utah", 50: "Vermont", 51: "Virginia", 53: "Washington", 54: "West Virginia",
    55: "Wisconsin", 56: "Wyoming", 410: "England", 411: "Scotland", 412: "Wales",
    414: "Ireland", 413: "Northern Ireland", 453: "Germany", 404: "Sweden", 401: "Norway",
    400: "Denmark", 425: "Netherlands", 421: "France", 426: "Switzerland", 150: "Canada",
    200: "Mexico", 501: "Japan", 502: "South Korea",
    # Catch anomalous IPUMS STATEICP codes (e.g. 67 = Utah) that sneaked into the dataset
    14: "Pennsylvania", 61: "Arizona", 62: "Colorado", 63: "Idaho", 64: "Montana",
    65: "Nevada", 66: "New Mexico", 67: "Utah", 68: "Wyoming",
    71: "California", 72: "Oregon", 73: "Washington"
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


def decode_bpld(bpld_str):
    if not bpld_str or str(bpld_str).strip() == '': return "Unknown"
    try:
        val = int(float(bpld_str))
        prefix = val // 100 if val >= 1000 else val
        return REVERSE_BPL.get(prefix, "Unknown")
    except (ValueError, TypeError):
        return "Unknown"


def export_gedcom(logger):
    logger.info("Extracting the deepest, longest Clan lines from the Time Machine...")

    county_names_dict = {}
    if os.path.exists(COUNTY_NAMES_JSON):
        with open(COUNTY_NAMES_JSON, 'r', encoding='utf-8') as f:
            county_names_dict = json.load(f)

    individuals_data = []
    families_data = []

    # Step 1: Secure VIP Passes for Real Families, then find Longest Lines
    target_clans = set()
    family_to_clan = {}
    target_families = []
    resolved_names_dict = {}
    
    if os.path.exists(MATCH_DB):
        with sqlite3.connect(MATCH_DB) as m_conn:
            m_cur = m_conn.cursor()

            try:
                m_cur.execute("SELECT histid, first_name, last_name FROM resolved_names")
                for r in m_cur.fetchall():
                    resolved_names_dict[r[0]] = (r[1], r[2])
                logger.info(f"  -> Loaded {len(resolved_names_dict):,} resolved real names from the Time Machine.")
            except sqlite3.OperationalError:
                logger.info("  -> No resolved_names table found yet. Will use synthetic names.")

        # --- VIP PASS: Ensure real families are ALWAYS exported ---
        if resolved_names_dict:
            logger.info("  -> Securing VIP passes for all resolved real families...")
            resolved_histids = list(resolved_names_dict.keys())
            vip_family_ids = set()

            for filename in os.listdir(YEARLY_VAULT_DIR):
                if filename.startswith("YearVault_") and filename.endswith(".db"):
                    db_path = os.path.join(YEARLY_VAULT_DIR, filename)
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("CREATE TEMP TABLE IF NOT EXISTS temp_res (histid TEXT)")
                        cursor.execute("DELETE FROM temp_res")
                        cursor.executemany("INSERT INTO temp_res VALUES (?)", [(h,) for h in resolved_histids])

                        cursor.execute("""
                            SELECT f.family_id FROM families f
                            INNER JOIN temp_res t ON f.head_histid = t.histid OR f.spouse_histid = t.histid
                        """)
                        for r in cursor.fetchall():
                            vip_family_ids.add(r[0])

            if vip_family_ids:
                with sqlite3.connect(MATCH_DB) as m_conn:
                    m_cur = m_conn.cursor()
                    m_cur.execute("CREATE TEMP TABLE IF NOT EXISTS temp_vip_fids (family_id TEXT)")
                    m_cur.execute("DELETE FROM temp_vip_fids")
                    m_cur.executemany("INSERT INTO temp_vip_fids VALUES (?)", [(f,) for f in vip_family_ids])
                    
                    m_cur.execute("""
                        SELECT clan_id FROM clan_mapping
                        WHERE family_id IN (SELECT family_id FROM temp_vip_fids)
                    """)
                    for r in m_cur.fetchall():
                        target_clans.add(r[0])

            logger.info(f"  -> VIP Pass granted to {len(target_clans)} distinct real Clans.")

        # --- FILL THE REST OF THE LIMIT WITH THE DEEPEST PLACEHOLDER CLANS ---
        remaining_limit = max(0, CLAN_EXPORT_LIMIT - len(target_clans))
        with sqlite3.connect(MATCH_DB) as m_conn:
            m_cur = m_conn.cursor()
            if remaining_limit > 0:
                if target_clans:
                    m_cur.execute("CREATE TEMP TABLE IF NOT EXISTS temp_target_clans (clan_id TEXT)")
                    m_cur.execute("DELETE FROM temp_target_clans")
                    m_cur.executemany("INSERT INTO temp_target_clans VALUES (?)", [(c,) for c in target_clans])
                    
                    m_cur.execute(f"""
                        SELECT clan_id FROM clan_mapping 
                        WHERE clan_id NOT IN (SELECT clan_id FROM temp_target_clans) 
                        GROUP BY clan_id 
                        ORDER BY COUNT(*) DESC 
                        LIMIT {remaining_limit}
                    """)
                else:
                    m_cur.execute(f"SELECT clan_id FROM clan_mapping GROUP BY clan_id ORDER BY COUNT(*) DESC LIMIT {remaining_limit}")

                for r in m_cur.fetchall():
                    target_clans.add(r[0])

            if target_clans:
                m_cur.execute("CREATE TEMP TABLE IF NOT EXISTS final_clans (clan_id TEXT)")
                m_cur.execute("DELETE FROM final_clans")
                m_cur.executemany("INSERT INTO final_clans VALUES (?)", [(c,) for c in target_clans])
                
                m_cur.execute("""
                    SELECT family_id, clan_id FROM clan_mapping 
                    WHERE clan_id IN (SELECT clan_id FROM final_clans)
                """)
                for r in m_cur.fetchall():
                    family_to_clan[r[0]] = r[1]
                    
                target_families = list(family_to_clan.keys())

        logger.info(f"  -> Total selected Clans: {len(target_clans):,}, containing {len(target_families):,} total families.")
    else:
        logger.error(f"Could not find Match DB at {MATCH_DB}")
        return

    for filename in os.listdir(YEARLY_VAULT_DIR):
        if filename.startswith("YearVault_") and filename.endswith(".db"):
            db_path = os.path.join(YEARLY_VAULT_DIR, filename)
            logger.info(f"  -> Processing {filename}...")
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                if target_families:
                    # Bypass SQLite variable limits and force EXACTLY ONE table scan by using a TEMP TABLE
                    cursor.execute("CREATE TEMP TABLE IF NOT EXISTS temp_targets (family_id TEXT)")
                    cursor.execute("DELETE FROM temp_targets")
                    cursor.executemany("INSERT INTO temp_targets (family_id) VALUES (?)",
                                       [(str(f),) for f in target_families])

                    cursor.execute("""
                                   SELECT i.histid,
                                          i.first_name,
                                          i.last_name,
                                          i.sex,
                                          i.birthyr,
                                          i.bpld,
                                          i.family_id,
                                          i.father_histid,
                                          i.mother_histid
                                   FROM individuals i
                                            INNER JOIN temp_targets t ON i.family_id = t.family_id
                                   """)
                    individuals_data.extend(cursor.fetchall())

                    cursor.execute("""
                                   SELECT f.family_id, f.head_histid, f.spouse_histid, f.year, f.countyicp, f.stateicp
                                   FROM families f
                                            INNER JOIN temp_targets t ON f.family_id = t.family_id
                                   """)
                    families_data.extend(cursor.fetchall())

    if not individuals_data:
        logger.warning("No families found to export!")
        return

    logger.info(f"Found {len(individuals_data):,} individuals across all decades. Building GEDCOM...")

    # Execute Name Ripple in Python (respecting read-only ground truth)
    mutable_inds = [list(ind) for ind in individuals_data]
    ind_dict = {ind[0]: ind for ind in mutable_inds}
    for ind in mutable_inds:
        histid, fname, lname, sex, byr, bpld, fam_id, f_id, m_id = ind
        if lname and str(lname).strip().lower() == 'bosselstink' and f_id and f_id in ind_dict:
            father_lname = ind_dict[f_id][2]
            if father_lname and str(father_lname).strip().lower() != 'bosselstink':
                ind[2] = father_lname

    individuals_data = mutable_inds

    # Step 3: Consolidate Decade Snapshots into Unified Clan Entities
    fam_locs = {}
    histid_to_entity = {}
    clans = {}

    for fam in families_data:
        fid, hid, sid, yr, cty, st = fam
        clan_id = family_to_clan.get(fid)
        if not clan_id: continue

        fam_locs[fid] = (yr, cty, st)

        if clan_id not in clans:
            clans[clan_id] = {'husb': f"{clan_id}_H", 'wife': f"{clan_id}_W", 'children': set()}

        if hid: histid_to_entity[hid] = f"{clan_id}_H"
        if sid: histid_to_entity[sid] = f"{clan_id}_W"

    entities = {}
    child_entities = {}

    for ind in individuals_data:
        histid, fname, lname, sex, byr, bpld, fam_id, f_id, m_id = ind
        clan_id = family_to_clan.get(fam_id)
        if not clan_id: continue
        
        # --- REAL NAME INJECTION ---
        is_real = False
        if histid in resolved_names_dict:
            res_f, res_l = resolved_names_dict[histid]
            if res_f: fname = res_f
            if res_l: lname = res_l
            is_real = True

        ent_id = histid_to_entity.get(histid)
        if not ent_id:
            # Group Children across decades using a First Name + Birth Year heuristic
            clean_fname = str(fname).upper().strip().replace(' ', '_')
            try:
                byr_int = int(str(byr).strip())
            except ValueError:
                byr_int = 0

            if clan_id not in child_entities:
                child_entities[clan_id] = []

            matched_ent_id = None
            for existing in child_entities[clan_id]:
                if existing['fname'] == clean_fname:
                    # Allow a 3 year variance for census age drifting
                    if existing['byr'] == 0 or byr_int == 0 or abs(existing['byr'] - byr_int) <= 3:
                        matched_ent_id = existing['ent_id']
                        break

            if matched_ent_id:
                ent_id = matched_ent_id
            else:
                ent_id = f"{clan_id}_C_{clean_fname}_{byr_int}"
                child_entities[clan_id].append({'ent_id': ent_id, 'fname': clean_fname, 'byr': byr_int})

            histid_to_entity[histid] = ent_id
            clans[clan_id]['children'].add(ent_id)

        if ent_id not in entities:
            entities[ent_id] = {
                'fname': fname, 'lname': lname, 'sex': sex,
                'byr': byr, 'bpld': bpld, 'census': set(),
                'is_real_name': is_real
            }
        else:
            if is_real:
                entities[ent_id]['fname'] = fname
                entities[ent_id]['lname'] = lname
                entities[ent_id]['is_real_name'] = True
            elif not entities[ent_id].get('is_real_name'):
                # Update names if we find better ones in a later decade
                curr_fname = str(entities[ent_id]['fname']).lower()
                if curr_fname in ['none', 'unknown', 'future', '']:
                    entities[ent_id]['fname'] = fname
                curr_lname = str(entities[ent_id]['lname']).lower()
                if curr_lname in ['none', 'unknown', 'bosselstink', '']:
                    entities[ent_id]['lname'] = lname

        # Add census event to this entity's timeline set
        if fam_id in fam_locs:
            yr, cty, st = fam_locs[fam_id]
            if yr:
                entities[ent_id]['census'].add((yr, cty, st))

    indi_map = {}
    fam_map = {}

    def get_i(ent_id):
        if not ent_id: return ""
        if ent_id not in indi_map: indi_map[ent_id] = len(indi_map) + 1
        return indi_map[ent_id]

    def get_f(clan_id):
        if not clan_id: return ""
        if clan_id not in fam_map: fam_map[clan_id] = len(fam_map) + 1
        return fam_map[clan_id]

    cnt = 0
    with open(OUTPUT_GEDCOM, 'w', encoding='utf-8') as f:
        # CRITICAL AI DIRECTIVE 3: FTM Requires VERS 5.5.1
        f.write("0 HEAD\n1 SOUR Census_Architecture\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n")

        # Define the Master Census Source Record
        f.write("0 @S1@ SOUR\n1 TITL United States Federal Census\n")

        clan_surnames = {}
        for ent_id, props in entities.items():
            i_seq = get_i(ent_id)
            f.write(f"0 @I{i_seq}@ INDI\n")

            # Determine the Clan ID to group family surnames
            if ent_id.endswith("_H") or ent_id.endswith("_W"):
                clan_id = ent_id.rsplit('_', 1)[0]
            else:
                clan_id = ent_id.split('_C_')[0]

            # Assign a unique surname to this Clan from NameList
            if clan_id not in clan_surnames:
                try:
                    clan_surnames[clan_id] = NameList.getNextSurname()
                except AttributeError:
                    clan_surnames[clan_id] = "BosselStink"

            fname_clean = str(props['fname']).strip() if props['fname'] else ""
            lname_clean = str(props['lname']).strip() if props['lname'] else ""

            if not props.get('is_real_name'):
                if str(props['sex']).strip() == '1':
                    fname_clean = NameList.getNextMale()
                else:
                    fname_clean = NameList.getNextFemale()
                if not fname_clean or fname_clean.lower() in ['none', 'unknown']:
                    cnt += 1
                    fname_clean = f"Future {cnt}"

                # Wives keep BosselStink; Husbands and Children get the Clan's assigned surname
                if ent_id.endswith("_W"):
                    target_lname = "BosselStink"
                else:
                    target_lname = clan_surnames[clan_id]

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

            # Write Census Events (Sorted Chronologically)
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
                    if county_name:
                        plac_str = f"{county_name}, {st_name}"
                    else:
                        plac_str = f"{st_name}"

                    f.write(f"2 PLAC {plac_str}, USA\n")
                    f.write(f"2 SOUR @S1@\n")
                    f.write(f"3 PAGE Year: {yr}; Census Place: {plac_str};\n")

            # Is it a parent or a child?
            if ent_id.endswith("_H") or ent_id.endswith("_W"):
                f.write(f"1 FAMS @F{get_f(clan_id)}@\n")
            else:
                f.write(f"1 FAMC @F{get_f(clan_id)}@\n")

        for clan_id, c_props in clans.items():
            f_seq = get_f(clan_id)
            f.write(f"0 @F{f_seq}@ FAM\n")
            if c_props['husb'] in entities:
                f.write(f"1 HUSB @I{get_i(c_props['husb'])}@\n")
            if c_props['wife'] in entities:
                f.write(f"1 WIFE @I{get_i(c_props['wife'])}@\n")

            for child_id in sorted(list(c_props['children'])):
                if child_id in entities:
                    f.write(f"1 CHIL @I{get_i(child_id)}@\n")

        f.write("0 TRLR\n")

    logger.info(f"\nSUCCESS! Your Census-Level GEDCOM is ready: {OUTPUT_GEDCOM}")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="EXPORT_GEDCOM")

    export_gedcom(main_logger)
