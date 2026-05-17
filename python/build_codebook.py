"""
build_codebook.py

Parses an IPUMS basic.txt file and builds a codebook.db SQLite database.
Tables:
    variables  -- variable name + description
    codes      -- variable, code, label  (meaningful entries only)

Skips:
    - Section headers (indented lines with no code)
    - Tautological entries where label == code  (1=1, 2=2, etc.)
    - Variables where no meaningful codes survive filtering
"""

import re
import sqlite3
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
BASIC_FILE   = r"E:\Users\Andy\PycharmProjects\Genealogy\data\basic.txt"
CODEBOOK_DB  = r"D:\Data\Genealogy_Data\codebook.db"
VERBOSE      = True   # Print progress as it runs
# ───────────────────────────────────────────────────────────────────────────────


# Matches a variable header line:  VARNAME    Some description text
# Variable names are all caps, no spaces, start at column 0
VAR_HEADER   = re.compile(r'^([A-Z][A-Z0-9_]+)\s{2,}(.+)$')

# Matches a code line:  123    Some label text
# Code is digits/letters at start of line, followed by 2+ spaces, then label
CODE_LINE    = re.compile(r'^(\S+)\s{2,}(.+)$')


def is_tautology(code: str, label: str) -> bool:
    """Return True if label conveys no more information than the code itself."""
    # Direct match:  "1" = "1"
    if code.strip() == label.strip():
        return True
    # Numeric code where label is just the same number
    # e.g. code="01" label="1" or code="1" label="01"
    try:
        if int(code) == int(label):
            return True
    except ValueError:
        pass
    return False


def parse_basic_file(filepath: Path) -> dict:
    """
    Parse the basic .txt file into a dict:
        { varname: { 'description': str, 'codes': { code: label } } }
    """
    variables   = {}
    current_var = None

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Remove trailing whitespace but preserve leading spaces
            line = line.rstrip()

            # Blank line -- no action needed
            if not line.strip():
                continue

            # Check for a variable header (starts at column 0, all-caps name)
            var_match = VAR_HEADER.match(line)
            if var_match and not line.startswith(' '):
                varname = var_match.group(1)
                desc    = var_match.group(2).strip()

                # Skip the file header pseudo-variables
                if varname in ('Variable', 'RECTYPE', 'All'):
                    current_var = None
                    continue

                current_var = varname
                variables[varname] = {
                    'description': desc,
                    'codes': {}
                }
                if VERBOSE:
                    print(f"  Variable: {varname:20s}  {desc}")
                continue

            # If we have no current variable, skip the line
            if current_var is None:
                continue

            # Skip pure section headers -- indented lines with no leading code
            # These look like "                    Family Households:"
            if line.startswith(' ') and not CODE_LINE.match(line.lstrip()):
                continue

            # Try to match a code line (may be indented)
            code_match = CODE_LINE.match(line.lstrip())
            if code_match:
                code  = code_match.group(1).strip()
                label = code_match.group(2).strip()

                # Skip tautologies
                if is_tautology(code, label):
                    continue

                # Skip if label is empty
                if not label:
                    continue

                variables[current_var]['codes'][code] = label

    return variables


def filter_variables(variables: dict) -> dict:
    """
    Remove variables that have no meaningful codes at all.
    These are things like COUNTYICP (just numbers) or
    pure numeric sequences with no labels.
    """
    filtered = {}
    skipped  = []

    for varname, data in variables.items():
        if data['codes']:
            filtered[varname] = data
        else:
            skipped.append(varname)

    if VERBOSE and skipped:
        print(f"\nSkipped {len(skipped)} variables with no meaningful codes:")
        for v in skipped:
            print(f"  {v}")

    return filtered


def build_database(variables: dict, db_path: Path) -> None:
    """Create codebook.db and populate variables and codes tables."""

    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove old database if it exists so we start clean
    if db_path.exists():
        db_path.unlink()
        print(f"\nRemoved existing {db_path.name}")

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    # ── Create tables ──────────────────────────────────────────────────────────
    cur.executescript("""
        CREATE TABLE variables (
            varname     TEXT PRIMARY KEY,
            description TEXT NOT NULL
        );

        CREATE TABLE codes (
            varname     TEXT    NOT NULL,
            code        TEXT    NOT NULL,
            label       TEXT    NOT NULL,
            PRIMARY KEY (varname, code),
            FOREIGN KEY (varname) REFERENCES variables(varname)
        );

        CREATE INDEX idx_codes_varname ON codes(varname);
    """)

    # ── Insert data ────────────────────────────────────────────────────────────
    var_count  = 0
    code_count = 0

    for varname, data in variables.items():
        cur.execute(
            "INSERT INTO variables (varname, description) VALUES (?, ?)",
            (varname, data['description'])
        )
        var_count += 1

        for code, label in data['codes'].items():
            cur.execute(
                "INSERT INTO codes (varname, code, label) VALUES (?, ?, ?)",
                (varname, code, label)
            )
            code_count += 1

    conn.commit()
    conn.close()

    print(f"\nDatabase built: {db_path}")
    print(f"  {var_count:>4} variables")
    print(f"  {code_count:>4} code entries")


def main():
    basic_path = Path(BASIC_FILE)
    db_path    = Path(CODEBOOK_DB)

    if not basic_path.exists():
        print(f"ERROR: File not found: {basic_path}")
        return

    print(f"Parsing: {basic_path.name}\n")
    print("-" * 60)

    variables = parse_basic_file(basic_path)
    variables = filter_variables(variables)
    build_database(variables, db_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
