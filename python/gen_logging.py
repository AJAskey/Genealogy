import logging
import os
from datetime import datetime


def setup_logging(year="ALL"):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 1. Aggressively clear ALL existing root handlers to completely eliminate double logging.
    # Some Python libraries sneakily attach a basic handler before setup_logging runs.
    if logger.handlers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

    # 2. File Handler: Full date and time, extremely detailed for debugging
    log_dir = r"E:\Users\Andy\PycharmProjects\Genealogy\output"
    os.makedirs(log_dir, exist_ok=True)

    time_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_filename = os.path.join(log_dir, f"vault_{year}_{time_str}.log")

    file_handler = logging.FileHandler(log_filename, mode='w', encoding='utf-8')
    file_formatter = logging.Formatter('%(asctime)s  %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 3. Console Handler: Only Hours, Minutes, and Seconds for a cleaner screen
    console_handler = logging.StreamHandler()
    # The datefmt="%H:%M:%S" strips the year, month, and day out of the console output
    console_formatter = logging.Formatter('%(asctime)s  %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logging.info("Logging successfully initialized.")
