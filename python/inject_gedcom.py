"""
-----------------------------------
File: inject_gedcom.py

Summary: The final step in the External GEDCOM Enrichment Pipeline.
         Takes a dictionary/CSV of matched census facts and safely 
         injects them into a user's original GEDCOM file as new 
         '1 CENS' events without altering their existing tree structure.
-----------------------------------
"""

import csv
import os
import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
ORIGINAL_GEDCOM = r"E:\Users\Andy\PycharmProjects\Genealogy\output\friend_original.ged"
ENRICHED_GEDCOM = r"E:\Users\Andy\PycharmProjects\Genealogy\output\friend_enriched.ged"
MATCHES_CSV = r"E:\Users\Andy\PycharmProjects\Genealogy\output\matched_facts.csv"


def load_matches(csv_path, logger):
    """
    Loads the matched census data from Splink/DuckDB into a dictionary.
    Expected CSV columns: gedcom_id, census_year, location, age, notes
    """
    matches = {}
    if not os.path.exists(csv_path):
        logger.warning(f"No matches file found at {csv_path}. Skipping.")
        return matches
        
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            g_id = row['gedcom_id']
            if g_id not in matches:
                matches[g_id] = []
            matches[g_id].append(row)
            
    logger.info(f"Loaded new facts for {len(matches)} individuals.")
    return matches


def inject_facts_to_gedcom(original_ged, output_ged, matches, logger):
    """
    Reads the original GEDCOM line by line. When it finishes reading an 
    Individual (INDI) block, it checks if we have new facts for them. 
    If so, it injects the new CENS tags before moving to the next record.
    """
    logger.info("Injecting facts into GEDCOM...")
    
    with open(original_ged, 'r', encoding='utf-8', errors='replace') as infile, \
         open(output_ged, 'w', encoding='utf-8') as outfile:
        
        current_indi = None
        
        for line in infile:
            # Whenever we hit ANY new '0' level record (a new person, a family, or the end of the file)
            if line.startswith("0 "):
                # 1. If we just finished reading an INDI that has matches, inject the facts NOW
                if current_indi and current_indi in matches:
                    for fact in matches[current_indi]:
                        outfile.write("1 CENS\n")
                        if fact.get('census_year'):
                            outfile.write(f"2 DATE {fact['census_year']}\n")
                        if fact.get('location'):
                            outfile.write(f"2 PLAC {fact['location']}\n")
                        outfile.write("2 SOUR U.S. Federal Census (Provided by St. Joe's Genealogy Engine)\n")
                        if fact.get('notes'):
                            outfile.write("2 DATA\n")
                            outfile.write(f"3 TEXT {fact['notes']}\n")
                    
                    logger.info(f"Enriched {current_indi} with {len(matches[current_indi])} new census facts.")
                
                # 2. Update our tracker. Are we entering a NEW individual block?
                if line.strip().endswith(" INDI"):
                    current_indi = line.split(' ')[1]  # Extracts the @I123@ part
                else:
                    current_indi = None  # We entered a FAM, SOUR, or TRLR block
            
            # Write the original line to the new file exactly as we found it
            outfile.write(line)
            
    logger.info(f"Successfully generated enriched GEDCOM at: {output_ged}")

if __name__ == "__main__":
    logger = gen_logging.setup_logging("GEDCOM_INJECTOR")
    
    matched_facts = load_matches(MATCHES_CSV, logger)
    inject_facts_to_gedcom(ORIGINAL_GEDCOM, ENRICHED_GEDCOM, matched_facts, logger)