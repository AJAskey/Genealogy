"""
Utility script to peek at the formatting of large historical text files.
"""
import os

FILE_PATH = r"E:\Users\Andy\PycharmProjects\Genealogy\data\deaths file 1975.txt"


def peek_file():
    if not os.path.exists(FILE_PATH):
        print(f"ERROR: Cannot find {FILE_PATH}")
        return

    print(f"--- First 10 lines of {os.path.basename(FILE_PATH)} ---\n")

    with open(FILE_PATH, 'r', encoding='utf-8', errors='replace') as f:
        for i in range(10):
            line = f.readline()
            if not line:
                break
            print(repr(line))  # repr() reveals hidden tabs (\t) and exact spacing!


if __name__ == "__main__":
    peek_file()
