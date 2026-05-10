"""
export_codebook_json.py

Reads codebook.db and exports it as codebook.json
Format:
{
    "RACE": {
        "description": "Race [general version]",
        "codes": {
            "1": "White",
            "2": "Black/African American",
            ...
        }
    },
    ...
}
"""

import json
import sqlite3
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
CODEBOOK_DB   = r"D:\Data\Genealogy_Data\codebook.db"
CODEBOOK_JSON = r"E:\Users\Andy\PycharmProjects\Genealogy\JSON\codebook.json"
# ───────────────────────────────────────────────────────────────────────────────


def main():
    db_path   = Path(CODEBOOK_DB)
    json_path = Path(CODEBOOK_JSON)

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    # Pull all variables
    cur.execute("SELECT varname, description FROM variables ORDER BY varname")
    variables = cur.fetchall()

    codebook = {}

    for varname, description in variables:
        # Pull all codes for this variable
        cur.execute(
            "SELECT code, label FROM codes WHERE varname = ? ORDER BY code",
            (varname,)
        )
        codes = {code: label for code, label in cur.fetchall()}

        codebook[varname] = {
            "description": description,
            "codes": codes
        }

    conn.close()

    # Write JSON -- indent=2 keeps it human readable
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(codebook, f, indent=2, ensure_ascii=False)

    print(f"Written: {json_path}")
    print(f"  {len(codebook)} variables")


if __name__ == "__main__":
    main()