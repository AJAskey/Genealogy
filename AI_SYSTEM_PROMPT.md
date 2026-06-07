<CONTEXT>
You are an advanced AI coding assistant tasked with maintaining and extending the "Genealogy Data Engine."
Before suggesting code modifications, writing new queries, or debugging errors, you MUST read and understand the architectural constraints below.
</CONTEXT>

<PROJECT_OVERVIEW>
This project mathematically links manual genealogy (GEDCOM) records to 100 years of raw historical census data (1850-1950 IPUMS) and death indexes (BIRLS). 
It uses a "Golden Architecture":
1. Raw data is stored in read-only SQLite vaults (up to 100GB / 816 million rows).
2. DuckDB is used as an in-memory engine to perform lightning-fast streaming and joining.
3. Splink AI is used for probabilistic string matching.
4. Python graph algorithms ("Living Room Sweep") traverse historical pointers to expand nuclear families.
5. Outputs are FTM-compliant GEDCOM 5.5.1 files.
</PROJECT_OVERVIEW>

<DATA_VAULTS>
- `MasterVault_ALL.db`: 100% census data (816M rows). Nameless. Read-only.
- `MasterVault_ALLs.db`: 5% sample census data (40M rows). Contains names. Read-only.
- `DeathIndexVault.db`: BIRLS and Universal Death indexes.
- `GedcomVault.db`: The user's parsed GEDCOM family anchors.
- `CleanVault.db` (or `CleanVault_Gedcom.db`): Writable SQLite vault. Stores "Golden Records" (mathematically verified human identities with 16-char UUIDs).
</DATA_VAULTS>

<PIPELINE_EXECUTION_ORDER>
To process a specific GEDCOM into a fully cited, expanded historical tree:

1. `python python/IngestGedcomFile.py`
   Parses the .ged file, captures the `FAM` tags (husband/wife/child relationships), and saves to `GedcomVault.db`.
   
2. `python python/MergeGedcomToCleanVault.py`
   Deterministically pushes the GEDCOM names and their inter-generational relationships into `CleanVault_Gedcom.db` as foundational Golden Records.

3. `python python/ExpandHouseholds.py --vault D:\Data\Genealogy_Data\CleanVault_Gedcom.db`
   "The Living Room Sweep". Looks at target households, streams the raw census, follows POPLOC (Father) and MOMLOC (Mother) pointers, and mints new Golden Records for previously un-named dependents.

4. `python python/utils/SnapGedcomLinks.py`
   Aggressive deterministic snap. Matches isolated GEDCOM shells (who didn't get census timelines) to Census Golden Records using EXACT last name, +/- 5 birth year, and First Initial. Grafts their pointers together.
   
5. `python python/utils/export_gedcom.py --out output\Tree.ged --vault D:\Data\Genealogy_Data\CleanVault_Gedcom.db --gedcom_only`
   Fetches historical timelines for all matched pointers. Generates a Family Tree Maker (FTM) compliant GEDCOM file.
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
   FTM has a strict 22-character limit for GEDCOM XREF IDs. Our Golden Record IDs are 24+ characters (e.g., `@SJ_AUTO_1234567890ABCDEF@`). 
   When exporting GEDCOM files, you MUST map the long UUIDs to sequential integers (e.g., `@I1@`, `@F1@`).
   The GEDCOM version MUST be written as `2 VERS 5.5.1`, not `7.0.18`, to prevent FTM rejection.

4. THE PYTHON PATH CATCH-22
   Do not append messy `sys.path.append()` boilerplate to new files. The project uses a `.env` file in the root directory containing `PYTHONPATH=./python`. Assume the IDE or terminal will read this to resolve `from utils import gen_logging`.
</CRITICAL_AI_DIRECTIVES>