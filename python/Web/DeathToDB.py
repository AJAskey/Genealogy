"""
-----------------------------------
File: DeathtoDB.py

Summary:

Usage:   Tweak the parameters below and run. That's it.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sys

# Add the 'python' directory to sys.path so we can import from 'Web'
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.abspath(os.path.join(script_dir, '..'))
if python_dir not in sys.path:
    sys.path.append(python_dir)

from Web import IngestDeathFile
from Web import IngestBirls

if __name__ == '__main__':
    print("Running Death File Ingestion...")
    IngestDeathFile.main()
    IngestBirls.main()
    print("Done!")
