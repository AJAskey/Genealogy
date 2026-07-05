"""
File: genealogy_classes.py

Summary: Defines the core data structures for the "Clean DB" phase.
         These classes represent the distilled lineage-linked data.

Design:
  - Individual: Represents a single person with an immutable "St. Joseph's ID".
                Contains pointers to parents (for bottom-up traversal) and
                a pointer back to the raw database (for rich attributes).
  - Family: Represents a nuclear family unit. Contains pointers to parents
            and a list of children (for top-down traversal).

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy

"""

import csv
import os
import psutil, gen_logging, common_utils
from duckdb.experimental.spark.sql.type_utils import convert_nested_type
from networkx.algorithms.d_separation import find_minimal_d_separator


class Individual:
    """
    Represents a single verified person in the family tree.
    This object will eventually be persisted into the 'Clean DB'.
    """
    __slots__ = ('in_use', 'family', 'st_joes_id', 'raw_composite_id', 'linenum',
                 'father_id', 'mother_id', 'adam_id', 'eve_id', 'status',

                 # Extracted individual census variables
                 'histid', 'year', 'serial', 'pernum', 'statefip', 'countyicp',
                 'relate', 'age', 'sex', 'race', 'marst', 'birthyr',
                 'bpl', 'fbpl', 'mbpl', 'momloc', 'poploc', 'namefrst', 'namelast',
                 'hhtype', 'famsize', 'nchild', 'nsibs')

    def __init__(self, data, linenum):
        # ---------------------------------------------------------
        # THE PRIMARY KEYS
        # ---------------------------------------------------------

        if linenum < 2:
            gen_logging.log_dict(logger, data)

        self.in_use = False

        # Two-way linking
        self.family = None
        # The permanent, immutable integer ID (e.g., 1, 2, 3...)
        self.st_joes_id = None

        # The pointer back to the raw IPUMS data (e.g., "192001_101_1_1")
        # This is how we look up the person's detailed history later.
        self.raw_composite_id = None

        # ---------------------------------------------------------
        # CORE ATTRIBUTES (Stored in Clean DB for quick reference)
        # ---------------------------------------------------------
        self.linenum = linenum

        # Explicitly extract only the useful demographic/matching variables.
        # The rest of the raw dictionary is discarded to save memory.
        self.histid = data.get('HISTID')
        self.year = data.get('YEAR')
        self.serial = common_utils.safe_cast(data.get('SERIAL'))
        self.pernum = data.get('PERNUM')
        self.statefip = data.get('STATEFIP')
        self.countyicp = data.get('COUNTYICP')
        self.relate = common_utils.safe_cast(data.get('RELATE'))
        self.age = common_utils.safe_cast(data.get('AGE'))
        self.sex = data.get('SEX')
        self.race = data.get('RACE')
        self.marst = common_utils.safe_cast(data.get('MARST'))
        self.birthyr = common_utils.safe_cast(data.get('BIRTHYR'))
        self.bpl = common_utils.safe_cast(data.get('BPLD') or data.get('BPL'))
        self.fbpl = common_utils.safe_cast(data.get('FBPL'))
        self.mbpl = common_utils.safe_cast(data.get('MBPL'))
        self.momloc = common_utils.safe_cast(data.get('MOMLOC'))
        self.poploc = common_utils.safe_cast(data.get('POPLOC'))
        self.namefrst = data.get('NAMEFRST')
        self.namelast = data.get('NAMELAST')
        self.hhtype = common_utils.safe_cast(data.get('HHTYPE'))
        self.famsize = common_utils.safe_cast(data.get('FAMSIZE'))
        self.nchild = common_utils.safe_cast(data.get('NCHILD'))
        self.nsibs = common_utils.safe_cast(data.get('NSIBS'))

        # ---------------------------------------------------------
        # LINEAGE POINTERS (For Bottom-Up Traversal)
        # ---------------------------------------------------------
        # These are St. Joes IDs pointing to other Individual records
        self.father_id = None
        self.mother_id = None

        # ---------------------------------------------------------
        # CLAN / BLOODLINE IDs (The Founders)
        # ---------------------------------------------------------
        self.adam_id = None  # Maps to st_joes_patrilineal_id
        self.eve_id = None  # Maps to st_joes_matrilineal_id
        self.status = None

    def __repr__(self):
        return f"<Individual [{self.st_joes_id}] line={self.linenum}>"

    def get_byr(self):
        if self.birthyr and str(self.birthyr).isnumeric():
            return int(self.birthyr)
        return 0

    def is_avail_hoh(self):
        if not self.in_use:
            if self.relate == 1:
                pass
        return False


