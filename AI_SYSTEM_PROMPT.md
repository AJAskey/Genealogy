<CONTEXT>
You are an advanced AI coding assistant tasked with maintaining and extending the "Genealogy Data Engine."
Before suggesting code modifications, writing new queries, or debugging errors, you MUST read and understand the architectural constraints below.
</CONTEXT>

<PROJECT_OVERVIEW>
This project mathematically links manual genealogy (Family Tree Maker reports) to 100 years of raw historical census data (1850-1950 IPUMS). 
It uses a "Census-First Architecture":
1. Raw IPUMS CSV data is ingested into strictly normalized SQLite Decade Vaults (approx. 800 million rows). Unnamed individuals are assigned a placeholder name.
2. DuckDB is used as an in-memory OLAP "Time Machine" engine. It groups families into "Demographic Profiles" to completely bypass Cartesian explosions, mathematically linking millions of households in seconds.
3. Connected Components (Graph algorithms) group these households into continuous 100-year "Clans".
4. Family Tree Maker (FTM) descendant reports are processed into detailed JSON documents containing names, facts, and relationships.
5. Python executes a mathematically strict demographic handshake against the database to overwrite placeholder names with real historical names from the JSON data.
6. Outputs are FTM-compliant GEDCOM 5.5.1 files containing fully verifiable census timelines.
</PROJECT_OVERVIEW>

<DATA_VAULTS>
- `YearlyVaults/YearVault_19XX.db`: 10 individual SQLite databases (1850-1950). Contains `families` and `individuals` tables. Read-only ground truth.
- `DemographicMatches.db`: The "Time Machine". Stores the `household_links` (DuckDB outputs) and the `clan_mapping` (Connected Components).
- `MasterVault_Named.db`: The mutable copy of the vaults where real names are "painted" over placeholders.
</DATA_VAULTS>

<PIPELINE_EXECUTION_ORDER>
To process raw census data into a fully cited, expanded historical tree:
   
1. `python python/gedcom_analysis.py`
   Parses a GEDCOM file to provide names, facts, and relationships to be compared to the database for matching criteria. The output is a JSON file.

2. `python python/utils/ValidateLocations.py`
   Scans the generated JSON file to ensure all text birthplaces successfully translate to IPUMS numerical codes using the internal crosswalk dictionary.

3. `python python/DatabaseVault.py`
   Ingests the raw IPUMS census CSV. Chunks data into 100,000-household memory buffers and dynamically writes to the `YearlyVaults` using WAL mode for speed and safety.

4. `python python/LinkFamiliesByDemographics.py`
   "The Time Machine". Uses DuckDB to perform a 10-variable demographic hash across overlapping decades (10, 20, 30 year gaps) by grouping mathematical profiles. Builds the `clan_mapping` table.

5. `python python/GedcomNameOverlay_V2.py`
   The V2 Label-Maker. Acts as an overlay validation stage. Enforces a strict "Dead Weight" filter to drop irrelevant/unmarried census records from RAM, and applies a Geographic Tie-Breaker (Soft Scoring) to validate targets before names are rippled through the Clan graph.

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

6. AVOID CARTESIAN DEATH SPIRALS
   When joining census data in DuckDB across decades, early censuses (1850-1870) lack parent birthplaces (NULL). Direct row-by-row cross-joins of demographics containing NULL wildcards will generate 10+ billion row Cartesian explosions and crash. You MUST abstract the data into mathematically aggregated "Demographic Profiles" (with `COUNT(*)`) and multiply the counts (`c1 * c2`) rather than directly joining raw individuals. Also, always explicitly set DuckDB's `temp_directory` to a large data drive (e.g., `D:\`) to prevent C/E drive thrashing.
</CRITICAL_AI_DIRECTIVES>