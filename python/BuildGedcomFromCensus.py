"""
-----------------------------------
File: BuildGedcomFromCensus.py
Summary: Extracts the mathematically linked "Clans" from the Time Machine
         and formats them into a standard GEDCOM 5.5 file.
         *UPGRADED* to include ALL census years for a family timeline,
         generating multiple CENS and RESI tags per person,
         and auto-generates Ancestor records to preserve FBPL and MBPL.
-----------------------------------
"""

import os
import sqlite3
import json

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
SAMPLE_DB = os.path.join(VAULT_DIR, "CENSUS-SAMPLE.db")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches_SAMPLE.db")
OUT_GED = os.path.join(BASE_DATA_DIR, "Census_Ground_Truth.ged")
COUNTY_NAMES_JSON = os.path.join(project_root, "JSON", "county_codes_to_names.json")

IPUMS_STATES = {
    1: "Alabama", 2: "Alaska", 4: "Arizona", 5: "Arkansas", 6: "California", 
    8: "Colorado", 9: "Connecticut", 10: "Delaware", 11: "District of Columbia", 
    12: "Florida", 13: "Georgia", 15: "Hawaii", 16: "Idaho", 17: "Illinois", 
    18: "Indiana", 19: "Iowa", 20: "Kansas", 21: "Kentucky", 22: "Louisiana", 
    23: "Maine", 24: "Maryland", 25: "Massachusetts", 26: "Michigan", 
    27: "Minnesota", 28: "Mississippi", 29: "Missouri", 30: "Montana", 
    31: "Nebraska", 32: "Nevada", 33: "New Hampshire", 34: "New Jersey", 
    35: "New Mexico", 36: "New York", 37: "North Carolina", 38: "North Dakota", 
    39: "Ohio", 40: "Oklahoma", 41: "Oregon", 42: "Pennsylvania", 
    44: "Rhode Island", 45: "South Carolina", 46: "South Dakota", 47: "Tennessee", 
    48: "Texas", 49: "Utah", 50: "Vermont", 51: "Virginia", 53: "Washington", 
    54: "West Virginia", 55: "Wisconsin", 56: "Wyoming"
}

