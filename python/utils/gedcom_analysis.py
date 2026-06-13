"""
-----------------------------------
File: gedcom_to_spreadsheet.py

Summary: Parses a GEDCOM file and exports all individuals and family
         relationships to both CSV and a formatted Excel workbook.
         Captures: names, sex, birth/death/burial/marriage dates and places,
         parents, spouses, and children.
         Skips: sources, images, notes, and other non-essential records.

Architect & Designer: Andy Askey
Coder (AI Assistant): Anthropic Claude

License: Apache License 2.0
-----------------------------------
"""

import csv
import os
import sys
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

# ==============================================================================
# CONFIGURATION — edit these paths before running
# ==============================================================================
INPUT_GEDCOM = r"C:\Users\Andy\Documents\ThomasAskey.ged"
OUTPUT_DIR   = r"C:\Users\Andy\Documents"
# ==============================================================================


def parse_gedcom(filepath):
    """
    Single-pass GEDCOM parser.
    Returns two dicts: individuals and families.
    """
    individuals = {}   # id -> dict
    families    = {}   # id -> dict

    cur_indi_id  = None
    cur_fam_id   = None
    cur_event    = None   # 'BIRT', 'DEAT', 'BURI', 'MARR', etc.
    cur_level1   = None   # the level-1 tag currently open

    # DECISION: We only track these level-1 tags and ignore everything else.
    WANTED_EVENTS = {'BIRT', 'DEAT', 'BURI', 'MARR', 'BAPM', 'CHR'}

    def new_indi():
        return {
            'id': '', 'first_name': '', 'last_name': '', 'sex': '',
            'birth_date': '', 'birth_place': '',
            'death_date': '', 'death_place': '',
            'burial_date': '', 'burial_place': '',
            'fams': [],   # family IDs where this person is a spouse
            'famc': [],   # family IDs where this person is a child
        }

    def new_fam():
        return {
            'id': '', 'husb': '', 'wife': '',
            'marr_date': '', 'marr_place': '',
            'children': [],
        }

    with open(filepath, encoding='utf-8', errors='replace') as f:
        for raw_line in f:
            line = raw_line.rstrip('\r\n')
            if not line.strip():
                continue

            parts = line.split(' ', 2)
            if len(parts) < 2:
                continue

            level = parts[0].strip()
            tag   = parts[1].strip() if len(parts) > 1 else ''
            value = parts[2].strip() if len(parts) > 2 else ''

            # ------------------------------------------------------------------
            # Level 0 — start of a new record
            # ------------------------------------------------------------------
            if level == '0':
                cur_event   = None
                cur_level1  = None

                if tag.startswith('@I') and value == 'INDI':
                    cur_indi_id = tag.strip('@')
                    cur_fam_id  = None
                    individuals[cur_indi_id] = new_indi()
                    individuals[cur_indi_id]['id'] = cur_indi_id
                elif tag.startswith('@F') and value == 'FAM':
                    cur_fam_id  = tag.strip('@')
                    cur_indi_id = None
                    families[cur_fam_id] = new_fam()
                    families[cur_fam_id]['id'] = cur_fam_id
                else:
                    cur_indi_id = None
                    cur_fam_id  = None
                continue

            # ------------------------------------------------------------------
            # Level 1 inside an INDI record
            # ------------------------------------------------------------------
            if cur_indi_id:
                indi = individuals[cur_indi_id]

                if level == '1':
                    cur_event = None
                    cur_level1 = tag

                    if tag == 'NAME':
                        # GEDCOM name format: "First /Last/"
                        raw_name = value.replace('/', ' ').strip()
                        name_parts = raw_name.split()
                        # Last name is between the slashes
                        slash_parts = value.split('/')
                        if len(slash_parts) >= 2:
                            indi['last_name']  = slash_parts[1].strip()
                            indi['first_name'] = slash_parts[0].strip()
                        else:
                            indi['first_name'] = raw_name
                        continue

                    if tag == 'SEX':
                        indi['sex'] = value
                        continue

                    if tag == 'FAMS':
                        indi['fams'].append(value.strip('@'))
                        continue

                    if tag == 'FAMC':
                        indi['famc'].append(value.strip('@'))
                        continue

                    if tag in WANTED_EVENTS:
                        cur_event = tag
                        continue

                if level == '2' and cur_event:
                    if tag == 'DATE':
                        if cur_event == 'BIRT':
                            indi['birth_date'] = value
                        elif cur_event == 'DEAT':
                            indi['death_date'] = value
                        elif cur_event == 'BURI':
                            indi['burial_date'] = value
                    elif tag == 'PLAC':
                        if cur_event == 'BIRT':
                            indi['birth_place'] = value
                        elif cur_event == 'DEAT':
                            indi['death_place'] = value
                        elif cur_event == 'BURI':
                            indi['burial_place'] = value
                    # Ignore other level-2 tags (SOUR, MAP, etc.)
                    continue

            # ------------------------------------------------------------------
            # Level 1 inside a FAM record
            # ------------------------------------------------------------------
            if cur_fam_id:
                fam = families[cur_fam_id]

                if level == '1':
                    cur_event  = None
                    cur_level1 = tag

                    if tag == 'HUSB':
                        fam['husb'] = value.strip('@')
                        continue
                    if tag == 'WIFE':
                        fam['wife'] = value.strip('@')
                        continue
                    if tag == 'CHIL':
                        fam['children'].append(value.strip('@'))
                        continue
                    if tag == 'MARR':
                        cur_event = 'MARR'
                        continue

                if level == '2' and cur_event == 'MARR':
                    if tag == 'DATE':
                        fam['marr_date'] = value
                    elif tag == 'PLAC':
                        fam['marr_place'] = value
                    continue

    return individuals, families


