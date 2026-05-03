"""
-----------------------------------
File: build_county_json.py

Summary: Converts static county data from IPUMS into JSON,
         and provides a CountyLookup class for retrieving
         county codes and names from those JSON files.

Design: The COUNTYICP variable points to an ICPSR County Code which is manually
        formatted to a CSV file and then processed.

Inputs: CSV file from https://usa.ipums.org/usa/volii/ICPSR.shtml

Outputs:
  county_names_to_codes.json - Feed it a State and County Name, get the numeric code.
                               (Perfect for search script inputs)

  county_codes_to_names.json - Feed it a State and numeric Code, get the County Name.
                               (Perfect for printing GEDCOM or console output)

--------------------------------
"""
import csv
import json
import os


# ===========================================================================
# SECTION 1: BUILD THE JSON FILES FROM THE CSV
# ===========================================================================

def build_json_files(csv_path: str,
                     names_to_codes_path: str,
                     codes_to_names_path: str) -> None:
    """
    Reads the ICPSR county CSV and writes out two JSON lookup files.

    Args:
        csv_path:            Path to the input CSV file.
        names_to_codes_path: Path for the output county_names_to_codes.json
        codes_to_names_path: Path for the output county_codes_to_names.json
    """
    state_to_county_name_to_code = {}
    state_to_county_code_to_name = {}

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)

        # Header row: State, STATEICP, STATEFIPS, County cod, County, ...
        # Data starts on row 3
        cnt = 0
        for row in reader:
            cnt += 1
            if cnt < 3:
                continue

            # Guard against short rows
            if len(row) < 5:
                continue

            # .strip() removes accidental leading/trailing whitespace
            current_state = row[0].strip().title()
            code = row[3].strip()
            name = row[4].strip()

            if not current_state:
                continue

            # Only create the nested dict if the state isn't there yet
            if current_state not in state_to_county_name_to_code:
                state_to_county_name_to_code[current_state] = {}
                state_to_county_code_to_name[current_state] = {}

            state_to_county_name_to_code[current_state][name] = code
            state_to_county_code_to_name[current_state][code] = name

    # Make sure the output directory exists
    os.makedirs(os.path.dirname(names_to_codes_path), exist_ok=True)

    with open(names_to_codes_path, 'w') as f:
        json.dump(state_to_county_name_to_code, f, indent=4)

    with open(codes_to_names_path, 'w') as f:
        json.dump(state_to_county_code_to_name, f, indent=4)

    print("JSON generation complete!")


# ===========================================================================
# SECTION 2: THE GETTER — CountyLookup
# ===========================================================================

class CountyLookup:
    """
    Loads the two county JSON files once, then lets you look up codes
    or names quickly without re-reading the file every time.

    Usage:
        lookup = CountyLookup('../JSON/county_names_to_codes.json',
                              '../JSON/county_codes_to_names.json')

        code = lookup.get_code('New York', 'Albany')      # returns e.g. '0010'
        name = lookup.get_name('New York', '0010')        # returns e.g. 'Albany'

        # Or use the convenience methods that just return None on a miss
        # instead of raising an exception:
        code = lookup.find_code('new york', 'albany')     # case-insensitive
        name = lookup.find_name('New York', '0010')
    """

    def __init__(self, names_to_codes_path: str, codes_to_names_path: str):
        """
        Loads both JSON files into memory.  Call this once at startup;
        after that every lookup is just a dictionary access — very fast.
        """
        with open(names_to_codes_path, 'r', encoding='utf-8') as f:
            self._name_to_code = json.load(f)

        with open(codes_to_names_path, 'r', encoding='utf-8') as f:
            self._code_to_name = json.load(f)

    # ------------------------------------------------------------------
    # Primary getters — raise KeyError if state or county not found
    # ------------------------------------------------------------------

    def get_code(self, state: str, county_name: str) -> str:
        """
        Returns the ICPSR numeric code for a county name.
        Raises KeyError if state or county is not found.

        Example:
            code = lookup.get_code('New York', 'Albany')
        """
        return self._name_to_code[state.strip().title()][county_name.strip().title()]

    def get_name(self, state: str, county_code: str) -> str:
        """
        Returns the county name for an ICPSR numeric code.
        Raises KeyError if state or code is not found.

        Example:
            name = lookup.get_name('New York', '0010')
        """
        return self._code_to_name[state.strip().title()][county_code.strip()]

    # ------------------------------------------------------------------
    # Safe finders — return None instead of raising on a miss
    # ------------------------------------------------------------------

    def find_code(self, state: str, county_name: str) -> str | None:
        """
        Like get_code() but returns None if not found.
        Case-insensitive on both state and county name.

        Example:
            code = lookup.find_code('new york', 'albany')
        """
        state_data = self._name_to_code.get(state.strip().title())
        if state_data is None:
            return None
        return state_data.get(county_name.strip().title())

    def find_name(self, state: str, county_code: str) -> str | None:
        """
        Like get_name() but returns None if not found.

        Example:
            name = lookup.find_name('New York', '0010')
        """
        state_data = self._code_to_name.get(state.strip().title())
        if state_data is None:
            return None
        return state_data.get(county_code.strip())

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def list_states(self) -> list[str]:
        """Returns a sorted list of all state names in the lookup."""
        return sorted(self._name_to_code.keys())

    def list_counties(self, state: str) -> list[str]:
        """
        Returns a sorted list of all county names for a given state.
        Returns an empty list if the state is not found.
        """
        state_data = self._name_to_code.get(state.strip().title(), {})
        return sorted(state_data.keys())


# ===========================================================================
# SECTION 3: MAIN — builds the files, then does a quick smoke test
# ===========================================================================

if __name__ == '__main__':
    CSV_PATH = '../data/icpsrcnt.csv'
    NAMES_TO_CODES_PATH = '../JSON/county_names_to_codes.json'
    CODES_TO_NAMES_PATH = '../JSON/county_codes_to_names.json'

    # Step 1: Build the JSON files
    build_json_files(CSV_PATH, NAMES_TO_CODES_PATH, CODES_TO_NAMES_PATH)

    # Step 2: Load the getter and do a quick smoke test
    lookup = CountyLookup(NAMES_TO_CODES_PATH, CODES_TO_NAMES_PATH)

    print(f"\nStates loaded: {len(lookup.list_states())}")

    # Try a round-trip: name → code → name
    test_state = 'New York'
    test_county = lookup.list_counties(test_state)[0]  # first county alphabetically
    code = lookup.find_code(test_state, test_county)
    name = lookup.find_name(test_state, code)

    print(f"Test round-trip: '{test_county}' → code '{code}' → name '{name}'")
    print("Smoke test passed!" if name == test_county else "WARNING: round-trip mismatch!")
