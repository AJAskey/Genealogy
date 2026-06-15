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
TARGET_DECADE = "1880"  # Lock exactly to the specified database for testing

# FIPS mapping to resolve NameError crash during state code evaluation
STATEICP_TO_FIPS = {
    "1": "09", "2": "23", "3": "25", "4": "33", "5": "44", "6": "50", "11": "10", 
    "12": "34", "13": "36", "14": "42", "21": "17", "22": "18", "23": "26", "24": "39", 
    "25": "55", "31": "19", "32": "20", "33": "27", "34": "29", "35": "31", "36": "38", 
    "37": "46", "40": "51", "41": "01", "42": "05", "43": "12", "44": "13", "45": "22", 
    "46": "28", "47": "37", "48": "45", "49": "48", "51": "21", "52": "24", "53": "40", 
    "54": "47", "56": "54", "61": "04", "62": "08", "63": "16", "64": "30", "65": "32", 
    "66": "35", "67": "49", "68": "56", "71": "06", "72": "41", "73": "53", "81": "02", "82": "15"
}

# The most common counties found in your GEDCOM data
COUNTY_CODES = {
    "clearfield": ["033", "33", "042033", "14033"], 
    "centre": ["027", "27", "042027", "14027"],
    "clinton": ["035", "35", "042035", "14035"],
    "lycoming": ["081", "81", "042081", "14081"],
    "allegheny": ["003", "3", "042003", "14003"],
    "jefferson": ["065", "65", "042065", "14065"],
    "indiana": ["063", "63", "042063", "14063"],
    "blair": ["013", "13", "042013", "14013"],
    "cambria": ["021", "21", "042021", "14021"]
}


# ==============================================================================

def get_bpl_prefixes(birth_place, desc):
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
            main_logger.info(f"Found {desc} birth_place: {birth_place}  {prefixes}")
            return prefixes
    return None


def get_state_from_code(bpl_code, desc):
    """Translates an IPUMS BPL numeric code back into a readable state/country name."""
    if not bpl_code: return "Unknown"

    clean_code = str(bpl_code).strip()
    if len(clean_code) > 2 and clean_code.endswith("00"):
        clean_code = clean_code[:-2]

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

    for state, codes in crosswalk.items():
        if clean_code in codes or clean_code.lstrip("0") in codes:
            main_logger.info(f"Found {desc} birth_place: {bpl_code}  {state.title()}")
            return state.title()

    return f"Unknown Code ({bpl_code})"


def is_bpl_match(db_val, allowed_prefixes):
    """Safely compares IPUMS detailed codes to general base codes using integer math."""

    ret = False
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
                ret = True
            # Foreign countries have 3-digit base codes, allow sub-codes
            if len(p_strip) >= 3:
                ret = True
    # main_logger.info(f"is_bpl_match db_val: {db_val}  {ret}")
    return ret


def is_county_match(raw_json_str, county_name):
    """Checks if the GEDCOM county name or its FIPS code exists in the raw IPUMS JSON."""
    if not county_name or not raw_json_str: return False
    county_lower = county_name.lower().replace(" county", "").strip()
    if not county_lower: return False
    
    if county_lower in raw_json_str.lower():
        return True
        
    for code in COUNTY_CODES.get(county_lower, []):
        if f'"{code}"' in raw_json_str or f': {code}' in raw_json_str or f':{code}' in raw_json_str:
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


