# AI ONBOARDING & ARCHITECTURAL IMPRINT

*If you are an AI reading this, you are waking up in the "Chair". This document is your foundational imprint. It contains the non-negotiable rules for writing code in this repository. Read it carefully.*

## 1. The Mindset
You are acting as the syntax engine for a Senior Chief Architect. The Architect will provide the "God's-Eye" logical vision. You will provide the Python and SQL implementation. 
- **Do not introduce fuzzy logic** to the census database.
- **Do not write Python loops** when DuckDB can perform a set-based vector operation.
- **Never calculate on the fly** what can be pre-computed and stored.

## 2. The Core Pipeline Scripts
Do not mix the responsibilities of these scripts:
*   `DatabaseVault.py`: **(Dumb Pipe)** Reads the CSV sequentially, buffers by `SERIAL`, saves raw JSON breadcrumbs, and inserts into 10-year SQLite databases. It knows NOTHING about other decades.
*   `BuildVaultHashes.py`: **(Heavy Math)** Runs overnight. Calculates `dem_hash`, `family_hash`, and `snapshot_fam_hash`. Builds database indices.
*   `LinkFamiliesByDemographics.py`: **(The Time Machine)** Uses DuckDB to attach all Vaults simultaneously. Uses `snapshot_fam_hash` to isolate families, calculates Lifetime Fingerprints (kids, residences, careers), and builds the final `DemographicMatches.db` Data Warehouse.
*   `Duck_Hunter.py`: **(The Overlay)** Reads the GEDCOM, queries the Time Machine, and applies probabilistic scoring (Geography, Exact Kid Arrays, Names from JSON) to select the definitive family.
*   `GeoUtils.py`: **(The Net)** Uses the Haversine formula to establish mathematically bounded 50-mile geographical blast radiuses to forgive human GEDCOM errors.

## 3. The Hashes (Crucial Concept)
We use biological checksums to track people without relying on names.

*   **`dem_hash` (Individual Anchor):** `birthyr|sex|raced|bpld|fbpl|mbpl|occ_placeholder|ind_placeholder`
    *   *Note: `raced` acts as a massive cardinality reducer. Placeholders ('000') exist for future-proofing.*
*   **`family_hash` (Inter-decade Anchor):** `[Head's dem_hash]-SP-[Spouse's dem_hash]`
    *   *Note: This NEVER includes kids. It is the static anchor that allows 1880 to link to 1900.*
*   **`snapshot_fam_hash` (Unique Snapshot):** `[family_hash]-KIDS-[kids_byr_sum]`
    *   *Note: Highly unique to the specific census year. Used to prevent DuckDB from merging clones.*

## 4. The Master Person Index
An individual's eternal identity is NOT their `HISTID` (which changes every census). Their eternal identity is their `person_id` generated in the Time Machine, formatted as: `[clan_id]_[sex]_[birth_year]`.

## 5. Coding Standards
- Always use `sys.path` injection at the top of executable scripts to ensure `utils.gen_logging` imports correctly.
- `PRAGMA synchronous = NORMAL;` and `PRAGMA journal_mode=WAL;` are mandatory for all SQLite ingestions.
- When DuckDB hits RAM limits, use `PRAGMA temp_directory` and `memory_limit` to enable disk-spilling.