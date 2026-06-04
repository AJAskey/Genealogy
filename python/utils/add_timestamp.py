import os
import sys
from datetime import datetime


def add_timestamp_to_file(filepath):
    """
    Prepends a date and time stamp to the top of the specified text file.
    """
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        return False

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    timestamp_str = f"--- Timestamp: {current_time} ---\n"

    try:
        # Read the existing content
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Write the timestamp followed by the original content
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(timestamp_str + content)

        print(f"Successfully added timestamp to {filepath}")
        return True
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_timestamp.py <file_path>")
    else:
        file_to_stamp = sys.argv[1]
        add_timestamp_to_file(file_to_stamp)
