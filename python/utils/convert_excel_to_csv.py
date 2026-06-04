import os

import pandas as pd


def convert_excel_to_csv(input_path, output_path=None):
    """
    Converts heavy Excel genealogy blocks to light, high-performance CSVs.
    """
    if not output_path:
        output_path = input_path.replace('.xlsx', '.csv').replace('.xls', '.csv')

    print(f"--- Initializing Conversion: {os.path.basename(input_path)} ---")

    try:
        # Load the Excel file. 
        # Using 'engine=openpyxl' for .xlsx or 'engine=xlrd' for .xls
        df = pd.read_excel(input_path)

        # Save as CSV with UTF-8 encoding to preserve special characters
        df.to_csv(output_path, index=False, encoding='utf-8')

        print(f"Success! Data flattened and saved to: {output_path}")
        print(f"Total records processed: {len(df):,}")

    except Exception as e:
        print(f"CRITICAL ERROR: Failed to convert file. {e}")


if __name__ == "__main__":
    # Example usage with your ingestion path
    excel_file = r"D:\Data\Genealogy_Data\Ingestion\Raw_Blocks\Specific_Death_File.xlsx"
    convert_excel_to_csv(excel_file)
