"""
-----------------------------------
File: vault_stats.py

Summary:

Design:

Inputs:

Outputs:

Comments for G:

--------------------------------

"""

import datetime
import logging
import platform
import time
import psutil


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
    import os

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
    formatter = logging.Formatter("%(message)s")

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


# ==============================================================================
# STATS HELPERS
# ==============================================================================

def get_system_snapshot():
    """Capture a point-in-time snapshot of CPU, memory, and disk."""
    snapshot = {}

    # CPU
    snapshot['cpu_percent'] = psutil.cpu_percent(interval=1)
    snapshot['cpu_count_logical'] = psutil.cpu_count(logical=True)
    snapshot['cpu_count_physical'] = psutil.cpu_count(logical=False)

    # Memory (RAM)
    mem = psutil.virtual_memory()
    snapshot['ram_total_gb'] = mem.total / (1024 ** 3)
    snapshot['ram_used_gb'] = mem.used / (1024 ** 3)
    snapshot['ram_available_gb'] = mem.available / (1024 ** 3)
    snapshot['ram_percent'] = mem.percent

    # Swap (Windows calls this "page file"; same idea)
    swap = psutil.swap_memory()
    snapshot['swap_total_gb'] = swap.total / (1024 ** 3)
    snapshot['swap_used_gb'] = swap.used / (1024 ** 3)
    snapshot['swap_percent'] = swap.percent

    # Disk for the D: drive where the databases live
    try:
        disk = psutil.disk_usage(r'D:\\')
        snapshot['disk_d_total_gb'] = disk.total / (1024 ** 3)
        snapshot['disk_d_used_gb'] = disk.used / (1024 ** 3)
        snapshot['disk_d_free_gb'] = disk.free / (1024 ** 3)
        snapshot['disk_d_percent'] = disk.percent
    except Exception:
        snapshot['disk_d_total_gb'] = None  # drive not present on this machine

    # Disk I/O counters — cumulative bytes read/written since boot.
    # We capture before & after so print_stats_report can show the delta.
    try:
        io = psutil.disk_io_counters(perdisk=False)   # system-wide totals
        snapshot['io_read_bytes']  = io.read_bytes
        snapshot['io_write_bytes'] = io.write_bytes
        snapshot['io_read_count']  = io.read_count
        snapshot['io_write_count'] = io.write_count
    except Exception:
        snapshot['io_read_bytes'] = None

    # Snapshot wall time so throughput (MB/s) can be calculated
    snapshot['snapshot_time'] = time.time()

    return snapshot


