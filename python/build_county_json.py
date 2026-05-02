"""
-----------------------------------
File: build_county_json.py

Summary: Converts static county dota from IPUMS in json.

Design: The COUNTYICP variable points to a ICPSR County Codes which is manually formatted to a CSV
        file and ond processing.

Inputs: CSV file from https://usa.ipums.org/usa/volii/ICPSR.shtml

Outputs:
  county_names_to_codes.json - You feed it a State and a County Name, and it gives you
  the numeric code (Perfect for your search script inputs).

  county_codes_to_names.json - You feed it a State and a numeric Code, and it gives you
  the County Name (Perfect for printing your final GEDCOM or console output).

Comments for G:

--------------------------------

"""
"""
-----------------------------------
File: build_county_json.py

Summary: Converts static county data from IPUMS into JSON.

Design: The COUNTYICP variable points to an ICPSR County Code which is manually formatted to a CSV
        file and then processed.

Inputs: CSV file from https://usa.ipums.org/usa/volii/ICPSR.shtml

Outputs:
  county_names_to_codes.json - You feed it a State and a County Name, and it gives you
  the numeric code (Perfect for your search script inputs).

  county_codes_to_names.json - You feed it a State and a numeric Code, and it gives you
  the County Name (Perfect for printing your final GEDCOM or console output).

--------------------------------
"""
import csv
import json

state_to_county_name_to_code = {}
state_to_county_code_to_name = {}

# Open the new CSV file
with open('../data/icpsrcnt.csv', 'r', encoding='utf-8', errors='replace') as f:
    reader = csv.reader(f)

    # header - State,STATEICP,STATEFIPS,County cod,County,,,
    # data is expected to start on row 3
    cnt = 0
    for row in reader:
        # Skip header lines
        cnt += 1
        if cnt < 3:
            continue

        # Ensure the row has enough columns so we don't get an index error
        if len(row) < 5:
            continue

        # .strip() removes any accidental leading/trailing spaces from the CSV
        current_state = row[0].strip().title()
        code = row[3].strip()
        name = row[4].strip()

        if current_state:
            # THE FIX: Only create the nested dictionary if the state isn't in it yet!
            if current_state not in state_to_county_name_to_code:
                state_to_county_name_to_code[current_state] = {}
                state_to_county_code_to_name[current_state] = {}

            # Populate both dictionaries
            state_to_county_name_to_code[current_state][name] = code
            state_to_county_code_to_name[current_state][code] = name

# Write out the beautifully formatted JSON files
with open('../JSON/county_names_to_codes.json', 'w') as f:
    json.dump(state_to_county_name_to_code, f, indent=4)

with open('../JSON/county_codes_to_names.json', 'w') as f:
    json.dump(state_to_county_code_to_name, f, indent=4)

print("JSON generation complete! Files look perfect.")
