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

from _get_bpld import get_bpld
from _get_city import get_city
from _get_sex import get_sex
from _get_stateicp import get_stateicp
from county_lookup import CountyByCode


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

def search_by_name(db_path, last_name_prefix, county_lookup, first_name="", output_file="tmp.txt"):
    """
    Searches the database using wildcards to catch spelling variations.
    Translates numeric codes through getter modules.
    Adapts the SELECT list to whatever columns the database actually has.
    Writes results to output_file and prints to console.

    Args:
        db_path:          Full path to the MasterVault SQLite database
        last_name_prefix: Surname to search (wildcarded automatically)
        county_lookup:    CountyByCode instance (loaded once in main)
        first_name:       Optional first name prefix
        output_file:      Path to the output text file
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
        "year", "serial", "pernum",
        "namefrst", "namelast",
        "age", "birthyr", "sex", "raced", "related", "bpld",
        "stateicp", "countyicp", "city",
        "momloc", "poploc", "nsibs", "nchild", "nfathers", "famsize",
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

        if not results:
            msg = f"No records found in {os.path.basename(db_path)}.\n"
            f.write(msg)
            print(msg)
            conn.close()
            return

        header = (
            f"\n{'=' * 70}\n"
            f"  {len(results)} result(s) for '{last_name_prefix}'"
            f" in {os.path.basename(db_path)}\n"
            f"{'=' * 70}\n"
        )
        f.write(header)
        print(header)

        # -------------------------------------------------------------------
        # Loop over every result row -- everything below is inside this loop
        # -------------------------------------------------------------------
        for row in results:
            # Build a dict so we can safely pull optional columns
            row_dict = dict(zip(select_cols, row))

            year = row_dict.get("year", "")
            serial = row_dict.get("serial", "")
            pernum = row_dict.get("pernum", "")
            fname = row_dict.get("namefrst", "")
            lname = row_dict.get("namelast", "")
            age = row_dict.get("age", "")
            birthyr = row_dict.get("birthyr", "")

            momloc = row_dict.get("momloc", "")
            poploc = row_dict.get("poploc", "")

            stateicp = row_dict.get("stateicp", "")
            countyicp = row_dict.get("countyicp", "")
            city = row_dict.get("city", "")

            nfathers = row_dict.get("nfathers", "")
            nchild = row_dict.get("nchild", "")
            nsibs = row_dict.get("nsibs", "")
            famsize = row_dict.get("famsize", "")

            related = row_dict.get("related", "")
            sex = row_dict.get("sex", "")
            raced = row_dict.get("raced", "")
            bpld = row_dict.get("bpld", "")

            # --- Translate codes to human-readable strings ---
            state_name = get_stateicp(stateicp)
            county_name = county_lookup.get(stateicp, countyicp) or "(unknown county)"
            city_name = get_city(city)
            sex_str = get_sex(safe_int(sex))
            bpld_str = get_bpld(safe_int(bpld))

            # --- Build human-readable block ---
            lines = [
                f"",
                f"  ID:          {year}-{serial}-{pernum}",
                f"  Name:        {fname or '(none)'} {lname or '(none)'}",
                f"  Born:        {birthyr}  (age {age} in {year})",
                f"  Sex:         {sex_str}",
                f"  Race:        {safe_int(raced)}",
                f"  Relation:    {safe_int(related)}",
                f"  Location:    {county_name} / {city_name}",
                f"  Birthplace:  {bpld_str}",
                f"  Mother loc:  {momloc}",
                f"  Father loc:  {poploc}",
                f"  Siblings:    {nsibs}",
                f"  Children:    {nchild}",
                f"  Fathers:     {nfathers}",
                f"  Family size: {famsize}",
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

    target_surname = ""  # Change to % for everything, or a surname prefix

    # Load the county lookup ONCE here -- not inside the loop
    county_lookup = CountyByCode(
        r"E:\Users\Andy\PycharmProjects\Genealogy\JSON\county_by_codes.json"
    )

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
        r"D:\Data\Genealogy_Data\MasterVault_1850-1900.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1910.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1920.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1930.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1940.db",
        # r"D:\Data\Genealogy_Data\MasterVault_1950.db",
    ]

    print(f"Starting search through Vaults for surname: {target_surname}")
    for db in vaults:
        search_by_name(db,
                       last_name_prefix=target_surname,
                       county_lookup=county_lookup,
                       output_file=outfile)

    print(f"\n[ Analysis Complete. Check {outfile} for results. ]")
