import duckdb

VAULT_DB = r"d:\Data\Genealogy_Data\Test_DuckDB_Vault.db"
CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"


def hunt_specific_person(birth_year, bpl, fbpl, mbpl):
    print(f"Connecting to Vault: {VAULT_DB}...")
    con = duckdb.connect(database=VAULT_DB, read_only=True)

    print(f"\n🎯 Hunting for Known Ancestor:")
    print(f"   - Birth Year: ~{birth_year}")
    print(f"   - Birthplace: {bpl}")
    print(f"   - Father BPL: {fbpl}")
    print(f"   - Mother BPL: {mbpl}\n")

    # 1. Check which columns exist in your test database so it doesn't crash
    cols = [c[0].upper() for c in con.execute("DESCRIBE individuals").fetchall()]
    has_fbpl = 'FBPL' in cols
    has_mbpl = 'MBPL' in cols

    # 2. Build the query dynamically based on what you pass in
    select_clause = "HISTID, NAMEFIRST, NAMELAST, BIRTHYR, BPL, YEAR"
    if has_fbpl: select_clause += ", FBPL"
    if has_mbpl: select_clause += ", MBPL"

    where_clauses = [f"TRY_CAST(BIRTHYR AS INTEGER) BETWEEN {birth_year - 0} AND {birth_year + 0}"]

    if bpl: where_clauses.append(f"BPL ILIKE '%{bpl}%'")
    if fbpl and has_fbpl: where_clauses.append(f"FBPL ILIKE '%{fbpl}%'")
    if mbpl and has_mbpl: where_clauses.append(f"MBPL ILIKE '%{mbpl}%'")

    where_string = " \n        AND ".join(where_clauses)

    query = f"""
        SELECT {select_clause}
        FROM individuals
        WHERE {where_string}
        ORDER BY YEAR ASC
        LIMIT 20
    """

    results = con.execute(query).df()

    if results.empty:
        print("❌ No matches found.")
        print("   If you are 100% sure he is in there, your database might be using numeric")
        print("   location codes! Try changing 'Pennsylvania' to '42' at the bottom of the script.")
    else:
        print(f"✅ Found {len(results)} matching records in the Vault!\n")

        # 3. If we found him, automatically jump into the Crosswalk DB and grab the HIK!
        print("Fetching HIKs (Crosswalk IDs) for these matches...")
        con.execute(f"ATTACH '{CROSSWALK_DB}' AS cw (READ_ONLY);")

        histids_str = ", ".join([f"'{h}'" for h in results['HISTID']])
        hik_query = f"""
            WITH unpivoted_cw AS (
                SELECT TRIM(histid_1850) AS histid, HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1850) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1860), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1860) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1870), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1870) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1880), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1880) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1900), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1900) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1910), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1910) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1920), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1920) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1930), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1930) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1940), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1940) IN ({histids_str})
                UNION ALL SELECT TRIM(histid_1950), HIK FROM cw.ipums_crosswalk WHERE TRIM(histid_1950) IN ({histids_str})
            )
            SELECT histid AS HISTID, HIK FROM unpivoted_cw
        """
        hiks = con.execute(hik_query).df()

        if not hiks.empty:
            # Merge the HIKs onto our output table and print it beautifully
            final_output = results.merge(hiks.drop_duplicates(), on='HISTID', how='left')
            print("-" * 80)
            print(final_output.to_string())
            print("-" * 80)
            print("\n🎉 SUCCESS: Grab your grandfather's HISTID from the far left column above!")
            print("   (The HIK is also available on the far right if you need it for later scripts).")
        else:
            print(results.to_string())
            print("\n🎉 SUCCESS: Grab your grandfather's HISTID from the far left column above!")
            print("   (Note: No HIKs were attached to them in the Crosswalk, but you have the HISTID!).")


if __name__ == "__main__":
    # --- ENTER YOUR GRANDFATHER'S INFO HERE ---
    TARGET_BIRTH_YEAR = 1911
    TARGET_BPL = "42"
    TARGET_FBPL = "42"
    TARGET_MBPL = "42"

    hunt_specific_person(TARGET_BIRTH_YEAR, TARGET_BPL, TARGET_FBPL, TARGET_MBPL)
