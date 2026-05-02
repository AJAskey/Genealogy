"""
-----------------------------------
File: DumpVaultData.py

Summary: Reads and processes a SQLite database for the Askey/Erskine search.
         Dumps all fields through their getter modules for human-readable output.

Design:  - Opens one or more MasterVault SQLite databases
         - Searches by surname (and optionally first name)
         - Translates numeric codes to human-readable text via getters
         - Adapts automatically to whichever columns exist in each database
         - Writes timestamped output file

Inputs:  MasterVault_YYYY.db files on D: drive

Outputs: ../Output/<surname>_<timestamp>_dumpvault.txt

--------------------------------
"""

import os
import sqlite3
from datetime import datetime

from _get_bpl import get_bpl
from _get_bpld import get_bpld
from _get_city import get_city
from _get_race import get_race
from _get_raced import get_raced
from _get_relate import get_relate
from _get_related import get_related
from _get_sex import get_sex
from _get_stateicp import get_stateicp
from _get_versionhist import get_versionhist


# Uncomment this when you have the county getter ready:
# from _get_county import get_county


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def safe_int(val):
    """Return int(val) or 0 if it fails."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def col_exists(columns, name):
    """Check whether a column name exists in the detected column list."""
    return name.lower() in [c.lower() for c in columns]


# ---------------------------------------------------------------------------
# SEARCH FUNCTION
# ---------------------------------------------------------------------------

def search_by_name(db_path, last_name_prefix, first_name="", output_file="tmp.txt"):
    """
    Searches the database using wildcards to catch spelling variations.
    Translates numeric codes through getter modules.
    Adapts the SELECT list to whatever columns the database actually has.
    Writes results to output_file and prints to console.
    """

    # Pull census year from the database filename e.g. MasterVault_1880.db -> 1880
    try:
        basename = os.path.basename(db_path)
        cenyr_str = basename.split("_")[1][:4]
        cenyr = int(cenyr_str)
    except Exception:
        cenyr_str = "????"
        cenyr = 0

    if not os.path.exists(db_path):
        print(f"Skipping: {db_path} (File not found)")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- Detect what columns this database actually has ---
    cursor.execute("PRAGMA table_info(population)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"\n[ Database: {os.path.basename(db_path)} | Census Year: {cenyr_str} ]")
    print(f"Detected Columns: {columns}\n")

    # --- Build the SELECT list from columns that actually exist ---
    # These are the columns we WANT; we only ask for them if they're present.
    wanted = [
        "serial", "pernum", "namefrst", "namelast",
        "age", "sex", "race", "raced",
        "relate",
        "related",  # not in all years -- handled below
        "stateicp", "countyicp", "city",
        "bpl", "bpld",
        "birthyr",
        "versionhist",  # not in all years -- handled below
    ]

    select_cols = [c for c in wanted if col_exists(columns, c)]
    select_sql = ", ".join(select_cols)

    wildcard_last = last_name_prefix.upper() + '%'

    base_query = f"SELECT {select_sql} FROM population WHERE namelast LIKE ?"

    if first_name:
        wildcard_first = first_name.upper() + '%'
        cursor.execute(base_query + " AND namefrst LIKE ?",
                       (wildcard_last, wildcard_first))
    else:
        cursor.execute(base_query, (wildcard_last,))

    results = cursor.fetchall()

    with open(output_file, "a", encoding="utf-8") as f:

        if results:
            header = f"\n{'=' * 70}\n"
            header += f"  {len(results)} result(s) for '{last_name_prefix}'"
            header += f" in {os.path.basename(db_path)}\n"
            header += f"{'=' * 70}\n"
            f.write(header)
            print(header)
        else:
            msg = f"No records found in {os.path.basename(db_path)}.\n"
            f.write(msg)
            print(msg)
            conn.close()
            return

        0
        for row in results:

            # Build a dict so we can safely pull optional columns
            row_dict = dict(zip(select_cols, row))

            serial = row_dict.get("serial", "")
            pernum = row_dict.get("pernum", "")
            fname = row_dict.get("namefrst", "")
            lname = row_dict.get("namelast", "")
            age = row_dict.get("age", "")
            sex = row_dict.get("sex", "")
            race = row_dict.get("race", "")
            raced = row_dict.get("raced", "")
            relate = row_dict.get("relate", "")
            related = row_dict.get("related", None)  # may not exist
            stateicp = row_dict.get("stateicp", "")
            countyicp = row_dict.get("countyicp", "")
            city = row_dict.get("city", "")
            bpl = row_dict.get("bpl", "")
            bpld = row_dict.get("bpld", "")
            birthyr = row_dict.get("birthyr", None)
            versionhist = row_dict.get("versionhist", None)  # may not exist

            # --- Calculated birth year ---
            if birthyr:
                byr = safe_int(birthyr)
            else:
                byr = cenyr - safe_int(age) if age else 0

            # --- State name ---
            state_name = get_stateicp(stateicp)

            # --- County (uncomment when getter is ready) ---
            # county_name = get_county(state_name, countyicp)
            county_name = f"County code {countyicp}"  # placeholder until getter exists

            # --- Relation display -- show detail only if column exists ---
            if related is not None:
                relation_str = f"{get_relate(relate)}  /  {get_related(related)}"
            else:
                relation_str = get_relate(relate)

            # --- Version display -- only if column exists ---
            version_str = get_versionhist(versionhist) if versionhist is not None else "N/A"

            # --- Build human-readable block ---
            lines = [
                f"",
                f"  ID:          {cenyr_str}-{serial}-{pernum}",
                f"  Name:        {fname or '(none)'} {lname or '(none)'}",
                f"  Born:        {byr if byr else '?'}  (age {age} in {cenyr_str})",
                f"  Sex:         {get_sex(sex)}",
                f"  Race:        {get_race(race)}  /  {get_raced(raced)}",
                f"  Relation:    {relation_str}",
                f"  Location:    {state_name} / {county_name} / {get_city(city)}",
                f"  Birthplace:  {get_bpl(bpl)}  /  {get_bpld(bpld)}",
                # f"  Version:     {version_str}",
                f"  {'-' * 60}",
            ]

            block = "\n".join(lines) + "\n"
            print(block)
            f.write(block)

        conn.close()
        print(f"\n[ Done with {os.path.basename(db_path)} ]\n")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == '__main__':

    target_surname = "SMITH"  # Change to % for everything, or a surname prefix

    now = datetime.now()
    formatted_date = now.strftime("_%Y%m%d-%H%M%S")
    outfile = r"../Output/" + target_surname + formatted_date + "_dumpvault.txt"
    print(f"Output file: {outfile}\n")

    # Vault paths on D: drive -- uncomment decades you want to search
    vaults = [
        # r"D:\Data\Genealogy_Data\MasterVault_1850.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1860.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1870.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1880.db",
        r"D:\Data\Genealogy_Data\MasterVault_1900.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1910.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1920.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1930.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1940.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1950.db",
    ]

    print(f"Starting search through Vaults for surname: {target_surname}")
    for db in vaults:
        search_by_name(db, last_name_prefix=target_surname, output_file=outfile)

    print(f"\n[ Analysis Complete. Check {outfile} for results. ]")
