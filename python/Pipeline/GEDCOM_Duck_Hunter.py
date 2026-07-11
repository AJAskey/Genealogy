"""
File: GEDCOM_Duck_Hunter.py
Summary: Reads a personal GEDCOM file, extracts your family members, and
         hunts the DuckDB Vault for matching census records and HIKs.
"""

import duckdb
import os
import re
import logging
import gen_logging

# LOG_FILE = r"E:\Users\Andy\PycharmProjects\Genealogy\output\Duck_Hunter.log"
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(message)s',
#     filename=LOG_FILE,
#     filemode='w'
# )
# print(f"Hunting ducks... All output is being saved to: {LOG_FILE}")

# --- CONFIGURATION ---
# Point this to the GEDCOM file that has your family tree in it
INPUT_GEDCOM = r"E:\Users\Andy\PycharmProjects\Genealogy\design\WilliamAskey_Project.ged"
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Test_DuckDB_Vault.db"
CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"


def get_core_location(plac_str):
    """Extracts the state or primary region from a GEDCOM place string."""
    if not plac_str or plac_str == "Unknown": return ""
    parts = [p.strip() for p in plac_str.split(',')]
    if len(parts) >= 2 and parts[-1].upper() in ('USA', 'UNITED STATES'):
        return parts[-2]
    return parts[-1] if parts else ""


def parse_advanced_gedcom(filepath):
    if not os.path.exists(filepath):
        logging.info(f"Waiting for your GEDCOM file at: {filepath}")
        return []

    logging.info(f"Parsing Advanced GEDCOM Relationships: {filepath}...")
    individuals = {}
    families = {}

    current_id = None
    current_type = None
    in_birt_block = False

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line: continue

            parts = line.split(' ', 2)
            level = parts[0]
            tag = parts[1] if len(parts) > 1 else ""
            val = parts[2] if len(parts) > 2 else ""

            if level == '0':
                in_birt_block = False
                if len(parts) == 3 and parts[2] in ('INDI', 'FAM'):
                    current_id = parts[1]
                    current_type = parts[2]
                    if current_type == 'INDI':
                        individuals[current_id] = {
                            'id': current_id, 'first_name': '', 'last_name': '',
                            'birthyr': '', 'birthplac': '', 'famc': [], 'fams': []
                        }
                    elif current_type == 'FAM':
                        families[current_id] = {'husb': None, 'wife': None, 'chil': []}
                else:
                    current_type = None

            elif level == '1' and current_type == 'INDI':
                in_birt_block = False
                if tag == 'NAME':
                    name_match = re.search(r'(.*?) /(.*?)/', val)
                    if name_match:
                        individuals[current_id]['first_name'] = name_match.group(1).strip()
                        individuals[current_id]['last_name'] = name_match.group(2).strip()
                    else:
                        individuals[current_id]['first_name'] = val.replace('/', '').strip()
                elif tag == 'BIRT':
                    in_birt_block = True
                elif tag == 'FAMC':
                    individuals[current_id]['famc'].append(val)
                elif tag == 'FAMS':
                    individuals[current_id]['fams'].append(val)

            elif level == '2' and current_type == 'INDI' and in_birt_block:
                if tag == 'DATE':
                    year_match = re.search(r'\b(1[789]\d{2}|20\d{2})\b', val)
                    if year_match:
                        individuals[current_id]['birthyr'] = year_match.group(1)
                elif tag == 'PLAC':
                    individuals[current_id]['birthplac'] = val

            elif level == '1' and current_type == 'FAM':
                in_birt_block = False
                if tag == 'HUSB':
                    families[current_id]['husb'] = val
                elif tag == 'WIFE':
                    families[current_id]['wife'] = val
                elif tag == 'CHIL':
                    families[current_id]['chil'].append(val)

    # --- RELATIONAL RESOLUTION PASS ---
    people_to_hunt = []
    for ind_id, ind in individuals.items():
        ind['father_birthplac'] = "Unknown"
        ind['mother_birthplac'] = "Unknown"
        ind['father_birthyr'] = "Unknown"
        ind['mother_birthyr'] = "Unknown"

        # Resolve Parents
        for famc_id in ind['famc']:
            fam = families.get(famc_id)
            if fam:
                if fam['husb'] and fam['husb'] in individuals:
                    ind['father_birthplac'] = individuals[fam['husb']]['birthplac'] or "Unknown"
                    ind['father_birthyr'] = individuals[fam['husb']]['birthyr'] or "Unknown"
                if fam['wife'] and fam['wife'] in individuals:
                    ind['mother_birthplac'] = individuals[fam['wife']]['birthplac'] or "Unknown"
                    ind['mother_birthyr'] = individuals[fam['wife']]['birthyr'] or "Unknown"

        # Resolve Children
        ind['children_list'] = []
        for fams_id in ind['fams']:
            fam = families.get(fams_id)
            if fam:
                for chil_id in fam['chil']:
                    if chil_id in individuals:
                        c = individuals[chil_id]
                        c_name = f"{c['first_name']} {c['last_name']}".strip()
                        c_yr = c['birthyr'] or "Unk"
                        ind['children_list'].append(f"{c_name} (b. {c_yr})")

        if ind['first_name'] or ind['last_name']:
            people_to_hunt.append(ind)

    return people_to_hunt


