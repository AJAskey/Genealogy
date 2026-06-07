"""
-----------------------------------
File: download_genealogy_blocks.py

Summary: Automates the downloading of Internet Archive data blocks 
         (e.g., Reclaim The Records) with retry logic and API spacing.
-----------------------------------
"""
import datetime
import os
import sys
import time

# Add the 'python' directory to sys.path so we can import from 'utils'
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.abspath(os.path.join(script_dir, '..'))
if python_dir not in sys.path:
    sys.path.append(python_dir)

from internetarchive import search_items, get_item
from utils import gen_logging


# reclaimtherecords
def download_genealogy_blocks(collection_name='reclaimtherecords',
                              download_path=r"D:\Data\Genealogy_Data\Ingestion", block_id=1):
    """
    Corrected downloader for Internet Archive data blocks.
    """
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    main_logger.info(f"--- Initializing Scout: Searching {collection_name} ---")

    search_query = f'collection:{collection_name}'
    search_results = search_items(search_query)

    for result in search_results:
        item_id = result['identifier']
        item = get_item(item_id)

        main_logger.info(f"item:_id {item_id}")

        # if item_id[:1] < "O ":
        #     continue

        # List the exact extensions you want to SKIP here. 
        # Note: Because we use .endswith(), do not use asterisks (e.g., use '.zip', not '*.zip')
        excluded_extensions = ('.zip', '.tar', '.gz', '.mp4', '.iso', '.sqlite', '.sqlite3', '.db', '.pdf',
                               'djvu.txt', '.xml', '.html', '.torrent', '.jpg', '.epub', '.jpeg',
                               '.log', '.gif', '.json', '.tiff', 'zip.~1~')

        # FIX: Access 'name' as a dictionary key or object attribute safely
        files_to_download = []
        for f in item.files:
            # Some versions of the API return dicts, some return objects
            filename = f['name'] if isinstance(f, dict) else f.name

            if not any(filename.lower().endswith(ext) for ext in excluded_extensions):
                if not ('baltimore' in filename.lower()):
                    files_to_download.append(filename)

        if files_to_download:
            main_logger.info(f"Found {len(files_to_download)} data files in: {item_id}")
            item.download(files=files_to_download, destdir=download_path, verbose=True)
        else:
            main_logger.info(f"Skipping {item_id}: No structured data files found.")


def main():
    """
    Main entry point for downloading Reclaim the Records blocks.
    Inputs: None
    Outputs: Executes the download loop and logs results.
    """

    target_path = r"d:\Data\Genealogy_Data\Ingestion"

    total_records = 0

    # Range (1, 4) would give you blocks 1, 2, and 3
    for i in range(1, 2):
        success = False
        retries = 0

        while not success and retries < 3:
            try:
                main_logger.info(f"Starting download for loop {i}...")
                # Assuming the function can take an ID or block number
                download_genealogy_blocks(download_path=target_path, block_id=i)
                total_records += 1
                success = True
                main_logger.info(f"Loop {i} completed successfully, total_records: {total_records}.")

            except Exception as e:
                retries += 1
                wait = retries * 30  # Increasing wait: 30s, 60s, 90s
                main_logger.warning(f"Exception on loop {i} (Attempt {retries}): {e}")
                if retries < 3:
                    main_logger.warning(f"Retrying {i} in {wait} seconds...")
                    time.sleep(wait)
                else:
                    main_logger.error(f"Skipping block {i} after 3 failed attempts.")

            # Polite gap between DIFFERENT blocks to avoid rate-limiting
            if success:
                main_logger.info(f"Resting after success. Loop {i}")
                time.sleep(10)

    main_logger.info(f"\n  Total records across all files : {total_records:,}")
    main_logger.info(f"  Session ended: {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    main_logger.info("")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="SCRAPE")

    main()
