"""
-----------------------------------
File: VaultSearch.py

Summary: Search a single census year database using hardcoded filter
         parameters. Zero means "don't filter on this field."

Usage:   Tweak the parameters below and run. That's it.
-----------------------------------
"""

import sqlite3
import os

# ==============================================================================
# SEARCH PARAMETERS  ← change these and re-run
# ==============================================================================

YEAR        = 1880   # Which year's database to open

SEX         = 1      # 1=male, 2=female,        0=don't filter
STATEICP    = 41     # state code (e.g. 41=PA),  0=don't filter
COUNTYICP   = 0      # county code,              0=don't filter
CITY        = 0      # city code,                0=don't filter
FARM        = 0      # farm status code,         0=don't filter
AGE         = 0      # exact age,                0=don't filter
BIRTHYR     = 0      # birth year,               0=don't filter
RACED       = 0      # race code,                0=don't filter
BPLD        = 0      # birthplace code,          0=don't filter
RELATED     = 0      # relationship code,        0=don't filter
HHTYPE      = 0      # household type code,      0=don't filter

NAMELAST    = ""     # last name,  ""=don't filter
NAMEFRST    = ""     # first name, ""=don't filter

MAX_RESULTS = 100    # cap results so console doesn't explode; 0=no limit

# ==============================================================================
# DATABASE PATH  ← adjust if your path changes
# ==============================================================================

DB_PATH = r"D:\Data\Genealogy_Data\MasterVault_" + str(YEAR) + ".db"


# ==============================================================================
# SEARCH FUNCTION
# ==============================================================================

def build_query():
    """
    Builds a SELECT statement dynamically based on whichever parameters
    are non-zero (or non-empty for name strings).
    Returns (query_string, params_tuple).
    """
    conditions = []
    params     = []

    # Numeric filters — skip if zero
    numeric_fields = {
        "sex"       : SEX,
        "stateicp"  : STATEICP,
        "countyicp" : COUNTYICP,
        "city"      : CITY,
        "farm"      : FARM,
        "age"       : AGE,
        "birthyr"   : BIRTHYR,
        "raced"     : RACED,
        "bpld"      : BPLD,
        "related"   : RELATED,
        "hhtype"    : HHTYPE,
    }

    for column, value in numeric_fields.items():
        if value != 0:
            conditions.append(f"{column} = ?")
            params.append(str(value))   # stored as TEXT in the db

    # Name filters — skip if empty string
    if NAMELAST.strip():
        conditions.append("namelast = ?")
        params.append(NAMELAST.strip().upper())

    if NAMEFRST.strip():
        conditions.append("namefrst = ?")
        params.append(NAMEFRST.strip().upper())

    # Assemble query
    query = "SELECT year, namelast, namefrst, age, sex, stateicp, countyicp, " \
            "related, birthyr, raced, bpld, serial, pernum " \
            "FROM population"

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    if MAX_RESULTS > 0:
        query += f" LIMIT {MAX_RESULTS}"

    return query, tuple(params)


def run_search():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found: {DB_PATH}")
        return

    query, params = build_query()

    print(f"\nDatabase : {DB_PATH}")
    print(f"Query    : {query}")
    print(f"Params   : {params}")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # lets us access columns by name
    cursor = conn.cursor()

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No results found.")
        return

    # Print header
    print(f"  {'Last':<20} {'First':<15} {'Age':>4}  {'Sex':>3}  "
          f"{'State':>6}  {'County':>6}  {'BirthYr':>7}  Serial/Pernum")
    print(f"  {'-'*20} {'-'*15} {'-'*4}  {'-'*3}  "
          f"{'-'*6}  {'-'*6}  {'-'*7}  {'-'*15}")

    for row in rows:
        print(f"  {row['namelast']:<20} {row['namefrst']:<15} {row['age']:>4}  "
              f"{row['sex']:>3}  {row['stateicp']:>6}  {row['countyicp']:>6}  "
              f"{row['birthyr']:>7}  {row['serial']}_{row['pernum']}")

    print(f"\n  {len(rows)} result(s) returned."
          + (f"  (capped at {MAX_RESULTS})" if MAX_RESULTS > 0 and len(rows) == MAX_RESULTS else ""))


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    run_search()
