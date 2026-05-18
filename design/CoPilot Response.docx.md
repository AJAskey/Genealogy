Thanks for the detailed update — you’ve already made several strong architectural moves (SERIAL as a stable household key, and the Raw/Clean separation). Below is concrete guidance on the **design dilemma**, **performance/memory**, and **concurrency** questions, with an implementation approach that fits your current state (DB Browser/SQLite-style workflow) while keeping the door open to scaling.

**Note:** I searched your M365 file repository for internal docs/code related to *IPUMS / GEDCOM / entity resolution / Origin ID / two-tier DB*, but didn’t find any matching files to ground this in your org’s existing materials. So the recommendations below are **general engineering best practices** tailored to the pipeline you described.

---

**1\) Where should the family-link processing run? (Option A vs Option B)**

**Short answer: Option B (Post-Ingest) is the better default**

Because your matching requires **cross-record \+ cross-census context**, it naturally benefits from:

* indexing,

* repeatable reruns,

* easier debugging and auditability,

* and “idempotent” processing (recompute clean results without re-ingesting raw).

**Why Option A (During Ingest) is risky here**

Running entity resolution while streaming CSV sounds attractive, but in your case it creates real friction:

* **You rarely have full context in a single pass.** Linking unnamed individuals across decades requires looking backward/forward in time and across households.

* **Harder to debug and reproduce.** If a match is wrong, you’re chasing streaming state, not a stable dataset.

* **Harder to tune scoring.** Entity resolution almost always needs iteration; you want reruns without re-ingest.

**Recommended compromise (best of both): B \+ “light” preprocessing during ingest**

Do **minimal** transformations during ingest to make post-processing fast:

* Normalize fields (age to int, birth year estimate, location codes, gender codes)

* Generate **blocking keys** (more on that below)

* Store all raw rows intact \+ derived columns in the raw DB

Then do the heavy matching post-ingest.

---

**2\) Two-tier database: you’re on the right track — add an audit layer**

Your proposed architecture is strong:

**Raw DB**

* immutable import of IPUMS rows

* derived columns ok (as long as you can recompute them)

**Clean DB**

* resolved identities (Origin IDs)

* relationship edges (parent/child/spouse)

* confidence scores \+ match evidence

**Add one more concept: Match Evidence / Provenance**

Entity resolution is never perfect; you’ll want to explain “why” later.

Create a table like:

* link\_candidates (optional staging): 

  * from\_record\_id, to\_record\_id, score, reasons\_json, run\_id

* resolved\_links: 

  * origin\_id, record\_id, confidence, method, run\_id

* run\_metadata: 

  * scoring weights used, date, code version hash, census-year scope

This gives you:

* repeatability,

* “undo” by run\_id,

* and an audit trail (very helpful for genealogy outputs like GEDCOM).

---

**3\) Performance: how to finish within a 24-hour window**

You already have \~8 hours ingestion. The matching phase needs to be engineered around **reducing comparisons** (the \#1 killer in entity resolution).

**Key idea: Blocking first, scoring second**

Never compare “everyone to everyone.” Create candidate sets using blocking keys like:

* state \+ county \+ census\_year\_pair

* birth\_year\_bucket (e.g., 1880–1882)

* household composition signature (counts of children in age bands)

* SERIAL for within-household linking (strongest block)

Then score only inside those blocks.

**Practical indexing (huge impact)**

Whatever DB you use, index the columns you block on. Examples:

* census\_year

* state, county

* serial

* birth\_year\_est

* sex

* surname (when present)

If you stick with SQLite, indexes are often the difference between “hours” and “days”.

**Batch strategy**

Process census links in **year-pairs**:

* within-year household structure first (parents/children inference in that year)

* then cross-year linking: 1850↔1860, 1860↔1870, … 1940↔1950

This keeps the workload partitioned and parallelizable.

---

**4\) Memory Management: “Load all CSV into memory?” (usually no)**

**Can you read the entire CSV into memory and do one pass?**

Technically yes **if it fits**, but it’s rarely the best idea for IPUMS-scale data.

A good rule of thumb:

* **memory needed ≈ rows × average bytes per parsed row × overhead**

* parsing overhead in Python objects can be **multiple times** the raw CSV size

So even a “moderate” CSV can explode in RAM once parsed.

