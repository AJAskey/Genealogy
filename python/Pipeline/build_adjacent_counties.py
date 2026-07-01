import json
import os
import sys

# Add local directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

from GeoUtils import haversine_distance
from us_states import us_state_data

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
MAX_DISTANCE_MILES = 40.0

# Paths relative to the script location
JSON_DIR = os.path.abspath(os.path.join(script_dir, "..", "..", "JSON"))
COUNTY_NAMES_PATH = os.path.join(JSON_DIR, "county_codes_to_names.json")
COUNTY_COORDS_PATH = os.path.join(JSON_DIR, "county_coords.json")
CODEBOOK_PATH = os.path.join(JSON_DIR, "codebook.json")
OUTPUT_PATH = os.path.join(JSON_DIR, "adjacent_counties.json")

# ==============================================================================
# NAME NORMALIZATION
# ==============================================================================
def normalize_name(name):
    """Normalize county name to facilitate matches despite spelling differences."""
    if not name:
        return ""
    n = name.lower()
    # Replace common accents
    n = n.replace("ñ", "n").replace("ó", "o").replace("í", "i").replace("á", "a")
    # Strip suffixes and special chars
    for word in [" county", " city", " parish", " reservation", " judicial division", " district"]:
        n = n.replace(word, "")
    n = n.replace(".", "").replace("'", "").replace("`", "").replace(" ", "").replace("-", "").strip()
    return n

# ==============================================================================
# HISTORICAL & CUSTOM COORDINATES MAP
# ==============================================================================
# Connecticut traditional counties (since county_coords has modern Planning Regions)
CT_COUNTIES = {
    "fairfield": {"lat": 41.2682, "lon": -73.3828},
    "hartford": {"lat": 41.8028, "lon": -72.7303},
    "litchfield": {"lat": 41.7915, "lon": -73.2458},
    "middlesex": {"lat": 41.4397, "lon": -72.5255},
    "newhaven": {"lat": 41.3484, "lon": -72.9530},
    "newlondon": {"lat": 41.4775, "lon": -72.1062},
    "tolland": {"lat": 41.8517, "lon": -72.3370},
    "windham": {"lat": 41.8318, "lon": -71.9877}
}

# Alaska historical judicial divisions
AK_HISTORICAL = {
    "northerndistrict": {"lat": 65.0, "lon": -150.0},
    "southerndistrict": {"lat": 60.0, "lon": -145.0},
    "first": {"lat": 57.0, "lon": -135.0},
    "second": {"lat": 66.0, "lon": -162.0},
    "third": {"lat": 61.0, "lon": -150.0},
    "fourth": {"lat": 65.0, "lon": -150.0}
}

