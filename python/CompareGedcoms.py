"""
-----------------------------------
File: CompareGedcoms.py

Summary: Performs a semantic diff between two GEDCOM files.
         Since genealogy software often scrambles internal IDs (@I1@) 
         and record orders during export, standard text diffs fail. 
         This script parses both files, links individuals based on their 
         Name and Birth Year, and outputs a human-readable report of 
         Added, Deleted, and Modified individuals.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import argparse
import os
import re
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
ORIGINAL_GED = os.path.join(project_root, "output", "AncestryUpload.ged")
ANCESTRY_GED = os.path.join(project_root, "output", "AncestryDownload.ged")
REPORT_OUT = os.path.join(project_root, "output", "gedcom_diff_report.txt")


def parse_gedcom_for_diff(file_path, logger):
    """
    Parses a GEDCOM file and extracts individuals into a dictionary.
    Uses a composite key of "FIRSTNAME LASTNAME_BIRTHYEAR" to allow linking 
    across different files where internal GEDCOM IDs might have changed.
    
    Args:
        file_path (str): The absolute path to the GEDCOM file.
        logger (logging.Logger): The active logger instance.
        
    Returns:
        dict: A dictionary of individuals mapped by their semantic key.
    """
    logger.info(f"Parsing GEDCOM: {file_path}")
    records = {}

    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return records

    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        current_indi = {}
        current_tag = None

        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split(" ", 2)
            level = parts[0]
            tag = parts[1] if len(parts) > 1 else ""
            val = parts[2] if len(parts) > 2 else ""

            # Found a new individual block
            if level == "0" and tag.startswith("@") and val == "INDI":
                # Save the previous person if they had a name
                if current_indi and "name" in current_indi:
                    key = f"{current_indi['name']}_{current_indi.get('birth_year', 'UNKNOWN')}".upper()
                    records[key] = current_indi

                current_indi = {"name": "Unknown", "birth_year": "UNKNOWN", "death_year": "UNKNOWN"}
                current_tag = None
                continue

            if not current_indi:
                continue

            # Track current tag to attach dates to the right event
            if level == "1":
                current_tag = tag
                if tag == "NAME":
                    current_indi["name"] = val.replace("/", "").strip()

            elif level == "2" and tag == "DATE":
                match = re.search(r'\d{4}', val)
                year = match.group() if match else "UNKNOWN"

                if current_tag == "BIRT":
                    current_indi["birth_year"] = year
                elif current_tag == "DEAT":
                    current_indi["death_year"] = year

        # Catch the final person in the file
        if current_indi and "name" in current_indi:
            key = f"{current_indi['name']}_{current_indi.get('birth_year', 'UNKNOWN')}".upper()
            records[key] = current_indi

    logger.info(f"  -> Extracted {len(records)} unique individuals.")
    return records


def compare_gedcoms(logger, orig_path, new_path, report_path):
    """
    Performs the semantic diff between two dictionaries of GEDCOM individuals 
    and writes the results to a formatted text report.
    """
    orig_records = parse_gedcom_for_diff(orig_path, logger)
    new_records = parse_gedcom_for_diff(new_path, logger)

    if not orig_records or not new_records:
        logger.error("Cannot perform diff: One or both GEDCOM files are missing or empty.")
        return

    orig_keys = set(orig_records.keys())
    new_keys = set(new_records.keys())

    added = new_keys - orig_keys
    deleted = orig_keys - new_keys
    common = orig_keys & new_keys

    changed = []
    for key in common:
        orig_death = orig_records[key].get("death_year", "UNKNOWN")
        new_death = new_records[key].get("death_year", "UNKNOWN")

        if orig_death != new_death:
            changed.append(
                f"{orig_records[key]['name']} (Born {orig_records[key]['birth_year']}) -> Death Year changed from {orig_death} to {new_death}")

    logger.info(f"Diff Complete: {len(added)} Added | {len(deleted)} Deleted | {len(changed)} Modified")
    logger.info(f"Writing detailed report to: {report_path}")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("========================================================\n")
        f.write("                GEDCOM SEMANTIC DIFF REPORT               \n")
        f.write("========================================================\n\n")

        f.write(f"Original File: {os.path.basename(orig_path)} ({len(orig_keys)} individuals)\n")
        f.write(f"Ancestry File: {os.path.basename(new_path)} ({len(new_keys)} individuals)\n\n")

        f.write(f"--- ADDED IN ANCESTRY ({len(added)}) ---\n")
        for key in sorted(added):
            f.write(f"  + {new_records[key]['name']} (Born: {new_records[key]['birth_year']})\n")

        f.write(f"\n--- DELETED IN ANCESTRY ({len(deleted)}) ---\n")
        for key in sorted(deleted):
            f.write(f"  - {orig_records[key]['name']} (Born: {orig_records[key]['birth_year']})\n")

        f.write(f"\n--- MODIFIED RECORDS ({len(changed)}) ---\n")
        for change in sorted(changed):
            f.write(f"  * {change}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diff two GEDCOM files semantically.")
    parser.add_argument("--orig", default=ORIGINAL_GED, help="The original pipeline GEDCOM")
    parser.add_argument("--new", default=ANCESTRY_GED, help="The updated GEDCOM from Ancestry")
    parser.add_argument("--report", default=REPORT_OUT, help="Where to save the text report")
    args = parser.parse_args()

    main_logger = gen_logging.setup_logging(logger_name="GEDCOM_DIFF")
    compare_gedcoms(main_logger, args.orig, args.new, args.report)
