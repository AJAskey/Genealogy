"""
-----------------------------------
File: gen_logging.py

Summary: Centralized, thread-safe logging configuration. Forces immediate 
         flush to disk to prevent log loss during multi-threaded crashes.
         Utility routines have been added to facilitate easier logging on
         the project.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""
import logging
import os
import sys
import time
from datetime import datetime
from functools import wraps

from rich import inspect
from rich.console import Console

from utils import common_utils

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
        # 1. Get the absolute path of the directory where this specific script lives
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # 2. Step up two folder levels ('..') to reach the main project root
        project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))

        # --- File Handler (with immediate flushing) ---
        log_dir = os.path.join(project_root, "log")
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


def log_individuals(logger, h_indi, w_indi):
    rich_console = Console()
    with rich_console.capture() as capture:
        inspect(h_indi, console=rich_console)
    logger.info(f"\n[HUSBAND - OVERLAY VERIFIED]\n{capture.get()}")

    with rich_console.capture() as capture:
        inspect(w_indi, console=rich_console)
    logger.info(f"\n[SPOUSE - OVERLAY VERIFIED]\n{capture.get()}")


def log_reader(logger, reader, desc=''):
    for row in reader:
        log_dict(logger, row, desc)


def log_dict(logger, dik, desc=""):
    out_str = desc + "\n"
    for key, value in dik.items():
        out_str += f"  {key} | {value}\n"
    logger.info(out_str)


def log_tuple(logger, t, desc=""):
    out_str = f"{desc}\n"
    # i = 0
    # for item in t:
    # if item:
    #     i += 1
    for i, val in enumerate(t):
        if val:
            sval = str(val)
            out_str += f" {desc} [{i:<3}] : {sval:<20} -- {common_utils.DB_ROWS[i]}\n"
    logger.info(f" {out_str}")


def log_obj(logger, obj, desc=""):
    rich_console = Console()
    with rich_console.capture() as capture:
        inspect(obj, console=rich_console, private=True, value=True, sort=True)
    logger.info(f"\n{desc}\n{capture.get()}")


def log_sqlite_rows(logger, rows, desc=""):
    """Safely converts a list of sqlite3.Row objects to dictionaries and logs them."""
    if not rows:
        logger.info(f"{desc}\n  [No rows found]")
        return

    for idx, row in enumerate(rows):
        # Convert sqlite3.Row to a standard dictionary if possible
        row_dict = dict(row) if hasattr(row, 'keys') else {f"Col_{i}": val for i, val in enumerate(row)}
        log_dict(logger, row_dict, desc=f"{desc} (Row {idx + 1})")


def log_timing(logger):
    """A decorator to measure and log the execution time of any function."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"[TIMER] '{func.__name__}' completed in {elapsed:.4f} seconds.")
            return result

        return wrapper

    return decorator