# Other historical/unmatched counties or custom reservations
CUSTOM_COORDINATES = {
    # Georgia historical
    "campbell|GA": {"lat": 33.6, "lon": -84.6}, # Annexed into Fulton
    "milton|GA": {"lat": 34.1, "lon": -84.3}, # Annexed into Fulton
    # Florida historical
    "dade|FL": {"lat": 25.6150, "lon": -80.5624}, # Miami-Dade
    # Kentucky historical
    "joshbell|KY": {"lat": 36.73, "lon": -83.67}, # Now Bell County
    # Idaho historical
    "alturas|ID": {"lat": 43.5, "lon": -114.5},
    "logan|ID": {"lat": 43.0, "lon": -114.4},
    # California historical
    "klamath|CA": {"lat": 41.5, "lon": -123.8},
    # Colorado historical
    "greenwood|CO": {"lat": 38.5, "lon": -102.7},
    # Nevada historical
    "riovirgin|NV": {"lat": 36.5, "lon": -114.1},
    "roop|NV": {"lat": 40.5, "lon": -119.9},
    "stmarys|NV": {"lat": 39.0, "lon": -114.5},
    # New Mexico historical
    "santaana|NM": {"lat": 35.3, "lon": -106.5},
    # South Carolina historical
    "pendleton|SC": {"lat": 34.6, "lon": -82.8},
    # Texas historical
    "buchel|TX": {"lat": 29.8, "lon": -102.3},
    "encinal|TX": {"lat": 27.9, "lon": -99.4},
    "zavalla|TX": {"lat": 28.7, "lon": -99.8},
    # Tennessee historical
    "james|TN": {"lat": 35.1, "lon": -85.0},
    # Oregon historical
    "umpqua|OR": {"lat": 43.7, "lon": -123.8},
    # Hawaii Oahu
    "oahu|HI": {"lat": 21.43, "lon": -157.97},
    "unknown|HI": {"lat": 21.0, "lon": -157.0},
    # Michigan Isle Royale (annexed to Keweenaw)
    "isleroyale|MI": {"lat": 47.4, "lon": -88.1},
    "manitou|MI": {"lat": 45.2, "lon": -86.1},
    # Arizona Indian Reservations
    "sancarlosindianreservation|AZ": {"lat": 33.3, "lon": -110.2},
    # Oklahoma Indian Nations / Reservations
    "cherokeenation|OK": {"lat": 35.91, "lon": -94.97},
    "chickasawnation|OK": {"lat": 34.50, "lon": -97.00},
    "choctawnation|OK": {"lat": 34.30, "lon": -95.50},
    "creeknation|OK": {"lat": 35.60, "lon": -96.00},
    "seminolenation|OK": {"lat": 35.20, "lon": -96.60},
    "osagenation|OK": {"lat": 36.60, "lon": -96.30},
    # Other Oklahoma Nations
    "modocnation|OK": {"lat": 36.95, "lon": -94.63},
    "ottawanation|OK": {"lat": 36.85, "lon": -94.75},
    "peorianation|OK": {"lat": 36.90, "lon": -94.80},
    "senecanation|OK": {"lat": 36.70, "lon": -94.75},
    "shawneenation|OK": {"lat": 35.30, "lon": -96.90},
    "wyandottenation|OK": {"lat": 36.80, "lon": -94.70},
    "kawindianreservation|OK": {"lat": 36.80, "lon": -96.80},
    "apachekiowaandcomanchereservation|OK": {"lat": 34.60, "lon": -98.40},
    "wichitareservation|OK": {"lat": 35.20, "lon": -98.20},
    # South Dakota / North Dakota / Montana Reservations
    "standingrock|SD": {"lat": 45.8, "lon": -100.8},
    "standingrock|ND": {"lat": 45.8, "lon": -100.8},
    "standingrockreservation|ND": {"lat": 45.8, "lon": -100.8},
    "cheyenneriver|SD": {"lat": 45.0, "lon": -101.2},
    "pineriverreservation(alternate)|SD": {"lat": 43.2, "lon": -102.2},
    "crowreservation|MT": {"lat": 45.4, "lon": -107.5},
    "whiteearth|MN": {"lat": 47.2, "lon": -95.8},
    "whiteearthreservation|MN": {"lat": 47.2, "lon": -95.8},
}

