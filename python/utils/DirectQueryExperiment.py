"""
-----------------------------------
File: DirectQueryExperiment.py

Summary: A direct-query experiment to test the "Survival Rate" of families.
         It pulls a sample of families from a base year (e.g., 1850) and loops
         through them one by one, firing a direct SQL query to see if their
         10-variable demographic hash appears 10, 20, or 30 years later.

         This script calculates the exact percentage of families that 
         successfully "match up immediately" using standard SQL.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy


-----------------------------------
"""

import os
import sqlite3
import sys
import time

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [os.path.join(project_root, 'python'), project_root]:
    if p not in sys.path:
        sys.path.append(p)

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MASTER_DB = os.path.join(BASE_DATA_DIR, "MasterVault_Relational.db")


def run_direct_query_experiment(base_year=1850, sample_size=1000):
    print(f"--- STARTING DIRECT QUERY EXPERIMENT ---")
    print(f"Extracting {sample_size} base couples from {base_year}...")

    with sqlite3.connect(MASTER_DB) as conn:
        cursor = conn.cursor()

        # 1. Grab our baseline couples
        cursor.execute(f"""
            SELECT 
                h.sex, s.sex, 
                h.bpld, s.bpld, 
                h.birthyr, s.birthyr, 
                h.fbpl, h.mbpl, 
                s.fbpl, s.mbpl
            FROM families f
            JOIN individuals h ON f.head_histid = h.histid
            JOIN individuals s ON f.spouse_histid = s.histid
            WHERE f.year = ? 
              AND h.birthyr IS NOT NULL AND s.birthyr IS NOT NULL
            LIMIT ?
        """, (base_year, sample_size))

        baseline_couples = cursor.fetchall()
        total_couples = len(baseline_couples)

        if total_couples == 0:
            print("No couples found for the baseline year!")
            return

        print(f"Successfully loaded {total_couples} couples. Beginning direct query loop...\n")

        # 2. The Direct Query
        direct_sql = """
                     SELECT f.family_id, f.year
                     FROM families f
                              JOIN individuals h ON f.head_histid = h.histid
                              JOIN individuals s ON f.spouse_histid = s.histid
                     WHERE f.year IN (?, ?, ?)
                       AND h.sex = ?
                       AND s.sex = ?
                       AND h.bpld = ?
                       AND s.bpld = ?
                       AND h.birthyr BETWEEN ? AND ?
                       AND s.birthyr BETWEEN ? AND ?
                       AND (h.fbpl = ? OR h.fbpl IS NULL OR ? IS NULL)
                       AND (h.mbpl = ? OR h.mbpl IS NULL OR ? IS NULL)
                       AND (s.fbpl = ? OR s.fbpl IS NULL OR ? IS NULL)
                       AND (s.mbpl = ? OR s.mbpl IS NULL OR ? IS NULL) \
                     """

        matches_found = 0
        start_time = time.time()

        # 3. Loop through them one-by-one
        for i, couple in enumerate(baseline_couples):
            h_sex, s_sex, h_bpld, s_bpld, h_byr, s_byr, h_fbpl, h_mbpl, s_fbpl, s_mbpl = couple

            # Build our query parameters (We have to pass the parent BPLs twice to handle the "IS NULL" logic)
            params = (
                base_year + 10, base_year + 20, base_year + 30,
                h_sex, s_sex, h_bpld, s_bpld,
                h_byr - 2, h_byr + 2,
                s_byr - 2, s_byr + 2,
                h_fbpl, h_fbpl, h_mbpl, h_mbpl,
                s_fbpl, s_fbpl, s_mbpl, s_mbpl
            )

            cursor.execute(direct_sql, params)
            results = cursor.fetchall()

            # If we got exactly 1 unique match back, it's a success!
            if len(results) == 1:
                matches_found += 1

        elapsed = time.time() - start_time
        match_percentage = (matches_found / total_couples) * 100

        print(f"--- EXPERIMENT RESULTS ---")
        print(f"Total Base Couples Checked: {total_couples}")
        print(f"Perfect Unique Matches Found 10-30 Years Later: {matches_found}")
        print(f"SURVIVAL RATE: {match_percentage:.2f}%")
        print(f"Time Taken: {elapsed:.2f} seconds")


if __name__ == "__main__":
    # You can change the sample size to 10,000 or 100,000 to get a more accurate nationwide percentage!
    run_direct_query_experiment(base_year=1850, sample_size=1000)
