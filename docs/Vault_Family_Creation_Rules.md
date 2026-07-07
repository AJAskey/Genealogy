# Vault Family Creation Rules (The Extraction Phase)

## 1. The Core Philosophy: Immutable Snapshots
The SQLite Vaults (`YearVault_1850.db`, `YearVault_1860.db`, etc.) represent the raw Extract & Load phase of the pipeline. 
* **NO UPDATES:** Families in the vaults are strictly 10-year snapshots. When a new census year is ingested, it creates brand new family records in that year's specific vault. We **never** update an 1880 family with 1900 data during this phase. 
* **NO LINKING:** The vault ingestion script (`DatabaseVault.py`) does not know about previous or future decades. Inter-generational linking is reserved entirely for the DuckDB Time Machine.

## 2. The Sequential Buffer (How we group them)
The IPUMS U.S. Census CSV provides data row-by-row for individuals. 
* We read the CSV sequentially.
* We group individuals together by monitoring the `SERIAL` column (which IPUMS uses to designate a unique household in a specific census year).
* When the `SERIAL` number changes, the Python script flushes the previous household buffer and calculates the family metrics.

## 3. The Family Mathematical Rules
For every household buffer (a group of individuals sharing a `SERIAL`), we evaluate the raw data to extract the core Family Record using the following rules:

### A. The Primary Key (`family_id`)
Every family receives a unique, deterministic ID string for that specific census year.
* **Format:** `{YEAR}_{SERIAL}` (e.g., `1880_1234567`)
* *Note: "Lone Wolves" (people living entirely alone or in group quarters without family) are handled conditionally, but true families are keyed by the Serial.*

### B. Extracting the "Dual-Key" Parents
To establish the biological anchors for the family, we must find the parents.
* **The Head (`head_histid`):** We scan the buffer for the individual whose IPUMS relationship code (`RELATE`) indicates they are the Head of Household. We extract their universal `HISTID` and their birthplace (`BPLD`).
* **The Spouse (`spouse_histid`):** We scan the buffer for the individual whose relationship code indicates they are the Spouse of the Head. We extract their `HISTID` and birthplace.
* *Rule:* A family can exist with just a Head (single parent), but the Head is the primary anchor.

### C. The Kids' Fingerprint (`kids_byr_sum`)
This is the most critical metric for the downstream Time Machine.
* We scan the buffer for any individuals identified as children (either via the `RELATE` code, or by checking if their `POPLOC`/`MOMLOC` pointer columns match the Head/Spouse).
* We count the total number of children (`num_kids`).
* We calculate the **Sum of the Kids' Birth Years** (`kids_byr_sum`). 
* *Example:* If the kids were born in 1880, 1882, and 1885, the `kids_byr_sum` is `5647`. This provides a highly unique mathematical fingerprint for the family snapshot without relying on names.

### D. Geographic Anchors
* We extract the `STATEICP` and `COUNTYICP` codes from the household to establish where this specific snapshot occurred.

## 4. The Final Database Insertion
Once the buffer is evaluated, exactly **ONE** row is inserted into the `families` table of that decade's SQLite Vault.

**Schema of the `families` table:**
* `family_id` (TEXT, Primary Key)
* `year` (TEXT)
* `serial` (INTEGER)
* `head_histid` (TEXT)
* `spouse_histid` (TEXT)
* `head_bpld` (TEXT)
* `spouse_bpld` (TEXT)
* `num_kids` (INTEGER)
* `kids_byr_sum` (INTEGER)
* `stateicp` (TEXT)
* `countyicp` (TEXT)

## 5. What happens to the Individuals?
While the single `families` row is written, all of the actual people inside that buffer are written to the `individuals` table. 
* Every individual is stamped with the `family_id` (Foreign Key) so they are permanently tied to the household snapshot.
* The individuals retain their full raw JSON breadcrumbs (names, occupations, etc.) so that the eventual GEDCOM search engine can verify their identities.