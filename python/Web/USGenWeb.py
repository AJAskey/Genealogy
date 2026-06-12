import json
import os
import sys
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

# Add the 'python' directory and project root to sys.path so we can import properly
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.abspath(os.path.join(script_dir, '..'))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [python_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging


def download_file(url, local_path):
    """Downloads a single file if it doesn't already exist locally."""
    if os.path.exists(local_path):
        # Skip download if file exists (allows resume functionality)
        return

    # Ensure local directory structure exists
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Downloaded: {local_path}")
            time.sleep(DELAY_SECONDS)
        else:
            logger.info(f"Failed to download {url}: Status {response.status_code}")
    except Exception as e:
        logger.info(f"Error downloading {url}: {e}")


def crawl_archive(current_url, base_url, local_output_dir):
    """Recursively crawls directories and triggers file downloads."""
    try:
        response = requests.get(current_url, timeout=15)
        if response.status_code != 200:
            logger.info(f"Skipping directory {current_url}: Status {response.status_code}")
            return
    except Exception as e:
        logger.info(f"Error accessing directory {current_url}: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # Iterate through all hyperlinks in the directory listing
    for link in soup.find_all("a"):
        href = link.get("href")
        if not href:
            continue

        # Clean up the href (resolve relative paths)
        full_url = urllib.parse.urljoin(current_url, href)

        # Safety catch: Ensure we aren't escaping the base archive tree
        if not full_url.startswith(base_url):
            continue

        # Skip parent directory navigations and sorting headers
        if href.startswith("?") or href.startswith("/") or ".." in href:
            continue

        # Calculate where this file/folder should sit on the local disk
        relative_path = full_url.replace(base_url, "")
        local_path = os.path.normpath(os.path.join(local_output_dir, relative_path))

        # If the link ends with a slash, it's a directory -> Drill down
        if href.endswith("/"):
            logger.info(f"Entering directory: {relative_path}")
            time.sleep(DELAY_SECONDS)
            crawl_archive(full_url, base_url, local_output_dir)
        else:

            # It's a file (text data, index, etc.) -> Save it
            download_file(full_url, local_path)


if __name__ == "__main__":
    logger = gen_logging.setup_logging(logger_name="USGenWeb")

    JSON_dir = os.path.abspath(os.path.join(project_root, 'JSON'))
    DELAY_SECONDS = 2.0  # Polite scraping interval
    CONFIG_FILE = os.path.join(JSON_dir, "scrape_config_working.json")
    LOCAL_ROOT_DIR = r"D:\Data\Genealogy_Data\Ingestion"

    # Create a dummy config if it doesn't exist
    if not os.path.exists(CONFIG_FILE):
        dummy_config = {
            "oh": {
                "enabled": True,
                "counties": {
                    "adams": True,
                    "allen": False
                }
            },
            "pa": {
                "enabled": False,
                "counties": {}
            }
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(dummy_config, f, indent=4)
        logger.info(f"Created dummy configuration file at {CONFIG_FILE}. Please edit it and re-run.")
        exit()

    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)

    for state, state_data in config.items():
        if not state_data.get("enabled", False):
            logger.info(f"Skipping state: {state} (disabled in config)")
            continue

        state_base_url = f"http://files.usgwarchives.net/{state}/"
        state_local_dir = os.path.join(LOCAL_ROOT_DIR, f"usgw_archives_{state}")

        counties = state_data.get("counties", {})
        enabled_counties = [c for c, is_enabled in counties.items() if is_enabled]

        if not counties:
            logger.info(f"Starting mass download for FULL state: {state}")
            crawl_archive(state_base_url, state_base_url, state_local_dir)
        else:
            for county in enabled_counties:
                county_url = f"{state_base_url}{county}/"
                logger.info(f"Starting download for: {state.upper()} -> {county} county")
                crawl_archive(county_url, state_base_url, state_local_dir)

    logger.info("Download pipeline complete.")
