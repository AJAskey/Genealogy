"""
File: Export_MultiGen_GEDCOM.py

Summary: Uses the IPUMS Crosswalk to stitch individuals together across
         multiple decades. Outputs a multi-generational GEDCOM 5.5.1 file.
"""

import duckdb
import os

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"
CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"
OUTPUT_GEDCOM = r"C:\tempc\ShortTermCSVfiles\test_census.ged"

# --- ISOLATION CONFIGURATION ---
# Put a specific HIK here to extract ONLY their interconnected family tree.
# If left blank (""), the script will automatically find and export the single largest tree.
T_HIK = "wTsIougfveJTiHQ8iTKq8"
TARGET_HIK = T_HIK.strip()

STATE_MAP = {
    "1": "Alabama, USA", "01": "Alabama, USA",
    "2": "Alaska, USA", "02": "Alaska, USA",
    "4": "Arizona, USA", "04": "Arizona, USA",
    "5": "Arkansas, USA", "05": "Arkansas, USA",
    "6": "California, USA", "06": "California, USA",
    "8": "Colorado, USA", "08": "Colorado, USA",
    "9": "Connecticut, USA", "09": "Connecticut, USA",
    "10": "Delaware, USA", "11": "District of Columbia, USA",
    "12": "Florida, USA", "13": "Georgia, USA",
    "15": "Hawaii, USA", "16": "Idaho, USA",
    "17": "Illinois, USA", "18": "Indiana, USA",
    "19": "Iowa, USA", "20": "Kansas, USA",
    "21": "Kentucky, USA", "22": "Louisiana, USA",
    "23": "Maine, USA", "24": "Maryland, USA",
    "25": "Massachusetts, USA", "26": "Michigan, USA",
    "27": "Minnesota, USA", "28": "Mississippi, USA",
    "29": "Missouri, USA", "30": "Montana, USA",
    "31": "Nebraska, USA", "32": "Nevada, USA",
    "33": "New Hampshire, USA", "34": "New Jersey, USA",
    "35": "New Mexico, USA", "36": "New York, USA",
    "37": "North Carolina, USA", "38": "North Dakota, USA",
    "39": "Ohio, USA", "40": "Oklahoma, USA",
    "41": "Oregon, USA", "42": "Pennsylvania, USA",
    "44": "Rhode Island, USA", "45": "South Carolina, USA",
    "46": "South Dakota, USA", "47": "Tennessee, USA",
    "48": "Texas, USA", "49": "Utah, USA",
    "50": "Vermont, USA", "51": "Virginia, USA",
    "53": "Washington, USA", "54": "West Virginia, USA",
    "55": "Wisconsin, USA", "56": "Wyoming, USA"
}


