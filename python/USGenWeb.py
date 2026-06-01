import os
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

import gen_logging

# Base configuration
BASE_URL = "http://files.usgwarchives.net/oh/"
LOCAL_OUTPUT_DIR = r"E:\Data\Genealogy_Data\Ingestion/usgw_archives_oh"
DELAY_SECONDS = 0.5  # Polite scraping interval

s1 = r"http://files.usgwarchives.net/al/"  # Alabama </a></td>
s2 = r"http://files.usgwarchives.net/az/"  # Arizona </a></td>
s3 = r"http://files.usgwarchives.net/ar/"  # Arkansas </a></td>
s31 = r"http://files.usgwarchives.net/ca/"  # California </a></td>
s4 = r"http://files.usgwarchives.net/co/"  # Colorado </a></td>
s1 = r"http://files.usgwarchives.net/ct/"  # Connecticut </a></td>
s5 = r"http://files.usgwarchives.net/dc/"  # District of Columbia </a></td>
s6 = r"http://files.usgwarchives.net/ga/"  # Georgia </a></td>
s7 = r"http://files.usgwarchives.net/hi/"  # Hawaii </a></td>
s8 = r"http://files.usgwarchives.net/id/"  # Idaho </a></td>
s9 = r"http://files.usgwarchives.net/il/"  # Illinois </a></td>
s10 = "http://files.usgwarchives.net/in/"  # Indiana </a></td>
s11 = "http://files.usgwarchives.net/ia/"  # Iowa </a></td>
s12 = "http://files.usgwarchives.net/ks/"  # Kansas </a></td>
s13 = "http://files.usgwarchives.net/ky/"  # Kentucky </a></td>
s14 = "http://files.usgwarchives.net/la/"  # Louisiana </a></td>
s15 = "http://files.usgwarchives.net/me/"  # Maine </a></td>
s16 = r"http://files.usgwarchives.net/md/"  # Maryland</a></td>
s17 = r"http://files.usgwarchives.net/ma/"  # Massachusetts </a></td>
s18 = r"http://files.usgwarchives.net/mi/"  # Michigan </a></td>
s19 = r"http://files.usgwarchives.net/mn/"  # Minnesota </a></td>
s20 = r"http://files.usgwarchives.net/ms/"  # Mississippi </a></td>
s21 = r"http://files.usgwarchives.net/mo/"  # Missouri </a></td>
s22 = r"http://files.usgwarchives.net/mt/"  # Montana </a></td>
s23 = r"http://files.usgwarchives.net/ne/"  # Nebraska </a></td>
s24 = r"http://files.usgwarchives.net/nv/"  # Nevada</a></td>
s25 = r"http://files.usgwarchives.net/nh/"  # New Hampshire </a></td>
s26 = r"http://files.usgwarchives.net/nj/"  # New Jersey </a></td>
s27 = r"http://files.usgwarchives.net/nm/"  # New Mexico </a></td>
s28 = r"http://files.usgwarchives.net/ny/"  # New York </a></td>
s29 = r"http://files.usgwarchives.net/nd/"  # North Dakota </a></td>
s30 = r"http://files.usgwarchives.net/oh/"  # Ohio </a></td>
s31 = r"http://files.usgwarchives.net/ok/"  # Oklahoma </a></td>
s32 = r"http://files.usgwarchives.net/or/"  # Oregon </a></td>
s33 = r"http://files.usgwarchives.net/pa/"  # Pennsylvania </a></td>
s34 = r"http://files.usgwarchives.net/ri/"  # Rhode Island </a></td>
s35 = r"http://files.usgwarchives.net/sc/"  # South Carolina </a></td>
s36 = r"http://files.usgwarchives.net/sd/"  # South Dakota </a></td>
s37 = r"http://files.usgwarchives.net/tn/"  # Tennessee </a></td>
s38 = r"http://files.usgwarchives.net/tx/"  # Texas </a></td>
s39 = r"http://files.usgwarchives.net/ut/"  # Utah </a></td>
s40 = r"http://files.usgwarchives.net/vt/"  # Vermont </a></td>
s41 = r"http://files.usgwarchives.net/va/"  # Virginia </a></td>
s42 = r"http://files.usgwarchives.net/wa/"  # Washington </a></td>
s43 = r"http://files.usgwarchives.net/wv/"  # West Virginia </a></td>
s44 = r"http://files.usgwarchives.net/wi/"  # Wisconsin </a></td>
s45 = r"http://files.usgwarchives.net/wy/"  # Wyoming </a></td>


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


def crawl_archive(current_url):
    """Recursively crawls directories and triggers file downloads."""
    try:
        response = requests.get(current_url, timeout=15)
        if response.status_code != 200:
            prilogger.infont(f"Skipping directory {current_url}: Status {response.status_code}")
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
        if not full_url.startswith(BASE_URL):
            continue

        # Skip parent directory navigations and sorting headers
        if href.startswith("?") or href.startswith("/") or ".." in href:
            continue

        # Calculate where this file/folder should sit on the local disk
        relative_path = full_url.replace(BASE_URL, "")
        local_path = os.path.join(LOCAL_OUTPUT_DIR, relative_path)

        # If the link ends with a slash, it's a directory -> Drill down
        if href.endswith("/"):
            logger.info(f"Entering directory: {relative_path}")
            time.sleep(DELAY_SECONDS)
            crawl_archive(full_url)
        else:
            # It's a file (text data, index, etc.) -> Save it
            download_file(full_url, local_path)


if __name__ == "__main__":
    logger = gen_logging.setup_logging(logger_name="USGenWEeb")

    logger.info(f"Starting mass download from: {BASE_URL}")
    crawl_archive(BASE_URL)
    logger.info("Download pipeline complete.")
