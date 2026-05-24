"""
-----------------------------------
File: fragment_csv.py

Summary: Splits massive CSV files into smaller, Excel-friendly chunks 
         to prevent pandas or system memory crashes.
-----------------------------------
"""
import os

import pandas as pd


def fragment_csv(input_csv, rows_per_file=50000):
    """
    Splits a massive CSV into smaller, Excel-friendly chunks.
    Ensures every chunk has the original header.
    """
    # Create an output directory to keep the D: drive clean
    output_base = input_csv.replace('.csv', '_chunks')
    if not os.path.exists(output_base):
        os.makedirs(output_base)

    print(f"--- Initializing Fragmentation: {os.path.basename(input_csv)} ---")

    # Using 'chunksize' allows us to process a 10GB file on 128GB RAM easily
    # It streams the file instead of swallowing it whole
    reader = pd.read_csv(input_csv, chunksize=rows_per_file)

    for i, chunk in enumerate(reader):
        chunk_name = f"part_{i + 1}.csv"
        output_path = os.path.join(output_base, chunk_name)

        # index=False prevents that annoying extra column from appearing
        chunk.to_csv(output_path, index=False, encoding='utf-8')
        print(f"  > Generated: {chunk_name} ({len(chunk):,} records)")

    print(f"--- Fragmentation Complete: {output_base} ---")


if __name__ == "__main__":
    # Point this to one of your freshly converted CSVs
    big_death_file = \
        r"E:\Users\Andy\PycharmProjects\Genealogy\data\BIRLS_database\Reclaim_The_Records_-_BIRLS_database_-_update_file_received_from_the_VA_for_2020-2023.csv"

    # 50,000 rows is a 'sweet spot' for quick opening in Excel
    fragment_csv(big_death_file, rows_per_file=150000)
