import os
import sys

# Tell Sphinx exactly where your Python scripts live
sys.path.insert(0, os.path.abspath('../python'))

# Project Information
project = 'Census-First Genealogy Architecture'
copyright = '2026, Andy Askey'
author = 'Andy Askey'

# The Magic Extensions
extensions = [
    'sphinx.ext.autodoc',   # Automatically pulls in your scripts
    'sphinx.ext.viewcode',  # Creates the clickable "[source]" links to your code!
    'sphinx.ext.napoleon'   # Makes Google-style docstrings look beautiful
]

# HTML Theme Settings
html_theme = 'sphinx_rtd_theme'

# (Optional) If you have a logo, you can uncomment this later:
# html_logo = "_static/logo.png"
html_static_path = []