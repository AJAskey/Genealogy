import csv
import json
import os


def build_county_json_from_csv(csv_path, json_path):
    print(f"Reading US Counties CSV from: {csv_path}")
    county_db = {}

    if not os.path.exists(csv_path):
        print(f"Error: Could not find the file at {csv_path}")
        return

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        # Grab the field names to intelligently map the columns
        fieldnames = [f.lower() for f in reader.fieldnames]

        # Sniff out the correct column names for FIPS, Lat, and Lon
        fips_col = next((col for col in reader.fieldnames if col.lower() in ['county_fips', 'fips', 'geoid']), None)
        lat_col = next((col for col in reader.fieldnames if col.lower() in ['lat', 'latitude', 'intptlat']), None)
        lon_col = next(
            (col for col in reader.fieldnames if col.lower() in ['lng', 'lon', 'long', 'longitude', 'intptlong']), None)
        name_col = next((col for col in reader.fieldnames if col.lower() in ['county', 'county_name', 'name']), None)
        state_col = next((col for col in reader.fieldnames if col.lower() in ['state_id', 'state', 'usps']), None)

        if not all([fips_col, lat_col, lon_col]):
            print(
                f"Error: Could not automatically detect FIPS, Lat, or Lon columns in the CSV headers: {reader.fieldnames}")
            return

        for row in reader:
            geoid = str(row[fips_col]).strip()

            # Ensure GEOID is exactly 5 digits (some CSVs drop the leading zero for states like Alabama '01')
            geoid = geoid.zfill(5)

            name = str(row[name_col]).strip() if name_col else "Unknown County"
            state = str(row[state_col]).strip() if state_col else ""

            try:
                county_db[geoid] = {
                    "name": f"{name}, {state}".strip(", "),
                    "lat": float(row[lat_col]),
                    "lon": float(row[lon_col])
                }
            except (ValueError, TypeError):
                continue  # Skip any row with missing or mangled coordinate math

    with open(json_path, 'w', encoding='utf-8') as jf:
        json.dump(county_db, jf, indent=4)

    print(f"Successfully processed {len(county_db)} counties.")
    print(f"Saved spatial database to: {json_path}")


if __name__ == '__main__':
    # Input CSV and Output JSON paths
    INPUT_CSV = r"E:\Users\Andy\PycharmProjects\Genealogy\data\uscounties.csv"
    OUTPUT_JSON = r"E:\Users\Andy\PycharmProjects\Genealogy\JSON\county_coords.json"

    build_county_json_from_csv(INPUT_CSV, OUTPUT_JSON)
