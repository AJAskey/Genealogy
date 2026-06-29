"""
File: common_utils.py

Summary: Utility procedures required by other procedures.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0: http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy
-----------------------------------
"""
import re


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
    # FIPS and IPUMS ICPSR (trailing zero) codes
    "clearfield": ["033", "33", "330", "042033", "14033"],
    "centre": ["027", "27", "270", "042027", "14027"],
    "clinton": ["035", "35", "350", "042035", "14035"],
    "lycoming": ["081", "81", "810", "042081", "14081"],
    "allegheny": ["003", "3", "30", "042003", "14003"],
    "jefferson": ["065", "65", "650", "042065", "14065"],
    "indiana": ["063", "63", "630", "042063", "14063"],
    "blair": ["013", "13", "130", "042013", "14013"],
    "cambria": ["021", "21", "210", "042021", "14021"],
    "venango": ["121", "1210", "042121", "14121"],
    "washington": ["125", "1250", "042125", "14125"],
    "fayette": ["051", "51", "510", "042051", "14051"],
    "somerset": ["111", "1110", "042111", "14111"],
    "perry": ["099", "99", "990", "042099", "14099"],
    "dauphin": ["043", "43", "430", "042043", "14043"],
    "forest": ["053", "53", "530", "042053", "14053"],
    "armstrong": ["005", "5", "50", "042005", "14005"],
    "tioga": ["117", "1170", "042117", "14117"],
    "cameron": ["023", "23", "230", "042023", "14023"],
    "elk": ["047", "47", "470", "042047", "14047"],
    "potter": ["105", "1050", "042105", "14105"],
    "warren": ["123", "1230", "042123", "14123"],
    "mckean": ["083", "83", "830", "042083", "14083"],
    "huntingdon": ["061", "61", "610", "042061", "14061"],
    "mifflin": ["087", "87", "870", "042087", "14087"],
    "bedford": ["009", "9", "90", "042009", "14009"],
    "erie": ["049", "49", "490", "042049", "14049"],
    "northumberland": ["097", "97", "970", "042097", "14097"],

    # Ohio Counties
    "harrison": ["067", "67", "670", "039067", "24067"],
    "noble": ["121", "1210", "039121", "24121"],
    "coshocton": ["031", "31", "310", "039031", "24031"],
    "hancock": ["063", "63", "630", "039063", "24063"],
    "guernsey": ["059", "59", "590", "039059", "24059"],
    "summit": ["153", "1530", "039153", "24153"],
    "monroe": ["111", "1110", "039111", "24111"],
    "cuyahoga": ["035", "35", "350", "039035", "24035"],
    "franklin": ["049", "49", "490", "039049", "24049"],
    "jefferson": ["081", "81", "810", "039081", "24081"]
}

# FIX: Make dictionary case-insensitive to match GEDCOM's capitalized strings
COUNTY_CODES.update({k.title(): v for k, v in COUNTY_CODES.items()})
COUNTY_CODES['McKean'] = COUNTY_CODES.get('mckean', [])


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


def dict_to_str(dik, indent):
    if indent == 1:
        out_str = '\n'
        tab = ''
    else:
        out_str = ''
        for i in range(1, indent + 2):
            tab = "   "

    for key, value in dik.items():

        out_str += f"{tab}{key} | {value}\n"
        if isinstance(value, dict):
            out_str += dict_to_str(value, indent + 1)
        elif isinstance(value, list):
            for i in value:
                if isinstance(i, str):
                    out_str += tab + tab + i
                # elif isinstance(i, dict):
                #     out_str += dict_to_str(i, indent + 9)

        else:
            out_str += f"{tab}{key} | {value}\n"

    return out_str + '\n'


def is_bpl_match(db_val, allowed_prefixes):
    """Safely compares IPUMS detailed codes to general base codes using integer math."""
    if not db_val: return False
    try:
        db_int = int(str(db_val).strip())
    except ValueError:
        return False

    for p in allowed_prefixes:
        try:
            p_int = int(p)
        except ValueError:
            continue
        if db_int == p_int or db_int // 100 == p_int:
            return True

    return False


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


