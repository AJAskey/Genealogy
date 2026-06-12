"""
-----------------------------------
File: match2words.py

Summary:

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import re


def find(w1, w2, line):
    ret = False
    m1 = re.compile(w1, re.IGNORECASE)
    f1 = m1.search(line)
    if f1:
        m2 = re.compile(w2, re.IGNORECASE)
        f2 = m2.search(line)
        if f2: ret = True
    return ret


if __name__ == "__main__":
    print("Match2Words module loaded")

    file_path = r"../data/testfile.txt"

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f_in:
        lines = f_in.readlines()
        for i, line in enumerate(lines):
            print(f"Line {i + 1}: {line.strip()}")

            # str = "M'CORMACK, JAMES BOON, WILLIAM G. ALEXANDER, ERSKINE HAZARD, JOSHUA"

            found = find("ERSKINE", "HAZARD", line)
            print(found)
