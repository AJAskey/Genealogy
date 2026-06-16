"""
-----------------------------------
File: analyze_telemetry.py

Summary: A utility script to parse massive log files and extract only
         the [MULTIPLE] match anomalies for targeted debugging.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import glob
import os


def analyze_log(log_filepath):
    print(f"Scanning Telemetry Log: {log_filepath}")
    print("=" * 70)

    with open(log_filepath, 'r', encoding='utf-8', errors='replace') as f:
        capturing_multiple = False
        multiple_buffer = []
        summary_buffer = []
        capturing_summary = False
        capturing_search = False
        search_buffer = []

        for line in f:
            if "Lookup Complete:" in line:
                capturing_summary = True

            if capturing_summary:
                summary_buffer.append(line)

            # A new search block resets all other captures
            if "[SEARCHING] Couple:" in line:
                if capturing_multiple:
                    print("".join(multiple_buffer))
                    print("-" * 70)
                capturing_multiple = False
                multiple_buffer = []
                capturing_search = True
                search_buffer = [line]
                continue

            if capturing_search:
                search_buffer.append(line)

                # If they hit the 20+ safety valve, print the captured search block
                if "[ABORTED]" in line:
                    print("".join(search_buffer))
                    print("-" * 70)
                    capturing_search = False
                    search_buffer = []
                elif any(stop_tag in line for stop_tag in ["[MATCH FOUND]", "[NO MATCH FOUND]"]):
                    capturing_search = False  # It was a success or zero, so clear the buffer
                    search_buffer = []

            # When we hit a multiple, turn on the capture beam
            if "[MULTIPLE]" in line:
                capturing_multiple = True
                multiple_buffer.append("\n" + line.strip() + "\n")
                continue

            # Capture the juicy telemetry data associated with the multiple
            if capturing_multiple:
                if any(keyword in line for keyword in
                       ["--- TARGET DEMOGRAPHICS ---", "--- DATABASE MATCHES ---", "MATCHES", "score |", "h_bpl_str |",
                        "w_bpl_str |", "fam |", "HUSB:", "WIFE:", "MARR:", "KIDS:", "gedcom_kids", "db_kids"]):
                    multiple_buffer.append(line.strip() + "\n")

        # Catch the final multiple if it was at the very end of the file
        if capturing_multiple and multiple_buffer:
            print("".join(multiple_buffer))
            print("-" * 70)

    print("\n--- FINAL RUN SUMMARY ---")
    for line in summary_buffer:
        print(line.strip())

    print("Scan Complete.")


if __name__ == '__main__':
    # Auto-grab the most recent log file
    log_dir = r"E:\Users\Andy\PycharmProjects\Genealogy\log"
    log_files = glob.glob(os.path.join(log_dir, "vault_NAME_OVERLAY_*.log"))

    if log_files:
        target_log = max(log_files, key=os.path.getctime)
        analyze_log(target_log)
    else:
        print(f"No log files found in {log_dir}")
