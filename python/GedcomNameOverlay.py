"""
-----------------------------------
File: GedcomNameOverlay.py

Summary: The "Label-Maker" for the Census-First Architecture.
         Diagnostic Mode Enabled. Reads the gedcom_individuals.csv.
         Targeted to 1900 for deep demographic verification using the
         unbreakable 10-Variable Couple Anchor.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0: http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy
-----------------------------------
"""
# The format of the CSV file used as a data flow from the
# GEDCOM to our model is gedcom_individuals.csv.
"""
Here's the columns and format. 

ID	I1865
First Name	William Francis
Last Name	Askey
Sex	M
Birth Date	4 JUL 1849
Birth Place	Karthaus, Clearfield, Pennsylvania, USA
Death Date	11-Mar-39
Death Place	Karthaus, Clearfield, Pennsylvania, USA
Burial Date	15-Mar-39
Burial Place	Karthaus, Clearfield, Pennsylvania, USA
Father	James Burton Askey
Father Birth Year	1816
Father Birth Place	Curwensville, Clearfield, Pennsylvania, USA
Mother	Harriet Wycoff
Mother Birth Year	1832
Mother Birth Place	Cameron, Pennsylvania, USA
Spouse(s)	Catharine Matilda Gross
Spouse Birth Year(s)	1856
Spouse Birth Place(s)	Keewaydin, Clearfield, Pennsylvania, USA
Marriage Date(s)	20 SEP 1874
Marriage Place(s)	Snow Shoe, Centre, Pennsylvania, USA
Children	Josiah James Askey | Dortha Ellen Askey | Foster Edgar Askey | Richard Homer Askey | Mitchel Monroe Askey | Lemuel Talmage Askey | Roy Ralph Askey | Millard Cameron Askey | Rachel Pearl Askey | Nellie Ethel Askey | David Earl Askey | Sara Marie Askey | Eva M Askey
"""

