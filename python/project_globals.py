"""
-----------------------------------
File: project_globals.py

Summary: A central module to initialize and hold global objects that can be
         shared across the entire application, such as the codebook lookup.
         This prevents re-loading large files and provides a single
         source of truth.

Design:
  - This module is intended to be imported once.
  - It calculates absolute paths from the project root to avoid errors.
  - It instantiates the Codebook and other lookups, making them available
    as module-level variables.
--------------------------------
"""
import json
import logging
import os

# Assuming the Codebook class is in a file named codebook_lookup.py
# in the same directory.
import CodebookReader

# --- Define Absolute Paths ---
# Get the absolute path of the directory where this file is located (the 'python' directory)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the project root by going one level up from the 'python' directory
PROJECT_ROOT = os.path.dirname(_CURRENT_DIR)

# --- Define Centralized File Paths ---
CODEBOOK_PATH = os.path.join(PROJECT_ROOT, 'JSON', 'codebook.json')
COUNTY_LOOKUP_PATH = os.path.join(PROJECT_ROOT, 'JSON', 'county_codes_to_names.json')

# We can also centralize other common paths here
DEFAULT_DB = r"D:\Data\Genealogy_Data\MasterVault_1900.db"
OUTPUT_REPORT = os.path.join(PROJECT_ROOT, 'output', 'database_inspection_report.txt')

# --- Instantiate Global Objects ---
# This code runs only ONCE when the module is first imported.
logging.info("Initializing global codebook...")
CODEBOOK = CodebookReader.Codebook(CODEBOOK_PATH)

logging.info("Initializing global county lookup...")
COUNTY_LOOKUP = {}
try:
    with open(COUNTY_LOOKUP_PATH, 'r', encoding='utf-8') as f:
        COUNTY_LOOKUP = json.load(f)
except FileNotFoundError:
    logging.error(f"County lookup file not found at: {COUNTY_LOOKUP_PATH}")
except json.JSONDecodeError:
    logging.error(f"County lookup file contains invalid JSON: {COUNTY_LOOKUP_PATH}")
except Exception as e:
    logging.error(f"Unexpected error loading global county lookup: {e}")
