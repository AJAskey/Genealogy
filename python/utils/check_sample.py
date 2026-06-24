import sqlite3

db_path = r"D:\Data\Genealogy_Data\YearlyVaults\CENSUS-SAMPLE.db"

print(f"Checking database: {db_path}...")
with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()

    # Check total people
    cursor.execute("SELECT COUNT(*) FROM individuals")
    total_people = cursor.fetchone()[0]

    # Check total families with BOTH a Head and a Spouse
    cursor.execute("SELECT COUNT(*) FROM families WHERE head_histid IS NOT NULL AND spouse_histid IS NOT NULL")
    married_couples = cursor.fetchone()[0]

print(f"Total Individuals: {total_people:,}")
print(f"Valid Married Couples: {married_couples:,}")
