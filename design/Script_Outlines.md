# Project Pipeline: Script Outlines

## Phase 1: Ingestion & Vault Generation
*   **`DatabaseVault.py`**
    *   **Role:** The core Census ingestion engine.
    *   **Action:** Spawns parallel threads (up to `MAX_WORKERS`) to read IPUMS CSV chunks. Uses `CODEBOOK.json` to translate codes into text and writes to year-specific SQLite vaults using WAL mode.
*   **`IngestBirls.py`**
    *   **Role:** The Auxiliary Data ingestion engine.
    *   **Action:** Reads massive VA Death Index (BIRLS) CSVs in parallel and bulk-inserts them into `DeathIndexVault.db` with optimized indexes.

## Phase 2: Analysis & AI Resolution
*   **`run_analyst.py`**
    *   **Role:** The Driver Script for AI resolution.
    *   **Action:** Mounts all databases simultaneously via DuckDB, filters targets, and passes the graph to Splink. (See `Analyst_Pipeline_Deep_Dive.md` for detail).
*   **`CreateGoldenRecord.py`**
    *   **Role:** The Entity Resolution brain (Splink v4).
    *   **Action:** Handles EM training, probabilistic prediction, graph clustering, and survivorship rules.
*   **`GoldenRecordGenerator.py`**
    *   **Role:** Legacy Splink implementation script.

## Phase 3: Output Generation
*   **`export_gedcom.py`**
    *   **Role:** The Final Output Builder.
    *   **Action:** Reads structured household data and generates a strictly compliant GEDCOM 7.0.18 `.ged` file with `INDI` and `FAM` tags for software like Family Tree Maker.

## Utility & Helper Scripts
*   **`process_monitor.py`**
    *   CLI tool to monitor CPU/Memory during DuckDB operations.
*   **`gen_logging.py`**
    *   Centralized logging configuration ensuring thread-safe disk writes without double-logging.
*   **`fragment_csv.py`**
    *   Slices massively bloated CSV files into smaller chunks to protect RAM.
*   **`download_genealogy_blocks.py`**
    *   Automates retrieving target data blocks from the Internet Archive API.
*   **`gedcom_to_csv.py`**
    *   Flattens external, pre-existing GEDCOM family trees into readable CSVs for Auxiliary Vault ingestion.