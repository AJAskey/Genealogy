**System Architecture Specification: The Census Truth Project**

**1. Architectural Philosophy: Demographic Truth vs. Nominal Evidence**

The strategic foundation of the \"Census Truth Project\" represents a
paradigm shift from traditional name-based genealogy to a philosophy of
**Demographic Truth**. Conventional genealogy treats identity as a
function of name-strings---a flawed approach given historical
misspelling, anglicization, and the \"Commercial Licensing Wall.\"
Between 1850 and 1870, the IPUMS/Ancestry/FamilySearch partnership
digitized 100% full-count data, but bulk distribution of name-strings is
restricted by corporate business models to protect subscription-based
indices.

Conversely, the 1880 100% file remains public domain due to the
volunteer efforts of the LDS Church and FamilySearch, providing a
high-resolution anchor for the nineteenth century. In this architecture,
names are treated as \"optional decoration\" while variables like
DNA-grade demographic metadata and stable identifiers constitute the
system\'s ground truth. By utilizing IPUMS full-count data (1850--1950),
the system builds an immutable inventory where identity is
mathematically derived through a multi-layered pipeline.

**The Census Truth Core**

  --------------------------------------------------------------------------------
  Component          Traditional Approach  Architectural Reality
  ------------------ --------------------- ---------------------------------------
  **Identity**       Surname-reliant       YEAR + SERIAL + PERNUM composite keys
                     strings               

  **Evidence**       Narrative-first       Demographic metadata (Age, Birthplace,
                     evidence              POPLOC)

  **Stability**      Subjective, variable  Immutable SQLite \"Vault\" persistent
                     records               storage

  **Verification**   Manual transcription  Probabilistic clustering and DNA
                                           persistence
  --------------------------------------------------------------------------------

This shift ensures that the system maintains high resolution even when
traversing the 1850--1870 commercial gap. We are auditing history; the
primary key is the demographic signature, not the alphabetic label.

\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\--

**2. Layer 1: The Ground Truth SQLite Vault**

The ingestion phase adheres to an **ELT (Extract, Load, Transform)**
philosophy. To ensure data integrity, raw data is locked in a two-tier
database architecture. Data is first secured in a persistent SQLite
\"Vault\" (the Raw Database) before any enrichment or matching occurs in
the Clean Database. This prevents matching errors or algorithmic drift
from corrupting the original census evidence.

**Technical Ingestion Requirements**

The ingestion engine manages decade-specific databases ranging from 2GB
to 20GB. The system is optimized for an approximately **8-hour ingestion
window** per full-count dataset, addressing critical data glitches
identified in the source context:

- **Encoding Mismatch:** IPUMS raw data often utilizes a UTF-16 encoding
  that standard UTF-8 readers fail to process, resulting in null
  characters (e.g., Y\\x00E\\x00A\\x00R\\x00). The vault engine
  explicitly normalizes these streams to UTF-8.

- **Delimiter Management:** The engine is strictly configured for
  Tab-separated values (\\t) to prevent the \"single-column collapse\"
  common when parsers default to commas.

**Vault Standards**

1.  **Persistence:** Use of SQLite for persistent, portable storage
    across 100 years of population data.

2.  **Schema Enforcement:** To ensure SQL query consistency, all IPUMS
    headers (e.g., NAMEFRST, NAMELAST) are lowercased upon ingestion.

3.  **Indexing:** The composite_id (Year-Sample-Serial-Pernum) serves as
    the primary key, eliminating duplicate computation and enabling
    high-speed relational queries.

\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\--

**3. Layer 2: Semantic Translation & The Getter Engine**

Once data is secured, the system implements a **Semantic Layer**. This
architecture draws a direct parallel to the **Ada Semantic Interface
Specification (ASIS)**, where the developer queries an internal
knowledge base to translate raw numeric codes into human-readable
narratives. We are not merely reading data; we are querying the
\"compiler\" of historical metadata.

**Radar-Inspired Message Service**

Inspired by the UNAS/TRW philosophy used in aerospace-grade radar
systems, the architecture utilizes auto-generated Python \"getters.\"
These provide an encapsulation layer that separates search logic from
output, allowing the system to \"illuminate\" the demographic map
without manual hardcoding.

**Getter Generation Logic**

The IpumsCodebookParser.py workflow automates the creation of the
semantic interface by ingesting the IPUMS basic.txt codebook:

- **Workflow:** The parser produces JSON lookups and corresponding
  Python modules (e.g., \_get_city.py, \_get_stateicp.py).

