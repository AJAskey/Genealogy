Technical Architecture Specification: Genealogy Data Processing Pipeline

1. Executive Summary and Strategic Context

This specification defines the architectural framework for the Genealogy project, a large-scale data engineering initiative designed to transform approximately 281 million IPUMS USA census records (1850–1950) into a validated, high-fidelity GEDCOM family tree. The project necessitates the conversion of raw, disparate historical data into a structured genealogical resource suitable for rigorous research.

The core technical challenge involves resolving identities across 10 census decades where approximately 25% of records lack name data due to historical document degradation. Despite the absence of names, these records maintain high data quality in other fields. Therefore, a structured engineering approach—utilizing multi-weighted algorithmic scoring and relationship modeling—is the only viable method to identify these individuals at scale. This architecture implements a two-tier database strategy and a modular processing pipeline to ensure the accuracy, auditability, and persistence of the resulting family tree.

2. Two-Tier Database Architecture: The Separation of Concerns

The architecture shall maintain a strict "Two-Tier" database system to isolate immutable ground-truth data from interpreted results. This separation is mandatory to preserve data integrity and allow for the iterative refinement of matching algorithms without jeopardizing the source data.

Database Tier Specifications

Database	Purpose	Description
Raw DB	The Immutable Vault	Houses exact IPUMS imports (1850–1950) in their original state. This tier is read-only after initial ingest; no modifications are permitted.
Clean DB	The Interpreted Output	Contains resolved identities, permanent Origin IDs, and full bibliographic citations resulting from the processing pipeline.

Strategic Impact: By isolating the Raw DB, the system facilitates rapid prototyping and iterative algorithm tuning. Engineering teams can rerun the pipeline across the 281-million-record set as matching heuristics evolve, eliminating the high computational cost and risk of re-ingesting 18GB source files. This strategy ensures a resilient environment for high-stakes historical data processing.

3. The Two-Script Modular Processing Pipeline

The processing pipeline shall utilize a bifurcated modular model, separating analysis from database persistence. A single-pass ingest model is rejected to support the backward-and-forward decade comparisons necessary for identity resolution and to prevent system failures from corrupting the production datasets.

Script 1: The Analyst

The Analyst script functions as the logic engine of the pipeline. It is mandated to:

* Read source records from the Raw DB.
* Execute complex scoring logic and blocking strategies to identify potential matches.
* Output candidate match files into human-readable text formats.
* Safety Protocol: The Analyst script is strictly prohibited from performing database writes, ensuring a risk-free environment for algorithmic iteration.

Script 2: The Writer

The Writer script handles the commitment of validated data. It is mandated to:

* Ingest only those candidate files that have passed the Human-in-the-Loop gate.
* Assign permanent, unique Origin IDs to validated individuals.
* Execute all write operations to the Clean DB and Citation tables.

Architect's Note: This "Decision 1" (Post-Ingest Processing) isolation ensures that the most computationally intensive and logic-heavy phase (the Analyst) is decoupled from the most sensitive phase (the Writer), maximizing system stability and simplifying error recovery.

4. Data Governance and the Human-in-the-Loop Gate

Due to the inherent nuances of historical data, a fully automated resolution system is insufficient. The architecture mandates a human review buffer to prevent the creation of false lineages.

The Text File Buffer Mechanism

The Analyst script shall write all potential matches to human-readable text files rather than the database. These files serve as the primary interface for the project lead to review, edit, and approve identifications. Only upon manual approval are these files passed to the Writer script for database commitment.

Strategic Impact: Auditability and Concurrency

This buffer provides a permanent, non-database audit trail of every matching decision made during the project. Furthermore, this design eliminates concurrency and write-contention issues; because the Analyst and Writer scripts interact with different data formats at different times, the risk of database locking in a high-volume environment is removed.

5. The Origin ID Strategy: Establishing Permanent Identity

Every validated individual shall be assigned a permanent "Origin ID" (internally designated as the "St. Joe’s ID"). This ID serves as the immutable anchor for the individual across the entire 100-year dataset.

ID Requirements and Structure

* Immutability: IDs shall never change, be reused, or encode personal data.
* Structure: Sequential integers starting at 1.
* Scope: Assigned at the Person level (using the combination of SERIAL + PERNUM).
* Registry: Managed in a dedicated Registry table to prevent ID collisions.

Architect's Note: Person-level identification is a non-negotiable requirement. GEDCOM standards require individuals as the primary entities, and household-level IDs are insufficient because historical households frequently split or merge across decades. The Origin ID ensures the individual remains a stable anchor even as their domestic circumstances shift.

6. Algorithmic Identity Resolution: Scoring and Blocking

Identity resolution across 100 years requires a multi-weighted heuristic to resolve individuals, particularly the 25% of records missing name data.

Scoring Components and Thresholds

Component	Points	Description
Age Consistency	0–3	Expected age ± tolerance across decades.
Household Structure	0–5	Comparison of the Household Vector.
Geography	0–3	Prioritizes same county/state over migration.
Name Match	0–2	Exact or phonetic (Soundex) matches when data is present.
Total Possible	13	

Decision Thresholds:

* 10–13: Strong match — candidate for likely approval.
* 7–9: Probable match — requires careful manual review.
* Below 7: Reject — insufficient evidence for linkage.

Technical Implementation Strategies

* Hybrid Blocking/Scoring: To prevent combinatorial explosion, SQL shall perform the blocking (filtering by State + County + Birth Year range ± 2 years). Python shall perform the scoring within those filtered blocks.
* Household Vectors: The system shall generate family "fingerprints" formatted as: [FatherAge, MotherAge, ChildAges-sorted]. Matching these vectors provides the strongest cross-census identification.
* Anchor and Audit Strategy: The algorithm shall anchor on fathers first and cascade to children using IPUMS pointers. Prior to custom logic execution, an audit query must be run on the MOMLOC, POPLOC, and SPLOC (Spouse Location) fields to determine if these internal links can automate 60–70% of the linking process.

7. Engineering Constraints and Performance Optimization

The system must process 18GB source files on local hardware. The following technical mandates are required to maintain a sustainable memory footprint and processing speed.

Technical Mandates

* Memory Management: Full-file loads are prohibited. All processing shall occur in chunks of 50,000 rows.
* SQLite Indexing: The following columns must be indexed to ensure query performance: census_year, serial, birth_year_est, sex, surname, and a composite index on state, county.
* Concurrency: Multi-threading is currently unnecessary. The text-buffer design isolates script execution, maintaining high throughput without the complexity of concurrent write management.

Strategic Impact: These optimizations reduce the processing window from weeks to hours, enabling the rapid iteration cycle required for the Analyst script's matching logic.

8. Citation Management and Data Provenance

The system shall implement a robust citation framework to ensure genealogical rigor and satisfy data use requirements.

Citation Structure and Fallback Strategy

The Citation table shall record the Record ID, Source, URL, and Access Date for every entry in the Clean DB.

Architect's Note: To mitigate risks associated with the IPUMS Data Use Agreement, the system must support a fallback strategy. The citation engine shall be capable of pivoting to reference National Archives (NARA) primary sources rather than the IPUMS aggregator. Because the Origin ID and tree structure are independent of the citation string, this pivot can be executed without altering the underlying family tree.
