import duckdb
import os

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches2.db")
OUTPUT_CSV = os.path.join(BASE_DATA_DIR, "Resolved_Ancestors.csv")

print("Connecting to DuckDB Time Machine...")
con = duckdb.connect(MATCH_DB, read_only=True)
print(f"Exporting resolved names to: {OUTPUT_CSV}")

csv_path_fwd = OUTPUT_CSV.replace('\\', '/')

con.execute(f"""
COPY (
    SELECT 
        r.first_name AS Real_First_Name, 
        r.last_name AS Real_Last_Name, 
        f.year AS Census_Year,
        i.birthyr AS Birth_Year, 
        i.bpld AS Birthplace, 
        i.fbpl AS Fathers_Birthplace, 
        i.mbpl AS Mothers_Birthplace,
        r.histid AS HISTID
    FROM resolved_names r
    LEFT JOIN tm_individuals i ON r.histid = i.histid
    LEFT JOIN tm_families f ON i.family_id = f.family_id
    ORDER BY r.last_name, r.first_name, f.year
) TO '{csv_path_fwd}' (HEADER, DELIMITER ',');
""")
print("Done! You can now double-click the CSV and open it in Excel.")
