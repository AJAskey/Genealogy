"""
-----------------------------------
File: IngestGedcomFile.py

Summary: Reads a standard GEDCOM file, extracts all individuals,
         cleans their dates, drops living/privatized relatives, 
         and saves them into the GedcomVault.db to act as 
         Golden Record anchors for the census pipeline.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import re
import sqlite3
import sys

# Ensure we can import from the utils directory
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.append(project_root)
if script_dir not in sys.path:
    sys.path.append(script_dir)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# -> UPDATE THIS to point to your massive 10,000 person GEDCOM or your Askey GEDCOM
INPUT_GEDCOM = r"E:\Users\Andy\PycharmProjects\Genealogy\design\wm_francis.ged"

if os.name == 'nt':
    GEDCOM_DB = r"D:\Data\Genealogy_Data\GedcomVault.db"
else:
    GEDCOM_DB = os.path.expanduser("~/Genealogy_Data/GedcomVault.db")


def normalize_gedcom_date(date_str):
    """
    Normalizes messy GEDCOM dates into standard DD MMM YYYY formats.
    - "ABT 1850" -> "1 JUL 1850"
    - "MAR 1820" -> "15 MAR 1820"
    """
    if not date_str or not str(date_str).strip():
        return ""

    # Standardize to uppercase and strip whitespace
    clean_str = str(date_str).upper().strip()

    # Remove common GEDCOM modifiers
    modifiers = ["ABT ", "ABOUT ", "EST ", "CAL ", "BEF ", "AFT "]
    for mod in modifiers:
        clean_str = clean_str.replace(mod, "")

    clean_str = clean_str.strip()
    parts = clean_str.split()

    # CONDITION 1: Just a year (e.g., "1850") -> Make it 1 JUL
    if len(parts) == 1 and parts[0].isdigit() and len(parts[0]) == 4:
        return f"1 JUL {parts[0]}"

    # CONDITION 2: Month and Year (e.g., "MAR 1820") -> Make it 15 MAR
    elif len(parts) == 2:
        if parts[1].isdigit() and len(parts[1]) == 4:
            return f"15 {parts[0]} {parts[1]}"

    # CONDITION 3: Already has Day, Month, Year. Return cleaned string
    return clean_str


def parse_gedcom(file_path, logger):
    logger.info(f"Parsing GEDCOM file: {file_path}")
    individuals = {}
    families = {}
    current_obj = None
    obj_type = None

    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        current_tag = None

        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split(" ", 2)
            level = parts[0]
            tag = parts[1] if len(parts) > 1 else ""
            val = parts[2] if len(parts) > 2 else ""

            # Found a new top-level record
            if level == "0" and tag.startswith("@"):
                if val == "INDI":
                    current_obj = {"gedcom_id": tag.strip("@"), "father_id": None, "mother_id": None}
                    individuals[tag.strip("@")] = current_obj
                    obj_type = "INDI"
                elif val == "FAM":
                    current_obj = {"fam_id": tag.strip("@"), "husb": None, "wife": None, "chil": []}
                    families[tag.strip("@")] = current_obj
                    obj_type = "FAM"
                else:
                    obj_type = "OTHER"
                current_tag = None
                continue

            if not current_obj:
                continue

            if obj_type == "INDI":
                if level == "1":
                    current_tag = tag
                    if tag == "NAME":
                        current_obj["full_name"] = val.replace("/", "").strip()
                        name_parts = val.split("/")
                        current_obj["first_name"] = name_parts[0].strip() if len(name_parts) > 0 else ""
                        current_obj["last_name"] = name_parts[1].strip() if len(name_parts) > 1 else ""
                    elif tag == "SEX":
                        current_obj["sex"] = val.strip()
                elif level == "2":
                    if tag == "DATE":
                        if current_tag == "BIRT":
                            current_obj["birt_date"] = val
                        elif current_tag == "DEAT":
                            current_obj["deat_date"] = val
                    elif tag == "PLAC":
                        if current_tag == "BIRT":
                            current_obj["birth_place"] = val
                        elif current_tag == "DEAT":
                            current_obj["death_place"] = val
            elif obj_type == "FAM":
                if level == "1":
                    if tag == "HUSB":
                        current_obj["husb"] = val.strip("@")
                    elif tag == "WIFE":
                        current_obj["wife"] = val.strip("@")
                    elif tag == "CHIL":
                        current_obj["chil"].append(val.strip("@"))

        # Post-process to map parents to children
        for fam_id, fam in families.items():
            for child_id in fam["chil"]:
                if child_id in individuals:
                    individuals[child_id]["father_id"] = fam["husb"]
                    individuals[child_id]["mother_id"] = fam["wife"]

        records = list(individuals.values())

    logger.info(f"Extracted {len(records)} raw individuals.")
    return records


def ingest_to_db(records, logger):
    valid_records = []
    for indi in records:
        b_date_raw = indi.get("birt_date", "")

        # Filter out privatized/living people with missing birth dates
        if not b_date_raw or not b_date_raw.strip():
            continue

        b_date_norm = normalize_gedcom_date(b_date_raw)
        d_date_norm = normalize_gedcom_date(indi.get("deat_date", ""))

        # Extract strict 4-digit year for Splink AI to anchor onto
        match = re.search(r'\d{4}', b_date_norm)
        if match:
            birth_year = int(match.group())
        else:
            continue  # Skip if we cannot parse a valid 4-digit year

        valid_records.append((
            indi.get("gedcom_id"),
            indi.get("full_name"),
            indi.get("first_name"),
            indi.get("last_name"),
            indi.get("sex"),
            b_date_norm,
            birth_year,
            indi.get("birth_place"),
            d_date_norm,
            indi.get("death_place"),
            indi.get("father_id"),
            indi.get("mother_id"),
            indi.get("picture_url", "")
        ))

    logger.info(f"Filtered down to {len(valid_records)} historical anchors with valid birth years.")

    os.makedirs(os.path.dirname(GEDCOM_DB), exist_ok=True)
    with sqlite3.connect(GEDCOM_DB) as conn:
        conn.execute("PRAGMA journal_mode=WAL")

        # Drop the table so we can rebuild it with the new schema columns
        conn.execute("DROP TABLE IF EXISTS gedcom_records")
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS gedcom_records
                     (
                         gedcom_id
                         TEXT
                         PRIMARY
                         KEY,
                         full_name
                         TEXT,
                         first_name
                         TEXT,
                         last_name
                         TEXT,
                         sex
                         TEXT,
                         birth_date
                         TEXT,
                         birth_year
                         INTEGER,
                         birth_place
                         TEXT,
                         death_date
                         TEXT,
                         death_place
                         TEXT,
                         father_gedcom_id
                         TEXT,
                         mother_gedcom_id
                         TEXT,
                         picture_url
                         TEXT
                     )
                     ''')

        conn.executemany('''
                         INSERT INTO gedcom_records
                         (gedcom_id, full_name, first_name, last_name, sex, birth_date, birth_year, birth_place,
                          death_date,
                          death_place, father_gedcom_id, mother_gedcom_id, picture_url)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                         ''', valid_records)

    logger.info(f"Successfully saved {len(valid_records)} records to {GEDCOM_DB}.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging("GEDCOM_INGEST")
    extracted_data = parse_gedcom(INPUT_GEDCOM, main_logger)
    ingest_to_db(extracted_data, main_logger)