def parse_csv_names_and_dates(filepath):
    """Reads the gedcom_individuals.csv and extracts target families."""
    individuals = {}
    target_couples = []
    seen_couples = set()

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)

        for row in reader:
            individuals[row['ID']] = row
            # if DEBUG_MODE and len(individuals) <= 3:
            #     gen_logging.log_dict(main_logger, row, f"Parsed row from {filepath}")

    for indi_id, row in individuals.items():
        sex = row.get('Sex', '').upper()

        spouse_ids = [s.strip() for s in row.get('Spouse ID(s)', '').split('|') if s.strip()]

        if not spouse_ids:
            # Lone Wolf
            byr_str = row.get('Birth Date', '')
            byr, bmo = parse_date(byr_str)
            byr = int(byr) if byr.isdigit() else None

            bpl = extract_state(row.get('Birth Place', ''))
            fbpl = extract_state(row.get('Father Birth Place', ''))
            mbpl = extract_state(row.get('Mother Birth Place', ''))
            if not fbpl: fbpl = bpl
            if not mbpl: mbpl = bpl

            bpl_county = row.get('Birth County', '').strip()
            fbpl_county = row.get('Father Birth County', '').strip()
            mbpl_county = row.get('Mother Birth County', '').strip()

            res = {str(yr): extract_state(row.get(f'{yr} Place', '')) for yr in range(1850, 1960, 10)}
            res_county = {str(yr): row.get(f'{yr} County', '').strip() for yr in range(1850, 1960, 10)}

            h_first, h_last, h_byr, h_bmo, h_bpl, h_fbpl, h_mbpl = "", "", None, "", "", "", ""
            h_bpl_county, h_fbpl_county, h_mbpl_county = "", "", ""
            w_first, w_last, w_byr, w_bmo, w_bpl, w_fbpl, w_mbpl = "", "", None, "", "", "", ""
            w_bpl_county, w_fbpl_county, w_mbpl_county = "", "", ""
            h_res = {str(yr): "" for yr in range(1850, 1960, 10)}
            w_res = {str(yr): "" for yr in range(1850, 1960, 10)}
            h_res_county = {str(yr): "" for yr in range(1850, 1960, 10)}
            w_res_county = {str(yr): "" for yr in range(1850, 1960, 10)}

            if sex == 'M':
                h_first, h_last = row.get('First Name', ''), row.get('Last Name', '')
                h_byr, h_bmo = byr, bmo
                h_bpl, h_fbpl, h_mbpl = bpl, fbpl, mbpl
                h_bpl_county, h_fbpl_county, h_mbpl_county = bpl_county, fbpl_county, mbpl_county
                h_res = res
                h_res_county = res_county
            elif sex == 'F':
                w_first, w_last = row.get('First Name', ''), row.get('Last Name', '')
                w_byr, w_bmo = byr, bmo
                w_bpl, w_fbpl, w_mbpl = bpl, fbpl, mbpl
                w_bpl_county, w_fbpl_county, w_mbpl_county = bpl_county, fbpl_county, mbpl_county
                w_res = res
                w_res_county = res_county
            else:
                continue

            if (not h_last or '--' in h_last or 'Hidden' in h_last or '[' in h_last) and \
                    (not w_last or '--' in w_last or 'Hidden' in w_last or '[' in w_last):
                continue

            if (not h_first or '--' in h_first or 'Living' in h_first or '[' in h_first) and \
                    (not w_first or '--' in w_first or 'Living' in w_first or '[' in w_first):
                continue

            target_couples.append({
                'h_first': h_first, 'h_last': h_last, 'h_byr': h_byr, 'h_bmo': h_bmo,
                'h_bpl': h_bpl, 'h_fbpl': h_fbpl, 'h_mbpl': h_mbpl, 'h_res': h_res,
                'h_bpl_county': h_bpl_county, 'h_fbpl_county': h_fbpl_county, 'h_mbpl_county': h_mbpl_county, 'h_res_county': h_res_county,
                'w_first': w_first, 'w_last': w_last, 'w_byr': w_byr, 'w_bmo': w_bmo,
                'w_bpl': w_bpl, 'w_fbpl': w_fbpl, 'w_mbpl': w_mbpl, 'w_res': w_res,
                'w_bpl_county': w_bpl_county, 'w_fbpl_county': w_fbpl_county, 'w_mbpl_county': w_mbpl_county, 'w_res_county': w_res_county,
                'marr_yr': None, 'num_children': 0
            })
            continue

        marr_dates = [d.strip() for d in row.get('Marriage Date(s)', '').split('|')]
        while len(marr_dates) < len(spouse_ids): marr_dates.append('')

        for idx, sp_id in enumerate(spouse_ids):
            spouse = individuals.get(sp_id)
            if not spouse: continue

            if sex == 'M':
                husb, wife = row, spouse
            else:
                husb, wife = spouse, row

            h_first, h_last = husb.get('First Name', ''), husb.get('Last Name', '')
            w_first, w_last = wife.get('First Name', ''), wife.get('Last Name', '')

            couple_key = f"{h_first}_{h_last}_{w_first}_{w_last}"
            if couple_key in seen_couples:
                continue
            seen_couples.add(couple_key)

            if (not h_last or '--' in h_last or 'Hidden' in h_last or '[' in h_last) and \
                    (not w_last or '--' in w_last or 'Hidden' in w_last or '[' in w_last):
                continue

            if (not h_first and not w_first) or \
                    ('--' in h_first or 'Living' in h_first or '[' in h_first) or \
                    ('--' in w_first or 'Living' in w_first or '[' in w_first):
                continue

            h_byr_str, h_bmo = parse_date(husb.get('Birth Date', ''))
            w_byr_str, w_bmo = parse_date(wife.get('Birth Date', ''))

            h_byr = int(h_byr_str) if h_byr_str.isdigit() else None
            w_byr = int(w_byr_str) if w_byr_str.isdigit() else None

            h_bpl = extract_state(husb.get('Birth Place', ''))
            h_fbpl = extract_state(husb.get('Father Birth Place', ''))
            h_mbpl = extract_state(husb.get('Mother Birth Place', ''))
            if not h_fbpl: h_fbpl = h_bpl
            if not h_mbpl: h_mbpl = h_bpl
            
            h_bpl_county = husb.get('Birth County', '').strip()
            h_fbpl_county = husb.get('Father Birth County', '').strip()
            h_mbpl_county = husb.get('Mother Birth County', '').strip()

            w_bpl = extract_state(wife.get('Birth Place', ''))
            w_fbpl = extract_state(wife.get('Father Birth Place', ''))
            w_mbpl = extract_state(wife.get('Mother Birth Place', ''))
            if not w_fbpl: w_fbpl = w_bpl
            if not w_mbpl: w_mbpl = w_bpl
            
            w_bpl_county = wife.get('Birth County', '').strip()
            w_fbpl_county = wife.get('Father Birth County', '').strip()
            w_mbpl_county = wife.get('Mother Birth County', '').strip()

            h_res = {str(yr): extract_state(husb.get(f'{yr} Place', '')) for yr in range(1850, 1960, 10)}
            w_res = {str(yr): extract_state(wife.get(f'{yr} Place', '')) for yr in range(1850, 1960, 10)}
            h_res_county = {str(yr): husb.get(f'{yr} County', '').strip() for yr in range(1850, 1960, 10)}
            w_res_county = {str(yr): wife.get(f'{yr} County', '').strip() for yr in range(1850, 1960, 10)}

            marr_yr_str, _ = parse_date(marr_dates[idx])
            marr_yr = int(marr_yr_str) if marr_yr_str.isdigit() else None

            num_children_str = husb.get('Num Children', '0')
            num_children = int(num_children_str) if num_children_str.isdigit() else 0

            target_couples.append({
                'h_first': h_first, 'h_last': h_last, 'h_byr': h_byr, 'h_bmo': h_bmo,
                'h_bpl': h_bpl, 'h_fbpl': h_fbpl, 'h_mbpl': h_mbpl, 'h_res': h_res,
                'h_bpl_county': h_bpl_county, 'h_fbpl_county': h_fbpl_county, 'h_mbpl_county': h_mbpl_county, 'h_res_county': h_res_county,
                'w_first': w_first, 'w_last': w_last, 'w_byr': w_byr, 'w_bmo': w_bmo,
                'w_bpl': w_bpl, 'w_fbpl': w_fbpl, 'w_mbpl': w_mbpl, 'w_res': w_res,
                'w_bpl_county': w_bpl_county, 'w_fbpl_county': w_fbpl_county, 'w_mbpl_county': w_mbpl_county, 'w_res_county': w_res_county,
                'marr_yr': marr_yr, 'num_children': num_children
            })

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

            if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                logger.info(f"  -> Copying {filename} to Named Vaults to protect raw data...")
                # Delete old database AND its hidden WAL/SHM files to prevent schema resurrection
                for old_file in os.listdir(NAMED_VAULT_DIR):
                    if old_file.startswith(filename.replace("YearVault_", "NamedVault_")):
                        try:
                            os.remove(os.path.join(NAMED_VAULT_DIR, old_file))
                        except OSError:
                            pass
                shutil.copy2(src, dst)
            else:
                logger.info(f"  -> {filename} already copied.")

    logger.info(f"\nStep 2/4: Scanning for CSV files in: {GEDCOM_INPUT_DIR}")
    csv_files = [f for f in os.listdir(GEDCOM_INPUT_DIR) if f.lower().endswith('individuals.csv')]
    # if not csv_files:
    #     logger.warning("  -> *individuals.csv not found!")
    #     return

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

    target_matches = {
        i: {
            'fam': fam,
            'results': [],
            'clans': set(),
            'unclanned': set(),
            'too_many': False,
            'searched': False,

            'h_sex': '1',  # Male
            'h_byr': fam['h_byr'],
            'h_bmo': fam['h_bmo'],
            'h_bpl_pref': get_bpl_prefixes(fam['h_bpl'], "h_bpl"),
            'h_fbpl_pref': get_bpl_prefixes(fam['h_fbpl'], "h_fbpl"),
            'h_mbpl_pref': get_bpl_prefixes(fam['h_mbpl'], "h_mbpl"),
            'h_res_prefs': {yr: get_bpl_prefixes(extract_state(loc), f"h_res_{yr}") for yr, loc in fam['h_res'].items()
                            if loc},
            'h_bpl_county': fam.get('h_bpl_county', ''),
            'h_fbpl_county': fam.get('h_fbpl_county', ''),
            'h_mbpl_county': fam.get('h_mbpl_county', ''),
            'h_res_county': fam.get('h_res_county', {}),

            'w_sex': '2',  # Female
            'w_byr': fam['w_byr'],
            'w_bmo': fam['w_bmo'],
            'w_bpl_pref': get_bpl_prefixes(fam['w_bpl'], "w_bpl"),
            'w_fbpl_pref': get_bpl_prefixes(fam['w_fbpl'], "w_fbpl"),
            'w_mbpl_pref': get_bpl_prefixes(fam['w_mbpl'], "w_mbpl"),
            'w_res_prefs': {yr: get_bpl_prefixes(extract_state(loc), f"w_res_{yr}") for yr, loc in fam['w_res'].items()
                            if loc},
            'w_bpl_county': fam.get('w_bpl_county', ''),
            'w_fbpl_county': fam.get('w_fbpl_county', ''),
            'w_mbpl_county': fam.get('w_mbpl_county', ''),
            'w_res_county': fam.get('w_res_county', {}),

            'marr_yr': fam['marr_yr'],
            'num_children': fam.get('num_children', 0)
        } for i, fam in enumerate(all_target_couples)
    }

    # Loop through the decades ONE AT A TIME
    for filename in os.listdir(NAMED_VAULT_DIR):
        if not (filename.startswith("NamedVault_") and filename.endswith(".db")):
            continue

        if TARGET_DECADE and TARGET_DECADE not in filename:
            continue

        census_year = int(filename.replace("NamedVault_", "").replace(".db", ""))

        db_path = os.path.join(NAMED_VAULT_DIR, filename)
        logger.info(f"  -> Loading nameless couples from {filename} into memory...")
        with sqlite3.connect(db_path) as conn:

            bosselstinks = conn.execute("""
                                        SELECT f.family_id,
                                               f.numprec,
                                               h.histid,
                                               h.sex,
                                               h.birthyr,
                                               h.bpld,
                                               h.fbpl,
                                               h.mbpl,
                                               s.histid,
                                               s.sex,
                                               s.birthyr,
                                               s.bpld,
                                               s.fbpl,
                                               s.mbpl,
                                               h.raw_data,
                                               s.raw_data
                                        FROM families f
                                                 JOIN individuals h ON f.head_histid = h.histid
                                                 JOIN individuals s ON f.spouse_histid = s.histid
                                        WHERE h.last_name = 'Bosselstink'
                                          AND h.first_name = 'Future'
                                          AND h.birthyr IS NOT NULL
                                          AND s.birthyr IS NOT NULL
                                        """)

        logger.info("     Building memory index from database... (This takes a few minutes)")
        mem_index = defaultdict(list)
        count = 0
        for row in bosselstinks:
            mem_index[(row[4], row[10])].append(row)  # Index by H_BYR, W_BYR
            count += 1
            if count % 1000000 == 0:
                logger.info(f"       -> Indexed {count:,} couples so far...")
        logger.info(f"     Successfully indexed {count:,} total couples!")

        logger.info(f"     Matching targets against {filename}...")

        for i, match_data in target_matches.items():

            if match_data['too_many'] or not match_data['h_byr'] or not match_data['w_byr']:
                continue

            # DECISION: Biological Reality Filter.
            # If they would be over 110 years old, they are dead. Under 14? Too young to be a Head/Spouse.
            # Don't waste CPU or log space searching for them!
            h_age = census_year - match_data['h_byr']
            w_age = census_year - match_data['w_byr']
            if not (14 <= h_age <= 110) or not (14 <= w_age <= 110):
                continue

            match_data['searched'] = True

            h_name = f"{match_data['fam']['h_first']} {match_data['fam']['h_last']}"
            w_name = f"{match_data['fam']['w_first']} {match_data['fam']['w_last']}"
            logger.info(
                f"\n[SEARCHING] Couple: {h_name} (b. {match_data['h_byr']}) & {w_name} (b. {match_data['w_byr']}) | Kids: {match_data['num_children']}")

            dbg_dik = {"h_name": h_name, "w_name": w_name,
                       "h_age": h_age, "w_age": w_age,
                       "h_bpl": match_data['h_bpl_pref'],
                       "f_bpl": match_data['h_fbpl_pref'],
                       "m_bpl": match_data['h_mbpl_pref'],
                       "w_bpl": match_data['w_bpl_pref'],
                       "w_fbpl": match_data['w_fbpl_pref'],
                       "w_mbpl": match_data['w_mbpl_pref'],
                       "h_res": match_data['h_res_prefs'],
                       "w_res": match_data['w_res_prefs']
                       }
            gen_logging.log_dict(main_logger, dbg_dik, "SEARCHING] Couple")

            matches_this_decade = 0

            # DECISION: Single-Pass Age Strategy. Evaluate all offsets in a +/- 2 year window simultaneously.
            # This prevents a terrible match at exactly (0,0) from blocking a perfect match at (-1, 0).
            pass_configs = [
                [(h, w) for h in range(-2, 3) for w in range(-2, 3)]
            ]

            for offsets in pass_configs:
                if matches_this_decade > 0:
                    break

                scored_matches = []

                match_dbg = {}

                for h_off, w_off in offsets:
                    key = (match_data['h_byr'] + h_off, match_data['w_byr'] + w_off)
                    if key in mem_index:
                        for db_row in mem_index[key]:
                            db_h_bpld, db_h_fbpl, db_h_mbpl = db_row[5], db_row[6], db_row[7]
                            db_w_bpld, db_w_fbpl, db_w_mbpl = db_row[11], db_row[12], db_row[13]

                            # Check Sex
                            if match_data['h_sex'] and db_row[3] != match_data['h_sex']: continue
                            if match_data['w_sex'] and db_row[9] != match_data['w_sex']: continue

                            match_dbg.update({'h_sex': match_data['h_sex']})
                            match_dbg.update({'dbh_sex': db_row[3]})

                            try:
                                h_raw = json.loads(db_row[14])
                                w_raw = json.loads(db_row[15])
                            except (json.JSONDecodeError, TypeError):
                                h_raw, w_raw = {}, {}

                            # DECISION: Extract exact child count from the JSON Bread Crumbs
                            # Try the 1900 CHBORN variable first (Total children ever born to the wife)
                            db_chborn_str = str(w_raw.get('CHBORN', '')).strip()
                            if db_chborn_str.isdigit() and int(db_chborn_str) < 99:  # IPUMS uses 99/999 for N/A
                                db_kids = int(db_chborn_str)
                            else:
                                # Fallback to NCHILD or numprec for other census years
                                db_nchild_str = str(h_raw.get('NCHILD', '')).strip()
                                if db_nchild_str.isdigit():
                                    db_kids = int(db_nchild_str)
                                else:
                                    numprec_str = str(db_row[1]).strip()
                                    db_kids = max(0, int(numprec_str) - 2) if numprec_str.isdigit() else 0

                            # DECISION: The "Has Kids" Boolean Filter.
                            if match_data['num_children'] > 0 and db_kids == 0:
                                continue

                            size_diff = abs(db_kids - match_data['num_children'])
                            age_diff = abs(h_off) + abs(w_off)

                            score = size_diff + age_diff

                            # DECISION: Soft-Score the Birthplaces!
                            # We apply a penalty for wrong states, but a BONUS for correct states
                            # to create a massive scoring gap between true matches and false positives!
                            score_breakdown = {
                                "base": score,
                                "kids_penalty": size_diff,
                                "age_penalty": age_diff
                            }
                            if match_data['h_bpl_pref']:
                                if is_bpl_match(db_h_bpld, match_data['h_bpl_pref']):
                                    score -= 5;
                                    score_breakdown['h_bpl'] = -5
                                else:
                                    score += 5;
                                    score_breakdown['h_bpl'] = 5
                            if match_data['h_fbpl_pref']:
                                if is_bpl_match(db_h_fbpl, match_data['h_fbpl_pref']):
                                    score -= 2;
                                    score_breakdown['h_fbpl'] = -2
                                else:
                                    score += 2;
                                    score_breakdown['h_fbpl'] = 2
                            if match_data['h_mbpl_pref']:
                                if is_bpl_match(db_h_mbpl, match_data['h_mbpl_pref']):
                                    score -= 2;
                                    score_breakdown['h_mbpl'] = -2
                                else:
                                    score += 2;
                                    score_breakdown['h_mbpl'] = 2

                            if match_data['w_bpl_pref']:
                                if is_bpl_match(db_w_bpld, match_data['w_bpl_pref']):
                                    score -= 5;
                                    score_breakdown['w_bpl'] = -5
                                else:
                                    score += 5;
                                    score_breakdown['w_bpl'] = 5
                            if match_data['w_fbpl_pref']:
                                if is_bpl_match(db_w_fbpl, match_data['w_fbpl_pref']):
                                    score -= 2;
                                    score_breakdown['w_fbpl'] = -2
                                else:
                                    score += 2;
                                    score_breakdown['w_fbpl'] = 2
                            if match_data['w_mbpl_pref']:
                                if is_bpl_match(db_w_mbpl, match_data['w_mbpl_pref']):
                                    score -= 2;
                                    score_breakdown['w_mbpl'] = -2
                                else:
                                    score += 2;
                                    score_breakdown['w_mbpl'] = 2
                                    
                            # DECISION: Apply the High-Fidelity County Anchors!
                            h_raw_str = str(db_row[14]).lower() if db_row[14] else ""
                            w_raw_str = str(db_row[15]).lower() if db_row[15] else ""
                            
                            if match_data['h_bpl_county'] and is_county_match(h_raw_str, match_data['h_bpl_county']):
                                score -= 3
                                score_breakdown['h_bpl_county'] = -3
                            if match_data['h_fbpl_county'] and is_county_match(h_raw_str, match_data['h_fbpl_county']):
                                score -= 1
                                score_breakdown['h_fbpl_county'] = -1
                            if match_data['h_mbpl_county'] and is_county_match(h_raw_str, match_data['h_mbpl_county']):
                                score -= 1
                                score_breakdown['h_mbpl_county'] = -1
                                
                            if match_data['w_bpl_county'] and is_county_match(w_raw_str, match_data['w_bpl_county']):
                                score -= 3
                                score_breakdown['w_bpl_county'] = -3
                            if match_data['w_fbpl_county'] and is_county_match(w_raw_str, match_data['w_fbpl_county']):
                                score -= 1
                                score_breakdown['w_fbpl_county'] = -1
                            if match_data['w_mbpl_county'] and is_county_match(w_raw_str, match_data['w_mbpl_county']):
                                score -= 1
                                score_breakdown['w_mbpl_county'] = -1

                            # DECISION: The Decadal Residence Anchor!
                            # Dynamically grab the GEDCOM's residence for THIS specific census year.
                            # If the cell is blank/null, the dict lookup returns None and it is gracefully ignored.
                            h_res_pref = match_data['h_res_prefs'].get(str(census_year))
                            w_res_pref = match_data['w_res_prefs'].get(str(census_year))
                            h_res_co = match_data['h_res_county'].get(str(census_year))
                            w_res_co = match_data['w_res_county'].get(str(census_year))

                            if h_res_pref:
                                db_h_statefip = str(h_raw.get('STATEFIP', '')).strip().lstrip('0')
                                if not db_h_statefip:
                                    db_h_stateicp = str(h_raw.get('STATEICP', '')).strip()
                                    db_h_statefip = STATEICP_TO_FIPS.get(db_h_stateicp, '')
                                if db_h_statefip:
                                    if is_bpl_match(db_h_statefip, h_res_pref):
                                        score -= 10;
                                        score_breakdown['h_res'] = -10
                                        # If state is a match, check the county for a massive tie-breaking bonus!
                                        if h_res_co and is_county_match(h_raw_str, h_res_co):
                                            score -= 15
                                            score_breakdown['h_res_county'] = -15
                                    else:
                                        score += 25;
                                        score_breakdown['h_res'] = 25
                            elif w_res_pref:
                                db_w_statefip = str(w_raw.get('STATEFIP', '')).strip().lstrip('0')
                                if not db_w_statefip:
                                    db_w_stateicp = str(w_raw.get('STATEICP', '')).strip()
                                    db_w_statefip = STATEICP_TO_FIPS.get(db_w_stateicp, '')
                                if db_w_statefip:
                                    if is_bpl_match(db_w_statefip, w_res_pref):
                                        score -= 10;
                                        score_breakdown['w_res'] = -10
                                        # If state is a match, check the county for a massive tie-breaking bonus!
                                        if w_res_co and is_county_match(w_raw_str, w_res_co):
                                            score -= 15
                                            score_breakdown['w_res_county'] = -15
                                    else:
                                        score += 25;
                                        score_breakdown['w_res'] = 25

                            # DECISION: Extract Birth Month and Years Married.
                            try:

                                db_h_bmo = str(h_raw.get('BIRTHMO', '')).strip().lstrip('0')
                                db_w_bmo = str(w_raw.get('BIRTHMO', '')).strip().lstrip('0')

                                if match_data['h_bmo'] and db_h_bmo:
                                    if match_data['h_bmo'] == db_h_bmo:
                                        score -= 2;
                                        score_breakdown['h_bmo'] = -2
                                    else:
                                        score += 10;
                                        score_breakdown['h_bmo'] = 10

                                if match_data['w_bmo'] and db_w_bmo:
                                    if match_data['w_bmo'] == db_w_bmo:
                                        score -= 2;
                                        score_breakdown['w_bmo'] = -2
                                    else:
                                        score += 10;
                                        score_breakdown['w_bmo'] = 10

                                db_marr_yrs = str(h_raw.get('MARRNOYR') or h_raw.get('MARRNOYRS', '')).strip()
                                if db_marr_yrs.isdigit() and int(db_marr_yrs) < 100:
                                    current_year = int(h_raw.get('YEAR', 0)) if str(
                                        h_raw.get('YEAR', '')).isdigit() else 0
                                    if current_year > 0:
                                        db_marr_yr = current_year - int(db_marr_yrs)
                                        score_breakdown['db_marr_yr'] = db_marr_yr
                                        if match_data['marr_yr']:
                                            if abs(match_data['marr_yr'] - db_marr_yr) <= 2:
                                                score -= 3;
                                                score_breakdown['marr_yr'] = -3
                                            else:
                                                score += 5;
                                                score_breakdown['marr_yr'] = 5
                            except (json.JSONDecodeError, TypeError):
                                pass

                            scored_matches.append((score, db_row, score_breakdown))

                if scored_matches:
                    scored_matches.sort(key=lambda x: x[0])
                    best_score = scored_matches[0][0]
                    winners = [m for m in scored_matches if m[0] == best_score]

                    for w in winners:
                        db_row = w[1]
                        fam_id = db_row[0]
                        clan_id = clan_map.get(fam_id)

                        if clan_id:
                            match_data['clans'].add(clan_id)
                        else:
                            match_data['unclanned'].add(fam_id)

                        match_data['results'].append((best_score, db_row))
                        matches_this_decade += 1

                        if matches_this_decade <= 5:
                            # Map the raw tuple to a dictionary so the rich logger displays it beautifully!
                            dbg_row = {
                                "h_sex": db_row[3], "h_birthyr": db_row[4],
                                "h_bpld_raw": db_row[5], "h_fbpl_raw": db_row[6], "h_mbpl_raw": db_row[7],
                                "w_sex": db_row[9], "w_birthyr": db_row[10],
                                "w_bpld_raw": db_row[11], "w_fbpl_raw": db_row[12], "w_mbpl_raw": db_row[13],
                                "family_id": db_row[0], "numprec": db_row[1], "h_histid": db_row[2],
                                "w_histid": db_row[8], "h_data": db_row[14], "w_data": db_row[15],
                                "score": w[0]
                            }
                            dbg_row.update(w[2])
                            gen_logging.log_dict(main_logger, dbg_row, "MATCH FOUND")

            if matches_this_decade > 5:
                logger.info(f"   ... and {matches_this_decade - 5} more matches found in this decade.")
            elif matches_this_decade == 0:
                logger.info(f"   [NO MATCH FOUND] Zero records matched these demographics in {filename}.")

            # Enforce the cap immediately
            total_entities = len(match_data['clans']) + len(match_data['unclanned'])
            if total_entities > 20:
                match_data['too_many'] = True
                match_data['results'] = []  # Dump the array from RAM
                match_data['clans'].clear()
                match_data['unclanned'].clear()
                logger.warning(f"   [ABORTED] Surpassed 20 matches. Flagged as 'Too Many'.")

        del bosselstinks
        del mem_index
        gc.collect()

    logger.info("\n  -> Evaluating Final Couple Matches Across All Decades...")
    update_queue_by_year = defaultdict(list)
    multiple_count = 0
    too_many_count = 0
    zero_count = 0
    success_count = 0
    ignored_count = 0

    clans_to_update = {}
    unclanned_to_update = {}
    flagged_multiples = set()

    for match_data in target_matches.values():
        fam = match_data['fam']
        h_name = f"{fam['h_first']} {fam['h_last']}"
        w_name = f"{fam['w_first']} {fam['w_last']}"

        if not match_data['searched']:
            ignored_count += 1
            continue

        if match_data['too_many'] or not match_data['h_byr'] or not match_data['w_byr']:
            too_many_count += 1
            continue

        total_unique_entities = len(match_data['clans']) + len(match_data['unclanned'])

        if total_unique_entities == 1:
            success_count += 1

            # Print the perfect match details!
            if match_data['results']:
                score, db_row = match_data['results'][0]
                match_label = "PERFECT MATCH" if score <= 0 else "BEST MATCH"

                h_bpl_str = get_state_from_code(db_row[5], "h_bpl_str")
                h_fbpl_str = get_state_from_code(db_row[6], "h_fbpl_str")
                h_mbpl_str = get_state_from_code(db_row[7], "h_mbpl_str")
                w_bpl_str = get_state_from_code(db_row[11], "w_bpl_str")
                w_fbpl_str = get_state_from_code(db_row[12], "w_fbpl_str")
                w_mbpl_str = get_state_from_code(db_row[13], "w_mbpl_str")

                # DECISION: Instantiate Genealogy Classes using the successfully matched data!
                fam_id = db_row[0]
                fam_obj = Family(family_id=fam_id)
                fam_obj.husband_id = db_row[2]
                fam_obj.wife_id = db_row[8]
                fam_obj.score = score

                try:
                    h_raw = json.loads(db_row[14]) if db_row[14] else {}
                    w_raw = json.loads(db_row[15]) if db_row[15] else {}
                except (json.JSONDecodeError, TypeError):
                    h_raw, w_raw = {}, {}

                h_indi = Individual(st_joes_id=fam_obj.husband_id, raw_composite_id=fam_obj.husband_id, fam_id=fam_id)
                h_indi.first_name, h_indi.last_name = fam['h_first'], fam['h_last']
                h_indi.sex, h_indi.birthyr = db_row[3], db_row[4]
                h_indi.bpld, h_indi.fbpl, h_indi.mbpl = db_row[5], db_row[6], db_row[7]
                h_indi.bpld_str, h_indi.fbpl_str, h_indi.mbpl_str = h_bpl_str, h_fbpl_str, h_mbpl_str
                h_indi.target_bpl, h_indi.target_bpl_codes = fam['h_bpl'], match_data['h_bpl_pref']
                h_indi.target_fbpl, h_indi.target_fbpl_codes = fam['h_fbpl'], match_data['h_fbpl_pref']
                h_indi.target_mbpl, h_indi.target_mbpl_codes = fam['h_mbpl'], match_data['h_mbpl_pref']
                h_indi.target_residences = fam['h_res']
                h_indi.target_residences_codes = match_data['h_res_prefs']
                h_indi.birthmo, h_indi.marrnoyrs = h_raw.get('BIRTHMO'), h_raw.get('MARRNOYRS')
                h_indi.status = "HUSBAND"

                w_indi = Individual(st_joes_id=fam_obj.wife_id, raw_composite_id=fam_obj.wife_id, fam_id=fam_id)
                w_indi.first_name, w_indi.last_name = fam['w_first'], fam['w_last']
                w_indi.sex, w_indi.birthyr = db_row[9], db_row[10]
                w_indi.bpld, w_indi.fbpl, w_indi.mbpl = db_row[11], db_row[12], db_row[13]
                w_indi.bpld_str, w_indi.fbpl_str, w_indi.mbpl_str = w_bpl_str, w_fbpl_str, w_mbpl_str
                w_indi.target_bpl, w_indi.target_bpl_codes = fam['w_bpl'], match_data['w_bpl_pref']
                w_indi.target_fbpl, w_indi.target_fbpl_codes = fam['w_fbpl'], match_data['w_fbpl_pref']
                w_indi.target_mbpl, w_indi.target_mbpl_codes = fam['w_mbpl'], match_data['w_mbpl_pref']
                w_indi.target_residences = fam['w_res']
                w_indi.target_residences_codes = match_data['w_res_prefs']
                w_indi.birthmo, w_indi.marrnoyrs = w_raw.get('BIRTHMO'), w_raw.get('MARRNOYRS')
                w_indi.status = "SPOUSE"

                logger.info(f" \n --- TARGET DEMOGRAPHICS ---")
                logger.info(f"      HUSB: {h_name}  {match_data['h_byr']}")
                logger.info(f"      WIFE: {w_name}  {match_data['w_byr']}")
                logger.info(f"      MARR: {match_data['marr_yr']} | KIDS: {match_data['num_children']}")

                # Fire your custom object logging function!
                gen_logging.log_individuals(main_logger, h_indi, w_indi)

                if len(match_data['clans']) == 1:
                    clans_to_update[list(match_data['clans'])[0]] = fam
                else:
                    unclanned_to_update[list(match_data['unclanned'])[0]] = fam

            elif total_unique_entities > 1:
                logger.warning(
                    f"  [MULTIPLE] Found {total_unique_entities} distinct families for Couple: {h_name} & {w_name}. Flagging as 'Multiple'.")
                multiple_count += 1

                # DECISION: If there are 8 or fewer matches, print them out so the user can see exactly why they tied!
                if total_unique_entities <= 8:

                    logger.info(f" \n --- TARGET DEMOGRAPHICS ---")
                    logger.info(f"      HUSB: {h_name}  {match_data['h_byr']}")
                    logger.info(f"      WIFE: {w_name}  {match_data['w_byr']}")
                    logger.info(f"      MARR: {match_data['marr_yr']} | KIDS: {match_data['num_children']}")

                    # Fire your custom object logging function!
                    gen_logging.log_individuals(main_logger, h_indi, w_indi)

                    logger.info(f"  --- DATABASE MATCHES ---")

                    printed_fams = set()
                    for score, db_row in match_data['results']:
                        fam_id = db_row[0]
                        if fam_id not in printed_fams:
                            h_bpl_str = get_state_from_code(db_row[5], h_name + " : h_bpl_str")
                            h_fbpl_str = get_state_from_code(db_row[6], h_name + " : h_fbpl_str")
                            h_mbpl_str = get_state_from_code(db_row[7], h_name + " : h_mbpl_str")
                            w_bpl_str = get_state_from_code(db_row[11], w_name + " : w_bpl_str")
                            w_fbpl_str = get_state_from_code(db_row[12], w_name + " : w_fbpl_str")
                            w_mbpl_str = get_state_from_code(db_row[13], w_name + " : w_mbpl_str")

                            dbg_dict = {
                                "h_bpl_str": h_bpl_str,
                                "h_fbpl_str": h_fbpl_str,
                                "h_mbpl_str": h_mbpl_str,
                                "w_bpl_str": w_bpl_str,
                                "w_fbpl_str": w_fbpl_str,
                                "w_mbpl_str": w_mbpl_str,
                                "score": score,
                                "fam": fam_id
                            }
                            gen_logging.log_dict(main_logger, dbg_dict, "MATCHES")

                            printed_fams.add(fam_id)

                for score, db_row in match_data['results']:
                    histid_h, histid_w, fam_id = db_row[2], db_row[8], db_row[0]  # Indices already shifted +1 in memory
                    if histid_h not in flagged_multiples:
                        update_queue_by_year[fam_id.split('_')[0]].append(('Multiple', 'Bosselstink', histid_h))
                        flagged_multiples.add(histid_h)
                    if histid_w not in flagged_multiples:
                        update_queue_by_year[fam_id.split('_')[0]].append(('Multiple', 'Bosselstink', histid_w))
                        flagged_multiples.add(histid_w)

            else:
                zero_count += 1
                logger.info(
                    f"  [ZERO MATCHES] No families found for {h_name} (b.{match_data['h_byr']}) & {w_name} (b.{match_data['w_byr']})")
                logger.info(
                    f"      HUSB: {h_name} -> BPL: {match_data['h_bpl_pref']} | FBPL: {match_data['h_fbpl_pref']} | MBPL: {match_data['h_mbpl_pref']}")
                logger.info(
                    f"      WIFE: {w_name} -> BPL: {match_data['w_bpl_pref']} | FBPL: {match_data['w_fbpl_pref']} | MBPL: {match_data['w_mbpl_pref']}")

    logger.info(f"\nLookup Complete:")
    logger.info(f"  -> Perfect Unique Anchors Found: {success_count:,}")
    logger.info(f"  -> Multiple Matches Flagged (<20): {multiple_count:,}")
    logger.info(f"  -> Too Many Matches (Skipped): {too_many_count:,}")
    logger.info(f"  -> Zero Matches (Skipped): {zero_count:,}")
    logger.info(f"  -> Biologically Impossible (Skipped): {ignored_count:,}")

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
                            logger.info(f"    [NAME APPLIED] {year_prefix} Vault -> Naming Head: {t_fam['h_first']} {t_fam['h_last']} (HISTID: {histid})")
                            update_queue_by_year[year_prefix].append((t_fam['h_first'], t_fam['h_last'], histid))
                        elif histid == spouse_id:
                            logger.info(f"    [NAME APPLIED] {year_prefix} Vault -> Naming Spouse: {t_fam['w_first']} {t_fam['w_last']} (HISTID: {histid})")
                            update_queue_by_year[year_prefix].append((t_fam['w_first'], t_fam['w_last'], histid))

    logger.info(f"\nStep 4/4: Applying historical names to the census records...")
    for year, q in update_queue_by_year.items():
        if not q: continue
        db_path = os.path.join(NAMED_VAULT_DIR, f"NamedVault_{year}.db")
        if os.path.exists(db_path):
            logger.info(f"  -> Executing {len(q):,} updates in {year}...")
            with sqlite3.connect(db_path) as sqlite_conn:
                sqlite_conn.execute("PRAGMA journal_mode=WAL")
                sqlite_conn.executemany("UPDATE individuals SET first_name = ?, last_name = ? WHERE histid = ?", q)
                sqlite_conn.commit()
            sqlite_conn.close()

    logger.info("\nSUCCESS! CSV Name Overlay complete.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="NAME_OVERLAY")
    apply_gedcom_names(main_logger)