import csv
import gc
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [script_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging
from genealogy_classes import Individual, Family
from rich import inspect
from rich.console import Console

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
NAMED_VAULT_DIR = os.path.join(BASE_DATA_DIR, "NamedVaults")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
GEDCOM_INPUT_DIR = os.path.join(project_root, "gedcom_sources")

# ==============================================================================
# DIAGNOSTIC MODE SETTINGS
# ==============================================================================
TARGET_DECADE = "1870"  # Lock exactly to the 1900 database for testing
DEBUG_MODE = True  # Enable highly detailed match logging


# ==============================================================================

def get_bpl_prefixes(birth_place):
    """Translates a free-text location string into standard IPUMS BPL prefixes."""
    if not birth_place: return None
    bp_lower = birth_place.lower()

    crosswalk = {
        "alabama": ["01", "1"], "alaska": ["02", "2"], "arizona": ["04", "4"], "arkansas": ["05", "5"],
        "california": ["06", "6"], "colorado": ["08", "8"], "connecticut": ["09", "9"],
        "delaware": ["10"], "district of columbia": ["11"], "florida": ["12"],
        "georgia": ["13"], "hawaii": ["15"], "idaho": ["16"], "illinois": ["17"],
        "indiana": ["18"], "iowa": ["19"], "kansas": ["20"], "kentucky": ["21"],
        "louisiana": ["22"], "maine": ["23"], "maryland": ["24"], "massachusetts": ["25"],
        "michigan": ["26"], "minnesota": ["27"], "mississippi": ["28"], "missouri": ["29"],
        "montana": ["30"], "nebraska": ["31"], "nevada": ["32"], "new hampshire": ["33"],
        "new jersey": ["34"], "new mexico": ["35"], "new york": ["36"], "north carolina": ["37"],
        "north dakota": ["38"], "ohio": ["39"], "oklahoma": ["40"], "oregon": ["41"],
        "pennsylvania": ["42", "042"], "rhode island": ["44", "044"], "south carolina": ["45", "045"],
        "south dakota": ["46", "046"], "tennessee": ["47", "047"], "texas": ["48", "048"],
        "utah": ["49", "049"], "vermont": ["50", "050"], "virginia": ["51", "051"],
        "washington": ["53", "053"], "west virginia": ["54", "054"], "wisconsin": ["55", "055"],
        "wyoming": ["56", "056"],
        "england": ["410"], "scotland": ["411"], "wales": ["412"],
        "ireland": ["414"], "northern ireland": ["413"],
        "germany": ["453"], "sweden": ["404"], "norway": ["401"],
        "denmark": ["400"], "netherlands": ["425"], "france": ["421"],
        "switzerland": ["426"], "canada": ["150"], "mexico": ["200"],
        "japan": ["501"], "south korea": ["502"], "korea": ["502"]
    }

    for state, prefixes in crosswalk.items():
        if state in bp_lower:
            return prefixes
    return None


def is_bpl_match(db_val, allowed_prefixes):
    """Safely compares IPUMS detailed codes to general base codes using integer math."""
    if not db_val: return False
    db_str = str(db_val).strip()
    for p in allowed_prefixes:
        p_strip = p.lstrip('0')
        if not p_strip: p_strip = p

        # Exact match
        if db_str == p_strip or db_str == p: return True

        # Handle trailing zeros (e.g. 4200 starts with 42)
        if db_str.startswith(p_strip):
            remainder = db_str[len(p_strip):]
            if remainder != '' and remainder.replace('0', '') == '':
                return True
            # Foreign countries have 3-digit base codes, allow sub-codes
            if len(p_strip) >= 3:
                return True
    return False


def extract_state(loc_str):
    """Strips city/county and returns only the state/country name."""
    if not loc_str: return ""
    loc_lower = loc_str.lower()
    states = [
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
        "delaware", "district of columbia", "florida", "georgia", "hawaii", "idaho", "illinois",
        "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts",
        "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire",
        "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
        "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas",
        "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming",
        "england", "scotland", "wales", "ireland", "northern ireland", "germany", "sweden", "norway",
        "denmark", "netherlands", "france", "switzerland", "canada", "mexico", "japan", "south korea"
    ]
    for s in states:
        if s in loc_lower:
            if s == "district of columbia": return "District of Columbia"
            return s.title()
    return loc_str.strip()


def split_name(full_name):
    """Safely splits a string into first/middle and last names, handling suffixes."""
    tokens = full_name.replace(',', '').strip().split()
    if not tokens: return "", ""
    if len(tokens) == 1: return tokens[0], ""

    suffixes = {'jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v'}
    if len(tokens) >= 3 and tokens[-1].lower() in suffixes:
        return " ".join(tokens[:-2]), f"{tokens[-2]} {tokens[-1]}"

    return " ".join(tokens[:-1]), tokens[-1]


def parse_date(date_str):
    """Extracts a 4-digit year and the month number from a date string."""
    if not date_str:
        return "", ""
    date_str = str(date_str).upper()
    byr_match = re.search(r'\b(1[456789]\d\d|20\d\d)\b', date_str)
    byr = byr_match.group(1) if byr_match else ""

    bmo = ""
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    for i, m in enumerate(months, 1):
        if m in date_str:
            bmo = str(i)
            break

    return byr, bmo


def find_person(name, byr_str, people_by_name):
    """Looks up a person in the dictionary by name and (optionally) birth year."""
    if not name or name not in people_by_name:
        return None
    candidates = people_by_name[name]
    if len(candidates) == 1:
        return candidates[0]

    target_byr, _ = parse_date(byr_str)
    for c in candidates:
        c_byr, _ = parse_date(c.get('Birth Date', ''))
        if c_byr == target_byr:
            return c
    return candidates[0]

def create_standard_dict(source, fam_id="", h_histid="", w_histid="",
                         h_first="", h_last="", h_byr=None, h_bmo="", h_bpl="", h_fbpl="", h_mbpl="",
                         w_first="", w_last="", w_byr=None, w_bmo="", w_bpl="", w_fbpl="", w_mbpl="",
                         marr_yr=None, num_children=0, score=0):
    """Creates an identical dictionary structure used for both GEDCOM targets and Census database matches."""
    return {
        'source': source,
        'fam_id': fam_id,
        'h_histid': h_histid,
        'w_histid': w_histid,
        'h_first': h_first,
        'h_last': h_last,
        'h_byr': h_byr,
        'h_bmo': h_bmo,
        'h_bpl': h_bpl,
        'h_fbpl': h_fbpl,
        'h_mbpl': h_mbpl,
        'h_bpl_pref': [],
        'h_fbpl_pref': [],
        'h_mbpl_pref': [],
        'w_first': w_first,
        'w_last': w_last,
        'w_byr': w_byr,
        'w_bmo': w_bmo,
        'w_bpl': w_bpl,
        'w_fbpl': w_fbpl,
        'w_mbpl': w_mbpl,
        'w_bpl_pref': [],
        'w_fbpl_pref': [],
        'w_mbpl_pref': [],
        'marr_yr': marr_yr,
        'num_children': num_children,
        'score': score
    }

def parse_csv_names_and_dates(filepath):
    """Reads the gedcom_individuals.csv and extracts target families.
    """
    target_couples = []
    people_by_name = {}

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            first = row.get('First Name', '').strip()
            last = row.get('Last Name', '').strip()
            if not last or '--' in last or 'Hidden' in last or '[' in last:
                continue

            name_key = f"{first} {last}".strip()
            if name_key not in people_by_name:
                people_by_name[name_key] = []
            people_by_name[name_key].append(row)

    seen_couples = set()

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            p1_first = row.get('First Name', '').strip()
            p1_last = row.get('Last Name', '').strip()
            if not p1_last or '--' in p1_last or 'Hidden' in p1_last or '[' in p1_last:
                continue

            p1_sex = row.get('Sex', '').strip().upper()
            p1_byr, p1_bmo = parse_date(row.get('Birth Date', ''))
            p1_bpl = extract_state(row.get('Birth Place', ''))
            p1_fbpl = extract_state(row.get('Father Birth Place', ''))
            p1_mbpl = extract_state(row.get('Mother Birth Place', ''))

            # DECISION: Fallback to individual's birthplace if parent's birthplace is missing
            if not p1_fbpl: p1_fbpl = p1_bpl
            if not p1_mbpl: p1_mbpl = p1_bpl

            spouses_str = row.get('Spouse(s)', '')

            if spouses_str and p1_sex == 'M':
                spouses = [s.strip() for s in spouses_str.split('|')]
                sp_byrs_str = [s.strip() for s in row.get('Spouse Birth Year(s)', '').split('|')]
                sp_bpls_str = [s.strip() for s in row.get('Spouse Birth Place(s)', '').split('|')]
                marr_dates = [s.strip() for s in row.get('Marriage Date(s)', '').split('|')]

                children_str = row.get('Children', '').strip()
                num_children_str = str(row.get('Num Children', '')).strip()

                if num_children_str.isdigit():
                    num_children = int(num_children_str)
                else:
                    num_children = len([c for c in children_str.split('|') if c.strip()]) if children_str else 0

                for i, sp_name in enumerate(spouses):
                    if not sp_name:
                        continue

                    sp_byr_fallback = sp_byrs_str[i].strip() if i < len(sp_byrs_str) else ""
                    sp_bpl_fallback = sp_bpls_str[i].strip() if i < len(sp_bpls_str) else ""
                    marr_date = marr_dates[i].strip() if i < len(marr_dates) else ""
                    marr_yr, _ = parse_date(marr_date)

                    sp_row = find_person(sp_name, sp_byr_fallback, people_by_name)
                    if sp_row:
                        w_first = sp_row.get('First Name', '').strip()
                        w_last = sp_row.get('Last Name', '').strip()
                        w_byr, w_bmo = parse_date(sp_row.get('Birth Date', ''))
                        w_bpl = extract_state(sp_row.get('Birth Place', ''))
                        w_fbpl = extract_state(sp_row.get('Father Birth Place', ''))
                        w_mbpl = extract_state(sp_row.get('Mother Birth Place', ''))
                    else:
                        w_first, w_last = split_name(sp_name)
                        w_byr, w_bmo = parse_date(sp_byr_fallback)
                        w_bpl = extract_state(sp_bpl_fallback)
                        w_fbpl, w_mbpl = "", ""

                    # DECISION: Fallback to individual's birthplace if parent's birthplace is missing
                    if not w_fbpl: w_fbpl = w_bpl
                    if not w_mbpl: w_mbpl = w_bpl

                    if not w_last or '--' in w_last or 'Hidden' in w_last or '[' in w_last:
                        continue

                    if not p1_byr or not w_byr:
                        continue

                    couple_key = f"{p1_first}_{p1_last}_{w_first}_{w_last}"
                    if couple_key not in seen_couples:
                        g_dict = create_standard_dict(
                            source='GEDCOM',
                            h_first=p1_first, h_last=p1_last,
                            h_byr=int(p1_byr) if p1_byr else None, h_bmo=p1_bmo,
                            h_bpl=p1_bpl, h_fbpl=p1_fbpl, h_mbpl=p1_mbpl,
                            w_first=w_first, w_last=w_last,
                            w_byr=int(w_byr) if w_byr else None, w_bmo=w_bmo,
                            w_bpl=w_bpl, w_fbpl=w_fbpl, w_mbpl=w_mbpl,
                            marr_yr=int(marr_yr) if marr_yr else None,
                            num_children=num_children
                        )
                        g_dict['h_bpl_pref'] = get_bpl_prefixes(p1_bpl) or []
                        g_dict['h_fbpl_pref'] = get_bpl_prefixes(p1_fbpl) or []
                        g_dict['h_mbpl_pref'] = get_bpl_prefixes(p1_mbpl) or []
                        g_dict['w_bpl_pref'] = get_bpl_prefixes(w_bpl) or []
                        g_dict['w_fbpl_pref'] = get_bpl_prefixes(w_fbpl) or []
                        g_dict['w_mbpl_pref'] = get_bpl_prefixes(w_mbpl) or []
                        
                        target_couples.append(g_dict)
                        seen_couples.add(couple_key)
    return target_couples


def apply_gedcom_names(logger):
    logger.info("Step 1/4: Preparing the 'Named' Database Vaults...")
    os.makedirs(NAMED_VAULT_DIR, exist_ok=True)

    for filename in os.listdir(VAULT_DIR):
        if filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename:
            # Diagnostic mode: Only process the target decade
            if TARGET_DECADE and TARGET_DECADE not in filename:
                continue

            src = os.path.join(VAULT_DIR, filename)
            dst = os.path.join(NAMED_VAULT_DIR, filename.replace("YearVault_", "NamedVault_"))

            if not os.path.exists(dst):
                logger.info(f"  -> Copying {filename} to Named Vaults to protect raw data...")
                shutil.copy2(src, dst)
            else:
                logger.info(f"  -> {filename} already copied.")

    logger.info(f"\nStep 2/4: Scanning for CSV files in: {GEDCOM_INPUT_DIR}")
    csv_files = [f for f in os.listdir(GEDCOM_INPUT_DIR) if f.lower().endswith('individuals.csv')]
    if not csv_files:
        logger.warning("  -> *_individuals.csv not found!")
        return

    all_target_couples = []
    for file in csv_files:
        filepath = os.path.join(GEDCOM_INPUT_DIR, file)
        couples = parse_csv_names_and_dates(filepath)
        all_target_couples.extend(couples)
        logger.info(f"  -> Extracted {len(couples)} target couples for 10-Variable Anchoring from {file}")

    logger.info("\nStep 3/4: Searching for nameless couples in the Named Vaults...")

    logger.info("  -> Loading Clan Mappings from the Time Machine...")
    try:
        with sqlite3.connect(MATCH_DB) as sq_conn:
            clan_map = {row[0]: row[1] for row in
                        sq_conn.execute("SELECT family_id, clan_id FROM clan_mapping").fetchall()}
        logger.info(f"  -> Loaded {len(clan_map):,} family-to-clan links.")
    except sqlite3.OperationalError:
        logger.warning("  -> MATCH_DB not found! Clan consolidation disabled.")
        clan_map = {}

    all_c_dicts_by_target = defaultdict(list)

    # Loop through the decades ONE AT A TIME
    for filename in os.listdir(NAMED_VAULT_DIR):
        if not (filename.startswith("NamedVault_") and filename.endswith(".db")):
            continue

        if TARGET_DECADE and TARGET_DECADE not in filename:
            continue

        census_year = int(filename.replace("NamedVault_", "").replace(".db", ""))

        db_path = os.path.join(NAMED_VAULT_DIR, filename)
        logger.info(f"  -> Formulating DuckDB Bulk Push-Down Query for {filename}...")
        
        target_rows = []
        
        # DECISION: Convert IPUMS prefixes into ultra-strict regular expressions for SQL!
        # Examples: PA ['42'] becomes "^0*420*$"  | Ireland ['414'] becomes "^0*414.*$"
        def get_sql_regex(pref_list):
            if not pref_list: return '.*'
            p = str(pref_list[0]).lstrip('0')
            if not p: p = str(pref_list[0])
            if len(p) >= 3: return f"^0*{p}.*$"
            else: return f"^0*{p}0*$"
            
        for i, g_dict in enumerate(all_target_couples):
            if not g_dict['h_byr'] or not g_dict['w_byr']:
                continue

            h_age = census_year - g_dict['h_byr']
            w_age = census_year - g_dict['w_byr']
            if not (14 <= h_age <= 110) or not (14 <= w_age <= 110):
                continue

            target_rows.append((
                i, 
                '1', g_dict['h_byr'], 
                get_sql_regex(g_dict['h_bpl_pref']), 
                get_sql_regex(g_dict['h_fbpl_pref']), 
                get_sql_regex(g_dict['h_mbpl_pref']),
                '2', g_dict['w_byr'], 
                get_sql_regex(g_dict['w_bpl_pref']), 
                get_sql_regex(g_dict['w_fbpl_pref']), 
                get_sql_regex(g_dict['w_mbpl_pref'])
            ))

        if not target_rows:
            logger.info("     No target couples alive/applicable for this decade.")
            continue

        con = duckdb.connect()
        con.execute("INSTALL sqlite; LOAD sqlite;")
        con.execute("""
            CREATE TABLE targets (
                target_idx INTEGER, 
                h_sex VARCHAR, h_byr INTEGER, h_bpl_rx VARCHAR, h_fbpl_rx VARCHAR, h_mbpl_rx VARCHAR, 
                w_sex VARCHAR, w_byr INTEGER, w_bpl_rx VARCHAR, w_fbpl_rx VARCHAR, w_mbpl_rx VARCHAR
            )
        """)
        con.executemany("INSERT INTO targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", target_rows)
        con.execute(f"ATTACH '{db_path}' AS vault (TYPE SQLITE, READ_ONLY);")

        # DECISION: The Big Database Filter! Execute one massive join to test everything at once.
        query = """
            SELECT t.target_idx,
                   f.family_id, f.numprec,
                   h.histid, h.sex, h.birthyr, h.bpld, h.fbpl, h.mbpl,
                   s.histid, s.sex, s.birthyr, s.bpld, s.fbpl, s.mbpl,
                   h.raw_data, s.raw_data
            FROM vault.families f
            JOIN vault.individuals h ON f.head_histid = h.histid
            JOIN vault.individuals s ON f.spouse_histid = s.histid
            JOIN targets t
              ON h.birthyr BETWEEN t.h_byr - 1 AND t.h_byr + 1
             AND s.birthyr BETWEEN t.w_byr - 1 AND t.w_byr + 1
             AND h.sex = t.h_sex
             AND s.sex = t.w_sex
            WHERE h.last_name = 'Bosselstink'
              AND h.first_name = 'Future'
              AND regexp_matches(COALESCE(h.bpld, ''), t.h_bpl_rx)
              AND regexp_matches(COALESCE(h.fbpl, ''), t.h_fbpl_rx)
              AND regexp_matches(COALESCE(h.mbpl, ''), t.h_mbpl_rx)
              AND regexp_matches(COALESCE(s.bpld, ''), t.w_bpl_rx)
              AND regexp_matches(COALESCE(s.fbpl, ''), t.w_fbpl_rx)
              AND regexp_matches(COALESCE(s.mbpl, ''), t.w_mbpl_rx)
        """
        
        logger.info("     Executing massive bulk demographic cross-match via DuckDB...")
        matches = con.execute(query).fetchall()
        con.close()

        logger.info(f"     Found {len(matches):,} precise matches. Processing into timelines...")
        
        matches_by_target = defaultdict(list)
        for db_row in matches:
            target_idx = db_row[0]
            g_dict = all_target_couples[target_idx]

            h_raw_str = db_row[15]
            s_raw_str = db_row[16]
            try:
                h_raw = json.loads(h_raw_str) if h_raw_str else {}
                s_raw = json.loads(s_raw_str) if s_raw_str else {}
            except (json.JSONDecodeError, TypeError):
                h_raw, s_raw = {}, {}

            h_byr_db = db_row[5]
            s_byr_db = db_row[11]
            score = abs(h_byr_db - g_dict['h_byr']) + abs(s_byr_db - g_dict['w_byr'])

            c_dict = create_standard_dict(
                source='CENSUS',
                fam_id=db_row[1],
                h_histid=db_row[3], w_histid=db_row[9],
                h_first=h_raw.get('NAMEFRST', 'Future').strip() or "Future",
                h_last=h_raw.get('NAMELAST', 'Bosselstink').strip() or "Bosselstink",
                h_byr=h_byr_db, h_bmo=h_raw.get('BIRTHMO', ''),
                h_bpl=db_row[6], h_fbpl=db_row[7], h_mbpl=db_row[8],
                w_first=s_raw.get('NAMEFRST', 'Future').strip() or "Future",
                w_last=s_raw.get('NAMELAST', 'Bosselstink').strip() or "Bosselstink",
                w_byr=s_byr_db, w_bmo=s_raw.get('BIRTHMO', ''),
                w_bpl=db_row[12], w_fbpl=db_row[13], w_mbpl=db_row[14],
                num_children=int(db_row[2] or 0),
                score=score
            )
            c_dict['h_bpl_pref'] = [db_row[6]] if db_row[6] else []
            c_dict['h_fbpl_pref'] = [db_row[7]] if db_row[7] else []
            c_dict['h_mbpl_pref'] = [db_row[8]] if db_row[8] else []
            c_dict['w_bpl_pref'] = [db_row[12]] if db_row[12] else []
            c_dict['w_fbpl_pref'] = [db_row[13]] if db_row[13] else []
            c_dict['w_mbpl_pref'] = [db_row[14]] if db_row[14] else []
            
            all_c_dicts_by_target[target_idx].append(c_dict)

    logger.info("\n  -> Evaluating Final Couple Matches...")
    update_queue_by_year = defaultdict(list)
    multiple_count = 0
    zero_count = 0
    success_count = 0

    clans_to_update = {}
    unclanned_to_update = {}
    flagged_multiples = set()

    for target_idx, g_dict in enumerate(all_target_couples):
        c_dicts = all_c_dicts_by_target.get(target_idx, [])
        h_name = f"{g_dict['h_first']} {g_dict['h_last']}"
        w_name = f"{g_dict['w_first']} {g_dict['w_last']}"

        if not c_dicts:
            zero_count += 1
            continue

        # Sort by score
        c_dicts.sort(key=lambda x: x['score'])
        best_score = c_dicts[0]['score']
        winners = [c for c in c_dicts if c['score'] == best_score]

        distinct_entities = {}
        for c in winners:
            clan_id = clan_map.get(c['fam_id'])
            key = clan_id if clan_id else c['fam_id']
            if key not in distinct_entities:
                distinct_entities[key] = c

        if len(distinct_entities) == 1:
            success_count += 1
            c_dict = list(distinct_entities.values())[0]
            
            logger.info(f"  [PERFECT MATCH] (Score: {best_score}) {h_name} & {w_name}")
            logger.info(f"    g_dict = {g_dict}")
            logger.info(f"    c_dict = {c_dict}")

            key = list(distinct_entities.keys())[0]
            if key.startswith('CLAN_'):
                clans_to_update[key] = g_dict
            else:
                unclanned_to_update[key] = g_dict

        elif len(distinct_entities) > 1:
            multiple_count += 1
            logger.warning(f"  [MULTIPLE] Found {len(distinct_entities)} distinct families for {h_name} & {w_name}.")
            logger.info(f"  --- TARGET DEMOGRAPHICS ---")
            logger.info(f"    g_dict = {g_dict}")
            logger.info(f"  --- DATABASE MATCHES ---")
            for k, c_dict in distinct_entities.items():
                logger.info(f"    c_dict = {c_dict}")
                
                if c_dict['h_histid'] not in flagged_multiples:
                    update_queue_by_year[c_dict['fam_id'].split('_')[0]].append(('Multiple', 'Bosselstink', c_dict['h_histid']))
                    flagged_multiples.add(c_dict['h_histid'])
                if c_dict['w_histid'] not in flagged_multiples:
                    update_queue_by_year[c_dict['fam_id'].split('_')[0]].append(('Multiple', 'Bosselstink', c_dict['w_histid']))
                    flagged_multiples.add(c_dict['w_histid'])

    logger.info(f"\nLookup Complete:")
    logger.info(f"  -> Perfect Unique Anchors Found: {success_count:,}")
    logger.info(f"  -> Multiple Matches Flagged (<20): {multiple_count:,}")
    logger.info(f"  -> Zero Matches (Skipped): {zero_count:,}")

    # DECISION: The Living Room Sweep
    if clans_to_update or unclanned_to_update:
        logger.info("\n  -> Resolving 'Time Machine Echoes' & Sweeping Living Rooms...")
        for filename in os.listdir(NAMED_VAULT_DIR):
            if not (filename.startswith("NamedVault_") and filename.endswith(".db")): continue
            year_prefix = filename.replace("NamedVault_", "").replace(".db", "")

            if TARGET_DECADE and TARGET_DECADE != year_prefix: continue

            with sqlite3.connect(os.path.join(NAMED_VAULT_DIR, filename)) as conn:
                rows = conn.execute("""
                                    SELECT i.histid, f.family_id, i.sex, i.birthyr, f.head_histid, f.spouse_histid
                                    FROM individuals i
                                             JOIN families f ON i.family_id = f.family_id
                                    WHERE i.last_name = 'Bosselstink'
                                      AND i.first_name = 'Future'
                                    """).fetchall()

                for histid, fam_id, sex, byr, head_id, spouse_id in rows:
                    t_fam = None
                    c_id = clan_map.get(fam_id)
                    if c_id and c_id in clans_to_update:
                        t_fam = clans_to_update[c_id]
                    elif fam_id in unclanned_to_update:
                        t_fam = unclanned_to_update[fam_id]

                    if t_fam:
                        if histid == head_id:
                            update_queue_by_year[year_prefix].append((t_fam['h_first'], t_fam['h_last'], histid))
                        elif histid == spouse_id:
                            update_queue_by_year[year_prefix].append((t_fam['w_first'], t_fam['w_last'], histid))

    logger.info(f"\nStep 4/4: Applying historical names to the census records...")
    if DEBUG_MODE:
        logger.info("  -> [DEBUG MODE] Skipping database UPDATE to preserve 'Bosselstink' test data.")
    else:
        for year, q in update_queue_by_year.items():
            if not q: continue
            db_path = os.path.join(NAMED_VAULT_DIR, f"NamedVault_{year}.db")
            if os.path.exists(db_path):
                logger.info(f"  -> Executing {len(q):,} updates in {year}...")
                with sqlite3.connect(db_path) as sqlite_conn:
                    sqlite_conn.execute("PRAGMA journal_mode=WAL")
                    sqlite_conn.executemany("UPDATE individuals SET first_name = ?, last_name = ? WHERE histid = ?", q)
                    sqlite_conn.commit()

    logger.info("\nSUCCESS! CSV Name Overlay complete.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="NAME_OVERLAY")
    apply_gedcom_names(main_logger)
