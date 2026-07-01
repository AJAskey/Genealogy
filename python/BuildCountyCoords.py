import json
import os


def build_county_json(txt_path, json_path):
    print(f"Reading Census Gazetteer file from: {txt_path}")
    county_db = {}

    try:
        with open(txt_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find the file at {txt_path}")
        return

    if not lines:
        print("File is empty.")
        return

    # The Census files sometimes use pipes (|) or tabs (\t). 
    # We will sniff the first line to be safe.
    header_line = lines[0].strip()
    delimiter = '|' if '|' in header_line else '\t'
    header = header_line.split(delimiter)

    try:
        geoid_idx = header.index('GEOID')
        name_idx = header.index('NAME')
        state_idx = header.index('USPS')
        lat_idx = header.index('INTPTLAT')
        lon_idx = header.index('INTPTLONG')
    except ValueError as e:
        print(f"Error finding required columns in header. Found: {header}")
        return

    for line in lines[1:]:
        if not line.strip():
            continue

        parts = line.strip().split(delimiter)
        geoid = parts[geoid_idx].strip()
        name = parts[name_idx].strip()
        state = parts[state_idx].strip()

        # Strip out whitespace and any leading '+' signs from the coordinates
        lat_str = parts[lat_idx].strip().replace('+', '')
        lon_str = parts[lon_idx].strip().replace('+', '')

        try:
            county_db[geoid] = {
                "name": f"{name}, {state}",
                "lat": float(lat_str),
                "lon": float(lon_str)
            }
        except ValueError:
            continue  # Skip any row with mangled coordinate math

    with open(json_path, 'w', encoding='utf-8') as jf:
        json.dump(county_db, jf, indent=4)

    print(f"Successfully processed {len(county_db)} counties.")
    print(f"Saved spatial database to: {json_path}")


if __name__ == '__main__':
    INPUT_TXT = r"E:\Users\Andy\PycharmProjects\Genealogy\data\2025_Gaz_counties_national.txt"
    OUTPUT_JSON = r"E:\Users\Andy\PycharmProjects\Genealogy\JSON\county_coords.json"

    build_county_json(INPUT_TXT, OUTPUT_JSON)
