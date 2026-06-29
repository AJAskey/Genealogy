# Demographics Database Architecture & Schema

---

## 1. Architectural Philosophy (The "God's Eye View")

* **We are not God. We don't know how everything works, but we accept the way it is. The concept of a flowing time is
  not part of our demographic database.**
* **Compute Once, Read Many:** Timeless facts (like a family's lifetime kid fingerprint) are pre-calculated once and
  stored permanently. We compute offline during the build phase, never on the fly during search.
* **Exact, Strict Matching:** Demographic connections between static datasets must be absolute. We rely on exact, 1-to-1
  strict matching without fuzzy logic or shifting windows. If the static data is true, it will align perfectly.
* **The Dual-Key Lock:** The eternal family unit is defined by a "Dual-Key Lock": The Head's static demographics AND the
  Spouse's static demographics (birth years and birthplaces) must both match perfectly. We do not search for isolated
  individuals; we search for the completed, eternal partnership.
* **Synthesized Events are Mutable Inferences:** Because census data lacks explicit events (like birth counties or exact
  death dates), we synthesize them from snapshots. However, these inferred events are written in pencil, not stone. They
  act as placeholders and must be overwritten whenever a higher-confidence source (such as a human-verified GEDCOM
  event) provides a better answer.

---

## 2. Core Tables (The Time-Bound Census Data)

These tables exist in the SQLite Yearly Vaults (as `families` and `individuals`) and are mirrored in the DuckDB Time
Machine (as `tm_families` and `tm_individuals`) to hold the raw historical snapshots.

### Table: `families` / `tm_families`

Represents a single household snapshot recorded by the enumerator.

* **`family_id`** *(VARCHAR)*: **[PRIMARY KEY]** A unique identifier for the household snapshot (e.g., `"1880_123456"`).
* **`head_histid`** *(VARCHAR)*: **[FOREIGN KEY]** Links to `individuals.histid`. Identifies the Head of Household.
* **`spouse_histid`** *(VARCHAR)*: **[FOREIGN KEY]** Links to `individuals.histid`. Identifies the Spouse (can be NULL).
* **`year`** *(INTEGER)*: The census year (e.g., 1880). This provides the time-context for the raw census database.
* **`stateicp`** *(INTEGER)*: The IPUMS state code (e.g., 14 for Pennsylvania).
* **`countyicp`** *(INTEGER)*: The IPUMS county code.
* **`kids_byr_sum`** *(INTEGER)*: A point-in-time mathematical fingerprint of the children physically present in the
  household snapshot.

### Table: `individuals` / `tm_individuals`

Represents a single person snapshot.

* **`histid`** *(VARCHAR)*: **[PRIMARY KEY]** The globally unique IPUMS historical identifier for this exact person's
  record.
* **`family_id`** *(VARCHAR)*: **[FOREIGN KEY]** Links to `families.family_id`. This is how children and relatives are
  tied to a specific household snapshot.
* **`byr_int`**, **`bpl_int`**, **`fbpl_int`**, **`mbpl_int`** *(INTEGER)*: Pre-calculated integer conversions for
  high-speed matching.

---

## 3. Entity Resolution (The Timeless Demographics Database)

The Demographics Database operates at a higher, timeless level. While the raw Census databases below it are
fundamentally time-bound, the final demographics resolution strips away the clocks and calendars.

To build this higher-level demographics database, the pipeline code must "knit across the decades" to link fragmented
historical records together. The final answer stored here is a static, eternal truth.

### Table: `resolved_vips`

This table acts as the "Rosetta Stone," linking raw database records to real-world Ancestry tree targets.

* **`target_idx`** *(INTEGER)*: **[PRIMARY KEY]** The unique ID mapping back to your GEDCOM/JSON target list.
* **`histid`** *(VARCHAR)*: The raw IPUMS historical ID.
* **`role`** *(VARCHAR)*: 'H' (Husband) or 'W' (Wife).
* **`first_name`** *(VARCHAR)*: The resolved, real-world given name.
* **`last_name`** *(VARCHAR)*: The resolved, real-world surname.

### Table: `clan_details` (The Eternal Family Facts)

* **`clan_id`** *(INTEGER)*: The eternal family grouping ID.
* **`lifetime_kfp`** *(INTEGER)*: The pre-calculated, eternal sum of all kids' birth years for this family. Stored at
  the demographics level so it never has to be recalculated.
* **`inferred_birth_state_icp`** *(INTEGER)*: Synthesized from the first known census snapshot for this individual.
* **`inferred_birth_county_icp`** *(INTEGER)*: Synthesized from the first known census snapshot for this individual.
* **`death_year`** *(INTEGER)*: The static, finalized year of death. Added as an eternal attribute so the GEDCOM builder
  can simply read and write the `DEAT` event without runtime calculation.
* **`death_state_icp`** *(INTEGER)*: The state where the death occurred (if known).

---

## 4. How Data is "Knitted" Together

### A. The Human Perspective vs. Database Links (No Pointers!)

In traditional programming (C/Java), a family tree is a linked list of memory pointers. A family points to a father, a
mother, and an array of children.

In a relational database, **there are no pointers**. Instead, we use shared IDs (Foreign Keys) to knit people together.

* **The Hub:** The `families` table acts as the central hub.
* **Parent Links:** The `families` table holds the `head_histid` and `spouse_histid`. This tells the database exactly
  which two records in the `individuals` table are the parents.
* **Child Links:** The `families` table *does not* hold a list of children. Instead, the children in the `individuals`
  table hold the `family_id`.

To gather a complete family efficiently, we do not use `for` loops. We ask the database to `JOIN` the tables together
where the IDs match, returning the entire nuclear family in a single operation.

**Inter-Generational Linking:**
How does a child in one family become a parent in another?
If IPUMS record `12345` is a child in Family A, their `individuals` row has Family A's `family_id`. When that child
grows up and gets married to form Family B, the `families` table for Family B will simply list `12345` as the
`head_histid`. The exact same person acts as a child hub in one direction and a parent hub in another.