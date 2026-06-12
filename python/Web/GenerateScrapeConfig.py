'''
ig.py

Summary: Automates the creation of the scrape_config.json file.
         It crawls the top-level USGenWeb archives, finds all state
         and county subdirectories, and writes a complete JSON
         configuration file with all states/counties disabled by default.

Usage:   Run this script once to generate the config. Then, manually
         edit scrape_config.json to enable the states/counties you
         want to download.
                   
Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
'''''

import json
import time

import requests
from bs4 import BeautifulSoup

from python.utils import gen_logging
from python.utils.us_states import us_state_data

CONFIG_FILE = "../../JSON/scrape_config.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ConfigGenerator/1.0"
}


def get_county_dirs(state_abbr, logger):
    # Crawls a state's root directory and returns a list of its county subdirectories.

    ccnt = 0
    county_dirs = []
    base_url = f"http://files.usgwarchives.net/{state_abbr}/"
    try:
        response = requests.get(base_url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a"):
                href = anchor.get("href")
                # A county directory is a relative link ending in a slash
                if href and href.endswith("/") and not href.startswith("?") and not href.startswith("/"):
                    county_name = href.strip("/")
                    # Ignore parent directory links or empty names
                    if county_name and ".." not in county_name:
                        county_dirs.append(county_name)
                        ccnt += 1
                        if ccnt > 100:
                            logger.info(
                                f"Found {ccnt} counties at {state_abbr.upper()}, {county_name.upper}. Resting 5 seconds")
                            time.sleep(5)
                            ccnt = 0
    except Exception as e:
        logger.error(f"Could not get counties for {state_abbr.upper()}: {e}")
    # Return a unique, sorted list
    return sorted(list(set(county_dirs)))


def generate_config(logger):
    """Generates and saves the scrape_config.json file."""
    logger.info(f"Generating new scraper configuration file: {CONFIG_FILE}")
    full_config = {}

    # Assumes us_states.py contains a list of state dicts with 'abbr' and 'name'
    for state in us_state_data:
        state_abbr = state['abbr'].lower()
        logger.info(f"Finding counties for {state['name']} ({state_abbr.upper()})...")

        county_list = get_county_dirs(state_abbr, logger)

        # Create the JSON structure for this state
        full_config[state_abbr] = {
            "enabled": False,  # Default to off
            "counties": {county: False for county in county_list}  # Default all counties to off
        }
        time.sleep(0.5)  # Be polite to the server

    logger.info(f"Saving configuration to {CONFIG_FILE}...")
    with open(CONFIG_FILE, "w") as f:
        json.dump(full_config, f, indent=4)

    logger.info("Config generation complete! You can now edit scrape_config.json to enable states/counties.")


if __name__ == "__main__":
    logger = gen_logging.setup_logging(logger_name="CONFIG_GEN")
    generate_config(logger)
