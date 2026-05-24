"""
-----------------------------------
File: gen_logging.py

Summary: Centralized, thread-safe logging configuration. Forces immediate 
         flush to disk to prevent log loss during multi-threaded crashes.
-----------------------------------
"""
import logging
import os
import sys
from datetime import datetime

# Force immediate console output at the OS level
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)


class FlushingFileHandler(logging.FileHandler):
    """
    A FileHandler that flushes the buffer after every log record is emitted.
    This ensures that log messages are written to disk immediately,
    so they aren't lost if the script is forcefully killed.
    """

    def emit(self, record):
        super().emit(record)
        self.flush()


def setup_logging(logger_name=None, year=None):
    """
    Configures the ROOT logger to write to both the console and a file.
    Because it configures the root logger, standard calls like `logging.info()`
    across all your modules will automatically use these handlers.
    """
    # Get the ROOT logger so that logging.info() works globally
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Completely wipe out ALL existing handlers (prevents the annoying double log)
    if logger.hasHandlers():
        logger.handlers.clear()
        
    # Failsafe: Remove handlers attached directly to the root explicitly
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Determine the log filename prefix based on the arguments provided
    if logger_name:
        log_prefix = f"vault_{logger_name}"
    elif year:
        log_prefix = f"vault_{year}"
    else:
        log_prefix = "vault_ALL"

    # --- File Handler (with immediate flushing) ---
    log_dir = r"E:\Users\Andy\PycharmProjects\Genealogy\log"
    os.makedirs(log_dir, exist_ok=True)
    time_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_filename = os.path.join(log_dir, f"{log_prefix}_{time_str}.log")

    # Use our custom flushing handler instead of standard FileHandler
    file_handler = FlushingFileHandler(log_filename, mode='w', encoding='utf-8')
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # --- Console Handler (with immediate flushing) ---
    console_handler = logging.StreamHandler(sys.stdout)
    # The datefmt="%H:%M:%S" strips the year, month, and day out of the console output
    console_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Log the file location right away
    logging.info(f"Log file started: {log_filename}")

    return logger
