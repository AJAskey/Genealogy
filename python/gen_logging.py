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

# Try to import the global flag. If it fails, default to False.
try:
    from config import MULTIPLE_DATABASE_FILES
except ImportError:
    MULTIPLE_DATABASE_FILES = False

class FlushingFileHandler(logging.FileHandler):
    """
    A FileHandler that flushes the buffer after every log record is emitted.
    This ensures that log messages are written to disk immediately,
    so they aren't lost if the script is forcefully killed.
    """

    def emit(self, record):
        super().emit(record)
        self.flush()


def setup_logging(logger_name=None, year=None, multiple_db_files=None):
    """
    Configures a NAMED logger to write to both the console and a file.
    This completely isolates thread logs and prevents double logging.
    """
    # Allow override via parameter, otherwise use the imported global
    use_multiple = multiple_db_files if multiple_db_files is not None else MULTIPLE_DATABASE_FILES

    # Determine the log filename prefix based on the arguments provided
    if use_multiple and year:
        log_prefix = f"vault_{year}"
    elif not use_multiple and year:
        log_prefix = "vault_ALL"
    elif logger_name:
        log_prefix = f"vault_{logger_name}"
    else:
        log_prefix = "vault_ALL"

    # USE A NAMED LOGGER so threads get isolated loggers, completely bypassing root duplication
    logger = logging.getLogger(log_prefix)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # DO NOT pass logs up to the root logger

    # Fix the duplicate logging issue: 
    # If scripts accidentally use `logging.info()` instead of `logger.info()`, 
    # Python auto-creates a root handler. We clear it and control it explicitly.
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Only add handlers if they don't already exist for THIS logger
    if not logger.handlers:
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
        # Strictly Hours:Minutes:Seconds for console, as requested
        console_formatter = logging.Formatter('%(asctime)s | %(message)s', datefmt='%H:%M:%S')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # Attach the exact same console handler to root so accidental `logging.info` doesn't double print
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.INFO)

        # Log the file location right away
        logger.info(f"Log file started: {log_filename}")

    return logger