def print_session_header():
    """Print a banner at the very top with machine info and start time."""
    logging.info("=" * 65)
    logging.info("  DATABASE VAULT  —  SESSION START")
    logging.info("=" * 65)
    logging.info(f"  Started   : {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    logging.info(f"  Machine   : {platform.node()}")
    logging.info(f"  OS        : {platform.system()} {platform.release()} ({platform.version()})")
    logging.info(f"  Python    : {platform.python_version()}")
    logging.info(f"  CPU cores : {psutil.cpu_count(logical=False)} physical  /  "
                 f"{psutil.cpu_count(logical=True)} logical")

    mem = psutil.virtual_memory()
    logging.info(f"  Total RAM : {mem.total / (1024 ** 3):.1f} GB")

    swap = psutil.swap_memory()
    logging.info(f"  Page file : {swap.total / (1024 ** 3):.1f} GB  (Windows swap / page file)")
    logging.info(f"  GPU note  : SQLite + Python CSV is CPU + disk only — no GPU involvement.")
    logging.info("=" * 65)
    logging.info("")


def print_stats_report(label, before, after, wall_seconds, cpu_times_before, cpu_times_after):
    """Print a nicely formatted before/after stats comparison."""

    cpu_user = cpu_times_after.user - cpu_times_before.user
    cpu_system = cpu_times_after.system - cpu_times_before.system
    cpu_total = cpu_user + cpu_system

    wall_min = wall_seconds / 60

    logging.info("")
    logging.info("=" * 65)
    logging.info(f"  STATS REPORT  —  {label}")
    logging.info("=" * 65)

    logging.info(f"\n  {'TIMING':}")
    logging.info(f"    Wall clock elapsed : {wall_seconds:,.1f} sec  ({wall_min:.2f} min)")
    logging.info(f"    CPU user time      : {cpu_user:,.1f} sec")
    logging.info(f"    CPU system time    : {cpu_system:,.1f} sec")
    logging.info(f"    CPU total time     : {cpu_total:,.1f} sec")
    logging.info(f"    (CPU total > wall clock means multiple cores were used in parallel)")

    logging.info(f"\n  {'CPU USAGE (during run)':}")
    logging.info(f"    Start  : {before['cpu_percent']:.1f}%")
    logging.info(f"    End    : {after['cpu_percent']:.1f}%")

    logging.info(f"\n  {'MEMORY  (RAM)':}")
    logging.info(f"    Start  used : {before['ram_used_gb']:.2f} GB  ({before['ram_percent']:.1f}%)")
    logging.info(f"    End    used : {after['ram_used_gb']:.2f} GB  ({after['ram_percent']:.1f}%)")
    logging.info(f"    Available   : {after['ram_available_gb']:.2f} GB remaining")

    logging.info(f"\n  {'SWAP / PAGE FILE':}")
    if before['swap_total_gb'] > 0:
        logging.info(f"    Total       : {before['swap_total_gb']:.2f} GB")
        logging.info(f"    Start  used : {before['swap_used_gb']:.2f} GB  ({before['swap_percent']:.1f}%)")
        logging.info(f"    End    used : {after['swap_used_gb']:.2f} GB  ({after['swap_percent']:.1f}%)")
    else:
        logging.info(f"    (No swap / page file configured)")

    if before['disk_d_total_gb'] is not None:
        logging.info(f"\n  {'DISK  (D: drive)':}")
        logging.info(f"    Total       : {before['disk_d_total_gb']:.1f} GB")
        logging.info(f"    Start  used : {before['disk_d_used_gb']:.1f} GB  ({before['disk_d_percent']:.1f}%)")
        logging.info(f"    End    used : {after['disk_d_used_gb']:.1f} GB  ({after['disk_d_percent']:.1f}%)")
        delta_gb = after['disk_d_used_gb'] - before['disk_d_used_gb']
        logging.info(f"    Space added : {delta_gb:+.2f} GB  (new database data written this run)")
        logging.info(f"    Free now    : {after['disk_d_free_gb']:.1f} GB")

    # Disk I/O throughput
    if before.get('io_read_bytes') is not None and after.get('io_read_bytes') is not None:
        read_gb    = (after['io_read_bytes']  - before['io_read_bytes'])  / (1024 ** 3)
        write_gb   = (after['io_write_bytes'] - before['io_write_bytes']) / (1024 ** 3)
        read_ops   =  after['io_read_count']  - before['io_read_count']
        write_ops  =  after['io_write_count'] - before['io_write_count']
        elapsed    = after['snapshot_time']   - before['snapshot_time']
        read_mbps  = (read_gb  * 1024) / elapsed if elapsed else 0
        write_mbps = (write_gb * 1024) / elapsed if elapsed else 0
        logging.info(f"\n  DISK I/O  (system-wide, all drives combined)")
        logging.info(f"    Data read      : {read_gb:,.2f} GB  ({read_mbps:,.1f} MB/s avg)")
        logging.info(f"    Data written   : {write_gb:,.2f} GB  ({write_mbps:,.1f} MB/s avg)")
        logging.info(f"    Read ops       : {read_ops:,}")
        logging.info(f"    Write ops      : {write_ops:,}")

    logging.info(f"\n  {'GPU':}")
    logging.info(f"    Not applicable — SQLite/CSV work is CPU + disk I/O only.")
    logging.info("=" * 65)
    logging.info("")


if __name__ == '__main__':
    # ---- Quick self-test when run directly ----------------------------------
    setup_logging()   # logs to console + file when run standalone

    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M:%S")
    logging.info(f"Current Time: {current_time}")

    file_wall_start = time.time()
    file_cpu_before = psutil.Process().cpu_times()
    file_stats_before = get_system_snapshot()

    print_session_header()
    session_wall_start = time.time()
    session_cpu_before = psutil.Process().cpu_times()

    file_wall_end = time.time()
    file_cpu_after = psutil.Process().cpu_times()
    file_stats_after = get_system_snapshot()

    print_stats_report(
        label=f"File: filename",
        before=file_stats_before,
        after=file_stats_after,
        wall_seconds=file_wall_end - file_wall_start,
        cpu_times_before=file_cpu_before,
        cpu_times_after=file_cpu_after,
    )
