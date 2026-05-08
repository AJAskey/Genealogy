"""
-----------------------------------
File: statistics.py

Summary:

Design:

Inputs:

Outputs:

Comments for G:

--------------------------------

"""

import datetime
import platform
import time
import psutil


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

    return snapshot


def print_session_header():

    """Print a banner at the very top with machine info and start time."""
    print("=" * 65)
    print("  DATABASE VAULT  —  SESSION START")
    print("=" * 65)
    print(f"  Started   : {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Machine   : {platform.node()}")
    print(f"  OS        : {platform.system()} {platform.release()} ({platform.version()})")
    print(f"  Python    : {platform.python_version()}")
    print(f"  CPU cores : {psutil.cpu_count(logical=False)} physical  /  "
          f"{psutil.cpu_count(logical=True)} logical")

    mem = psutil.virtual_memory()
    print(f"  Total RAM : {mem.total / (1024 ** 3):.1f} GB")

    swap = psutil.swap_memory()
    print(f"  Page file : {swap.total / (1024 ** 3):.1f} GB  (Windows swap / page file)")
    print(f"  GPU note  : SQLite + Python CSV is CPU + disk only — no GPU involvement.")
    print("=" * 65)
    print()


def print_stats_report(label, before, after, wall_seconds, cpu_times_before, cpu_times_after):
    """Print a nicely formatted before/after stats comparison."""

    cpu_user = cpu_times_after.user - cpu_times_before.user
    cpu_system = cpu_times_after.system - cpu_times_before.system
    cpu_total = cpu_user + cpu_system

    wall_min = wall_seconds / 60

    print()
    print("=" * 65)
    print(f"  STATS REPORT  —  {label}")
    print("=" * 65)

    print(f"\n  {'TIMING':}")
    print(f"    Wall clock elapsed : {wall_seconds:,.1f} sec  ({wall_min:.2f} min)")
    print(f"    CPU user time      : {cpu_user:,.1f} sec")
    print(f"    CPU system time    : {cpu_system:,.1f} sec")
    print(f"    CPU total time     : {cpu_total:,.1f} sec")
    print(f"    (CPU total > wall clock means multiple cores were used in parallel)")

    print(f"\n  {'CPU USAGE (during run)':}")
    print(f"    Start  : {before['cpu_percent']:.1f}%")
    print(f"    End    : {after['cpu_percent']:.1f}%")

    print(f"\n  {'MEMORY  (RAM)':}")
    print(f"    Start  used : {before['ram_used_gb']:.2f} GB  ({before['ram_percent']:.1f}%)")
    print(f"    End    used : {after['ram_used_gb']:.2f} GB  ({after['ram_percent']:.1f}%)")
    print(f"    Available   : {after['ram_available_gb']:.2f} GB remaining")

    print(f"\n  {'SWAP / PAGE FILE':}")
    if before['swap_total_gb'] > 0:
        print(f"    Total       : {before['swap_total_gb']:.2f} GB")
        print(f"    Start  used : {before['swap_used_gb']:.2f} GB  ({before['swap_percent']:.1f}%)")
        print(f"    End    used : {after['swap_used_gb']:.2f} GB  ({after['swap_percent']:.1f}%)")
    else:
        print(f"    (No swap / page file configured)")

    if before['disk_d_total_gb'] is not None:
        print(f"\n  {'DISK  (D: drive)':}")
        print(f"    Total       : {before['disk_d_total_gb']:.1f} GB")
        print(f"    Start  used : {before['disk_d_used_gb']:.1f} GB  ({before['disk_d_percent']:.1f}%)")
        print(f"    End    used : {after['disk_d_used_gb']:.1f} GB  ({after['disk_d_percent']:.1f}%)")
        delta_gb = after['disk_d_used_gb'] - before['disk_d_used_gb']
        print(f"    Space added : {delta_gb:+.2f} GB  (new database data written this run)")
        print(f"    Free now    : {after['disk_d_free_gb']:.1f} GB")

    print(f"\n  {'GPU':}")
    print(f"    Not applicable — SQLite/CSV work is CPU + disk I/O only.")
    print("=" * 65)
    print()


if __name__ == '__main__':
    # ---- SESSION-LEVEL start ------------------------------------------------
    # Get current date and time
    now = datetime.datetime.now()
    # Format and print just the clock time
    current_time = now.strftime("%H:%M:%S")
    print(f"Current Time: {current_time}")

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
