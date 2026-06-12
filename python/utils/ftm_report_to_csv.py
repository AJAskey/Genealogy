"""
-----------------------------------
File: ftm_report_to_csv.py

Summary: Parses an indented Family Tree Maker descendant text report
         and flattens it into a tabular CSV.
         It uses the generation numbers (1, 2, 3) and spouse indicators (+)
         to intelligently map parent birthplaces to every child!

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import csv
import os
import re
import sys

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [os.path.join(project_root, 'python'), project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging


def convert_ftm_report(input_file, output_file, logger):
    if not os.path.exists(input_file):
        logger.error(f"Cannot find input file: {input_file}")
        return

    logger.info(f"Parsing FTM report: {input_file}")

    records = []
    hierarchy = {}
    last_level = 1

    lines_to_process = []

    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        if input_file.lower().endswith('.csv'):
            reader = csv.reader(f)
            for row in reader:
                if not row or not any(row): continue
                gen = str(row[0]).strip()
                if not gen: continue
                if len(row) > 1:
                    # DECISION: Reconstruct the full text line by joining all remaining columns.
                    # If a comma in the text was unquoted, the CSV reader splits the sentence 
                    # across columns. This stitches it safely back together!
                    text_parts = [str(c).strip() for c in row[1:] if str(c).strip()]
                    text = ", ".join(text_parts)
                    lines_to_process.append((gen, text))
        else:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.startswith('+'):
                    lines_to_process.append(('+', line[1:].strip()))
                else:
                    match = re.match(r'^(\d+)\s+(.*)', line)
                    if match:
                        lines_to_process.append((match.group(1), match.group(2).strip()))

    logger.info(f"  -> Found {len(lines_to_process)} raw lines to parse.")

    for gen, text in lines_to_process:
        if not text: continue

        is_spouse = False
        if gen == '+':
            is_spouse = True
            level = last_level
        elif gen.isdigit():
            level = int(gen)
            last_level = level
        else:
            continue

        line = text

        # Strip lifespan parens injected by FTM e.g., (1727 - 1807) or (1856 - )
        line = re.sub(r'\(\d{4}\s*-\s*\d{0,4}\s*\)', '', line).strip()

        # 1. Extract Sex from the full line first
        sex_match = re.search(r'\bSex:\s*(Male|Female)\b', line, flags=re.IGNORECASE)
        sex = ""
        if sex_match:
            sex = '1' if sex_match.group(1).lower() == 'male' else '2'

        # 2. Extract Name and Birth Info
        # Find where demographic markers start so we can isolate Name + Birth
        first_marker_idx = len(line)
        for marker in [' m:', ' sex:', ' d:', ' death:', ' burial:']:
            idx = line.lower().find(marker.lower())
            if idx != -1 and idx < first_marker_idx:
                first_marker_idx = idx

        name_birth_chunk = line[:first_marker_idx].strip()

        # Find the 4-digit year as the anchor
        yr_match = re.search(r'\b(1[456789]\d\d|20\d\d)\b', name_birth_chunk)
        birth_year = ""
        birth_place = ""

        if yr_match:
            birth_year = yr_match.group(1)
            year_idx = yr_match.start(1)
            year_end = yr_match.end(1)

            prefix = name_birth_chunk[:year_idx].strip()
            tokens = prefix.split()

            months = {'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
                      'january', 'february', 'march', 'april', 'june', 'july', 'august', 'september', 'october',
                      'november', 'december',
                      'abt', 'abt.', 'about', 'bef', 'bef.', 'before', 'aft', 'aft.', 'after', 'b', 'b.', 'b:'}

            # Pop off tokens that are part of the date
            while tokens:
                last_token = tokens[-1].lower()
                if last_token in months or re.match(r'^\d{1,2}$', last_token):
                    tokens.pop()
                else:
                    break

            first_name_str = " ".join(tokens)

            birth_place = name_birth_chunk[year_end:].strip()
            if birth_place.lower().startswith('in '):
                birth_place = birth_place[3:].strip()
            birth_place = birth_place.lstrip(',-; ').strip()
        else:
            first_name_str = name_birth_chunk

        name_tokens = first_name_str.split()
        if len(name_tokens) > 1:
            first_name = " ".join(name_tokens[:-1])
            last_name = name_tokens[-1]
        else:
            first_name = first_name_str
            last_name = ""

        person = {
            'first_name': first_name,
            'last_name': last_name,
            'sex': sex,
            'birth_year': birth_year,
            'birth_place': birth_place,
            'father_birth_place': '',
            'mother_birth_place': ''
        }

        # 3. Inherit Parent Birthplaces!
        if not is_spouse and level > 1:
            parent_level = level - 1
            if parent_level in hierarchy:
                p1 = hierarchy[parent_level].get('primary', {})
                p2 = hierarchy[parent_level].get('spouse', {})

                p1_sex = p1.get('sex', '')
                p2_sex = p2.get('sex', '')

                # Check sexes to assign father vs mother correctly
                if p1_sex == '1' or p2_sex == '2':
                    person['father_birth_place'] = p1.get('birth_place', '')
                    person['mother_birth_place'] = p2.get('birth_place', '')
                elif p1_sex == '2' or p2_sex == '1':
                    person['father_birth_place'] = p2.get('birth_place', '')
                    person['mother_birth_place'] = p1.get('birth_place', '')
                else:
                    # Fallback just in case
                    person['father_birth_place'] = p1.get('birth_place', '')
                    person['mother_birth_place'] = p2.get('birth_place', '')

        # 4. Update the active tree hierarchy
        if level not in hierarchy:
            hierarchy[level] = {}

        if is_spouse:
            hierarchy[level]['spouse'] = person
        else:
            hierarchy[level]['primary'] = person
            hierarchy[level]['spouse'] = {}  # Clear the spouse for the new primary person

        records.append(person)

    # Write to CSV
    headers = ['first_name', 'last_name', 'sex', 'birth_year', 'birth_place', 'father_birth_place',
               'mother_birth_place']
    logger.info(f"Writing {len(records)} parsed records to {output_file}")

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)

    logger.info("SUCCESS! FTM text report converted to CSV.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging("FTM_PARSER")

    input_file = os.path.join(project_root, "gedcom_sources", "captthom.csv")
    output_file = os.path.join(project_root, "gedcom_sources", "ftm_extracted.csv")

    convert_ftm_report(input_file, output_file, main_logger)
