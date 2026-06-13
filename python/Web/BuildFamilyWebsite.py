"""
-----------------------------------
File: BuildFamilyWebsite.py

Summary: A Static Site Generator (SSG) for the Genealogy Project.
         Reads the SQLite Decade Vaults and generates a completely 
         static, indestructible, clickable HTML website.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0: http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sqlite3
import sys

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [os.path.join(project_root, 'python'), project_root]:
    if p not in sys.path:
        sys.path.append(p)

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

NAMED_VAULT_DIR = os.path.join(BASE_DATA_DIR, "NamedVaults")
OUTPUT_DIR = os.path.join(project_root, "HTML")
SNIPPETS_DIR = os.path.join(project_root, "web_snippets")
TARGET_LAST_NAME = 'Askey'

# Clean HTML/CSS Template for the individual profile pages
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{full_name}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 0; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; margin-top: 0; }}
        h3 {{ color: #2980b9; margin-top: 30px; }}
        a {{ color: #3498db; text-decoration: none; font-weight: bold; }}
        a:hover {{ text-decoration: underline; color: #2980b9; }}
        .nav {{ margin-bottom: 20px; font-size: 0.9em; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
        th {{ background-color: #ecf0f1; color: #2c3e50; }}
        .snippet-box {{ background-color: #fffde7; border-left: 4px solid #f1c40f; padding: 15px; margin-top: 20px; font-style: italic; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav"><a href="index.html">← Back to Master Index</a></div>
        <h1>{full_name} (b. {birth_year})</h1>
        
        <h3>Family Connections</h3>
        <ul>
            <li><strong>Parents:</strong> {parents_html}</li>
            <li><strong>Children:</strong> {children_html}</li>
        </ul>

        <h3>Census Timeline</h3>
        <table>
            <tr><th>Year</th><th>Age</th><th>Location (State)</th></tr>
            {timeline_rows}
        </table>
        
        {snippets_html}
    </div>
</body>
</html>
"""


def make_key(first, last, byr):
    """Creates a URL-safe unique filename for a person."""
    f = str(first).strip().replace(" ", "")
    l = str(last).strip().replace(" ", "")
    b = str(byr).strip()
    return f"{f}_{l}_{b}".lower()


def build_website():
    print("Step 1: Gathering family data from all Decade Vaults...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(SNIPPETS_DIR, exist_ok=True)

    profiles = {}  # key -> dict of person info
    histid_to_key = {}  # maps a specific census row to a person key

    # 1. Fetch the data
    for filename in os.listdir(NAMED_VAULT_DIR):
        if filename.startswith("NamedVault_") and filename.endswith(".db"):
            db_path = os.path.join(NAMED_VAULT_DIR, filename)
            with sqlite3.connect(db_path) as conn:
                # Get anyone in a household that contains an Askey
                rows = conn.execute(f"""
                    SELECT histid, first_name, last_name, birthyr, sex, father_histid, mother_histid, year, age, bpld
                    FROM individuals 
                    WHERE family_id IN (
                        SELECT DISTINCT family_id FROM individuals WHERE last_name COLLATE NOCASE = '{TARGET_LAST_NAME}'
                    )
                """).fetchall()

                for r in rows:
                    histid, fname, lname, byr, sex, f_histid, m_histid, year, age, bpld = r
                    if not byr or fname == 'Future': continue

                    p_key = make_key(fname, lname, byr)
                    histid_to_key[histid] = p_key

                    if p_key not in profiles:
                        profiles[p_key] = {
                            'first_name': fname, 'last_name': lname, 'birthyr': byr,
                            'timeline': [], 'parents': set(), 'children': set(),
                            'father_histid': f_histid, 'mother_histid': m_histid  # Temp storage
                        }

                    profiles[p_key]['timeline'].append((year, age, bpld))

    print("Step 2: Resolving Parent/Child Hyperlinks...")
    # Second pass: Now that we know who everyone is, map the parents to the children
    for p_key, data in profiles.items():
        f_histid = data['father_histid']
        m_histid = data['mother_histid']

        if f_histid and f_histid in histid_to_key:
            father_key = histid_to_key[f_histid]
            profiles[p_key]['parents'].add(father_key)
            profiles[father_key]['children'].add(p_key)

        if m_histid and m_histid in histid_to_key:
            mother_key = histid_to_key[m_histid]
            profiles[p_key]['parents'].add(mother_key)
            profiles[mother_key]['children'].add(p_key)

    print(f"Step 3: Generating HTML pages for {len(profiles)} individuals...")
    index_links = []

    for p_key, data in profiles.items():
        full_name = f"{data['first_name']} {data['last_name']}"

        # Format Parent HTML
        parents_html = ", ".join(
            [f"<a href='{k}.html'>{profiles[k]['first_name']} {profiles[k]['last_name']}</a>" for k in data['parents']])
        if not parents_html: parents_html = "Unknown"

        # Format Children HTML
        children_html = ", ".join(
            [f"<a href='{k}.html'>{profiles[k]['first_name']} {profiles[k]['last_name']}</a>" for k in
             data['children']])
        if not children_html: children_html = "None identified"

        # Format Timeline HTML
        data['timeline'].sort(key=lambda x: x[0])  # Sort by year
        timeline_rows = ""
        for t_year, t_age, t_bpld in data['timeline']:
            timeline_rows += f"<tr><td>{t_year}</td><td>{t_age}</td><td>State Code: {t_bpld}</td></tr>\n"

        # Format Web Snippets
        snippets_html = ""
        snippet_path = os.path.join(SNIPPETS_DIR, f"{p_key}.txt")
        if os.path.exists(snippet_path):
            with open(snippet_path, 'r', encoding='utf-8') as sf:
                snippet_text = sf.read().strip()
            if snippet_text:
                paragraphs = "".join([f"<p>{p.strip()}</p>" for p in snippet_text.split('\n\n') if p.strip()])
                snippets_html = f'<div class="snippet-box"><h3>Web Search Snippets & Notes</h3>{paragraphs}</div>'

        # Inject into template
        html_content = HTML_TEMPLATE.format(
            full_name=full_name, birth_year=data['birthyr'],
            parents_html=parents_html, children_html=children_html,
            timeline_rows=timeline_rows,
            snippets_html=snippets_html
        )

        with open(os.path.join(OUTPUT_DIR, f"{p_key}.html"), 'w', encoding='utf-8') as f:
            f.write(html_content)

        index_links.append((data['last_name'], data['first_name'], data['birthyr'], p_key))

    print("Step 4: Building the Master Index...")
    index_links.sort()  # Sort alphabetically
    index_html = "<html><head><title>Master Index</title><style>body { font-family: sans-serif; padding: 40px; line-height: 1.6; } a { text-decoration: none; color: #3498db; font-weight: bold; }</style></head><body>"
    index_html += "<h1>Family Tree Master Index</h1><ul>"
    for last, first, byr, p_key in index_links:
        index_html += f"<li><a href='{p_key}.html'>{last}, {first} (b. {byr})</a></li>\n"
    index_html += "</ul></body></html>"

    with open(os.path.join(OUTPUT_DIR, "index.html"), 'w', encoding='utf-8') as f:
        f.write(index_html)

    print(f"\nSUCCESS! Website generated at: {OUTPUT_DIR}\\index.html")


if __name__ == '__main__':
    build_website()