- **Compiler-Grade Resilience:** Manual hardcoding is strictly
  forbidden. The system uses f-string templates to generate bulletproof
  functions. These functions must utilize str(code).strip() to mitigate
  mapping failures between integer inputs and string-based JSON keys
  (e.g., ensuring code \"01\" maps correctly to its descriptive label).

- **Efficiency:** Each getter is a cache-efficient O(1) lookup,
  preparing the data for high-performance memory objects.

\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\--

**4. High-Performance Execution: Memory Management & OOP Strategy**

Processing 100GB+ datasets is an exercise in resource constraint.
Standard Python dictionaries are an \"architectural trap\" for
million-record arrays due to their massive memory overhead. This system
prioritizes memory efficiency as the primary metric for success.

**The High-Performance Toolkit**

- **\_\_slots\_\_ Optimization:** All record-level classes (e.g.,
  IndividualRecord) utilize \_\_slots\_\_. By locking down class
  attributes, the system specifically **suppresses the creation of the
  hidden \_\_dict\_\_** for every object. This slashes memory overhead
  by 50%, allowing millions of records to reside in RAM for graph
  traversal.

- **Generators (yield):** The engine employs the \"Bulldozer\" method.
  By streaming data line-by-line via Python generators, the system
  maintains **near-zero RAM usage** regardless of whether the file
  contains 50,000 or 50 million records.

- **Vectorized Operations:** While individual objects manage complex
  logic, the architecture leverages columnar memory (Apache
  Arrow/Polars) for massive concatenations and multi-record derived
  field generation.

\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\--

**5. Record Linkage: Missile-Tracking & Cluster Philosophy**

Linking individuals across census decades utilizes **Family Orbit**
logic. This compares genealogical record linkage to tracking missile
debris clusters in radar software: identifying separate \"tracks\"
(individual census records) that belong to a single \"parent object\"
(the biological family unit).

**Probabilistic Clustering Algorithm**

The system utilizes a scoring logic based on demographic
\"trajectories\" to bridge the commercial gap of 1850--1870:

- **Primary Anchors:** SERIAL (Household ID) and HISTID (Historical
  Identifier) lock the initial cluster.

- **Trajectory Variables:** Matches are weighted based on Age
  progression (+/- 2-year tolerance), Birthplace constraints (BPL), and
  proximity pointers (POPLOC/MOMLOC).

- **Bi-Directional Linking:** In keeping with robust graph architecture,
  the \"Family Orbit\" must be bi-directional. Individual records must
  point to the Family ID, and Family records must contain pointers back
  to all component Individuals (Husband, Wife, Children).

**The St. Joe's ID (Surrogate Key)**

A **Surrogate Key**, known as the \"St. Joe's ID,\" tracks lineages
across 10-year intervals. This allows the system to logically infer the
identity of an unnamed individual in 1860 by matching their demographic
signature to a named individual in the 1880 public domain flagship year.

\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\--

**6. External Integration: GEDCOM Serialization & \"Tomorrow Today\"**

The ultimate goal of the Census Truth Project is bi-directional linking:
maintaining local ground truth while exporting validated data to
external platforms like Ancestry.

**Minimum Viable GEDCOM Mapping**

To ensure compatibility with industry standards, the IndividualRecord
and FamilyRecord classes map to specific GEDCOM tags. Note that in
GEDCOM architecture, the CHIL tag must point to the unique alphanumeric
fingerprint of the individual (person_id), not the sequential household
number.

  ------------------------------------------------------------------------
  GEDCOM Tag   Source          Purpose
               Attribute       
  ------------ --------------- -------------------------------------------
  **INDI**     person_id       Unique alphanumeric fingerprint for an
                               individual.

  **FAM**      family_id       Container of pointers linking INDI records.

  **HUSB /     poploc / momloc Relational pointers for parents.
  WIFE**                       

  **CHIL**     person_id       Pointers for children within a family unit.

  **SOUR**     year / sample   Attribution to the IPUMS census ground
                               truth.
  ------------------------------------------------------------------------

**The Night Shift Pipeline**

The architecture employs an LLM as a \"rendering engine.\" During a
\"Night Shift\" batch process, the system pulls structured facts (JSON)
and transforms them into human-readable biographies and citation-heavy
PDFs. This replaces generic commercial templates with historically
contextualized narratives.

This system follows a **\"Bring Your Own Data\" (BYOD)** philosophy,
ensuring 100% licensing compliance. The GitHub/AJAskey/Genealogy
repository provides the processing engine; the user provides the raw
IPUMS data. This vision transforms raw demographic snapshots into an
indisputable, open-source inventory of human history.
