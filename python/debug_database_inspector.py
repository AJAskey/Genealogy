"""
-----------------------------------
File: debug_database_inspector.py

Summary: A utility to inspect records from a census database, look up
         their codes using the JSON codebook, and write a human-readable
         report to a text file. This is useful for verifying that data
         is being interpreted correctly.

Design:
  - Connects to a single specified SQLite database.
  - Loops through a limited number of records.
  - For each record, it extracts specified fields (e.g., STATEICP, RACE).
  - Uses the global Codebook and County lookup objects.
  - Writes the original code and the translated string to an output file.
--------------------------------
"""
import logging
import os
import sqlite3

# Import the global objects from our new central module
from project_globals import CODEBOOK, COUNTY_LOOKUP, OUTPUT_REPORT

# Define the path to the master database
MASTER_DB_PATH = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"

# ==============================================================================
# INSPECTION SCRIPT
# ==============================================================================

def inspect_database(db_path, output_path, limit=100, order_by=None, **filters):
    """
    Connects to a database, reads records based on filters, and writes a report.

    Args:
        db_path (str): Path to the SQLite database file.
        output_path (str): Path to write the final text report.
        limit (int): The maximum number of records to inspect.
        order_by (str): Column to sort the results by (e.g., "year ASC").
        **filters (dict): A dictionary of column names and values to filter by.
                          e.g., namelast="Smith", stateicp="42"
    """
    if not os.path.exists(db_path):
        logging.error(f"Database not found at: {db_path}")
        return

    # Connect to the database
    logging.info(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # --- Dynamically build the WHERE clause ---
    where_clauses = []
    params = []
    if filters:
        for key, value in filters.items():
            # Using LIKE for flexibility with string matching
            where_clauses.append(f"{key} LIKE ?")
            params.append(value)
    
    base_query = "SELECT * FROM population"
    if where_clauses:
        query = f"{base_query} WHERE {' AND '.join(where_clauses)}"
    else:
        query = base_query

    if order_by:
        query += f" ORDER BY {order_by}"

    query += " LIMIT ?"
    params.append(limit)

    logging.info(f"Executing query: {query}")
    logging.info(f"With parameters: {params}")
    
    cursor.execute(query, tuple(params))

    # Open the output file for writing
    with open(output_path, 'w', encoding='utf-8') as f:
        logging.info(f"Writing inspection report to: {output_path}")
        f.write("--- Database Inspection Report ---\n")
        f.write(f"Query Filters: {filters}\n\n")

        record_count = 0
        for row in cursor:
            record_count += 1
            f.write(f"--- Record {record_count} (Composite ID: {row['composite_id']}) ---\n")

            # Extract Names First to Make it Human
            first_name = str(row['namefrst']).strip() if row['namefrst'] else "Unknown"
            last_name = str(row['namelast']).strip() if row['namelast'] else "Unknown"
            age = str(row['age']).strip() if row['age'] else "?"
            year = str(row['year']).strip() if row['year'] else "Unknown"

            f.write(f"  NAME:     {first_name} {last_name} (Age {age})\n")
            f.write(f"  YEAR:     {year}\n")

            # --- Use the global CODEBOOK and COUNTY_LOOKUP objects ---

            # State (STATEICP)
            state_code = row['stateicp']
            state_value = CODEBOOK.get_code_value("STATEICP", state_code)
            f.write(f"  STATE:    {state_code:<5} -> {state_value}\n")

            # County
            county_code = str(row['countyicp']).strip() if row['countyicp'] else ""
            
            county_value = "Unknown County"
            if state_value and state_value in COUNTY_LOOKUP:
                state_counties = COUNTY_LOOKUP[state_value]
                county_value = state_counties.get(county_code, "Unknown County")

            f.write(f"  COUNTY:   {county_code:<5} -> {county_value}\n")

            # Race (RACED)
            race_code = row['raced']
            race_value = CODEBOOK.get_code_value("RACED", race_code)
            f.write(f"  RACED:    {race_code:<5} -> {race_value}\n")

            # Sex (SEX)
            sex_code = row['sex']
            sex_value = CODEBOOK.get_code_value("SEX", sex_code)
            f.write(f"  SEX:      {sex_code:<5} -> {sex_value}\n")

            # Relationship to Head (RELATED)
            relate_code = row['related']
            relate_value = CODEBOOK.get_code_value("RELATED", relate_code)
            f.write(f"  RELATED:  {relate_code:<5} -> {relate_value}\n")

            # Birthplace
            bpl_code = row['bpld']
            bpl_value = CODEBOOK.get_code_value("BPLD", bpl_code)
            f.write(f"  BPL:      {bpl_code:<5} -> {bpl_value}\n")

            # Add a blank line for readability
            f.write("\n")

    logging.info(f"Inspection complete. Found {record_count} records matching filters.")


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == '__main__':
    # Set up basic logging to see progress
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

    # --- You can define your filters here ---
    search_filters = {
        "namelast": "Askey",
    }

    inspect_database(
        db_path=MASTER_DB_PATH,
        output_path=OUTPUT_REPORT,
        limit=100,
        order_by="year ASC",
        **search_filters
    )
