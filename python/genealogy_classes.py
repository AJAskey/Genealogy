"""
File: genealogy_classes.py

Summary: Defines the core data structures for the "Clean DB" phase.
         These classes represent the distilled lineage-linked data.

Design:
  - Individual: Represents a single person with an immutable "St. Joseph's ID".
                Contains pointers to parents (for bottom-up traversal) and
                a pointer back to the raw database (for rich attributes).
  - Family: Represents a nuclear family unit. Contains pointers to parents
            and a list of children (for top-down traversal).
"""

class Individual:
    """
    Represents a single verified person in the family tree.
    This object will eventually be persisted into the 'Clean DB'.
    """
    def __init__(self, st_joes_id, raw_composite_id):
        # ---------------------------------------------------------
        # THE PRIMARY KEYS
        # ---------------------------------------------------------
        # The permanent, immutable integer ID (e.g., 1, 2, 3...)
        self.st_joes_id = st_joes_id
        
        # The pointer back to the raw IPUMS data (e.g., "192001_101_1_1")
        # This is how we look up the person's detailed history later.
        self.raw_composite_id = raw_composite_id
        
        # ---------------------------------------------------------
        # CORE ATTRIBUTES (Stored in Clean DB for quick reference)
        # ---------------------------------------------------------
        self.first_name = None
        self.last_name = None
        
        # ---------------------------------------------------------
        # LINEAGE POINTERS (For Bottom-Up Traversal)
        # ---------------------------------------------------------
        # These are St. Joes IDs pointing to other Individual records
        self.father_id = None
        self.mother_id = None

    def __repr__(self):
        return f"<Individual [{self.st_joes_id}] {self.first_name} {self.last_name}>"


class Family:
    """
    Represents a nuclear family unit (Parents + Children).
    This object will eventually be persisted into the 'Clean DB'.
    """
    def __init__(self, family_id):
        # The unique ID for this specific family unit (e.g., F1, F2...)
        self.family_id = family_id
        
        # ---------------------------------------------------------
        # LINEAGE POINTERS (For Top-Down Traversal)
        # ---------------------------------------------------------
        # These are St. Joes IDs pointing to Individual records
        self.husband_id = None
        self.wife_id = None
        
        # A list of St. Joes IDs representing the children in this family
        self.children_ids = []

        # Score for matching algorithms
        self.score = 0

    def add_child(self, child_st_joes_id):
        if child_st_joes_id not in self.children_ids:
            self.children_ids.append(child_st_joes_id)

    def __repr__(self):
        children_str = ", ".join(map(str, self.children_ids))
        return (f"Family ID: {self.family_id}\n"
                f"  Husband: {self.husband_id}\n"
                f"  Wife: {self.wife_id}\n"
                f"  Children: [{children_str}]\n"
                f"  Score: {self.score}")


class Person:
    """
    A temporary object to hold raw data from a CSV row during ingestion.
    The __repr__ is designed to output a human-readable, decoded format
    for easy logging and debugging.
    """
    def __init__(self, codebook=None, **kwargs):
        self._data = kwargs
        self._codebook = codebook
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        if not self._codebook:
            # Fallback to original CSV format if no codebook is provided
            return ",".join(str(v) for v in self._data.values())

        output = ["--- Person Record ---"]
        for var, code in self._data.items():
            # Attempt to look up the decoded label
            label = self._codebook.get_code_value(var, code)
            if label:
                # Show both the code and the human-readable label
                output.append(f"  {var:<15}: {code} ({label})")
            else:
                # If no label exists (e.g., for names, ages), just show the value
                output.append(f"  {var:<15}: {code}")
        return "\n".join(output)
