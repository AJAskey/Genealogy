# Project Goals and Vision: The "God's-Eye" Demographics Time Machine

## The Core Mission
To build a flawlessly accurate, longitudinal map of the United States population from 1850 to 1930 using raw census data, and to intelligently map messy, human-generated GEDCOM family trees onto that mathematical foundation.

## The Grand Paradigm: Separation of Concerns
The fundamental rule of this project is the strict separation between **Historical Truth** and **Human Memory**.

### 1. The Census Foundation (100% Deterministic)
The U.S. Census data provided by IPUMS is treated as absolute, unalterable truth. In the database architecture:
- **No Names:** First and last names change, are misspelled, or get mangled. They are strictly ignored during the record linkage phase.
- **No Guesswork:** We do not use fuzzy logic, probability, or scoring to link census records across decades.
- **Pure Biology:** Records are linked using only eternally static biological anchors: Birth Year, Sex, Race, Birthplace, Father's Birthplace, and Mother's Birthplace.
- **The God's-Eye View:** Because we are processing static history, we don't guess the future. We sweep the entire 80-year dataset simultaneously to compile perfect "Lifetime Fingerprints" for every family.

### 2. The GEDCOM Overlay (Probabilistic)
GEDCOM files represent human memory. Human memory is flawed, full of typos, and highly probabilistic (the "Crazy Grandma" effect). 
- **Manicured Fuzz:** We apply probabilistic scoring *only* when mapping GEDCOMs to the deterministic census foundation.
- **Mathematical Bounding:** We do not let the search engine guess wildly. We bind fuzzy logic using hard math—such as applying the Haversine formula to draw a strict 50-mile geographical "blast radius" around a guessed county.

## The Master Architecture (ELT Pipeline)
We have abandoned monolithic ETL scripts in favor of a modular Extract, Load, Transform (ELT) architecture.

1. **Extract & Load (Daytime):** `DatabaseVault.py` sequential-reads 150GB of IPUMS CSVs at blistering speeds (1.2M rows/min), buffering households by `SERIAL` and writing them to 10-year SQLite snapshot vaults.
2. **Transform (Overnight):** `BuildVaultHashes.py` sweeps the vaults to calculate deep, deterministic index hashes (`dem_hash`, `family_hash`, and `snapshot_fam_hash`).
3. **The Time Machine:** `LinkFamiliesByDemographics.py` utilizes DuckDB's vectorized set-math to smash the decades together, completely bypassing imperative Python loops to instantly build the inter-generational `DemographicMatches.db` Warehouse.

## The Fail-Safes
* **Do Not Guess:** If the deterministic pipeline finds identical clones that cannot be separated by geography, exact kid-spacing arrays, or historical occupation trails, **the target is dropped**. A false negative is acceptable; a false positive (introducing clones into the base tree) is a fatal error.
* **Preserve the Raw Data:** All IPUMS rows are JSON-serialized into a `raw_data` column. No data is ever truly lost, ensuring the "Bread Crumbs" are always available for the GEDCOM overlay engine.