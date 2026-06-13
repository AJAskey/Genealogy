"""
-----------------------------------
File: ValidateLocations.py

Summary: Scans the ftm_extracted.csv file and checks every single birthplace
         against the IPUMS translation dictionary. Flags any locations that
         the system currently does not recognize.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import csv
import glob
import os

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))

search_pattern = os.path.join(project_root, "gedcom_sources", "*_individuals.csv")
files = glob.glob(search_pattern)
CSV_PATH = files[0] if files else os.path.join(project_root, "gedcom_sources", "gedcom_individuals.csv")

# The exact dictionary used by our overlay script
crosswalk = {
    "alabama": ["01", "1"], "alaska": ["02", "2"], "arizona": ["04", "4"], "arkansas": ["05", "5"],
    "california": ["06", "6"], "colorado": ["08", "8"], "connecticut": ["09", "9"],
    "delaware": ["10"], "district of columbia": ["11"], "florida": ["12"],
    "georgia": ["13"], "hawaii": ["15"], "idaho": ["16"], "illinois": ["17"],
    "indiana": ["18"], "iowa": ["19"], "kansas": ["20"], "kentucky": ["21"],
    "louisiana": ["22"], "maine": ["23"], "maryland": ["24"], "massachusetts": ["25"],
    "michigan": ["26"], "minnesota": ["27"], "mississippi": ["28"], "missouri": ["29"],
    "montana": ["30"], "nebraska": ["31"], "nevada": ["32"], "new hampshire": ["33"],
    "new jersey": ["34"], "new mexico": ["35"], "new york": ["36"], "north carolina": ["37"],
    "north dakota": ["38"], "ohio": ["39"], "oklahoma": ["40"], "oregon": ["41"],
    "pennsylvania": ["42", "042"], "rhode island": ["44", "044"], "south carolina": ["45", "045"],
    "south dakota": ["46", "046"], "tennessee": ["47", "047"], "texas": ["48", "048"],
    "utah": ["49", "049"], "vermont": ["50", "050"], "virginia": ["51", "051"],
    "washington": ["53", "053"], "west virginia": ["54", "054"], "wisconsin": ["55", "055"],
    "wyoming": ["56", "056"],

    "england": ["410"], "scotland": ["411"], "wales": ["412"],
    "ireland": ["414"], "northern ireland": ["414"],
    "germany": ["453"], "sweden": ["404"], "norway": ["401"],
    "denmark": ["400"], "netherlands": ["425"], "france": ["421"],
    "switzerland": ["426"], "canada": ["150"], "mexico": ["200"],
    "japan": ["501"], "south korea": ["502"], "korea": ["502"]
}


def main():
    if not os.path.exists(CSV_PATH):
        print(f"File not found: {CSV_PATH}")
        return

    unrecognized = set()
    total_checked = 0

    with open(CSV_PATH, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            places = [
                row.get('Birth Place', '').strip(),
                row.get('Father Birth Place', '').strip(),
                row.get('Mother Birth Place', '').strip()
            ]

            for p in places:
                if p:
                    total_checked += 1
                    p_lower = p.lower()
                    if not any(state in p_lower for state in crosswalk.keys()):
                        unrecognized.add(p)

    print(f"\nScan complete! Checked {total_checked} locations.")
    if not unrecognized:
        print("All locations perfectly match the dictionary! You are 100% ready.")
    else:
        print(f"\nFound {len(unrecognized)} unrecognized locations:")
        for u in sorted(unrecognized):
            print(f"  - {u}")


if __name__ == '__main__':
    main()
