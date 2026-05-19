"""
-----------------------------------
File: county_lookup.py

Summary: Builds a JSON lookup keyed by (STATEICP, COUNTYICP) code pair,
         and provides a getter that returns a formatted string like
         "Douglas County, Colorado".

Why a pair?  COUNTYICP codes are NOT globally unique -- code 350 exists
in 39 different states.  You always need both codes together.

Inputs:  CSV file from https://usa.ipums.org/usa/volii/ICPSR.shtml
         Columns: State, STATEICP, STATEFIPS, County cod, County

Output:  county_by_codes.json
         Key:   "62_350"   (stateicp_countyicp)
         Value: "Douglas County, Colorado"

Usage in your search scripts:
    from county_lookup import CountyByCode
    lookup = CountyByCode('../JSON/county_by_codes.json')
    label = lookup.get(stateicp=62, countyicp=350)
    # returns "Douglas County, Colorado"
    # returns None if not found

-----------------------------------
"""
import csv
import json
import os


# ===========================================================================
# SECTION 1: BUILD THE JSON FILE
# ===========================================================================

def build_county_by_codes_json(csv_path: str, output_path: str) -> None:
    """
    Reads the ICPSR county CSV and writes county_by_codes.json.

    The key is  "<stateicp>_<countyicp>"  (e.g. "62_350")
    The value is the formatted string      (e.g. "Douglas County, Colorado")

    Args:
        csv_path:    Path to icpsrcnt.csv
        output_path: Path for the output JSON file
    """
    lookup = {}

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)

        # Header:  State, STATEICP, STATEFIPS, County cod, County, ...
        # Data starts on row 3
        cnt = 0
        for row in reader:
            cnt += 1
            if cnt < 3:
                continue
            if len(row) < 5:
                continue

            state_name = row[0].strip().title()
            stateicp = row[1].strip()
            county_code = row[3].strip()
            county_name = row[4].strip()

            # Skip blank rows (the CSV has some)
            if not state_name or not stateicp or not county_code or not county_name:
                continue

            key = f"{stateicp}_{county_code}"
            value = f"{county_name} County, {state_name}"

            lookup[key] = value

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(lookup, f, indent=4, sort_keys=True)

    print(f"Built {len(lookup)} entries → {output_path}")


# ===========================================================================
# SECTION 2: THE GETTER
# ===========================================================================

class CountyByCode:
    """
    Loads county_by_codes.json once, then lets you look up a formatted
    county+state string using the two numeric codes from your database rows.

    Usage:
        lookup = CountyByCode('../JSON/county_by_codes.json')

        label = lookup.get(stateicp=62, countyicp=350)
        # "Douglas County, Colorado"

        label = lookup.get(stateicp=62, countyicp=350)
        # Returns None if not found -- never raises, safe to call in a loop
    """

    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            self._data = json.load(f)

    def get(self, stateicp: int | str, countyicp: int | str) -> str | None:
        """
        Returns a formatted string like "Douglas County, Colorado",
        or None if the code pair is not found.

        Args:I'm updating the log files to go to the output directory. They went to another directory for some reason. I don't know why. But their kind of special spot is the output directory, so I'll put the log files there. So you can look at them any time you want.
            stateicp:  The STATEICP value from your database row  (e.g. 62)
            countyicp: The COUNTYICP value from your database row (e.g. 350)
        """
        key = f"{stateicp}_{countyicp}"
        return self._data.get(key)


# ===========================================================================
# SECTION 3: MAIN — build the file and run a smoke test
# ===========================================================================

if __name__ == '__main__':
    CSV_PATH = '../data/icpsrcnt.csv'
    OUTPUT_PATH = '../JSON/county_by_codes.json'

    # Build the JSON
    build_county_by_codes_json(CSV_PATH, OUTPUT_PATH)

    # Load the getter
    lookup = CountyByCode(OUTPUT_PATH)

    # Smoke tests
    tests = [
        (62, 350, "Douglas County, Colorado"),
        (13, 350, "Fulton County, New York"),
        (24, 350, "Cuyahoga County, Ohio"),
        (62, 10, "Adams County, Colorado"),
    ]

    print()
    all_passed = True
    for stateicp, countyicp, expected in tests:
        result = lookup.get(stateicp, countyicp)
        status = "OK" if result == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"  [{status}]  get({stateicp}, {countyicp}) = '{result}'  (expected '{expected}')")

    print()
    print("All tests passed!" if all_passed else "WARNING: some tests failed.")
