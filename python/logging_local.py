"""
-----------------------------------
File: logging_local.py

Summary:  Set up logging in the Genealogy project.

Design:

Inputs:

Outputs:

--------------------------------

"""
import datetime, os
import logging


# ==============================================================================
# LOGGING SETUP
# ==============================================================================

def setup_logging(log_dir=r"D:\Data\Genealogy_Data\Logs"):
    """
    Call this once at session start (from DatabaseVault_threaded.py __main__).

    Creates two handlers:
      1. StreamHandler  → console (same output you've always seen)
      2. FileHandler    → timestamped .log file in log_dir

    The log file is named like:
        vault_2025-07-14_09-32-11.log

    If log_dir doesn't exist it will be created automatically.
    If something goes wrong creating the directory the log still goes to
    the console — it won't crash the run.
    """

    # Build a timestamped filename
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"vault_{ts}.log"

    # Make sure the log folder exists
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, log_filename)
    except Exception as e:
        log_path = None
        print(f"[WARNING] Could not create log directory '{log_dir}': {e}")
        print("[WARNING] Logging to console only.")

    # Root logger — INFO level so everything at INFO and above is captured
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Formatter: no "INFO:root:" prefix — just the message, same as print()
    formatter = logging.Formatter("%(asctime)s\n%(message)s -- %(module)s P%(process)d T%(thread)d %(threadName)s %(levelname)s")

    # Console handler (replaces what print() was doing)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_path:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logging.info(f"  Log file  : {log_path}")

    return log_path