def build_individuals_rows(individuals, families):
    """
    Produces one row per individual with resolved parent and spouse names.
    """
    rows = []

    def name_of(indi_id):
        if not indi_id or indi_id not in individuals:
            return ''
        i = individuals[indi_id]
        return f"{i['first_name']} {i['last_name']}".strip()

    for indi_id, i in individuals.items():
        # Resolve father / mother from the first FAMC family
        father_name = ''
        mother_name = ''
        if i['famc']:
            fam = families.get(i['famc'][0])
            if fam:
                father_name = name_of(fam['husb'])
                mother_name = name_of(fam['wife'])

        # Resolve spouses and marriage info
        spouse_names  = []
        marr_dates    = []
        marr_places   = []
        for fam_id in i['fams']:
            fam = families.get(fam_id)
            if not fam:
                continue
            # The spouse is whichever role the current person is NOT
            spouse_id = fam['wife'] if fam['husb'] == indi_id else fam['husb']
            spouse_names.append(name_of(spouse_id))
            marr_dates.append(fam['marr_date'])
            marr_places.append(fam['marr_place'])

        # Resolve children from all FAMS families
        child_names = []
        for fam_id in i['fams']:
            fam = families.get(fam_id)
            if fam:
                for c_id in fam['children']:
                    child_names.append(name_of(c_id))

        rows.append({
            'ID':             indi_id,
            'First Name':     i['first_name'],
            'Last Name':      i['last_name'],
            'Sex':            i['sex'],
            'Birth Date':     i['birth_date'],
            'Birth Place':    i['birth_place'],
            'Death Date':     i['death_date'],
            'Death Place':    i['death_place'],
            'Burial Date':    i['burial_date'],
            'Burial Place':   i['burial_place'],
            'Father':         father_name,
            'Mother':         mother_name,
            'Spouse(s)':      ' | '.join(filter(None, spouse_names)),
            'Marriage Date(s)':  ' | '.join(filter(None, marr_dates)),
            'Marriage Place(s)': ' | '.join(filter(None, marr_places)),
            'Children':       ' | '.join(filter(None, child_names)),
        })

    # Sort: last name, then first name
    rows.sort(key=lambda r: (r['Last Name'].upper(), r['First Name'].upper()))
    return rows


def build_families_rows(individuals, families):
    """
    Produces one row per family unit.
    """
    rows = []

    def name_of(indi_id):
        if not indi_id or indi_id not in individuals:
            return ''
        i = individuals[indi_id]
        return f"{i['first_name']} {i['last_name']}".strip()

    def dates_of(indi_id, field):
        if not indi_id or indi_id not in individuals:
            return ''
        return individuals[indi_id].get(field, '')

    for fam_id, fam in families.items():
        child_names = [name_of(c) for c in fam['children']]
        rows.append({
            'Family ID':      fam_id,
            'Husband':        name_of(fam['husb']),
            'Husb Birth':     dates_of(fam['husb'], 'birth_date'),
            'Husb Death':     dates_of(fam['husb'], 'death_date'),
            'Wife':           name_of(fam['wife']),
            'Wife Birth':     dates_of(fam['wife'], 'birth_date'),
            'Wife Death':     dates_of(fam['wife'], 'death_date'),
            'Marriage Date':  fam['marr_date'],
            'Marriage Place': fam['marr_place'],
            'Num Children':   len(fam['children']),
            'Children':       ' | '.join(filter(None, child_names)),
        })

    rows.sort(key=lambda r: r['Husband'].upper())
    return rows


def write_csv(rows, filepath):
    if not rows:
        return
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  CSV written: {filepath}")


