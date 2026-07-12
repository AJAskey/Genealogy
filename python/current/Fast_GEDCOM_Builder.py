"""
File: Fast_GEDCOM_Builder.py
Summary: Extracts a multi-generational family tree starting from a TARGET_HIK.
         Optimized for the full master database: it only queries the specific
         relatives instead of loading the entire US population into memory!
"""
import duckdb
import pandas as pd
import os

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"
OUTPUT_GEDCOM = r"E:\Users\Andy\PycharmProjects\Genealogy\output\Target_Family.ged"

# Put your grandfather's verified HIK here!
TARGET_HIK = "7HbCHD5pUfSslqyHea8Jp"


def build_fast_gedcom():
    if not TARGET_HIK or TARGET_HIK == "PUT_YOUR_HIK_HERE":
        print("❌ ERROR: You must specify a TARGET_HIK!")
        return

    print(f"Connecting to Master Vault: {MASTER_VAULT_DB}")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    print(f"\nPhase 1: Crawling the database to map the family tree for HIK: {TARGET_HIK}...")

    visited_hiks = set()
    visited_households = set()
    queue_hiks = {TARGET_HIK}

    # Iterate through the database, pulling only connected households
    while queue_hiks:
        visited_hiks.update(queue_hiks)

        # 1. Find all households these people lived in
        hiks_str = ", ".join([f"'{h}'" for h in queue_hiks])
        hh_query = f"SELECT DISTINCT YEAR, SERIAL FROM individuals WHERE HIK IN ({hiks_str})"
        households = set(con.execute(hh_query).fetchall())

        new_households = households - visited_households
        if not new_households:
            break

        visited_households.update(new_households)

        # 2. Find everyone who lived in those households
        hh_tuples = ", ".join([f"({y}, {s})" for y, s in new_households])
        members_query = f"SELECT DISTINCT HIK FROM individuals WHERE HIK IS NOT NULL AND (YEAR, SERIAL) IN ({hh_tuples})"
        members = con.execute(members_query).fetchall()

        # 3. Queue up any new relatives we haven't searched yet
        new_hiks = {m[0] for m in members} - visited_hiks
        queue_hiks = new_hiks

    print(
        f"✅ Tree isolated! Found {len(visited_hiks)} connected relatives across {len(visited_households)} households.")

    print("\nPhase 2: Extracting demographic profiles...")
    hiks_list = list(visited_hiks)
    hiks_str = ", ".join([f"'{h}'" for h in hiks_list])

    profiles_query = f"""
        SELECT 
            HIK,
            MODE(SEX) AS SEX,
            MODE(BIRTHYR) AS BIRTHYR,
            MODE(BPL) AS BPL
        FROM individuals
        WHERE HIK IN ({hiks_str})
        GROUP BY HIK
    """
    profiles = con.execute(profiles_query).df()

    # Store profiles in a dict for GEDCOM writing
    ind_data = {}
    for _, row in profiles.iterrows():
        ind_data[row['HIK']] = {
            'sex': 'M' if str(row['SEX']).strip() == '1' else 'F',
            'birthyr': row['BIRTHYR'],
            'bpl': row['BPL']
        }

    print("Phase 3: Reconstructing Family Units...")
    hh_tuples = ", ".join([f"({y}, {s})" for y, s in visited_households])
    fam_query = f"""
        SELECT YEAR, SERIAL, HIK, RELATE, SEX 
        FROM individuals 
        WHERE HIK IS NOT NULL AND (YEAR, SERIAL) IN ({hh_tuples})
    """
    fam_members = con.execute(fam_query).df()

    families = {}
    ind_fams = {h: set() for h in visited_hiks}  # families where person is head/spouse
    ind_famc = {h: set() for h in visited_hiks}  # families where person is child

    for (year, serial), group in fam_members.groupby(['YEAR', 'SERIAL']):
        fam_id = f"{year}_{serial}"
        families[fam_id] = {'husb': None, 'wife': None, 'chil': []}

        for _, row in group.iterrows():
            hik = row['HIK']
            relate = str(row['RELATE']).strip()
            sex = str(row['SEX']).strip()

            if relate in ('1', '2'):  # Head or Spouse
                if sex == '1':  # Male
                    families[fam_id]['husb'] = hik
                else:  # Female
                    families[fam_id]['wife'] = hik
                ind_fams[hik].add(fam_id)
            elif relate == '3':  # Child
                families[fam_id]['chil'].append(hik)
                ind_famc[hik].add(fam_id)

    print(f"Phase 4: Writing GEDCOM to {OUTPUT_GEDCOM}...")
    with open(OUTPUT_GEDCOM, 'w', encoding='utf-8') as f:
        f.write("0 HEAD\n1 SOUR IPUMS_DUCKDB\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n")

        # Ensure TARGET_HIK is always @I1@ (The "Home Person" in Ancestry)
        hiks_list.remove(TARGET_HIK)
        hiks_list.insert(0, TARGET_HIK)

        ind_map = {hik: f"I{i + 1}" for i, hik in enumerate(hiks_list)}
        fam_map = {fam_id: f"F{i + 1}" for i, fam_id in enumerate(families.keys())}

        # Write Individuals
        for hik in hiks_list:
            data = ind_data[hik]
            f.write(f"0 @{ind_map[hik]}@ INDI\n")
            f.write(f"1 NAME Unknown /Unknown/\n")
            f.write(f"1 SEX {data['sex']}\n")

            has_birth = bool(data['birthyr'])
            has_plac = bool(data['bpl'])

            if has_birth or has_plac:
                f.write("1 BIRT\n")
                if has_birth:
                    f.write(f"2 DATE {data['birthyr']}\n")
                if has_plac:
                    f.write(f"2 PLAC {data['bpl']}\n")

            f.write(f"1 REFN {hik}\n")

            for fam_id in ind_fams[hik]:
                f.write(f"1 FAMS @{fam_map[fam_id]}@\n")
            for fam_id in ind_famc[hik]:
                f.write(f"1 FAMC @{fam_map[fam_id]}@\n")

        # Write Families
        for fam_id, fam in families.items():
            f.write(f"0 @{fam_map[fam_id]}@ FAM\n")
            if fam['husb']:
                f.write(f"1 HUSB @{ind_map[fam['husb']]}@\n")
            if fam['wife']:
                f.write(f"1 WIFE @{ind_map[fam['wife']]}@\n")
            for chil in fam['chil']:
                f.write(f"1 CHIL @{ind_map[chil]}@\n")

        f.write("0 TRLR\n")

    print("\n🎉 Done! Open the new GEDCOM in Ancestry to view the tree.")


if __name__ == "__main__":
    build_fast_gedcom()
