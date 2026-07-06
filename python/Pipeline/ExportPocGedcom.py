import duckdb
import os
import time
from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MATCH_DB_PATH = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
OUTPUT_GEDCOM = os.path.join(BASE_DATA_DIR, "TimeMachine_POC.ged")

TARGET_CLAN_LIMIT = 10000  # How many families to extract for the POC

# ==============================================================================
# ROTATING FAKE NAMES
# ==============================================================================
MALE_NAMES = ["James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
              "Daniel", "Matthew", "Anthony", "Mark", "Donald", "Steven", "Paul", "Andrew", "Joshua", "Kenneth"]
FEMALE_NAMES = ["Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen",
                "Nancy", "Lisa", "Betty", "Margaret", "Sandra", "Ashley", "Kimberly", "Emily", "Donna", "Michelle"]
SURNAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
            "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
            "Lee", "Perez", "Thompson", "White", "Harris"]


def get_fake_name(person_id, clan_id, sex_int):
    """Uses the numeric IDs to deterministically pick a realistic rotating name."""
    # Hash the IDs to get a consistent index
    pid_hash = hash(person_id)

    last_name = SURNAMES[clan_id % len(SURNAMES)]

    if sex_int == 1:
        first_name = MALE_NAMES[pid_hash % len(MALE_NAMES)]
    else:
        first_name = FEMALE_NAMES[pid_hash % len(FEMALE_NAMES)]

    return first_name, last_name


def main():
    logger = gen_logging.setup_logging('GedcomExporter')
    logger.info("=====================================================================")
    logger.info("  TIME MACHINE GEDCOM POC EXPORTER")
    logger.info("=====================================================================")

    if not os.path.exists(MATCH_DB_PATH):
        logger.error(f"CRITICAL: Match DB not found at {MATCH_DB_PATH}")
        return

    logger.info(f"Targeting Time Machine: {MATCH_DB_PATH}")
    logger.info(f"Extracting {TARGET_CLAN_LIMIT} Clans for FTM Proof of Concept...")

    con = duckdb.connect(database=MATCH_DB_PATH, read_only=True)

    # -------------------------------------------------------------------------
    # STEP 1: Query the people and figure out their family roles
    # -------------------------------------------------------------------------
    logger.info("Querying DuckDB for family structures...")
    start_time = time.time()

    # We join tm_individuals and tm_families to determine who was the Head, Spouse, or Child
    query = f"""
        WITH target_clans AS (
            SELECT clan_id FROM main.clan_details LIMIT {TARGET_CLAN_LIMIT}
        ),
        person_roles AS (
            SELECT i.person_id, 
                   i.clan_id, 
                   i.sex_int, 
                   i.byr_int,
                   MAX(CASE 
                       WHEN i.histid = f.head_histid THEN 1 
                       WHEN i.histid = f.spouse_histid THEN 2 
                       ELSE 3 
                   END) as role_score
            FROM main.tm_individuals i
            JOIN main.tm_families f ON i.family_id = f.family_id
            JOIN target_clans tc ON i.clan_id = tc.clan_id
            WHERE i.person_id IS NOT NULL
            GROUP BY i.person_id, i.clan_id, i.sex_int, i.byr_int
        )
        SELECT person_id, clan_id, sex_int, byr_int, role_score 
        FROM person_roles
        ORDER BY clan_id, role_score;
    """

    results = con.execute(query).fetchall()
    logger.info(f"Extracted {len(results)} individuals. Generating GEDCOM...")

    # Group the results by clan_id to easily build the FAM records later
    clans = {}
    for row in results:
        p_id, c_id, sex_int, byr_int, role = row
        if c_id not in clans:
            clans[c_id] = {'husb': None, 'wife': None, 'chil': []}

        if role == 1 and sex_int == 1 and not clans[c_id]['husb']:
            clans[c_id]['husb'] = p_id
        elif (role == 2 or (role == 1 and sex_int == 2)) and not clans[c_id]['wife']:
            clans[c_id]['wife'] = p_id
        else:
            clans[c_id]['chil'].append(p_id)

    # -------------------------------------------------------------------------
    # STEP 2: Write the GEDCOM File
    # -------------------------------------------------------------------------
    with open(OUTPUT_GEDCOM, "w", encoding="utf-8") as f:
        # Write GEDCOM Header
        f.write("0 HEAD\n")
        f.write("1 SOUR DuckDB_TimeMachine\n")
        f.write("1 GEDC\n")
        f.write("2 VERS 5.5.1\n")
        f.write("2 FORM LINEAGE-LINKED\n")
        f.write("1 CHAR UTF-8\n")

        # Write Individuals (INDI)
        for row in results:
            p_id, c_id, sex_int, byr_int, role = row
            first_name, last_name = get_fake_name(p_id, c_id, sex_int)
            sex_char = "M" if sex_int == 1 else "F"

            f.write(f"0 @I{p_id}@ INDI\n")
            f.write(f"1 NAME {first_name} /{last_name}/\n")
            f.write(f"1 SEX {sex_char}\n")
            f.write("1 BIRT\n")
            if byr_int:
                f.write(f"2 DATE {byr_int}\n")
            f.write(f"1 FAMS @F{c_id}@\n" if role in [1, 2] else f"1 FAMC @F{c_id}@\n")

        # Write Families (FAM)
        for c_id, fam_data in clans.items():
            f.write(f"0 @F{c_id}@ FAM\n")
            if fam_data['husb']:
                f.write(f"1 HUSB @I{fam_data['husb']}@\n")
            if fam_data['wife']:
                f.write(f"1 WIFE @I{fam_data['wife']}@\n")
            for child_id in fam_data['chil']:
                f.write(f"1 CHIL @I{child_id}@\n")

        # Write EOF
        f.write("0 TRLR\n")

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"SUCCESS! GEDCOM exported to {OUTPUT_GEDCOM} in {elapsed} seconds.")
    logger.info(f"Total Families: {len(clans)}")
    logger.info(f"Total Individuals: {len(results)}")


if __name__ == '__main__':
    main()