class Family:
    """
    Represents a nuclear family unit (Parents + Children).
    This object will eventually be persisted into the 'Clean DB'.
    """

    def __init__(self, family_id):
        # The unique ID for this specific family unit (e.g., F1, F2...)
        self.family_id = family_id

        # ---------------------------------------------------------
        # LINEAGE POINTERS (For Top-Down Traversal)
        # ---------------------------------------------------------

        # if set to none, set to the husband and the wife.
        self.adam_id = None
        self.eve_id = None

        # These are St. Joes IDs pointing to Individual records

        self.father_id = None
        self.mother_id = None

        # A list of St. Joes IDs representing the children in this family
        self.children_ids = []

    def add_child(self, child_st_joes_id):
        """Adds a child's St. Joes ID to the family if not already present."""
        if child_st_joes_id not in self.children_ids:
            self.children_ids.append(child_st_joes_id)

    def __repr__(self):
        children_str = ", ".join(map(str, self.children_ids))
        return (f"Family ID: {self.family_id}\n"
                f"  Husband: {self.husband_id}\n"
                f"  Wife: {self.wife_id}\n"
                f"  Children: [{children_str}]\n"
                f"  Score: {self.score}")


class Person:
    """
    A temporary object to hold raw data from a CSV row during ingestion.
    The __repr__ is designed to output a human-readable, decoded format
    for easy logging and debugging.
    """

    def __init__(self, codebook=None, **kwargs):
        self._data = kwargs
        self._codebook = codebook
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        if not self._codebook:
            # Fallback to original CSV format if no codebook is provided
            return ",".join(str(v) for v in self._data.values())

        output = ["--- Person Record ---"]
        for var, code in self._data.items():
            # Attempt to look up the decoded label
            label = self._codebook.get_code_value(var, code)
            if label:
                # Show both the code and the human-readable label
                output.append(f"  {var:<15}: {code} ({label})")
            else:
                # If no label exists (e.g., for names, ages), just show the value
                output.append(f"  {var:<15}: {code}")
        return "\n".join(output)


def read():
    inds = []
    skipped_count = 0
    total_lines_read = 0

    if os.path.exists(checkpoint_file):

        logger.info(f"Found checkpoint file! Loading directly from {checkpoint_file}...")
        with open(checkpoint_file, mode='r', encoding='utf-8-sig', errors='replace') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                if total_lines_read > MAX_RECORDS:
                    return inds, total_lines_read, skipped_count

                total_lines_read += 1

                ind = Individual(row, total_lines_read)
                inds.append(ind)

                # Progress indicator for fast load
                if total_lines_read % 100000 == 0:
                    mem_percent = psutil.virtual_memory().percent
                    logger.info(
                        f"\nYear:{ind.year} Lines Loaded: {total_lines_read:,}, Individuals: {len(inds):,}, RAM: {mem_percent}%")
                elif total_lines_read % 10000 == 0:
                    logger.info(".")

        logger.info("\n--- Checkpoint Load Complete ---")

    else:
        logger.info("No checkpoint found. Parsing and filtering raw CSV...")
        total_lines_written = 0
        with open(csv_file, mode='r', encoding='utf-8-sig', errors='replace') as infile, \
                open(checkpoint_file, mode='w', encoding='utf-8-sig', newline='') as outfile:

            reader = csv.DictReader(infile, delimiter=',')

            # 'extrasaction=ignore' tells it to automatically throw away columns we don't care about!
            writer = csv.DictWriter(outfile, fieldnames=CHECKPOINT_FIELDS, extrasaction='ignore')
            writer.writeheader()

            for raw_row in reader:
                total_lines_read += 1
                row = {k.upper().strip(): v for k, v in raw_row.items() if k}

                yr = int(row.get('YEAR'))
                if total_lines_read % 1000000 == 0:
                    logger.info(f"YEAR : {yr}   linecnt = {total_lines_read:,} writecnt = {total_lines_written:,}")

                if total_lines_written > 1000000:
                    return inds, total_lines_read, skipped_count

                # 1. State Filter
                if row.get('STATEFIP') not in TARGET_STATES:
                    skipped_count += 1
                    continue

                    # 1. State Filter
                if row.get('COUNTYICP') not in TARGET_COUNTIES:
                    skipped_count += 1
                    continue

                # 2. Race Filter
                if row.get('RACE') not in TARGET_RACES:
                    skipped_count += 1
                    continue

                # 3. Marital Status Filter
                if row.get('SEX') == '1' and row.get('MARST') == '6':
                    skipped_count += 1
                    continue

                # --- PASSED ALL FILTERS ---
                # Write to the much smaller checkpoint file
                writer.writerow(row)
                total_lines_written += 1
                if total_lines_written % 10_000 == 0:
                    outfile.flush()
                    os.fsync(outfile.fileno())

                # Create the object and store in RAM
                ind = Individual(row, total_lines_read)
                inds.append(ind)

                if total_lines_read % 100000 == 0:
                    mem_percent = psutil.virtual_memory().percent
                    logger.info(
                        f"\nYear:{ind.year} Lines Read: {total_lines_read:,}, Individuals: {len(inds):,}, Skipped: {skipped_count:,}, RAM: {mem_percent}%")

                    if mem_percent > 95.0:
                        logger.info(
                            f"\n[!] WARNING: Memory limit reached ({mem_percent}%). Stopping CSV read to prevent crash!")
                        break

        logger.info("Returning fro bread()")

    return inds, total_lines_read, skipped_count


