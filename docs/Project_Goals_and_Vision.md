# Project Goals & Architectural Vision

*This document serves as the "North Star" for the IPUMS Census Time Machine project. All scripts, database schemas, and data engineering decisions should ultimately drive toward these core capabilities.*

---

## Goal 1: The "Holy Grail" Multi-Generational Query (Instant Tree Traversal)
**The Vision:** 
We must be able to query the database for a single ancestor (e.g., "William Francis") and instantaneously retrieve their *entire* multi-generational family tree—including all descendants, spouses, and linked generations across all census decades. 

**The Constraint:**
This retrieval must take a fraction of a second. The database must **never** use recursive loops ("pointer, pointer") or calculate family tree traversal on the fly during a search.

**The Implementation (The Closure Table):**
The heavy lifting required to map out these multi-generational trees must be executed **offline, overnight, during the Demographics Link build phase.** This is a non-negotiable rule.
The builder script will traverse the tree, calculate all the ancestral and descendant linkages, and write them into a static, flat "Lineage Map" (Closure Table) in the Demographics Database. When the user queries the database, it simply performs a lightning-fast lookup against this pre-calculated map.

## Goal 2: Absolute Separation of Processing and Storage
**The Vision:**
The final Demographics Database is a purely static, "God-like" snapshot of eternal truths. It does not think; it only knows.

**The Constraint:**
If a data point can be derived, summed, or calculated (like a Kid Fingerprint, a county trajectory, or a generational linkage), it must be calculated by Python *before* it enters the final database.

**The Implementation:**
We rely on "Compute Once, Read Many." Complex algorithms, fuzzy matching, and deep cross-referencing are isolated to the overnight build scripts. The final database schema is kept brutally simple and heavily indexed for read speed.

---