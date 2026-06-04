import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import gen_logging
from us_states import us_state_data

# User-Agent header to identify the request properly
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DirectoryMapper/1.0"
}

# Set to keep track of visited URLs to avoid infinite circular loops
VISITED_DIRECTORIES = set()


def crawl_directories(current_url, st, depth=0, max_depth=5):
    """Recursively traverses HTTP directory listings and prints subdirectory paths."""
    # Safety boundaries
    if current_url in VISITED_DIRECTORIES or depth > max_depth:
        return
    if not current_url.endswith("/"):
        return

    VISITED_DIRECTORIES.add(current_url)

    # Indentation matching the depth of the directory tree for clean printing
    indent = "  " * depth
    # Display the relative or absolute path (printing relative to base here)
    display_path = current_url.replace(BASE_URL, "/")
    logger.info(f"{st}  {indent}{display_path}")
    time.sleep(0.25)

    try:
        # Courteous delay to prevent hammering the server (50-100ms)
        time.sleep(0.05)

        response = requests.get(current_url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract all anchor tags
        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue

            # Standard Apache directory listings contain parent directory links,
            # query sorting parameters, or absolute links to external assets.
            if (
                    href.startswith("?")
                    or href.startswith("/")
                    or "://" in href
                    or href.startswith("..")
            ):
                continue

            # In HTTP directory listings, a subdirectory is identified by a trailing slash
            if href.endswith("/"):
                # Resolve relative href against the current directory URL
                subdirectory_url = urljoin(current_url, href)
                # Recurse down into the discovered directory
                crawl_directories(subdirectory_url, st, depth + 1, max_depth)

    except Exception as e:
        logger.info(f"{indent}[Error accessing {display_path}: {e}]")


if __name__ == "__main__":
    logger = gen_logging.setup_logging(logger_name="GETDIRS")

    for state in us_state_data:
        # Base URL target

        BASE_URL = f"http://files.usgwarchives.net/{state['abbr']}/"
        #            http://files.usgwarchives.net/pa/

        logger.info(f"Starting recursive directory map of: {BASE_URL}")
        logger.info("------------------------------------------------")

        logger.info(f"{state['abbr']}: {state['name']}")

        # Initialized with a max_depth safety rail to evaluate performance first
        crawl_directories(BASE_URL, state['name'], depth=0, max_depth=1)
        logger.info("------------------------------------------------")
        logger.info(f"Traversal complete. Discovered {len(VISITED_DIRECTORIES)} directories.")