def create_standard_dict(source, fam_id="", h_histid="", w_histid="",
                         h_first="", h_last="", h_byr=None, h_bmo="", h_bpl="", h_fbpl="", h_mbpl="",
                         w_first="", w_last="", w_byr=None, w_bmo="", w_bpl="", w_fbpl="", w_mbpl="",
                         marr_yr=None, num_children=0, score=0):
    """Creates an identical dictionary structure used for both GEDCOM targets and Census database matches."""
    return {
        'source': source, 'fam_id': fam_id, 'h_histid': h_histid, 'w_histid': w_histid,
        'h_first': h_first, 'h_last': h_last, 'h_byr': h_byr, 'h_bmo': h_bmo,
        'h_bpl': h_bpl, 'h_fbpl': h_fbpl, 'h_mbpl': h_mbpl, 'h_bpl_pref': [], 'h_fbpl_pref': [], 'h_mbpl_pref': [],
        'w_first': w_first, 'w_last': w_last, 'w_byr': w_byr, 'w_bmo': w_bmo,
        'w_bpl': w_bpl, 'w_fbpl': w_fbpl, 'w_mbpl': w_mbpl, 'w_bpl_pref': [], 'w_fbpl_pref': [], 'w_mbpl_pref': [],
        'marr_yr': marr_yr, 'num_children': num_children, 'score': score
    }


def get_bpl_num(birth_place):
    lnum = get_bpl_prefixes(birth_place)
    if not lnum: return None
    return int(lnum[0])


def extract_county(loc_str):
    """Strips city/state and returns only the county name."""
    if not loc_str: return ""
    parts = [p.strip() for p in loc_str.split(',')]
    if len(parts) >= 2:
        # If the last part is a country like USA, the logic shifts
        if parts[-1].upper() == 'USA':
            if len(parts) >= 3:  # e.g., "Clearfield, Pennsylvania, USA" or "City, County, State, USA"
                return parts[-3]
            else:
                return ""  # Not enough parts for a county (e.g., "Pennsylvania, USA")
        else:  # No "USA" at the end, e.g., "Pike, Clearfield, Pennsylvania"
            return parts[-2]
    return ""


def extract_state(loc_str):
    """Strips city/county and returns only the state name."""
    if not loc_str: return ""
    parts = [p.strip() for p in loc_str.split(',')]
    if len(parts) >= 1:
        # If the last part is a country like USA, the state is the one before it
        if parts[-1].upper() == 'USA':
            if len(parts) >= 2:  # e.g., "Pennsylvania, USA"
                return parts[-2]
            else:
                return ""  # Just "USA", no state
        else:  # No "USA" at the end, e.g., "Pennsylvania" or "Clearfield, Pennsylvania"
            return parts[-1]
    return ""


def safe_cast(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_check(value):
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def get_bpl_prefixes(birth_place, desc=""):
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
        "japan": ["501"], "south korea": ["502"], "korea": ["502"],
        # Canadian Provinces
        "alberta": ["150"], "nova scotia": ["150"], "new brunswick": ["150"], "ontario": ["150"]
    }

    for state, prefixes in crosswalk.items():
        if state in bp_lower:
            return prefixes

    return None


DB_ROWS = [
    "target_idx", "family_id", "clan_id", "match_year",  # 0-3
    "h_first_gedcom", "h_first_db", "h_last_gedcom", "h_last_db",  # 4-7
    "w_first_gedcom", "w_first_db", "w_last_gedcom", "w_last_db",  # 8-11
    "h_byr_gedcom", "h_byr_db", "w_byr_gedcom", "w_byr_db",  # 12-15
    "h_bpl_gedcom", "h_bpl_db", "w_bpl_gedcom", "w_bpl_db",  # 16-19
    "h_fbpl_gedcom", "h_fbpl_db", "h_mbpl_gedcom", "h_mbpl_db",  # 20-23
    "w_fbpl_gedcom", "w_fbpl_db", "w_mbpl_gedcom", "w_mbpl_db",  # 24-27
    "num_kids_gedcom", "num_kids_db",  # 28-29
    "kid_fp_gedcom", "kids_byr_sum_db",  # 30-31
    "county_db", "state_db"  # 32-33
]