**Better pattern: chunk \+ block**

* Stream ingest to raw DB (what you do now)

* For matching: 

  * pull *one block at a time* (e.g., one county, one year-pair)

  * load only those rows into memory

  * compute links

  * write results

This gives you predictable memory usage and makes concurrency far easier.

---

**5\) Concurrency: “If we identify a Father record, can we resolve Children in parallel?”**

**Yes — but be careful about database write contention**

There are two concurrency dimensions:

**A) Parallel scoring** (easy to parallelize)  
Compute candidate scores for independent partitions (blocks).

**B) Writing results** (harder with SQLite)  
SQLite is great for single-user analysis but has limitations:

* Many readers: OK

* Many writers: contention

**If you’re on SQLite today: use a “single writer” pattern**

Best practice:

* Each worker process: 

  * reads its partition

  * computes results

  * writes to its own output (CSV / temp table / temp DB)

* A final merge step inserts results into the Clean DB with one writer

This avoids “database is locked” pain.

**Parallelizing father→children resolution**

A clean concurrency approach is to define a unit of work that doesn’t overlap:

**Good work units**

* (census\_year, state, county)

* (census\_year\_pair, state, county)

* or even (census\_year, serial) for within-household inference

Then each worker can:

1. find candidate father/mother in that unit

2. link children within the same unit

3. produce edges \+ evidence

**Global Origin IDs in parallel**

If multiple workers assign Origin IDs, you must avoid collisions:

* Use a GUID/UUID origin\_id, or

* allocate ID ranges per worker, or

* let the DB assign IDs centrally (but then you’re back to contention)

**Simplest:** UUID-based Origin IDs.

---

**6\) A concrete pipeline I’d recommend (fits your slides)**

**Phase 0 — Ingest (Raw DB)**

* Import CSV rows (immutable)

* Compute derived fields: 

  * birth\_year\_est \= census\_year \- age (store as estimate)

  * geo\_key \= state|county

  * name\_present\_flag

  * basic household signatures (counts by age bands)

**Phase 1 — Within-census household structure**

For each (census\_year, serial):

* infer parent candidates (age thresholds, relationship codes if present)

* attach children edges with confidence

Store:

* person\_record\_id

* edges like (parent\_record\_id \-\> child\_record\_id)

* confidence \+ reasons

**Phase 2 — Cross-census linking (Origin ID resolution)**

For each year-pair (Y, Y+10) and each geo partition:

* build candidate sets using blocking keys

* compute sibling/age/geo similarity scores

* assign/merge Origin IDs using a clustering approach (often union-find works well)

Store:

* origin\_id

* record\_id

* link confidence \+ evidence

**Phase 3 — Build GEDCOM**

* Each origin\_id becomes an INDI (individual)

* Parent/child edges become FAM structures

* Include confidence as notes or custom tags so provenance isn’t lost

---

**7\) Answers to your “Key Technical Considerations” directly**

**Performance**

* Prefer **post-ingest** with indexed blocking \+ partitioned processing.

* Use multiprocessing across **non-overlapping partitions**.

* Avoid N² comparisons by blocking early.

**Memory**

* Don’t aim to load the entire CSV unless it’s small and you’ve proven it fits.

* Prefer “block-wise in-memory” loading from DB.

* Keep memory stable by processing one partition at a time.

**Concurrency**

* Yes, you can trigger parallel child resolution after identifying a father — **but define the unit of work** (e.g., household/serial or county partition) to avoid overlap.

* If SQLite: parallel reads are fine; parallel writes are not. Use “single-writer” merge.

---

**A small “next step” that will pay off immediately**

Even without changing any tools, you can do this now:

1. Decide your **partition key** (e.g., state+county+year\_pair)

2. Add indexes in the raw DB for those keys

3. Implement matching as: 

   * fetch partition → compute → emit results → merge

That structure will make the 24-hour target achievable *far more reliably* than threading inside a single streaming ingest.

---

If you want, paste a tiny sample of:

* your raw table schema (column names you’re ingesting), and

* what you currently consider a “father/child” record in the IPUMS fields you have

…and I’ll sketch a **scoring function \+ blocking keys** that align to your exact columns and the 1850–1950 quirks (e.g., missing surnames, age drift, migration).

