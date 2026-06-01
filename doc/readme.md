# Detailed Outline: The Analyst Pipeline

This document details the mechanics of the two core AI scripts executing Phase 2: `run_analyst.py` and `CreateGoldenRecord.py`.

## Part 1: Engine Initialization (`run_analyst.py`)
1.  **DuckDB Core Startup:** Connects to an in-memory analytical engine.
2.  **Safety Limits:** Applies `PRAGMA memory_limit='90GB';` to ensure the OS never blue-screens. Offloads excess to NVMe temp storage.
3.  **Cross-Vault Attachment:** Uses SQLite Scanner extensions to simultaneously attach `MasterVault_ALL.db`, `DeathIndexVault.db`, and `CleanVault.db` without loading them entirely into memory.

## Part 2: Data Extraction & Pre-Filtering
1.  **State Targeting:** Limits scope to a target variable (`STATE_FILTER = "Alabama"`).
2.  **BIRLS Pre-Filtering:** Creates a temporary table of surnames found in the Alabama census and strictly limits the 15-million-row Death Index to those specific names.
3.  **Union View:** Combines the extracted Census and BIRLS records into a single, standardized DuckDB view (`population_for_splink`).

## Part 3: Splink Configuration (`CreateGoldenRecord.py`)
1.  **Linker Instantiation:** Connects the DuckDB backend to Splink 4 via `DuckDBAPI`.
2.  **Comparison Algorithms:**
    *   `LevenshteinAtThresholds` on first names (catches typos like John vs Jhon).
    *   `JaroWinklerAtThresholds` on last names (handles phonetic drift).
    *   `ExactMatch` on State and Birth Year.
3.  **Blocking Rules:** Prevents a Cartesian explosion by only calculating pairwise math for:
    *   Exact First/Last name matches.
    *   Exact Last Name/Birth Year matches (catches 1st name abbreviations).
    *   Exact First Name/Birth Year matches (catches last name typos).

## Part 4: Training & Execution
1.  **Expectation-Maximisation (EM):** Unsupervised training over multiple iterations to determine the statistical likelihood of names occurring randomly (e.g., "John Smith" vs "Ezekiel Askey").
2.  **Pairwise Prediction:** Calculates 0.0 to 1.0 confidence scores for every blocked pair.
3.  **Graph Clustering:** Resolves transitively linked pairs (A=B, B=C, therefore A=C) into stable `cluster_ids`.

## Part 5: Survivorship & Writing
1.  **Data Extraction:** Pulls the resolved clusters down to Pandas for processing.
2.  **Name Selection:** Uses statistical mode (`value_counts`) to select the most common spelling of a person's name across decades.
3.  **Date Selection:** Resolves date-of-birth drift by using the median birth year minus extreme outliers. If available, uses BIRLS exact dates for death data.
4.  **Vault Committing:** Writes the unified identity back to `CleanVault.db` while appending the `vault_pointers` field to ensure a permanent paper trail back to the raw source rows.