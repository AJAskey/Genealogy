import json
import os
import sqlite3
import sys

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [os.path.join(project_root, 'python'), project_root]:
    if p not in sys.path:
        sys.path.append(p)

MASTER_DB = r"D:\Data\Genealogy_Data\MasterVault_Relational.db"
DEBUG_OUT = os.path.join(project_root, "debug", "FamilyTree_Objects_Debug.txt")


class Person:
    def __init__(self, db_row):
        # Unpack the database row
        self.histid = db_row[0]
        self.first_name = db_row[1]
        self.last_name = db_row[2]
        self.age = db_row[8]
        self.sex = db_row[9]

        # Unpack the bread crumbs to get the exact relationship!
        raw_json = json.loads(db_row[17])
        self.relate = raw_json.get("RELATE", "Unknown")
        self.occupation = raw_json.get("OCCUPATION", "N/A")

    def __str__(self):
        return f"    [{self.relate}] {self.first_name} {self.last_name} (Age: {self.age}, Sex: {self.sex}) - {self.histid}"


class Family:
    def __init__(self, db_row):
        self.family_id = db_row[0]
        self.year = db_row[1]
        self.serial = db_row[2]
        self.famunit = db_row[3]
        self.head_histid = db_row[4]
        self.members = []

    def add_member(self, person):
        self.members.append(person)

    def __str__(self):
        output = [f"Family: {self.family_id} (Year: {self.year}, House: {self.serial})"]
        for member in self.members:
            output.append(str(member))
        return "\n".join(output)


def debug_database_objects(limit=10):
    print(f"Connecting to {MASTER_DB}...")
    os.makedirs(os.path.dirname(DEBUG_OUT), exist_ok=True)

    with sqlite3.connect(MASTER_DB) as conn:
        cursor = conn.cursor()

        # 1. Grab a few families
        cursor.execute(f"SELECT * FROM families LIMIT {limit}")
        family_rows = cursor.fetchall()

        all_families = []

        for f_row in family_rows:
            family_obj = Family(f_row)

            # 2. Grab all the individuals that belong to this family
            cursor.execute("SELECT * FROM individuals WHERE family_id = ?", (family_obj.family_id,))
            individual_rows = cursor.fetchall()

            # 3. Populate the Person objects and add them to the Family
            for i_row in individual_rows:
                person_obj = Person(i_row)
                family_obj.add_member(person_obj)

            all_families.append(family_obj)

    # 4. Write the Object data out to the debug file
    print(f"Writing Object report to {DEBUG_OUT}...")
    with open(DEBUG_OUT, 'w', encoding='utf-8') as f:
        f.write("========================================================\n")
        f.write("            OBJECT-ORIENTED DATABASE DUMP               \n")
        f.write("========================================================\n\n")
        for fam in all_families:
            f.write(str(fam) + "\n\n")

    print("Done! Check the debug directory.")


if __name__ == "__main__":
    # Change this number to output more or fewer families
    debug_database_objects(limit=25)
