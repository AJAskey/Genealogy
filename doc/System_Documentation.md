# Genealogy Project - System Documentation

## 1. System Architecture & Overview

The Genealogy project is a highly parallelized, SQLite-backed data processing pipeline designed to ingest, normalize, and link massive historical datasets (such as IPUMS U.S. Census records and Death Indexes). The ultimate goal is to build "Golden Records" representing distinct individuals across time and export this lineage-linked data into a strict GEDCOM 7.0.18 format.

### The "Two-Tier" Database Strategy
Following the project's Golden Rules, data is separated into two logical tiers:
1. **Raw DB / Master Vaults**: Read-only SQLite databases containing raw ingested data from CSVs (e.g., `MasterVault_ALL.db`).
2. **Clean DB / Golden Vault**: Writable databases where normalized, merged, and resolved identities reside.

### High-Performance Considerations
- **Concurrency**: Threading (`ThreadPoolExecutor`) is utilized to process multiple CSV files simultaneously.
- **Thread Safety**: SQLite databases strictly use **WAL (Write-Ahead Logging)** mode to prevent database locking and ensure thread-safe writing.
- **In-Memory Analytics**: DuckDB is utilized via the Analyst pipeline (`run_analyst.py`) for high-speed, in-memory cross-database joins and record linkage via Splink.

---

## 2. Core Workflows

### A. Data Ingestion Phase
Raw data is downloaded and imported into the SQLite "Vaults". 
- `download_genealogy_blocks.py`: Connects to external APIs (e.g., Internet Archive) to scout and download structured data files (.csv, .json).
- `DatabaseVault.py`: The heavy-lifter for CSV ingestion. Uses a thread pool to read census CSVs and write them into the SQLite master database (`MasterVault_ALL.db`) in batches of 100,000 records.

### B. Record Linkage & Analysis Phase
- `run_analyst.py`: Primes the DuckDB in-memory engine, attaching the raw census vault, the death index vault, and the clean vault. Normalizes data for Splink (probabilistic record linkage).
- `CreateGoldenRecord.py` / `GoldenRecordGenerator.py`: Uses resolved identities to collapse multiple appearances of a person (e.g., across the 1850, 1860, and 1880 censuses) into a single "Golden Record".
- `identity_registry.py`: Manages the generation and assignment of the immutable "St. Joe's ID" which acts as the primary key for an individual.

### C. Output & Export Phase
- `export_gedcom.py`: Reads the organized households from the database and formats them into a strict GEDCOM 7.0.18 text file. Creates `INDI` (Individual), `FAM` (Family), and `SOUR` (Source) blocks. Converts numeric codes to human-readable text via the JSON Codebook.

---

## 3. Key Utility Modules

### Lookups & Global Context
- `project_globals.py`: A centralized singleton file that loads the JSON Codebook and County Lookup dictionaries into memory once, preventing redundant disk reads.
- `CodebookReader.py` / `codebook_lookup.py`: Interfaces for translating numeric census codes (e.g., `STATEICP=41`) into descriptive text (e.g., `Alabama`).

### Logging & Performance Monitoring
- `gen_logging.py`: A custom logging implementation that ensures log buffers are flushed immediately to disk (`FlushingFileHandler`). It provides a clean, time-only `HH:MM:SS` output for the console, and a highly detailed output for the persistent log files.
- `vault_stats.py`: Captures deep system metrics (RAM, CPU times, Swap, and Disk I/O) before and after thread execution to monitor ingestion performance.
- `debug_database_inspector.py`: A tool to query the SQLite vaults, apply the Codebook translations, and dump a highly readable text report (e.g., searching for the first appearance of a specific surname).

---

## 4. GEDCOM Specifics

- **Standard**: Strictly GEDCOM 7.0.18.
- **Encoding**: UTF-8 without exception.
- **Identifiers**: The project replaces raw composite keys with safe, short `@I1@` format identifiers for GEDCOM objects, utilizing the custom tag `1 REFN [ID]` with `2 TYPE ST_JOES_ID` to store the permanent database key.
- **Citations**: Standard `CENS` (Census) tags are used with `PAGE` parameters containing Microfilm roll, Page, Line, and Sequence numbers, pointing back to a master U.S. Federal Census `SOUR` (Source) record.