def main():
    print(f"Connecting to Test Vault: {MASTER_VAULT_DB}...")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    print(f"Attaching Crosswalk Time Machine...")
    con.execute(f"ATTACH '{CROSSWALK_DB}' AS cw (READ_ONLY);")

    print("Mapping all HISTIDs to their eternal Crosswalk IDs (HIK)...")
    con.execute("""
                CREATE
                TEMP TABLE vault_hiks AS
        WITH all_histids AS (
            SELECT DISTINCT HISTID FROM individuals
        ),
        cw_unpivoted AS (
            SELECT TRIM(histid_1850) AS histid, HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1850)) > 5
            UNION ALL SELECT TRIM(histid_1860), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1860)) > 5
            UNION ALL SELECT TRIM(histid_1870), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1870)) > 5
            UNION ALL SELECT TRIM(histid_1880), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1880)) > 5
            UNION ALL SELECT TRIM(histid_1900), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1900)) > 5
            UNION ALL SELECT TRIM(histid_1910), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1910)) > 5
            UNION ALL SELECT TRIM(histid_1920), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1920)) > 5
            UNION ALL SELECT TRIM(histid_1930), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1930)) > 5
            UNION ALL SELECT TRIM(histid_1940), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1940)) > 5
            UNION ALL SELECT TRIM(histid_1950), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1950)) > 5
        )
                SELECT a.HISTID, TRIM(COALESCE(c.HIK, a.HISTID)) AS HIK
                FROM all_histids a
                         LEFT JOIN cw_unpivoted c ON UPPER(TRIM(a.HISTID)) = UPPER(c.histid);
                """)

    print("Extracting Unified Individuals across all decades...")
    inds = con.execute("""
                       SELECT TRIM(v.HIK)     AS HIK,
                              MODE(i.SEX)     AS SEX,
                              MODE(i.BIRTHYR) AS BIRTHYR,
                              MODE(i.BPL)     AS BPL
                       FROM individuals i
                                JOIN vault_hiks v ON i.HISTID = v.HISTID
                       GROUP BY v.HIK
                       """).fetchall()

    print("Extracting Families across all decades...")
    fams = con.execute("""
                       SELECT f.YEAR || '_' || f.SERIAL AS fam_id,
                              vh.HIK                    AS head_hik,
                              vs.HIK                    AS spouse_hik
                       FROM families f
                                LEFT JOIN vault_hiks vh ON f.head_histid = vh.HISTID
                                LEFT JOIN vault_hiks vs ON f.spouse_histid = vs.HISTID
                       """).fetchall()

    print("Mapping children to multi-generational families...")
    children = con.execute("""
                           SELECT i.YEAR || '_' || i.SERIAL AS fam_id,
                                  v.HIK                     AS child_hik
                           FROM individuals i
                                    JOIN vault_hiks v ON i.HISTID = v.HISTID
                           WHERE i.RELATE IN ('03', '3', 'Child')
                           """).fetchall()

    # Build linking dictionaries
    fam_children = {}
    ind_fams = {}  # Families where this person is a spouse/head
    ind_famc = {}  # Families where this person is a child

    for child in children:
        fam_id, child_hik = child
        fam_children.setdefault(fam_id, []).append(child_hik)
        ind_famc.setdefault(child_hik, []).append(fam_id)

    fam_dict = {}
    for fam in fams:
        fam_id, head_hik, spouse_hik = fam
        fam_dict[fam_id] = fam
        if head_hik:
            ind_fams.setdefault(head_hik, []).append(fam_id)
        if spouse_hik:
            ind_fams.setdefault(spouse_hik, []).append(fam_id)

    # --- ISOLATE A SINGLE SIGNIFICANT TREE ---
    print("Isolating a single significant family tree to reduce file size...")

    def get_tree(start_hik):
        visited_hiks = set()
        visited_fams = set()
        stack = [start_hik]

        while stack:
            curr_hik = stack.pop()
            if curr_hik in visited_hiks:
                continue
            visited_hiks.add(curr_hik)

            connected_fams = ind_fams.get(curr_hik, []) + ind_famc.get(curr_hik, [])
            for f_id in connected_fams:
                if f_id not in visited_fams:
                    visited_fams.add(f_id)
                    fam_record = fam_dict.get(f_id)
                    if fam_record:
                        _, h_hik, s_hik = fam_record
                        if h_hik and h_hik not in visited_hiks: stack.append(h_hik)
                        if s_hik and s_hik not in visited_hiks: stack.append(s_hik)
                    for c_hik in fam_children.get(f_id, []):
                        if c_hik not in visited_hiks: stack.append(c_hik)
        return visited_hiks, visited_fams

    target_tree_hiks = set()
    target_tree_fams = set()
    all_hiks = {i[0] for i in inds}

    if TARGET_HIK and TARGET_HIK in all_hiks:
        print(f"Isolating tree for targeted HIK: {TARGET_HIK}")
        target_tree_hiks, target_tree_fams = get_tree(TARGET_HIK)
    else:
        if TARGET_HIK:
            print(f"\n❌ ERROR: TARGET_HIK '{TARGET_HIK}' was NOT found in the database!")
            print("Aborting so you don't accidentally export the wrong tree.")
            return
        print("Automatically finding the largest interconnected tree...")
        global_visited = set()
        for hik in all_hiks:
            if hik not in global_visited:
                tree_hiks, tree_fams = get_tree(hik)
                global_visited.update(tree_hiks)
                if len(tree_hiks) > len(target_tree_hiks):
                    target_tree_hiks = tree_hiks
                    target_tree_fams = tree_fams

    print(f"Isolated Tree Size: {len(target_tree_hiks)} individuals, {len(target_tree_fams)} families.")

    # Overwrite our main lists with ONLY the isolated tree
    inds = [i for i in inds if i[0] in target_tree_hiks]
    fams = [f for f in fams if f[0] in target_tree_fams]

    # Ensure the TARGET_HIK is the first person in the list
    # This makes Ancestry automatically assign them as the default "Home Person"
    if TARGET_HIK:
        inds.sort(key=lambda x: 0 if x[0] == TARGET_HIK else 1)

    # Create simple 22-character limit GEDCOM IDs
    ind_map = {ind[0]: f"I{i}" for i, ind in enumerate(inds, 1)}
    fam_map = {fam[0]: f"F{i}" for i, fam in enumerate(fams, 1)}

    # --- NEW: ROOT ANCESTOR TRACING ---
    print("Calculating ultimate root ancestors (Adams & Eves) for each person...")
    ind_data = {ind[0]: ind for ind in inds}
    roots_memo = {}

    def get_roots(hik, current_path=None):
        if current_path is None:
            current_path = set()
        if hik in roots_memo:
            return roots_memo[hik]
        if hik in current_path:
            return set()  # Cycle detected in data, safely abort this path

        current_path.add(hik)
        parents = []
        if hik in ind_famc:
            for fam_id in ind_famc[hik]:
                fam_record = fam_dict.get(fam_id)
                if fam_record:
                    _, h_hik, s_hik = fam_record
                    if h_hik and h_hik in ind_data: parents.append(h_hik)
                    if s_hik and s_hik in ind_data: parents.append(s_hik)

        if not parents:
            roots_memo[hik] = {hik}
            current_path.remove(hik)
            return {hik}

        ultimate_roots = set()
        for p_hik in parents:
            ultimate_roots.update(get_roots(p_hik, current_path))

        roots_memo[hik] = ultimate_roots
        current_path.remove(hik)
        return ultimate_roots

    print(f"Writing Multi-Generational GEDCOM to {OUTPUT_GEDCOM}...")
    with open(OUTPUT_GEDCOM, 'w', encoding='utf-8') as f:
        # --- 1. GEDCOM HEADER ---
        f.write("0 HEAD\n")
        f.write("1 SOUR DuckDB_Pipeline\n")
        f.write("1 SUBM @U1@\n")
        f.write("1 GEDC\n")
        f.write("2 VERS 5.5.1\n")
        f.write("2 FORM LINEAGE-LINKED\n")
        f.write("1 CHAR UTF-8\n")

        f.write("0 @U1@ SUBM\n")
        f.write("1 NAME Andy Askey\n")

        # --- 2. INDIVIDUALS (INDI) ---
        for ind in inds:
            hik, first_name, last_name, sex_code, birthyr, bpl_code = ind
            mapped_hik = ind_map.get(hik)

            first_name = first_name if first_name else "Unknown"
            last_name = last_name if last_name else "Unknown"
            sex = 'M' if str(sex_code).strip() == '1' else 'F'

            clean_bpl = str(bpl_code).strip()
            if len(clean_bpl) > 2 and clean_bpl.endswith("00"):
                clean_bpl = clean_bpl[:-2]
            birth_place = STATE_MAP.get(clean_bpl, f"Code {clean_bpl}")

            f.write(f"0 @{mapped_hik}@ INDI\n")
            f.write(f"1 NAME {first_name} /{last_name}/\n")
            f.write(f"1 SEX {sex}\n")

            if birthyr:
                f.write("1 BIRT\n")
                f.write(f"2 DATE {birthyr}\n")
                if birth_place:
                    f.write(f"2 PLAC {birth_place}\n")

            # Add the HIK as a searchable Reference Number in the GEDCOM
            f.write(f"1 REFN {hik}\n")

            # --- Calculate and Add Adam/Eve Notes ---
            roots = get_roots(hik)
            roots_excluding_self = [r for r in roots if r != hik]

            if roots_excluding_self:
                f.write("1 NOTE Ultimate Root Ancestors:\n")
                for r_hik in roots_excluding_self:
                    r_ind = ind_data.get(r_hik)
                    if r_ind:
                        r_fname = r_ind[1] if r_ind[1] else "Unknown"
                        r_lname = r_ind[2] if r_ind[2] else "Unknown"
                        r_sex = 'Adam' if str(r_ind[3]).strip() == '1' else 'Eve'
                        f.write(f"2 CONT - {r_fname} {r_lname} ({r_sex}) [HIK: {r_hik}]\n")
            else:
                f.write("1 NOTE This person is a root ancestor (Adam/Eve) in this tree.\n")

            # Link to Spouse Families
            if hik in ind_fams:
                for fam_id in set(ind_fams[hik]):
                    f.write(f"1 FAMS @{fam_map.get(fam_id)}@\n")

            # Link to Child Families (The Grandparent Link!)
            if hik in ind_famc:
                for fam_id in set(ind_famc[hik]):
                    f.write(f"1 FAMC @{fam_map.get(fam_id)}@\n")

        # --- 3. FAMILIES (FAM) ---
        for fam in fams:
            fam_id, head_hik, spouse_hik = fam
            mapped_fam = fam_map.get(fam_id)

            f.write(f"0 @{mapped_fam}@ FAM\n")
            if head_hik:
                f.write(f"1 HUSB @{ind_map.get(head_hik)}@\n")
            if spouse_hik:
                f.write(f"1 WIFE @{ind_map.get(spouse_hik)}@\n")

            if fam_id in fam_children:
                for child_hik in set(fam_children[fam_id]):
                    f.write(f"1 CHIL @{ind_map.get(child_hik)}@\n")

        # --- 4. GEDCOM TRAILER ---
        f.write("0 TRLR\n")

    print("SUCCESS! Multi-Generational GEDCOM ready for Ancestry.")


if __name__ == "__main__":
    main()
