# IPUMS Census Time Machine: Database Schema & Architecture

## 1. High-Level Architecture
The database architecture is split into two distinct tiers:
1. **The Yearly Vaults (SQLite):** `YearVault_1850.db` through `YearVault_1940.db`. These are read-only, long-term storage vaults containing the raw CSV data downloaded directly from IPUMS.
2. **The Time Machine (DuckDB):** `DemographicMatches2.db`. This is the high-speed analytical database where relevant families are consolidated, resolved, and prepared for GEDCOM export.

---

## 2. Core Tables (The Time-Bound Census Data)
These tables exist in the SQLite Yearly Vaults (as `families` and `individuals`) and are mirrored in the DuckDB Time Machine (as `tm_families` and `tm_individuals`) to hold the raw historical snapshots.

### Table: `families` / `tm_families`
Represents a single household snapshot recorded by the enumerator.

* **`family_id`** *(VARCHAR)*: **[PRIMARY KEY]** A unique identifier for the household snapshot (e.g., `"1880_123456"`).
* **`head_histid`** *(VARCHAR)*: **[FOREIGN KEY]** Links to `individuals.histid`. Identifies the Head of Household.
* **`spouse_histid`** *(VARCHAR)*: **[FOREIGN KEY]** Links to `individuals.histid`. Identifies the Spouse (can be NULL).
* **`year`** *(INTEGER)*: The census year (e.g., 1880). This provides the time-context for the raw census database.
* **`stateicp`** *(INTEGER)*: The IPUMS state code (e.g., 14 for Pennsylvania).
* **`countyicp`** *(INTEGER)*: The IPUMS county code.
* **`kids_byr_sum`** *(INTEGER)*: A mathematical "fingerprint" representing the sum of the birth years of all children in the household. Used to match families uniquely.
* *(Note: Includes other geographical/demographic metadata from IPUMS).*

### Table: `individuals` / `tm_individuals`
Represents a single person.

* **`histid`** *(VARCHAR)*: **[PRIMARY KEY]** The globally unique IPUMS historical identifier for this exact person's record.
* **`family_id`** *(VARCHAR)*: **[FOREIGN KEY]** Links to `families.family_id`. This is how children and relatives are tied to a specific household.
* **`first_name`** *(VARCHAR)*: The person's given name (often blanked or scrambled in our dataset).
* **`last_name`** *(VARCHAR)*: The person's surname (often blanked or scrambled).
* **`sex`** *(VARCHAR)*: '1' for Male, '2' for Female.
* **`birthyr`** *(INTEGER)*: Calculated birth year.
* **`bpld`** *(INTEGER)*: Birthplace code (e.g., 4200 for Pennsylvania).
* **`fbpl`** *(INTEGER)*: Father's birthplace code.
* **`mbpl`** *(INTEGER)*: Mother's birthplace code.

---

## 3. How Data is "Knitted" Together

### A. Knitting a Single Household
A family is constructed using the `family_id`. 
1. The `families` table defines the physical household.
2. The `families.head_histid` and `families.spouse_histid` point directly to the parents in the `individuals` table.
3. Any other record in the `individuals` table that shares that exact `family_id` (but is NOT the head or spouse) is treated as a child or dependent living in that household.

### B. Entity Resolution (The "God's Eye View")
**Architectural Philosophy:** *We are not God. We don't know how everything works, but we accept the way it is. The concept of a flowing time is not part of our demographic database.*
*Furthermore, timeless facts (like a family's lifetime kid fingerprint) are pre-calculated once and stored permanently. We compute offline during the build phase, never on the fly during search.*
*Finally, demographic connections between static datasets must be absolute. We rely on exact, 1-to-1 strict matching without fuzzy logic or shifting windows. If the static data is true, it will align perfectly.*
*The eternal family unit is defined by a "Dual-Key Lock": The Head's static demographics AND the Spouse's static demographics (birth years and birthplaces) must both match perfectly. We do not search for isolated individuals; we search for the completed, eternal partnership.*

The Demographics Database operates at a higher, timeless level. While the raw Census databases below it are fundamentally time-bound, the final demographics resolution strips away the clocks and calendars. 

To build this higher-level demographics database, the pipeline code must "knit across the decades" to link fragmented historical records together. The final answer stored here is a static, eternal truth.

Because raw IPUMS data is fragmented across different source vaults, a single eternal person might be represented by multiple different `histid`s. We must collapse these fragmented records into a single, unified entity.

This is handled by our Resolution tables:

#### Table: `resolved_vips`
This table acts as the "Rosetta Stone," linking blank database records to real-world Ancestry tree targets.

* **`histid`** *(VARCHAR)*: **[PRIMARY/FOREIGN KEY]** Links to `tm_individuals.histid`.
* **`target_idx`** *(INTEGER)*: The index ID of the real couple from our `gedcom_couples.json` file.
* **`role`** *(VARCHAR)*: 'H' (Husband) or 'W' (Wife).
* **`first_name`** *(VARCHAR)*: The resolved, real-world given name (e.g., "Foster Edgar").
* **`last_name`** *(VARCHAR)*: The resolved, real-world surname (e.g., "Askey").
* **`lifetime_kid_fingerprint`** *(INTEGER)*: The pre-calculated, eternal sum of all kids' birth years for this family. Stored at the demographics level so it never has to be recalculated.

**How Entity Resolution Works:**
If `histid` "A" and `histid` "B" are both mapped to `target_idx` 15 in the `resolved_vips` table, the GEDCOM Exporter collapses them into a **single person** in the final family tree. The `target_idx` acts as the eternal primary key for human entities.

#### Table: `clan_mapping` (Deprecated/Background)
* **`clan_id`** *(INTEGER)*: An arbitrary group ID.
* **`family_id`** *(VARCHAR)*: Links to `tm_families.family_id`.
* *Note: Originally used to group identical demographic clones. Largely superseded by the precise `resolved_vips` targeting logic for core family lines, but still used by the exporter to generate realistic background populations (synthetic neighbors).*

#### Table: `manual_links`
* **`histid_1`** *(VARCHAR)*: The child ID.
* **`histid_2`** *(VARCHAR)*: The adult ID.
* *Note: Used to explicitly force the exporter to merge two records into a single entity if the demographics drifted too far for automated matching.*

---

## 4. The Data Pipeline Flow
1. **`gedcom_analysis.py`**: Parses real Ancestry data into a JSON Target list.
2. **`LinkFamiliesByDemographics.py`**: Reads the JSON, queries the 10 SQLite Vaults, and extracts only the households matching the target demographics into the `DemographicMatches2.db` DuckDB file.
3. **`GedcomNameOverlay_V3_FINAL.py`**: Evaluates the extracted candidates, checks their geographical county migration trajectories, and writes the proven 1-to-1 matches into the `resolved_vips` table.
4. **`ExportCensusToGedcom.py`**: Reads the Time Machine (`tm_families`, `tm_individuals`, `resolved_vips`), applies the real names, pads the remaining tree with synthetic placeholders, and generates the final `.ged` file.