"""
File: CSV_to_JSON.py
Summary: A utility script to convert a CSV file into a JSON file.
         This allows you to manage your target ancestors in Excel (CSV),
         and instantly convert them into the JSON format expected by the DuckDB pipeline.
"""
import csv
import json
import os

# --- CONFIGURATION ---
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(project_root, "JSON", "duck_hunting.csv")
JSON_PATH = os.path.join(project_root, "JSON", "duck_hunting.json")


def main():
    print(f"--- Starting CSV to JSON Converter ---")

    if not os.path.exists(CSV_PATH):
        print(f"ERROR: Cannot find CSV file at {CSV_PATH}")
        print("Please ensure your Excel file is saved as a CSV in that location.")
        return

    data = []

    # Read the CSV (DictReader automatically uses the first row as the JSON keys!)
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            str = row['h_first']
            if not str or len(str.strip()) < 1:
                continue
            data.append(row)

    # Write the JSON
    with open(JSON_PATH, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4)

    print(f"SUCCESS! Converted {len(data)} rows from CSV into {JSON_PATH}")


if __name__ == "__main__":
    main()
