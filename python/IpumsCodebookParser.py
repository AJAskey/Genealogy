"""
-----------------------------------
File: IpumsCodebookParser.py

Summary: Parses an IPUMS codebook text file (basic.txt), extracts
         code/description pairs for each variable, saves them as
         JSON files, and generates a matching _get_xxx.py getter module
         for each variable.

         The getter modules handle ALL input formats automatically.
         Example: code 70, "70", "070", or "0070" all return
         "Albuquerque, NM" for CITY -- no matter what the database
         hands back.

         Key width (1, 2, 3, 4 digits) is detected from the JSON data
         itself at getter load time, so nothing is hardcoded.

Design:  1. set_target_vars() reads the variable list directly from the
            header section of basic.txt so the target list is always in
            sync with the current IPUMS extract -- no hardcoded list needed.
         2. parse_ipums_codebook() scans the file for a variable header
            and returns a dict of {code_string: description}.
         3. The __main__ block loops over all target variables, saves
            each JSON, then calls write_getter() to produce the
            corresponding _get_xxx.py file.
         4. write_getter() generates a self-contained module with a
            load-once cache, a normalize-and-lookup function, and a
            test block that exercises several input formats.

Inputs:  E:/Claude/data/basic.txt  (IPUMS codebook for current extract)

Outputs: E:/Claude/JSON/<var>_codes.json      one per variable
         E:/Claude/python/_get_<var>.py       one getter module per variable

--------------------------------
"""

import json
import os
import re

# Populated dynamically from basic.txt by set_target_vars()
TARGET_VARS = []


