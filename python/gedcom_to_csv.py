"""
-----------------------------------
File: gedcom_to_csv.py

Summary: Parses a standard GEDCOM file and flattens it into a CSV.
         Extracts Individuals (INDI) and grabs their birth, death,
         and names so they can be ingested as Auxiliary Data.
         
Inputs:  A standard .ged file
Outputs: A tabular .csv file
-----------------------------------
"""

import csv
import os
import re
from datetime import datetime

import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Privacy Switch: Set to True ONLY if the user explicitly consents to media backup
EXTRACT_MEDIA = False

# Privacy Switch: Prevent processing of potentially living people (72-year Census rule)
EXCLUDE_LIVING = True


def is_likely_living(person_dict: dict) -> bool:
    """Heuristic to determine if a person in the GEDCOM is still living."""
    # If there is any death data, they are not living.
    if person_dict.get("death_date") or person_dict.get("death_place"):
        return False
        
    # Try to extract a 4-digit birth year
    b_date = person_dict.get("birth_date", "")
    match = re.search(r'\d{4}', b_date)
    if match:
        b_year = int(match.group())
        current_year = datetime.now().year
        # Using the 72-year rule (similar to US Census record releases)
        if current_year - b_year < 72:
            return True
            
    return False

def convert_gedcom_to_csv(gedcom_path: str, csv_path: str, logger, extract_media: bool = False, exclude_living: bool = True):
    """Reads a GEDCOM file and extracts individuals into a flat CSV."""

    if not os.path.exists(gedcom_path):
        logger.error(f"Cannot find GEDCOM file: {gedcom_path}")
        return

    logger.info(f"Parsing GEDCOM: {gedcom_path}")

    records = []
    current_person = {}
    current_tag = ""
    skipped_media_count = 0
    skipped_living_count = 0

    # Open using UTF-8 to handle any special characters in external trees safely
    with open(gedcom_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split(' ', 2)
            level = parts[0]
            tag = parts[1] if len(parts) > 1 else ""
            value = parts[2] if len(parts) > 2 else ""

            # When we hit a new individual (0 @I123@ INDI)
            if level == "0" and value == "INDI":
                if current_person:
                    if exclude_living and is_likely_living(current_person):
                        skipped_living_count += 1
                    else:
                        records.append(current_person)
                current_person = {"gedcom_id": tag}
                current_tag = ""

            elif level == "1":
                current_tag = tag
                if tag == "NAME":
                    # Names usually come in as "First Middle /Last/"
                    clean_name = value.replace("/", "").strip()
                    current_person["full_name"] = clean_name
            elif level == "2":
                if current_tag == "BIRT" and tag == "DATE":
                    current_person["birth_date"] = value
                elif current_tag == "BIRT" and tag == "PLAC":
                    current_person["birth_place"] = value
                elif current_tag == "DEAT" and tag == "DATE":
                    current_person["death_date"] = value
                elif current_tag == "DEAT" and tag == "PLAC":
                    current_person["death_place"] = value
                elif current_tag == "OBJE" and tag == "FILE":
                    if not extract_media:
                        skipped_media_count += 1
                        continue
                    # Ancestry stores media links in the FILE tag of an OBJE block
                    if "picture_url" not in current_person:
                        current_person["picture_url"] = value
                    else:
                        # Pipe-delimit multiple photos
                        current_person["picture_url"] += f" | {value}"

        # Don't forget to append the very last person in the file!
        if current_person:
            if exclude_living and is_likely_living(current_person):
                skipped_living_count += 1
            else:
                records.append(current_person)

    if not records:
        logger.warning("No individuals found in GEDCOM.")
        return
        
    if not extract_media and skipped_media_count > 0:
        logger.info(f"Privacy Mode ON: Ignored {skipped_media_count} media links found in the GEDCOM.")
        
    if exclude_living and skipped_living_count > 0:
        logger.info(f"Privacy Mode ON: Excluded {skipped_living_count} potentially living individuals.")

    headers = ["gedcom_id", "full_name", "birth_date", "birth_place", "death_date", "death_place", "picture_url"]

    logger.info(f"Writing {len(records):,} records to {csv_path}")

    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)

    logger.info("Conversion complete!")


if __name__ == "__main__":
    # Set up the console logger
    main_logger = gen_logging.setup_logging("GEDCOM_TO_CSV")

    # You can change these paths when you are ready to process an external file!
    input_file = r"E:\Haley\Documents\CaptThom\CaptThom-ftm.ged"
    output_file = r"E:\Users\Andy\PycharmProjects\Genealogy\output\thom.csv"

    convert_gedcom_to_csv(input_file, output_file, main_logger, extract_media=EXTRACT_MEDIA, exclude_living=EXCLUDE_LIVING)
