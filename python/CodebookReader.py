import json
import logging


class Codebook:
    def __init__(self, filename):
        """
        Initializes the Codebook by loading the specified JSON file.
        Handles file not found and JSON decoding errors.
        """
        self._data = {}
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                self._data = json.load(file)
        except FileNotFoundError:
            logging.error(f"Codebook file not found: '{filename}'.")
        except json.JSONDecodeError:
            logging.error(f"Codebook file '{filename}' contains invalid JSON.")
        except Exception as e:
            logging.error(f"Unexpected error loading '{filename}': {e}")

    def get_code_value(self, category, code):
        """
        Retrieves the descriptive value for a given category and code.

        Args:
            category (str): The top-level key (e.g., "BPL", "RACE").
            code (int or str): The specific code to look up. Integers are
                               automatically padded with leading zeros.

        Returns:
            str: The descriptive value, or None if not found.
        """
        # Ensure the primary category exists
        if category not in self._data:
            return None

        # --- Smart Code Formatting ---
        # Convert integer codes to strings
        if isinstance(code, int):
            code_str = str(code)
        else:
            code_str = str(code).strip()

        # Try to find the code, padding if necessary
        try:
            # First, try a direct lookup
            return self._data[category]['codes'][code_str]
        except KeyError:
            # If direct lookup fails, try padding to 3 digits (for BPL, etc.)
            try:
                padded_code = f"{int(code_str):03}"
                return self._data[category]['codes'][padded_code]
            except (KeyError, ValueError):
                # If that fails, try padding to 5 digits (for BPLD, etc.)
                try:
                    padded_code_5 = f"{int(code_str):05}"
                    return self._data[category]['codes'][padded_code_5]
                except (KeyError, ValueError):
                    return None  # Return None if all attempts fail


# ==============================================================================
# --- How to use it ---
# ==============================================================================
if __name__ == '__main__':
    # 1. Instantiate the class with your codebook file
    codebook = Codebook('../JSON/codebook.json')

    # 2. Look up values using the new method

    # Example 1: Look up Birthplace (BPL) for code 1
    birthplace = codebook.get_code_value("BPL", '042')
    print(f"BPL code '1' means: {birthplace}")  # Should print Alabama

    # Example 2: Look up Detailed Birthplace (BPLD) for code 42000
    detailed_bpl = codebook.get_code_value("BPLD", 42000)
    print(f"BPLD code '42000' means: {detailed_bpl}")  # Should print Belgium

    # Example 3: Look up Race for code "2"
    race = codebook.get_code_value("RACE", "2")
    print(f"RACE code '2' means: {race}")  # Should print Black/African American

    # Example 4: Handle a code that doesn't exist
    bad_code = codebook.get_code_value("BPL", 99999)
    print(f"BPL code '99999' means: {bad_code}")  # Should print None
