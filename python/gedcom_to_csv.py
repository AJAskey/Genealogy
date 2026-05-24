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

import gen_logging


def convert_gedcom_to_csv(gedcom_path: str, csv_path: str, logger):
    """Reads a GEDCOM file and extracts individuals into a flat CSV."""

    if not os.path.exists(gedcom_path):
        logger.error(f"Cannot find GEDCOM file: {gedcom_path}")
        return

    logger.info(f"Parsing GEDCOM: {gedcom_path}")

    records = []
    current_person = {}
    current_tag = ""

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

        # Don't forget to append the very last person in the file!
        if current_person:
            records.append(current_person)

    if not records:
        logger.warning("No individuals found in GEDCOM.")
        return

    headers = ["gedcom_id", "full_name", "birth_date", "birth_place", "death_date", "death_place"]

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

    convert_gedcom_to_csv(input_file, output_file, main_logger)
