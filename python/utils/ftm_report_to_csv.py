"""
-----------------------------------
File: ftm_report_to_csv.py

Summary: Parses an indented Family Tree Maker descendant text report
         and flattens it into a tabular CSV.
         Uses Natural Language Processing (Regex) to read complete sentences
         ("He married...", "She was born...") and extracts husbands and wives
         onto the exact same row to create the 10-Variable Couple Fingerprint.
         Also bridges manually cleaned locations and counts children.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0 http://www.apache.org/licenses/LICENSE-2.0
-----------------------------------
"""

import csv
import os
import re
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [os.path.join(project_root, 'python'), project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging


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


def clean_name(name_raw):
    """Strips parentheticals and generation numbers (e.g., David Thomas2 (Thomas1) -> David Thomas)"""
    name = re.sub(r'\([^\)]*\)', '', name_raw)
    name = re.sub(r'\d+', '', name)
    return " ".join(name.split()).strip()


def split_name(full_name):
    """Safely splits a string into first/middle and last names, handling suffixes."""
    # Remove commas that might separate suffixes (e.g., "Smith, Jr.")
    tokens = full_name.replace(',', '').strip().split()
    if not tokens: return "", ""
    if len(tokens) == 1: return tokens[0], ""

    suffixes = {'jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v'}
    if len(tokens) >= 3 and tokens[-1].lower() in suffixes:
        return " ".join(tokens[:-2]), f"{tokens[-2]} {tokens[-1]}"

    return " ".join(tokens[:-1]), tokens[-1]


def extract_year_place(info_str):
    """Extracts a 4-digit year and the text following 'in' from a sentence fragment."""
    year = ""
    place = ""
    yr_m = re.search(r'\b(1[456789]\d\d|20\d\d)\b', info_str)
    if yr_m: year = yr_m.group(1)

    pl_m = re.search(r'\bin\s+(.*?)(?:\(|$)', info_str, re.IGNORECASE)
    if pl_m: place = pl_m.group(1).strip()

    return year, place


def convert_ftm_report(input_file, cleaned_csv_file, couples_csv, logger):
    if not os.path.exists(input_file):
        logger.error(f"Cannot find input file: {input_file}")
        return

    # DECISION: Load the manually cleaned CSV to preserve all your hard work!
    cleaned_locations = {}
    if os.path.exists(cleaned_csv_file):
        with open(cleaned_csv_file, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            for row in reader:
                fname = row.get('first_name', '').strip().lower()
                lname = row.get('last_name', '').strip().lower()
                byr = row.get('birth_year', '').strip()
                key = f"{fname}_{lname}_{byr}"
                cleaned_locations[key] = {
                    'bp': row.get('birth_place', '').strip(),
                    'fbp': row.get('father_birth_place', '').strip(),
                    'mbp': row.get('mother_birth_place', '').strip()
                }

    logger.info(f"NLP Parsing Narrative FTM report: {input_file}")

    records = []
    current_parents = []

    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not any(row): continue
            # Flatten the entire row to a string
            line = " ".join([str(c).strip() for c in row if str(c).strip()])

            # If this line doesn't declare a birth, it's not a primary record
            if "was born" not in line: continue

            prefix = line.split("was born")[0].lower()
            is_child_line = bool(re.search(r'^\s*\d*\s*[ivxlc]+\.\s+', prefix))

            if is_child_line:
                for p_couple in current_parents:
                    p_couple[12] += 1
            else:
                current_parents = []

            # --- EXTRACT PRIMARY PERSON ---
            primary_name_raw = line.split("was born")[0]
            primary_name_raw = re.sub(r'^\s*\d+\.\s*', '', primary_name_raw)  # Strip leading IDs
            primary_name_raw = re.sub(r'^\s*[ivxlc]+\.\s*', '', primary_name_raw, flags=re.IGNORECASE)

            p1_first, p1_last = split_name(clean_name(primary_name_raw))

            # DECISION: Filter out any primary individual with a blank or placeholder last name
            if not p1_last or '--' in p1_last or 'Hidden' in p1_last or '[' in p1_last:
                continue

            # Determine Sex via pronouns
            p1_sex = "1" if re.search(r'\bHe\b', line) else "2" if re.search(r'\bShe\b', line) else ""

            p1_birth_chunk = line.split("was born")[1].split(".")[0]
            p1_byr, p1_bpl_raw = extract_year_place(p1_birth_chunk)

            # Lookup cleaned locations
            p1_key = f"{p1_first.lower()}_{p1_last.lower()}_{p1_byr}"
            p1_locs = cleaned_locations.get(p1_key, {})
            p1_bpl = extract_state(p1_locs.get('bp') or p1_bpl_raw)
            p1_fbpl = extract_state(p1_locs.get('fbp', ''))
            p1_mbpl = extract_state(p1_locs.get('mbp', ''))

            spouses_found = 0

            # --- EXTRACT SPOUSES ---
            if " married " in line:
                m_chunks = line.split(" married ")[1:]  # Can be married multiple times!
                for spouse_chunk in m_chunks:
                    sp_first, sp_last, sp_byr, sp_bpl, sp_bpl_raw = "", "", "", "", ""
                    sp_fbpl, sp_mbpl = "", ""
                    sp_sex = "2" if p1_sex == "1" else "1"

                    spouse_chunk = re.sub(r'^\s*\(\d+\)\s+', '', spouse_chunk)  # Strip (1) if multiple
                    sp_name_match = re.search(r'^(.*?)(?:, daughter|, son|\s+on\b|\s+in\b|\s+about\b|\.|$)',
                                              spouse_chunk)
                    if sp_name_match:
                        sp_name_raw = sp_name_match.group(1).strip()
                        if "unknown" not in sp_name_raw.lower():
                            sp_first, sp_last = split_name(clean_name(sp_name_raw))

                            # DECISION: Filter out spouses with blank or placeholder last names
                            if not sp_last or '--' in sp_last or 'Hidden' in sp_last or '[' in sp_last:
                                continue

                            sp_b_match = re.search(r'(?:He|She) was born (.*?)\.', spouse_chunk)
                            if sp_b_match:
                                sp_byr, sp_bpl_raw = extract_year_place(sp_b_match.group(1))

                            # Lookup cleaned locations for spouse
                            sp_key = f"{sp_first.lower()}_{sp_last.lower()}_{sp_byr}"
                            sp_locs = cleaned_locations.get(sp_key, {})
                            sp_bpl = extract_state(sp_locs.get('bp') or sp_bpl_raw)
                            sp_fbpl = extract_state(sp_locs.get('fbp', ''))
                            sp_mbpl = extract_state(sp_locs.get('mbp', ''))

                    if p1_sex == "1" or sp_sex == "2":
                        couple = [p1_first, p1_last, p1_byr, p1_bpl, p1_fbpl, p1_mbpl, sp_first, sp_last, sp_byr,
                                  sp_bpl, sp_fbpl, sp_mbpl, 0]
                    else:
                        couple = [sp_first, sp_last, sp_byr, sp_bpl, sp_fbpl, sp_mbpl, p1_first, p1_last, p1_byr,
                                  p1_bpl, p1_fbpl, p1_mbpl, 0]

                    records.append(couple)
                    if not is_child_line:
                        current_parents.append(couple)
                    spouses_found += 1

            # Lone wolf (No spouse)
            if spouses_found == 0:
                if p1_sex == "1":
                    couple = [p1_first, p1_last, p1_byr, p1_bpl, p1_fbpl, p1_mbpl, "", "", "", "", "", "", 0]
                else:
                    couple = ["", "", "", "", "", "", p1_first, p1_last, p1_byr, p1_bpl, p1_fbpl, p1_mbpl, 0]

                records.append(couple)
                if not is_child_line:
                    current_parents.append(couple)

    logger.info(f"  -> Extracted {len(records)} nuclear family units!")

    headers = [
        'h_first', 'h_last', 'h_byr', 'h_bpl', 'h_fbpl', 'h_mbpl',
        'w_first', 'w_last', 'w_byr', 'w_bpl', 'w_fbpl', 'w_mbpl', 'num_children'
    ]
    with open(couples_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(records)


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging("FTM_PARSER")
    input_file = os.path.join(project_root, "design", "Descendants of Thomas Askey.csv")
    cleaned_csv_file = os.path.join(project_root, "gedcom_sources", "ftm_extracted.csv")
    couples_csv_file = os.path.join(project_root, "gedcom_sources", "ftm_couples.csv")
    convert_ftm_report(input_file, cleaned_csv_file, couples_csv_file, main_logger)
