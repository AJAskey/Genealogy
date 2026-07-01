# Database Schema Dictionary

## Layer 1: The Data Lake (Yearly SQLite Vaults)
*Files: `YearVault_1850.db`, `YearVault_1860.db`, etc.*

### Table: `individuals`
- `histid` (TEXT, PK): IPUMS universal ID. Changes every decade.
- `first_name`, `last_name` (TEXT): Kept only for the JSON/GEDCOM phase.
- `sex`, `birthyr`, `birthmo`, `marrnoyrs` (TEXT/INT): Raw demographics.
- `bpld`, `fbpl`, `mbpl` (TEXT): Detailed birthplaces.
- `father_histid`, `mother_histid` (TEXT): Calculated from POPLOC/MOMLOC pointers.
- `family_id` (TEXT, FK): Formatted as `{year}_{serial}_{famunit}`. NULL for "lone wolves".
- `related`, `marst`, `raced` (TEXT): Relationship, Marital Status, and Detailed Race (e.g., 100 for White).
- `stateicp`, `countyicp` (TEXT): Physical location for the census snapshot.
- `occ1950`, `ind1950` (TEXT): Historical occupation and industry tracking codes.
- `raw_data` (TEXT): Complete JSON dump of the CSV row. ("The Breadcrumbs").

### Table: `families`
- `family_id` (TEXT, PK): Primary Key.
- `year`, `serial`, `famunit` (TEXT/INT): IPUMS hierarchical locators.
- `head_histid`, `spouse_histid` (TEXT): Extracted for high-speed indexing.
- `head_bpld`, `spouse_bpld` (TEXT): Birthplaces of the "Dual-Key" parents.
- `num_kids`, `kids_byr_sum` (INT): Snapshot counts used for tie-breaking.
- `stateicp`, `countyicp` (TEXT): Location of the household.

### Table: `computed_ind_hashes` & `computed_fam_hashes`
*Built overnight by `BuildVaultHashes.py`*
- `dem_hash`: `birthyr|sex|raced|bpld|fbpl|mbpl|000|000`
- `family_hash`: `[head_hash]-SP-[spouse_hash]`
- `snapshot_fam_hash`: `[family_hash]-KIDS-[kids_byr_sum]`

---

## Layer 2: The Data Warehouse (DuckDB Time Machine)
*File: `DemographicMatches.db` (Compiled from the SQLite Vaults)*

### Table: `tm_individuals` & `tm_families`
- A massively stripped-down, lean version of the vault tables containing ONLY the data needed for inter-decade tracking (histid, family_id, sex, byr_int, stateicp, countyicp).
- Contains the `person_id` pointer (`[clan_id]_[sex]_[birth_year]`).

### Table: `clan_mapping`
- `clan_id` (INT): A Dense-Ranked integer assigned mathematically by grouping `snapshot_fam_hash` to isolate clones.

### Table: `clan_details` (The God's-Eye View)
- `clan_id` (INT)
- `snapshot_fam_hash` (TEXT)
- `lifetime_kfp` (INT): The ultimate sum of ALL children's birth years across all decades.
- `lifetime_kid_list` (TEXT): e.g., `1885,1887,1890`
- `lifetime_residence_list` (TEXT): e.g., `1880:42_027, 1900:42_033`
- `lifetime_occ_trail` & `lifetime_ind_trail`: (Upcoming) Chronological career maps.

### Table: `person_trajectories` (The Master Person Index)
- `person_id` (TEXT, PK): Eternal individual ID (`[clan_id]_[sex]_[birthyr]`).
- `histid_trail` (TEXT): Map to all raw snapshot data, e.g., `1880:12345, 1900:67890`.