def set_target_vars(filepath):
    """
    Reads the variable list from the header section of the IPUMS codebook.
    Populates the global TARGET_VARS list so the parser stays in sync with
    whatever variables are in the current extract -- no hardcoded list needed.
    Skips YEAR and SAMPLE which are metadata fields without code definitions.
    """
    find_vars = False

    with open(filepath, 'r', encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line.startswith("Variable"):
                find_vars = True
                continue

            if find_vars:
                if len(line) < 1:
                    break
                if line.startswith("YEAR"):
                    continue
                if line.startswith("SAMPLE"):
                    continue
                if line.startswith("All Years X"):
                    return

                v = line.split()
                TARGET_VARS.append(v[0])


# ---------------------------------------------------------------------------
# PART 1 -- PARSER
# ---------------------------------------------------------------------------

def parse_ipums_codebook(filepath, target_variable):
    """
    Scans an IPUMS codebook text file and extracts code/description pairs
    for one variable. Returns a plain dict {code_string: description}.
    Variables with no code definitions (SERIAL, AGE, BIRTHYR etc.) will
    return an empty dict and are skipped by the caller.
    """
    codes_dict   = {}
    is_capturing = False

    with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
        for line in file:
            line = line.strip()

            # Stop when we hit a blank line or a non-digit line after capture starts
            if is_capturing and (line == "" or not line[0].isdigit()):
                if codes_dict:
                    break

            # Start capturing on the exact variable header line
            if line.startswith(target_variable):
                is_capturing = True
                continue

            # Capture lines that look like:  0070  Albuquerque, NM
            if is_capturing:
                match = re.match(r"^(\d+)\s+(.+)$", line)
                if match:
                    code        = match.group(1).strip()
                    description = match.group(2).strip()
                    codes_dict[code] = description

    return codes_dict


# ---------------------------------------------------------------------------
# PART 2 -- GETTER GENERATOR
# ---------------------------------------------------------------------------

def detect_key_width(codemap):
    """
    Returns the length of the first key in codemap.
    All keys for a given IPUMS variable are the same width so
    checking the first one is sufficient.
    Returns 1 if the map is empty (safe fallback).
    """
    if not codemap:
        return 1
    return len(next(iter(codemap)))


def write_getter(variable_name, json_path, key_width, output_dir):
    """
    Writes a self-contained _get_<var>.py getter module.

    The generated module:
      - loads the JSON once at import time into a module-level cache
      - detects key width from the JSON itself (stays correct even if
        the JSON is regenerated with a different width)
      - normalises any incoming code to the right width before lookup
      - includes a test block that exercises several input formats
    """
    l_var = variable_name.lower()
    u_var = variable_name.upper()

    filename = os.path.join(output_dir, f"_get_{l_var}.py")

    getter_code = f'''"""
-----------------------------------
File: _get_{l_var}.py  (auto-generated by IpumsCodebookParser.py)

Summary: Data Access Layer for {u_var} codes.
         Accepts any numeric representation of the code:
         integer or string, with or without leading zeros.
         Key width ({key_width} digits for {u_var}) is detected
         automatically from the JSON, so no hardcoding needed.
--------------------------------
"""
import json


# ---------------------------------------------------------------------------
# 1. CACHE -- loaded once at import time
# ---------------------------------------------------------------------------
_map   = {{}}          # code_string -> description
_width = 1            # key width detected from JSON (e.g. 1, 2, 3, 4)

_json_path = r"E:/Claude/JSON/{l_var}_codes.json"

try:
    with open(_json_path, 'r', encoding='utf-8') as _f:
        _raw = json.load(_f)
    _map = _raw.get("{u_var}", _raw)
    _width = len(next(iter(_map))) if _map else 1
except FileNotFoundError:
    print(f"WARNING: {{_json_path}} not found -- {u_var} lookups will return Unknown")
except Exception as _e:
    print(f"WARNING: could not load {u_var} codes: {{_e}}")


# ---------------------------------------------------------------------------
# 2. GETTER
# ---------------------------------------------------------------------------
def get_{l_var}(code):
    """
    Returns the description for a {u_var} code.

    Accepts: integer 70, string "70", "070", or "0070" -- all equivalent.
    Returns: description string, or "Unknown (<code>)" if not found.
    """
    try:
        normalized = str(int(str(code).strip())).zfill(_width)
    except (ValueError, TypeError):
        return f"Unknown ({{code}})"
    return _map.get(normalized, f"Unknown ({{normalized}})")


# ---------------------------------------------------------------------------
# 3. TEST BLOCK
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"--- Testing {u_var} Getter (key width = {{_width}}) ---")
    print(f"    JSON entries loaded: {{len(_map)}}")
    print()

    if _map:
        first_key = next(iter(_map))
        first_val = int(first_key)

        test_inputs = [
            first_val,
            str(first_val),
            first_key.lstrip("0") or "0",
            first_key,
        ]

        print(f"    Testing all input formats for key={{first_key!r}} ({{_map[first_key]}}):")
        for t in test_inputs:
            result = get_{l_var}(t)
            print(f"      get_{l_var}({{t!r:>8}}) -> {{result}}")
    else:
        print("    No data loaded -- check JSON path.")
'''

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(getter_code)

    print(f"  Getter written: {filename}")


# ---------------------------------------------------------------------------
# PART 3 -- MAIN
# ---------------------------------------------------------------------------

if __name__ == '__main__':

    CODEBOOK_FILE = r"E:/Claude/data/basic.txt"
    JSON_DIR      = r"E:/Claude/JSON"
    GETTER_DIR    = r"E:/Claude/python"

    os.makedirs(JSON_DIR,   exist_ok=True)
    os.makedirs(GETTER_DIR, exist_ok=True)

    success_count = 0
    fail_list     = []

    set_target_vars(CODEBOOK_FILE)
    print(f"Variables found in codebook: {len(TARGET_VARS)}\n")

    for var in TARGET_VARS:
        print(f"Processing {var} ...")

        codes = parse_ipums_codebook(CODEBOOK_FILE, var)

        if not codes:
            print(f"  No code definitions found -- skipping")
            fail_list.append(var)
            continue

        width = detect_key_width(codes)
        print(f"  Found {len(codes)} codes, key width = {width}")

        json_file = os.path.join(JSON_DIR, f"{var.lower()}_codes.json")
        with open(json_file, 'w', encoding='utf-8') as jf:
            json.dump({var: codes}, jf, indent=4)
        print(f"  JSON saved: {json_file}")

        write_getter(var, json_file, width, GETTER_DIR)

        success_count += 1

    print(f"\n{'='*50}")
    print(f"Done. {success_count} variables processed successfully.")
    if fail_list:
        print(f"\nNo code definitions found for {len(fail_list)} variables:")
        print(f"  {fail_list}")
        print("These are numeric data fields (AGE, SERIAL etc.) that do not need getters.")