def hunt_in_duckdb(people):
    if not people:
        logging.info("No people found to hunt!")
        return

    logging.info(f"Connecting to Vault: {MASTER_VAULT_DB}...")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)
    con.execute(f"ATTACH '{CROSSWALK_DB}' AS cw (READ_ONLY);")

    logging.info("Building HIK Crosswalk (Time Machine)...")
    con.execute("""
                CREATE
                TEMP TABLE vault_hiks AS
        WITH all_histids AS (
            SELECT DISTINCT HISTID FROM individuals
        ),
        cw_unpivoted AS (
            SELECT TRIM(histid_1850) AS histid, HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1850)) > 5
            UNION ALL SELECT TRIM(histid_1860), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1860)) > 5
            UNION ALL SELECT TRIM(histid_1870), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1870)) > 5
            UNION ALL SELECT TRIM(histid_1880), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1880)) > 5
            UNION ALL SELECT TRIM(histid_1900), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1900)) > 5
            UNION ALL SELECT TRIM(histid_1910), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1910)) > 5
            UNION ALL SELECT TRIM(histid_1920), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1920)) > 5
            UNION ALL SELECT TRIM(histid_1930), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1930)) > 5
            UNION ALL SELECT TRIM(histid_1940), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1940)) > 5
            UNION ALL SELECT TRIM(histid_1950), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1950)) > 5
        )
                SELECT a.HISTID, COALESCE(c.HIK, a.HISTID) AS HIK
                FROM all_histids a
                         LEFT JOIN cw_unpivoted c ON UPPER(TRIM(a.HISTID)) = UPPER(c.histid);
                """)

    # --- DYNAMIC SCHEMA CHECK ---
    columns_info = con.execute("DESCRIBE individuals").fetchall()
    ind_cols = [c[0].upper() for c in columns_info]
    has_serial = 'SERIAL' in ind_cols
    has_fbpl = 'FBPL' in ind_cols
    has_mbpl = 'MBPL' in ind_cols

    logging.info(f"\n🎯 Hunting for {len(people)} people in the Vault...\n")

    for p in people:
        fname = p.get('first_name', '')
        lname = p.get('last_name', '')
        byear = p.get('birthyr')
        bplac = p.get('birthplac', 'Unknown')
        fbplac = p.get('father_birthplac', 'Unknown')
        mbplac = p.get('mother_birthplac', 'Unknown')
        fbyear = p.get('father_birthyr', 'Unknown')
        mbyear = p.get('mother_birthyr', 'Unknown')
        children = p.get('children_list', [])

        if not fname or not lname or not byear:
            continue

        logging.info(f"[{fname} {lname}] (Born: ~{byear} in {bplac})")
        logging.info(f"   > Father: b. {fbyear} in {fbplac} | Mother: b. {mbyear} in {mbplac}")
        if children:
            logging.info(f"   > Children: {', '.join(children[:4])}" + ("..." if len(children) > 4 else ""))

        # Skip people born after 1950 due to the 72-year census privacy rule
        if int(byear) > 1950:
            logging.info("   => Skipped: Census records are restricted for 72 years (1950 is the latest).")
            logging.info("-" * 50)
            continue

        # Skip people missing required birthplaces
        if not bplac or bplac == 'Unknown' or not fbplac or fbplac == 'Unknown' or not mbplac or mbplac == 'Unknown':
            logging.info("   => Skipped: Missing required birthplace fields (BPL, FBPL, MBPL).")
            logging.info("-" * 50)
            continue

        # Extract core location (e.g. "Arkansas") to match IPUMS database
        core_bpl = get_core_location(bplac)
        safe_bpl = core_bpl.replace("'", "''")
        core_fbpl = get_core_location(fbplac)
        core_mbpl = get_core_location(mbplac)

        expected_child_years = []
        for c in children:
            match = re.search(r'\(b\. (\d{4})\)', c)
            if match:
                expected_child_years.append(int(match.group(1)))

        select_clause = "v.HIK, MAX(i.NAMEFIRST), MAX(i.NAMELAST), MIN(i.BIRTHYR), i.YEAR, MAX(i.BPL)"
        select_clause += ", MAX(i.SERIAL)" if has_serial else ", '0'"
        select_clause += ", MAX(i.FBPL)" if has_fbpl else ", 'Unknown'"
        select_clause += ", MAX(i.MBPL)" if has_mbpl else ", 'Unknown'"

        query = f"""
            SELECT {select_clause}
            FROM individuals i
            JOIN vault_hiks v ON i.HISTID = v.HISTID
            WHERE TRY_CAST(i.BIRTHYR AS INTEGER) BETWEEN {int(byear) - 2} AND {int(byear) + 2}
        """

        if safe_bpl:
            query += f"              AND i.BPL ILIKE '%{safe_bpl}%'\n"

        query += """
            GROUP BY v.HIK, i.YEAR
            ORDER BY i.YEAR ASC
        """

        results = con.execute(query).fetchall()

        if results:
            logging.info(f"   => Found {len(results)} matching records!")
            for r in results:
                c_serial = r[6]
                c_fbpl = r[7]
                c_mbpl = r[8]
                score_notes = []

                if has_fbpl and core_fbpl and c_fbpl and core_fbpl.lower() in str(c_fbpl).lower():
                    score_notes.append("✓ Father BPL")
                if has_mbpl and core_mbpl and c_mbpl and core_mbpl.lower() in str(c_mbpl).lower():
                    score_notes.append("✓ Mother BPL")

                if has_serial and str(c_serial) != '0' and expected_child_years:
                    hh_query = f"SELECT TRY_CAST(BIRTHYR AS INTEGER) FROM individuals WHERE SERIAL = '{c_serial}' AND YEAR = {r[4]} AND TRY_CAST(BIRTHYR AS INTEGER) IS NOT NULL"
                    hh_members = [row[0] for row in con.execute(hh_query).fetchall()]
                    matched_kids = sum(
                        1 for e_cy in expected_child_years if any(abs(e_cy - h_by) <= 2 for h_by in hh_members))
                    if matched_kids > 0:
                        score_notes.append(f"✓ {matched_kids}/{len(expected_child_years)} Children")

                note_str = f"  -->  [{' | '.join(score_notes)}]" if score_notes else ""
                logging.info(f"      Census {r[4]}: {r[1]} {r[2]} (HIK: {r[0]}){note_str}")
        else:
            logging.info("   => No matches found in the Vault.")
        logging.info("-" * 50)


if __name__ == "__main__":
    logging = gen_logging.setup_logging(logger_name="MAIN")
    targets = parse_advanced_gedcom(INPUT_GEDCOM)
    hunt_in_duckdb(targets)