# ==============================================================================
# RESOLVER
# ==============================================================================
def get_county_coords(state_name, county_name, state_name_to_abbr, coords_index):
    """Resolves coordinates for a county name using standard, custom, or fuzzy matching."""
    norm_state = state_name.lower()
    county_parts = county_name.split("/")
    state_abbr = state_name_to_abbr.get(norm_state)
    
    # 1. Connecticut traditional counties
    if norm_state == "connecticut":
        for p in county_parts:
            np = normalize_name(p)
            if np in CT_COUNTIES:
                return CT_COUNTIES[np]
    
    # 2. Alaska historical judicial divisions
    if norm_state == "alaska":
        for p in county_parts:
            np = normalize_name(p)
            for k, v in AK_HISTORICAL.items():
                if k in np:
                    return v

    if state_abbr:
        for p in county_parts:
            np = normalize_name(p)
            
            # Check custom coordinates index first
            custom_key = f"{np}|{state_abbr}"
            if custom_key in CUSTOM_COORDINATES:
                return CUSTOM_COORDINATES[custom_key]
            
            # Check regular coordinate index
            if custom_key in coords_index:
                return coords_index[custom_key]

            # Check historical VA/WV split (West Virginia was originally part of Virginia in census)
            if state_abbr == "VA":
                wv_key = f"{np}|WV"
                if wv_key in coords_index:
                    return coords_index[wv_key]
                if wv_key in CUSTOM_COORDINATES:
                    return CUSTOM_COORDINATES[wv_key]

    # 3. Fuzzy match: Search across all states if a unique matching name exists anywhere in the US
    for p in county_parts:
        np = normalize_name(p)
        matches = []
        for key, val in coords_index.items():
            c_part, s_part = key.split("|")
            if c_part == np:
                matches.append(val)
        if len(matches) == 1:
            return matches[0]

    return None

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print("====================================================")
    print("  COUNTY ADJACENCY BUILDER")
    print("====================================================")

    # 1. Load data files
    print(f"Loading {COUNTY_NAMES_PATH}...")
    with open(COUNTY_NAMES_PATH, 'r', encoding='utf-8') as f:
        county_names = json.load(f)

    print(f"Loading {COUNTY_COORDS_PATH}...")
    with open(COUNTY_COORDS_PATH, 'r', encoding='utf-8') as f:
        county_coords = json.load(f)

    print(f"Loading {CODEBOOK_PATH}...")
    with open(CODEBOOK_PATH, 'r', encoding='utf-8') as f:
        codebook = json.load(f)

    # 2. Build lookups
    # Map state names to abbreviations
    state_name_to_abbr = {s["name"].lower(): s["abbr"].upper() for s in us_state_data}
    state_name_to_abbr["district of columbia"] = "DC"

    # Map state names to BPL codes (from codebook.json)
    bpl_codes = codebook.get("BPL", {}).get("codes", {})
    bpl_state_map = {name.lower(): code for code, name in bpl_codes.items()}
    # DC fallback mapping
    bpl_state_map["district of columbia"] = "098"

    # Build coordinates index
    coords_index = {}
    for fips, val in county_coords.items():
        parts = val["name"].split(",")
        if len(parts) == 2:
            c_name = parts[0].strip().lower()
            s_abbr = parts[1].strip().upper()
            c_clean = normalize_name(c_name)
            coords_index[f"{c_clean}|{s_abbr}"] = val

    # 3. Pre-resolve coordinates for all target counties
    print("\nResolving county coordinates...")
    resolved_counties = []
    unmatched_counties = []

    for state, counties in county_names.items():
        if state == "Other":
            continue
        
        state_bpl = bpl_state_map.get(state.lower())
        if not state_bpl:
            print(f"Warning: Missing BPL state code for state '{state}'")
            continue

        for code, name in counties.items():
            coords = get_county_coords(state, name, state_name_to_abbr, coords_index)
            if coords:
                resolved_counties.append({
                    "state_name": state,
                    "state_bpl": state_bpl,
                    "county_code": code,
                    "county_name": name,
                    "lat": coords["lat"],
                    "lon": coords["lon"]
                })
            else:
                unmatched_counties.append((state, code, name))

    print(f"Successfully resolved {len(resolved_counties)} / {len(resolved_counties) + len(unmatched_counties)} counties ({len(resolved_counties)/(len(resolved_counties) + len(unmatched_counties))*100:.2f}%)")
    if unmatched_counties:
        print(f"Unmatched counties: {len(unmatched_counties)}")
        # Print a few samples
        for s, c, n in unmatched_counties[:10]:
            print(f"  - {s} Code {c}: {n}")

    # 4. Calculate adjacencies
    print("\nComputing adjacent counties (within 40 miles)...")
    output_adjacencies = {}

    for state, counties in county_names.items():
        output_adjacencies[state] = {}
        
        # Resolve BPL code for target state
        state_bpl = bpl_state_map.get(state.lower())
        if not state_bpl:
            # For "Other", output empty values
            for code, name in counties.items():
                output_adjacencies[state][code] = ""
            continue

        for code, name in counties.items():
            # Find coordinates of target county
            target_coords = get_county_coords(state, name, state_name_to_abbr, coords_index)
            
            if not target_coords:
                # Fallback: if coordinate is unresolved, list only its own code to prevent crashes
                output_adjacencies[state][code] = f"{state_bpl}:{code}"
                continue

            lat1, lon1 = target_coords["lat"], target_coords["lon"]
            adjacent_list = []

            # Compare against all pre-resolved counties
            for other in resolved_counties:
                lat2, lon2 = other["lat"], other["lon"]
                dist = haversine_distance(lat1, lon1, lat2, lon2)
                if dist <= MAX_DISTANCE_MILES:
                    adjacent_list.append((dist, f"{other['state_bpl']}:{other['county_code']}"))

            # Sort by distance, then format as pipe-separated string
            adjacent_list.sort()
            formatted_adjacencies = " | ".join([item[1] for item in adjacent_list])
            output_adjacencies[state][code] = formatted_adjacencies

    # 5. Save the output
    print(f"\nSaving output to {OUTPUT_PATH}...")
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_adjacencies, f, indent=4, sort_keys=True)

    print("Success! County adjacency JSON database created.")
    print("====================================================")


if __name__ == "__main__":
    main()
