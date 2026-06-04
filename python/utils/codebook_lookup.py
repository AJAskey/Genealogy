# codebook_lookup.py
#
# Simple helper to look up a label from the codebook.
# Load it once at the top of any script, call it anywhere.
#
# Usage:
#     from codebook_lookup import CodeBook
#
#     # cb = CodeBook(r"D:\Data\Genealogy_Data\codebook.json")
#     cb.lookup("RACE", "2")        # --> "Black/African American"
#     cb.lookup("STATEICP", "13")   # --> "New York"
#     cb.lookup("SEX", "1")         # --> "Male"
#     cb.lookup("RACE", "99")       # --> None  (not found)


import json
from pathlib import Path


class CodeBook:

    def __init__(self, json_path: str):
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Codebook not found: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

        print(f"Codebook loaded -- {len(self._data)} variables")

    def lookup(self, varname: str, code) -> str | None:
        """
        Return the label for a variable/code pair.
        Returns None if not found rather than crashing.
        code can be int or string -- we handle both.
        """
        var = self._data.get(varname.upper())
        if var is None:
            return None

        # Normalize code to string for the lookup
        label = var["codes"].get(str(code))
        return label

    def describe(self, varname: str) -> str | None:
        """Return the description of a variable.  e.g. 'Race [general version]'"""
        var = self._data.get(varname.upper())
        return var["description"] if var else None

    def all_codes(self, varname: str) -> dict | None:
        """Return the full code->label dict for a variable."""
        var = self._data.get(varname.upper())
        return var["codes"] if var else None

    def known_variables(self) -> list:
        """Return a sorted list of all variable names in the codebook."""
        return sorted(self._data.keys())
