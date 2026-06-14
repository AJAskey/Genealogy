"""
-----------------------------------
File: CensusVsGedcomReport.py

Summary: Generates a text report comparing the original GEDCOM anchors 
         to the historical census data in the Clean Vault.
         Identifies who is missing from the census, and who was 
         discovered as a new dependent in the census.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sys

import duckdb

# Add the 'python' directory and project root to sys.path so we can import properly
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.abspath(os.path.join(script_dir, '..'))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [python_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

CLEAN_TRACER_DB = r"D:\Data\Genealogy_Data\CleanVault_Gedcom.db"
OUTPUT_REPORT = os.path.join(project_root, "output", "Census_vs_Gedcom_Report.txt")


def generate_report():
    print(f"Connecting to {CLEAN_TRACER_DB}...")
    con = duckdb.connect()
    con.execute(f"ATTACH '{CLEAN_TRACER_DB}' AS clean (TYPE SQLITE, READ_ONLY);")

    print("Analyzing database...")

    # 1. Missing from Census (Has GED_ pointer, but no 18xx/19xx census pointers and census_count = 0)
    missing_df = con.execute("""
                             SELECT first_name, last_name, birth_year
                             FROM clean.golden_records
                             WHERE vault_pointers LIKE '%GED_%'
                               AND vault_pointers NOT LIKE '%18%'
                               AND vault_pointers NOT LIKE '%19%'
                             ORDER BY last_name, first_name
                             """).df()

    # 2. Newly Discovered in Census (Has no GED_ pointer, meaning ExpandHouseholds found them)
    new_df = con.execute("""
                         WITH gedcom_anchors AS (SELECT UNNEST(string_split(vault_pointers, '|')) AS comp_id
                                                 FROM clean.golden_records
                                                 WHERE vault_pointers LIKE '%GED_%')
                         SELECT *
                         FROM (SELECT d.first_name, d.last_name, d.birth_year
                               FROM clean.golden_records d
                                        JOIN gedcom_anchors a ON d.father_pointer = a.comp_id
                               WHERE d.vault_pointers NOT LIKE '%GED_%'
                               UNION
                               SELECT d.first_name, d.last_name, d.birth_year
                               FROM clean.golden_records d
                                        JOIN gedcom_anchors a ON d.mother_pointer = a.comp_id
                               WHERE d.vault_pointers NOT LIKE '%GED_%')
                         ORDER BY last_name, first_name
                         """).df()

    # 3. Successfully Matched Both (Has a GED_ pointer AND census pointers)
    matched_df = con.execute("""
                             SELECT first_name, last_name, birth_year
                             FROM clean.golden_records
                             WHERE vault_pointers LIKE '%GED_%'
                               AND (vault_pointers LIKE '%18%' OR vault_pointers LIKE '%19%')
                             ORDER BY last_name, first_name
                             """).df()

    print(f"Writing report to: {OUTPUT_REPORT}")
    os.makedirs(os.path.dirname(OUTPUT_REPORT), exist_ok=True)

    with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
        f.write("========================================================\n")
        f.write("             CENSUS VS GEDCOM: DATABASE REPORT          \n")
        f.write("========================================================\n\n")

        f.write(f"--- MATCHED IN BOTH ({len(matched_df)} individuals) ---\n")
        f.write("These individuals were in your GEDCOM and mathematically matched to Census data.\n")
        for _, row in matched_df.iterrows():
            f.write(f"  * {row['first_name']} {row['last_name']} (Born: {row['birth_year']})\n")

        f.write(f"\n\n--- MISSING FROM CENSUS ({len(missing_df)} individuals) ---\n")
        f.write("These individuals were in your GEDCOM, but could not be confidently found in the 1850-1950 Census.\n")
        for _, row in missing_df.iterrows():
            f.write(f"  - {row['first_name']} {row['last_name']} (Born: {row['birth_year']})\n")

        f.write(f"\n\n--- NEWLY DISCOVERED IN CENSUS ({len(new_df)} individuals) ---\n")
        f.write(
            "These individuals were NOT in your GEDCOM. They were discovered living in the same historical households as your family!\n")
        for _, row in new_df.iterrows():
            f.write(f"  + {row['first_name']} {row['last_name']} (Born: {row['birth_year']})\n")

    print("\nReport Generation Complete!")
    print(f"Matched: {len(matched_df)} | Missing: {len(missing_df)} | New Discoveries: {len(new_df)}")


if __name__ == "__main__":
    generate_report()