def build_gedcom():
    print("Connecting to databases...")
    county_names_dict = {}
    if os.path.exists(COUNTY_NAMES_JSON):
        with open(COUNTY_NAMES_JSON, 'r', encoding='utf-8') as f:
            county_names_dict = json.load(f)
    else:
        print(f"Warning: {COUNTY_NAMES_JSON} not found. Counties will be left blank.")

    con = sqlite3.connect(SAMPLE_DB)
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db")
    cursor = con.cursor()

    print("Fetching full Clan Timelines... (This pulls ALL decades for each family)")
    
    cursor.execute("""
        SELECT 
            c.clan_id, f.year, f.stateicp, f.countyicp,
            i.histid, i.first_name, i.last_name, i.sex, i.birthyr, i.bpld, i.fbpl, i.mbpl,
            f.head_histid, f.spouse_histid
        FROM match_db.clan_mapping c
        JOIN families f ON c.family_id = f.family_id
        JOIN individuals i ON f.family_id = i.family_id
        ORDER BY c.clan_id, f.year
    """)
    
    rows = cursor.fetchall()
    print(f"Extracted {len(rows):,} individual census records. Organizing...")

    clans = {}
    for row in rows:
        clan_id, year, stateicp, countyicp, histid, fname, lname, sex, byr, bpl, fbpl, mbpl, head_id, spouse_id = row
        
        if clan_id not in clans:
            clans[clan_id] = {
                'head': None,
                'spouse': None,
                'kids': {}
            }
        
        # Track the most consistent head/spouse (we'll use the first one we find as the anchor)
        if head_id and not clans[clan_id].get('head_anchor'): clans[clan_id]['head_anchor'] = head_id
        if spouse_id and not clans[clan_id].get('spouse_anchor'): clans[clan_id]['spouse_anchor'] = spouse_id

        # Format the residence string
        state_name = ""
        if stateicp and str(stateicp).isdigit():
            state_name = IPUMS_STATES.get(int(stateicp), "")
            
        county_name = ""
        if countyicp and str(countyicp).isdigit() and state_name:
            county_name = county_names_dict.get(state_name, {}).get(str(countyicp), "")
            
        res_str = ""
        if county_name and state_name: res_str = f"{county_name}, {state_name}, USA"
        elif state_name: res_str = f"{state_name}, USA"

        event = {'year': year, 'res_str': res_str, 'histid': histid}
        
        # Consolidate multiple decades into a single person based on their role
        is_head = (histid == head_id) or (histid == clans[clan_id].get('head_anchor'))
        is_spouse = (histid == spouse_id) or (histid == clans[clan_id].get('spouse_anchor'))

        if is_head:
            if not clans[clan_id]['head']:
                clans[clan_id]['head'] = {
                    'id': f"H_{clan_id}", 'fname': fname, 'lname': lname, 'sex': sex, 
                    'byr': byr, 'bpl': bpl, 'fbpl': fbpl, 'mbpl': mbpl, 'events': []
                }
            clans[clan_id]['head']['events'].append(event)
            
        elif is_spouse:
            if not clans[clan_id]['spouse']:
                clans[clan_id]['spouse'] = {
                    'id': f"S_{clan_id}", 'fname': fname, 'lname': lname, 'sex': sex, 
                    'byr': byr, 'bpl': bpl, 'fbpl': fbpl, 'mbpl': mbpl, 'events': []
                }
            clans[clan_id]['spouse']['events'].append(event)
            
        else:
            # For kids, group them by their first initial and birth year across decades
            first_init = str(fname)[0].upper() if fname else "U"
            kid_key = f"K_{clan_id}_{first_init}_{byr}"
            if kid_key not in clans[clan_id]['kids']:
                clans[clan_id]['kids'][kid_key] = {
                    'id': kid_key, 'fname': fname, 'lname': lname, 'sex': sex, 
                    'byr': byr, 'bpl': bpl, 'fbpl': fbpl, 'mbpl': mbpl, 'events': []
                }
            clans[clan_id]['kids'][kid_key]['events'].append(event)

    print(f"Formed {len(clans):,} complete multi-decade families. Generating GEDCOM...")

    # ID Translators for strict GEDCOM compliance
    indi_xref_map = {}
    def get_i(hid):
        if hid not in indi_xref_map: indi_xref_map[hid] = len(indi_xref_map) + 1
        return indi_xref_map[hid]

    fam_xref_map = {}
    def get_f(cid):
        if cid not in fam_xref_map: fam_xref_map[cid] = len(fam_xref_map) + 1
        return fam_xref_map[cid]

    with open(OUT_GED, 'w', encoding='utf-8') as f:
        f.write("0 HEAD\n1 SOUR CENSUS_TIME_MACHINE\n1 GEDC\n2 VERS 5.5\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n")
        
        names_printed = 0
        
        for clan_id, data in clans.items():
            head = data['head']
            spouse = data['spouse']
            kids = data['kids'].values()

            family_members = []
            if head: family_members.append(head)
            if spouse: family_members.append(spouse)
            family_members.extend(kids)

            # Setup for Dummy Parents to hold FBPL and MBPL
            head_fath, head_moth = None, None
            spouse_fath, spouse_moth = None, None

            if head:
                if head['fbpl'] and str(head['fbpl']).isdigit() and int(head['fbpl']) > 0: head_fath = f"DUMMY_F_H_{clan_id}"
                if head['mbpl'] and str(head['mbpl']).isdigit() and int(head['mbpl']) > 0: head_moth = f"DUMMY_M_H_{clan_id}"
            if spouse:
                if spouse['fbpl'] and str(spouse['fbpl']).isdigit() and int(spouse['fbpl']) > 0: spouse_fath = f"DUMMY_F_S_{clan_id}"
                if spouse['mbpl'] and str(spouse['mbpl']).isdigit() and int(spouse['mbpl']) > 0: spouse_moth = f"DUMMY_M_S_{clan_id}"

            for ind in family_members:
                if names_printed < 5:
                    print(f"  -> Writing to GEDCOM: {ind['fname']} {ind['lname']}")
                    names_printed += 1

                f.write(f"0 @I{get_i(ind['id'])}@ INDI\n")
                if ind['fname'] or ind['lname']:
                    f.write(f"1 NAME {ind['fname']} /{ind['lname']}/\n")
                
                ged_sex = "M" if str(ind['sex']) == "1" else "F" if str(ind['sex']) == "2" else "U"
                f.write(f"1 SEX {ged_sex}\n")
                
                # Write Birth Event
                if ind['byr']:
                    f.write(f"1 BIRT\n2 DATE {ind['byr']}\n")
                    if ind['bpl'] and str(ind['bpl']).isdigit() and int(ind['bpl']) > 0:
                        bpl_base = int(ind['bpl']) // 100
                        bpl_state_name = IPUMS_STATES.get(bpl_base)
                        if bpl_state_name:
                            f.write(f"2 PLAC {bpl_state_name}, USA\n")

                # Write Residence/Census Timeline for EVERY YEAR recorded
                for ev in ind['events']:
                    if ev['year']:
                        f.write(f"1 RESI\n2 DATE {ev['year']}\n")
                        if ev['res_str']: f.write(f"2 PLAC {ev['res_str']}\n")
                        
                        f.write(f"1 CENS\n2 DATE {ev['year']}\n")
                        if ev['res_str']: f.write(f"2 PLAC {ev['res_str']}\n")

                # Link to main family
                if ind != head and ind != spouse:
                    f.write(f"1 FAMC @F{get_f(clan_id)}@\n")
                    
                # Link Ancestors to base couple
                if ind == head and (head_fath or head_moth):
                    f.write(f"1 FAMC @F{get_f(clan_id + '_HEAD_PARENTS')}@\n")
                if ind == spouse and (spouse_fath or spouse_moth):
                    f.write(f"1 FAMC @F{get_f(clan_id + '_SPOUSE_PARENTS')}@\n")

            # Write Dummy Parents Function
            def write_dummy(dummy_id, bpl_code, sex):
                f.write(f"0 @I{get_i(dummy_id)}@ INDI\n")
                f.write(f"1 NAME Unknown /Unknown/\n")
                f.write(f"1 SEX {sex}\n")
                if bpl_code and str(bpl_code).isdigit() and int(bpl_code) > 0:
                    bpl_base = int(bpl_code) // 100
                    bpl_name = IPUMS_STATES.get(bpl_base)
                    if bpl_name: f.write(f"1 BIRT\n2 PLAC {bpl_name}, USA\n")

            if head_fath: write_dummy(head_fath, head['fbpl'], "M")
            if head_moth: write_dummy(head_moth, head['mbpl'], "F")
            if spouse_fath: write_dummy(spouse_fath, spouse['fbpl'], "M")
            if spouse_moth: write_dummy(spouse_moth, spouse['mbpl'], "F")

            # Main Family Block
            f.write(f"0 @F{get_f(clan_id)}@ FAM\n")
            if head: f.write(f"1 HUSB @I{get_i(head['id'])}@\n")
            if spouse: f.write(f"1 WIFE @I{get_i(spouse['id'])}@\n")
            for kid in kids:
                f.write(f"1 CHIL @I{get_i(kid['id'])}@\n")
                
            # Head's Parents Family
            if head_fath or head_moth:
                f.write(f"0 @F{get_f(clan_id + '_HEAD_PARENTS')}@ FAM\n")
                if head_fath: f.write(f"1 HUSB @I{get_i(head_fath)}@\n")
                if head_moth: f.write(f"1 WIFE @I{get_i(head_moth)}@\n")
                f.write(f"1 CHIL @I{get_i(head['id'])}@\n")
            
            # Spouse's Parents Family
            if spouse_fath or spouse_moth:
                f.write(f"0 @F{get_f(clan_id + '_SPOUSE_PARENTS')}@ FAM\n")
                if spouse_fath: f.write(f"1 HUSB @I{get_i(spouse_fath)}@\n")
                if spouse_moth: f.write(f"1 WIFE @I{get_i(spouse_moth)}@\n")
                f.write(f"1 CHIL @I{get_i(spouse['id'])}@\n")
                
        f.write("0 TRLR\n")
        
    print(f"SUCCESS! Saved to: {OUT_GED}")

if __name__ == "__main__":
    build_gedcom()