# Genealogy Core Scripts Summary

This document summarizes the three main working scripts in the genealogy pipeline:

1. `python/DatabaseVault.py`
2. `python/LinkFamiliesByDemographics.py`
3. `python/GedcomNameOverlay_V2.py`

It explains what each script does, how they fit together, and the current phase of the workflow.

---

## 1. `python/DatabaseVault.py`

**Purpose**
- Ingest raw IPUMS census CSV files into SQLite databases.
- Create decade-specific `YearVault` databases containing `families` and `individuals` tables.
- Preserve the original row data by storing each raw CSV row as JSON in `individuals.raw_data`.

**What it does**
- Reads CSV data sequentially and buffers rows by `SERIAL` so each household is processed as a unit.
- Uses `HISTID` for individual identity and generates a `family_id` for household family units.
- Resolves parent pointers using `POPLOC` and `MOMLOC` when possible.
- Filters rows by `HHTYPE`, `RELATE`, and `RELATED` values to focus on family households.
- Creates a family record only when a household has multiple members; single-person households are kept as individuals with `family_id = NULL`.
- Writes data into `YearVault_YYYY.db` files using SQLite WAL mode and batch commits for speed.

**Current state and intent**
- A working ingestion utility rather than a polished production loader.
- Contains test-mode fallbacks and hard-coded paths for current experimentation.
- Lives as the foundation for census truth and later matching steps.

**Project role**
- The source-of-truth ingestion stage.
- Produces the normalized census vaults used by the matching and overlay scripts.

**Notes**
- The script may use test-specific fallbacks for missing fields.
- Sample mode behavior currently skips records missing names in the test dataset.

---

## 2. `python/LinkFamiliesByDemographics.py`

**Purpose**
- Link census families across decades using demographic characteristics.
- Build the Time Machine graph of multi-decade family timelines called clans.
- Store the results in `DemographicMatches.db` with `household_links` and `clan_mapping`.

**What it does**
- Uses DuckDB to attach the decade vault SQLite databases and perform analytic joins.
- Extracts a compact demographic fingerprint for each family.
- Creates an in-memory `hh_features` table with the key fields used for matches.
- Groups families into "Demographic Profiles" mathematically to completely bypass Cartesian explosion death-spirals, allowing massive 20th-century populations to be matched in seconds.
- Compares these profiles across 10, 20, and 30 year gaps, including a 1890 bridge strategy.
- Applies a Highlander 1-to-1 filter: mathematically multiplying profile counts so only unambiguous 1-to-1 links are accepted.
- Writes confirmed links to `household_links` and stores completed chunks in `completed_chunks`.
- Builds connected components from confirmed links and applies a Highlander uniqueness check per clan.
- Stores final clan assignments in `clan_mapping`.

**Current state and intent**
- The core demographic linking engine for phase one.
- Designed to prioritize precision over recall.
- Highly optimized to scale through the massive population booms of the 1900s without disk thrashing.
- Does not apply names; it builds the census timeline structure.

**Project role**
- The census-to-census linkage stage.
- Produces the persistent family graph that supports later GEDCOM overlay.

**Notes**
- Includes resume logic for long-running matching work.
- Intentionally strict to avoid ambiguous links.

---

## 3. `python/GedcomNameOverlay_V2.py`

**Purpose**
- Find high-confidence GEDCOM couples that can be safely overlaid on census families.
- Validate overlay matches before names are applied.
- Provide conservative candidate matching rather than automatic name assignment.

**What it does**
- Loads GEDCOM couple anchor data from `gedcom_sources/gedcom_couples.json`.
- Converts GEDCOM birthplace text into IPUMS birthplace codes for husband, wife, and parents.
- Filters out GEDCOM couples missing the required demographic fingerprint.
- Builds a DuckDB `targets` table of high-quality anchor couples.
- Attaches census vault databases and uses a strict "Dead Weight" filter to drop millions of irrelevant/unmarried records from RAM before matching.
- Selects census families where the husband and wife match GEDCOM anchors on birth year and birthplace.
- Optionally validates kid counts and kid birth-year fingerprints.
- Applies a Geographic Tie-Breaker (Soft Scoring) using dynamically calculated family "Homeland" counties.
- Joins census families to `match_db.clan_mapping` for clan context.
- Logs candidate matches for manual review.

**Current state and intent**
- An analysis and validation step, not the final name-write stage.
- Focused on confirming matches before overlay application.
- Conservative by design to avoid false positives.

**Project role**
- The GEDCOM overlay validation stage.
- Bridges the census clan graph and genealogical name/fact data.

**Notes**
- Uses temporary `sys.path` injection for project imports, which is a development convenience.
- Designed to avoid wrong name assignments by favoring certainty.
- Can disable kid matching when the current IPUMS sample lacks reliable kid fingerprint data.

---

## How they fit together

1. `DatabaseVault.py` builds the raw census database vaults.
2. `LinkFamiliesByDemographics.py` links census families across decades and builds clans.
3. `GedcomNameOverlay_V2.py` validates GEDCOM matches against the census-derived clan graph.

In short:
- Stage 1: Ingest census truth.
- Stage 2: Link census families over time.
- Stage 3: Validate GEDCOM overlay matches.

## Current phase insight

The current workflow is a verification-first phase:
- Census data is treated as the authoritative truth.
- The demographic linking engine is tuned for precision.
- GEDCOM overlay is being used for conservative review rather than automatic labeling.

This matches the current project goal: find the right matches first, then lay names onto those matches.
