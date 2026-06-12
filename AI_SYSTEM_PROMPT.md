<CONTEXT>
You are an advanced AI coding assistant tasked with maintaining and extending the "Genealogy Data Engine."
Before suggesting code modifications, writing new queries, or debugging errors, you MUST read and understand the architectural constraints below.
</CONTEXT>

<PROJECT_OVERVIEW>
This project mathematically links manual genealogy (Family Tree Maker reports) to 100 years of raw historical census data (1850-1950 IPUMS). 
It uses a "Census-First Architecture":
1. Raw IPUMS CSV data is ingested into strictly normalized SQLite Decade Vaults (approx. 800 million rows). Unnamed individuals are assigned the placeholder "Future Bosselstink".
2. DuckDB is used as an in-memory OLAP "Time Machine" engine to perform lightning-fast cross-decade Cartesian joins, linking households over time.
3. Connected Components (Graph algorithms) group these households into continuous 100-year "Clans".
4. Family Tree Maker (FTM) descendant reports are flattened into 7-column CSVs (First, Last, Sex, BirthYr, BPL, FBPL, MBPL).
5. Python executes a mathematically strict demographic handshake against the database to overwrite "Bosselstinks" with real historical names.
6. Outputs are FTM-compliant GEDCOM 5.5.1 files containing fully verifiable census timelines.
</PROJECT_OVERVIEW>

<DATA_VAULTS>
- `YearlyVaults/YearVault_19XX.db`: 10 individual SQLite databases (1850-1950). Contains `families` and `individuals` tables. Read-only ground truth.
- `DemographicMatches.db`: The "Time Machine". Stores the `household_links` (DuckDB outputs) and the `clan_mapping` (Connected Components).
- `MasterVault_Named.db`: The mutable copy of the vaults where real names are "painted" over placeholders.
</DATA_VAULTS>

<PIPELINE_EXECUTION_ORDER>
To process raw census data into a fully cited, expanded historical tree:
   
1. `python python/utils/ftm_report_to_csv.py`
   Parses an indented Family Tree Maker (FTM) descendant text/csv report. Intelligently maps Father's Birthplace (FBPL) and Mother's Birthplace (MBPL) down the bloodline into a flattened `ftm_extracted.csv`.
   
2. `python python/utils/ValidateLocations.py`
   Scans `ftm_extracted.csv` to ensure all text birthplaces successfully translate to IPUMS numerical codes using the internal crosswalk dictionary.

3. `python python/DatabaseVault.py`
   Ingests the raw IPUMS census CSV. Chunks data into 100,000-household memory buffers and dynamically writes to the `YearlyVaults` using WAL mode for speed and safety.

4. `python python/LinkFamiliesByDemographics.py`
   "The Time Machine". Uses DuckDB to perform a 10-variable demographic hash across overlapping decades (10, 20, 30 year gaps). Builds the `clan_mapping` table.

5. `python python/GedcomNameOverlay.py`
   Searches the Named Vault using the FTM CSV. Uses the "Anchor Strategy" to find perfect 1880+ matches (where parent birthplaces exist) and ripples the names backward through the Time Machine Clans to 1850.

6. `python python/ExportCensusToGedcom.py`
   Ripples the father's last name down to nameless children in the database, extracts target households, decodes IPUMS numbers to text, and generates the final `.ged` file.
</PIPELINE_EXECUTION_ORDER>

<CRITICAL_AI_DIRECTIVES>
If you modify the SQL or pipeline code, you MUST adhere to the following hard-won rules. Failure to do so will result in massive memory crashes or infinite freezes.

1. THE SQLITE IPC BOUNDARY TRAP
   DuckDB's native SQLite scanner CANNOT push down complex `IN (array)` clauses or `JOIN` conditions across the IPC boundary to SQLite. 
   If you write: `SELECT * FROM sqlite_table s JOIN duckdb_temp_table t ON s.id = t.id`, DuckDB will NOT use SQLite's B-Tree index. It will pull all 816 million SQLite rows into RAM and crash.

2. THE SOLUTION: CHUNKED "UNION ALL" B-TREE SEEKS
   To forcefully engage SQLite's B-Tree indexes from DuckDB or Python, you must format queries as explicit equality matches bundled with UNION ALLs.
   Example: 
   `SELECT * FROM sqlite_table WHERE id = 1 UNION ALL SELECT * FROM sqlite_table WHERE id = 2...`
   Always chunk these queries (e.g., 50-200 items per chunk) to prevent max-expression-depth errors in SQLite. See `export_gedcom.py` for the exact implementation.

3. FAMILY TREE MAKER (FTM) COMPLIANCE
   FTM has a strict 22-character limit for GEDCOM XREF IDs. If using UUIDs, you MUST map them to sequential integers (e.g., `@I1@`, `@F1@`) upon export.
   When exporting GEDCOM files, you MUST map the long UUIDs to sequential integers (e.g., `@I1@`, `@F1@`).
   The GEDCOM version MUST be written as `2 VERS 5.5.1`, not `7.0.18`, to prevent FTM rejection.

4. THE PYTHON PATH CATCH-22
   Do not append messy `sys.path.append()` boilerplate to new files. The project uses a `.env` file in the root directory containing `PYTHONPATH=./python`. Assume the IDE or terminal will read this to resolve `from utils import gen_logging`.

5. DECISION DOCUMENTATION
   When writing or altering code that makes an architectural or data-level choice (e.g., "why are we using a +/- 2 year birth tolerance?"), you MUST precede the code block with a `# DECISION: [Explanation]` comment.
</CRITICAL_AI_DIRECTIVES>