def get_godview(t_ind):
    logger.info(f"In godview with {len(inds)} inds")
    f_inds = []
    for i, ind in enumerate(inds):
        if ind.in_use or ind.year == t_ind.year: continue
        if t_ind.birthyr != ind.birthyr:
            continue
        if t_ind.bpl == ind.bpl and t_ind.mbpl == ind.mbpl and t_ind.fbpl == ind.fbpl:
            f_inds.append(ind)

    return f_inds


def process(inds):
    ind = get_a_hoh(inds)
    gen_logging.log_obj(logger, ind, "HOH")

    if ind:
        fams = get_serial_family(inds, ind.serial, ind.year)
        for i, fam in enumerate(fams):
            fam.in_use = True
            f_inds = get_godview(fam)
            gen_logging.log_obj(logger, fam, f"Before godview with tgt: {i + 1} len f_inds {len(f_inds)}")

            for j, f_ind in enumerate(f_inds):
                f_ind.in_use = True
                gen_logging.log_obj(logger, f_ind, f"Ind : {j + 1}")


def get_serial_family(inds, sn, yr):
    fams = []
    for i, ind in enumerate(inds):
        if not ind.in_use:
            if ind.serial == sn:
                fams.append(ind)
    return fams


def get_in_time(tgt, fam, yr):
    return None


def get_a_hoh(inds):
    for i, ind in enumerate(inds):
        if not ind.in_use:
            if ind.relate == 1 and ind.famsize > 1:
                return ind


# ==============================================================================
# MAIN
# ==============================================================================
''' 
 "RELATE": {
    "description": "Relationship to household head [general version]",
    "codes": {
      "01": "Head/Householder",
      "02": "Spouse",
      "03": "Child",
      "04": "Child-in-law",
      "05": "Parent",
      "06": "Parent-in-Law",
      "07": "Sibling",
      "08": "Sibling-in-Law",
      "09": "Grandchild",
      "10": "Other relatives",
      "11": "Partner, friend, visitor",
      "12": "Other non-relatives",
      "13": "Institutional inmates"
    }
  },
  "MARST": {
    "description": "Marital status",
    "codes": {
      "1": "Married, spouse present",
      "2": "Married, spouse absent",
      "3": "Separated",
      "4": "Divorced",
      "5": "Widowed",
      "6": "Never married/single",
      "9": "Blank, missing"
    }
  },
    "HHTYPE": {
    "description": "Household Type",
    "codes": {
      "0": "N/A",
      "1": "Married-couple family household",
      "2": "Male householder, no wife present",
      "3": "Female householder, no husband present",
      "4": "Male householder, living alone",
      "5": "Male householder, not living alone",
      "6": "Female householder, living alone",
      "7": "Female householder, not living alone",
      "9": "HHTYPE could not be determined"
    }
  },
    "NSIBS": {
    "description": "Number of own siblings in household",
  },
'''
if __name__ == '__main__':
    logger = gen_logging.setup_logging('genealogy_classes')

    # --- FILTERING CONFIGURATION ---
    # Define the states you want to include by their FIPS codes.
    # This is a placeholder. Replace with the FIPS codes for your 10 states.
    # Common examples: Pennsylvania ('42'), New York ('36'), Ohio ('39'), etc.
    # Using a set provides the fastest possible lookup.
    # TARGET_STATES = {'42', '08', '39', '31', '20'}  # <-- EDIT THIS LIST
    TARGET_STATES = {'42'}  # <-- EDIT THIS LIST
    TARGET_COUNTIES = {'150'}  # <-- EDIT THIS LIST
    # Define target races (IPUMS RACE code: '1' = White)
    TARGET_RACES = {'1'}  # <-- EDIT THIS LIST

    # --- CHECKPOINT CONFIGURATION ---
    csv_file = r"C:\tempc\ShortTermCSVfiles\usa_00122.csv"
    checkpoint_file = r"C:\tempc\ShortTermCSVfiles\usa_00122_filtered_checkpoint.csv"

    # We only save the exact columns our Individual class actually uses.
    # This cuts the checkpoint file size down drastically.
    CHECKPOINT_FIELDS = [
        'HISTID', 'YEAR', 'SERIAL', 'PERNUM', 'STATEFIP', 'COUNTYICP',
        'RELATE', 'AGE', 'SEX', 'RACE', 'MARST', 'BIRTHYR',
        'BPL', 'BPLD', 'FBPL', 'MBPL', 'MOMLOC', 'POPLOC', 'NAMEFRST', 'NAMELAST',
        'HHTYPE', 'FAMSIZE', 'NCHILD', 'NSIBS'
    ]

    MAX_RECORDS = 3_000_000
    inds, total_lines_read, skipped_count = read()

    if inds:
        process(inds)

    # Print a final newline to clean up the progress dots.
    logger.info("\n--- Processing Complete ---")
    logger.info(f"Total lines read: {total_lines_read:,}")
    logger.info(f"Individuals stored in memory: {len(inds):,}")
    logger.info(f"Individuals skipped: {skipped_count:,}")
    logger.info(f"Final memory footprint is for individuals from: {TARGET_STATES}")
    logger.info("--- End ---")
