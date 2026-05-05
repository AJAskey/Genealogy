import json
import os
import re

TARGET_VARS = []


def set_target_vars(filepath):
    bad_tgts = ["COUNTYICP", "NFATHERS", "FAMUNIT", "FAMSIZE", "NCHILD", "NSIBS", "ELDCH", "YNGCH", "AGE",
                "HISTID", "Description:", "1940", "Note:", "SERIAL", "YEAR", "PERNUM", "NUMPREC", "HHWT", "PERWT",
                "BIRTHYR", "MOMLOC", "POPLOC", "SPLOC"]

    target_vars = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith("Variable"):
                # Process next line(s) to extract variable names
                next_line = next(f).strip()
                while next_line and not next_line.startswith("All Years X"):
                    if not any(bad in next_line for bad in bad_tgts):
                        target_vars.append(next_line.split()[0])
                    next_line = next(f).strip()
    return target_vars


def parse_ipums_codebook(filepath, target_variable):
    codes_dict = {}
    is_capturing = False

    with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
        for line in file:
            line = line.strip()

            if is_capturing and (not line or not line.isdigit()):
                continue

            if line.startswith(target_variable):
                is_capturing = True
                continue

            if is_capturing and line.isdigit():
                match = re.match(r'^(\d+)\s+(.+)$', line)
                if match:
                    code = match.group(1).strip()
                    description = match.group(2).strip()
                    codes_dict[code] = description
    return codes_dict


def detect_key_width(codemap):
    return len(next(iter(codemap), '')) if codemap else 1


def write_getter(variable_name, json_path, key_width, output_dir):
    l_var = variable_name.lower()
    u_var = variable_name.upper()

    filename = os.path.join(output_dir, f"_get_{l_var}.py")

    getter_code = f'''"""\nFile: _get_{l_var}.py  (auto-generated)\n\nSummary: Data Access Layer for {u_var} codes.\n"""
import json

_map = {{}}  # code_string -> description
_width = 1   # key width detected from JSON

_json_path = r"{json_path}"

try:
    with open(_json_path, 'r') as _f:
        _raw = json.load(_f)
    _map = _raw.get("{u_var}")
    _width = len(next(iter(_map), '')) if _map else 1
except FileNotFoundError:
    print(f"WARNING: {_json_path} not found")
except json.JSONDecodeError:
    print(f"WARNING: could not load {_json_path}: JSON decode error")
except Exception as _e:
    print(f"WARNING: {_e}")

def get_{l_var}(code):
    try:
        if isinstance(code, int):
            normalized = str(code).zfill(_width)
        elif isinstance(code, str) and code.isdigit():
            normalized = code.zfill(_width)
        else:
            return f"Unknown({code})"
        return _map.get(normalized, f"Unknown({normalized})")
    except Exception:
        return f"Unknown({code})"

if __name__ == "__main__":
    print(f"--- Testing {u_var} Getter (key width = {_width}) ---")
    if _map:
        first_key = next(iter(_map))
        test_inputs = [
            int(first_key),
            str(first_key),
            first_key.lstrip("0") or "0"
        ]
        print(f"    Testing all input formats for key={first_key!r}:")
        for t in test_inputs:
            result = get_{l_var}(t)
            print(f"      get_{l_var}({t!r:>8}) -> {result}")
    else:
        print("    No data loaded -- check JSON path.")
'''
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(getter_code)
    return os.path.exists(filename)


if __name__ == '__main__':
    CODEBOOK_FILE = r"../data/basic.txt"
    JSON_DIR = r"JSON"
    GETTER_DIR = r"getters"

    os.makedirs(JSON_DIR, exist_ok=True)
    os.makedirs(GETTER_DIR, exist_ok=True)

    success_count = 0
    fail_list = []

    target_vars = set_target_vars(CODEBOOK_FILE)
    print(f"Variables found in codebook: {len(target_vars)}")

    for var in target_vars:
        print(f"Processing {var}...")
        codes = parse_ipums_codebook(CODEBOOK_FILE, var)
        if not codes:
            print(f"  No code definitions found -- skipping")
            fail_list.append(var)
            continue

        width = detect_key_width(codes)
        json_file = os.path.join(JSON_DIR, f"{var.lower()}_codes.json")

        with open(json_file, 'w', encoding='utf-8') as jf:
            json.dump({var: codes}, jf, indent=4, ensure_ascii=False)

        if write_getter(var, json_file, width, GETTER_DIR):
            success_count += 1

    print(f"\nDone. {success_count} variables processed successfully.")
    if fail_list:
        print(f"No code definitions found for {len(fail_list)} variables:")
        print(f"  {fail_list}")
