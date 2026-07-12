"""
File: Lookup_HIK.py
Summary: Instantly translates a single HISTID into an HIK using the Crosswalk DB.
"""

import duckdb

CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"
TARGET_HISTID = "84BC89BD-09C6-4458-912B-B5C6FE8E6C76"

print(f"Searching Crosswalk for HISTID: {TARGET_HISTID}...")
con = duckdb.connect(database=CROSSWALK_DB, read_only=True)

query = f"""
    SELECT HIK 
    FROM ipums_crosswalk 
    WHERE '{TARGET_HISTID}' IN (
        TRIM(histid_1850), TRIM(histid_1860), TRIM(histid_1870), 
        TRIM(histid_1880), TRIM(histid_1900), TRIM(histid_1910), 
        TRIM(histid_1920), TRIM(histid_1930), TRIM(histid_1940), 
        TRIM(histid_1950)
    )
"""

results = con.execute(query).fetchall()

if results:
    print(f"\n🎉 SUCCESS! Found the HIK: {results[0][0]}")
else:
    print("\n❌ Could not find that HISTID in the crosswalk.")