def write_xlsx(indi_rows, fam_rows, filepath):
    wb = Workbook()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------
    header_font    = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    header_fill    = PatternFill('solid', start_color='2F5496')   # dark blue
    subhdr_fill    = PatternFill('solid', start_color='9DC3E6')   # light blue
    alt_fill       = PatternFill('solid', start_color='EBF3FB')   # very light blue
    center_align   = Alignment(horizontal='center', vertical='center', wrap_text=False)
    wrap_align     = Alignment(horizontal='left',   vertical='top',    wrap_text=True)
    normal_font    = Font(name='Arial', size=9)
    header_align   = Alignment(horizontal='center', vertical='center', wrap_text=True)

    def style_header_row(ws, row_num, num_cols):
        for col in range(1, num_cols + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.font      = header_font
            cell.fill      = header_fill
            cell.alignment = header_align

    def write_sheet(ws, rows, title):
        if not rows:
            return
        cols = list(rows[0].keys())
        ws.title = title

        # Header
        ws.append(cols)
        style_header_row(ws, 1, len(cols))
        ws.row_dimensions[1].height = 28

        # Data rows
        for i, row in enumerate(rows, start=2):
            ws.append([row.get(c, '') for c in cols])
            fill = alt_fill if i % 2 == 0 else None
            for col_idx in range(1, len(cols) + 1):
                cell = ws.cell(row=i, column=col_idx)
                cell.font      = normal_font
                cell.alignment = wrap_align
                if fill:
                    cell.fill = fill

        # Auto-size columns (capped at 60)
        for col_idx, col_name in enumerate(cols, start=1):
            max_len = len(col_name)
            for row in rows:
                val = str(row.get(col_name, ''))
                # For pipe-delimited multi-value cells, measure longest segment
                seg = max((s.strip() for s in val.split('|')), key=len, default='')
                max_len = max(max_len, len(seg))
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 60)

        # Freeze the header row
        ws.freeze_panes = 'A2'

    # ------------------------------------------------------------------
    # Sheet 1: Individuals
    # ------------------------------------------------------------------
    ws1 = wb.active
    write_sheet(ws1, indi_rows, 'Individuals')

    # ------------------------------------------------------------------
    # Sheet 2: Families
    # ------------------------------------------------------------------
    ws2 = wb.create_sheet('Families')
    write_sheet(ws2, fam_rows, 'Families')

    # ------------------------------------------------------------------
    # Sheet 3: Summary stats
    # ------------------------------------------------------------------
    ws3 = wb.create_sheet('Summary')
    ws3.title = 'Summary'
    ws3.column_dimensions['A'].width = 30
    ws3.column_dimensions['B'].width = 20

    summary_header_font = Font(name='Arial', bold=True, color='FFFFFF', size=11)
    title_cell = ws3['A1']
    title_cell.value = 'GEDCOM Export Summary'
    title_cell.font  = Font(name='Arial', bold=True, size=14)
    ws3.merge_cells('A1:B1')
    ws3['A1'].alignment = Alignment(horizontal='center')

    stats = [
        ('Total Individuals', len(indi_rows)),
        ('Total Families',    len(fam_rows)),
        ('With Birth Date',   sum(1 for r in indi_rows if r['Birth Date'])),
        ('With Death Date',   sum(1 for r in indi_rows if r['Death Date'])),
        ('With Burial Info',  sum(1 for r in indi_rows if r['Burial Date'] or r['Burial Place'])),
        ('With Marriage',     sum(1 for r in fam_rows  if r['Marriage Date'])),
        ('Males',             sum(1 for r in indi_rows if r['Sex'] == 'M')),
        ('Females',           sum(1 for r in indi_rows if r['Sex'] == 'F')),
    ]

    for row_num, (label, value) in enumerate(stats, start=3):
        ws3.cell(row=row_num, column=1, value=label).font = Font(name='Arial', bold=True, size=10)
        ws3.cell(row=row_num, column=2, value=value).font = Font(name='Arial', size=10)
        ws3.cell(row=row_num, column=2).alignment = Alignment(horizontal='right')

    wb.save(filepath)
    print(f"  XLSX written: {filepath}")


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == '__main__':
    # Allow overriding paths from command line
    gedcom_path = sys.argv[1] if len(sys.argv) > 1 else INPUT_GEDCOM
    out_dir     = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_DIR

    if not os.path.exists(gedcom_path):
        print(f"ERROR: GEDCOM file not found: {gedcom_path}")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(gedcom_path))[0]

    print(f"Parsing: {gedcom_path}")
    individuals, families = parse_gedcom(gedcom_path)
    print(f"  Found {len(individuals):,} individuals, {len(families):,} families.")

    print("Building rows...")
    indi_rows = build_individuals_rows(individuals, families)
    fam_rows  = build_families_rows(individuals, families)

    print("Writing CSV files...")
    write_csv(indi_rows, os.path.join(out_dir, f"{base_name}_individuals.csv"))
    write_csv(fam_rows,  os.path.join(out_dir, f"{base_name}_families.csv"))

    print("Writing Excel workbook...")
    write_xlsx(indi_rows, fam_rows, os.path.join(out_dir, f"{base_name}.xlsx"))

    print("\nDone!")
    print(f"Output folder: {out_dir}")
