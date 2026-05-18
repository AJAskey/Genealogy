### Cross-Decadal Kinship Reconstruction: A Technical Manual for IPUMS-Based Family Linking

##### 1\. Strategic Framework for IPUMS Genealogy Data

The Integrated Public Use Microdata Series (IPUMS) represents the gold standard for historical reconstruction because it provides harmonized, individual-level data across centuries of census records. For the modern quantitative genealogist, the value of IPUMS lies in the strategic shift from simple household analysis—viewing a family as a static "snapshot" in a single year—to longitudinal "life-course" tracking. This evolution is the essential foundation for modern genealogy software, allowing researchers to follow individuals through time by transforming disconnected decadal snapshots into a continuous narrative of human lives.A primary obstacle in this longitudinal approach is the "Sibling Separation Problem." This phenomenon occurs when children reach adulthood (typically after age 18\) and leave the parental household to establish their own residences. In standard household-based queries, these individuals appear to vanish or become "invisible" once they no longer share a SERIAL (Household) identifier with their family of origin. To overcome this, software must utilize specific kinship variables to "anchor" these individuals before they disperse, using the data structures detailed below.

##### 2\. Anatomy of the IPUMS Data Schema (1870–1940)

The efficacy of cross-decadal linking depends entirely on the consistency of the data schema across different census years. While census questions evolved between 1870 and 1940, IPUMS harmonizes these responses into a stable set of variables that allow for rigorous record linkage.

###### *Core Kinship Variables and Their Functionality*

Category,Variable,Description  
Identifiers,SERIAL,Unique identifier for a specific household.  
Identifiers,PERNUM,Unique person number within a household.  
Identifiers,HISTID,Persistent identifier used for full-count historical data linking.  
Household Composition,FAMUNIT,Identifies separate family groups within one household.  
Household Composition,FAMSIZE,Total number of family members in the unit.  
Household Composition,NCHILD,Number of own children in the household.  
Household Composition,NSIBS,Number of own siblings in the household.  
Pointers,MOMLOC,PERNUM of the person's mother in the same household.  
Pointers,POPLOC,PERNUM of the person's father in the same household.  
Pointers,SPLOC,PERNUM of the person's spouse in the same household.  
Static Bio-Data,BIRTHYR,Estimated year of birth based on reported age.  
Static Bio-Data,SEX,Biological sex of the individual.  
Static Bio-Data,RACED,Detailed racial or ethnic classification.  
Static Bio-Data,BPLD,Detailed 5-digit birthplace code (State or Country).  
The "Pointer" variables—MOMLOC and POPLOC—are the most critical tools for biological reconstruction. These fields allow the software to identify biological parents with mathematical precision within a household, even when surnames are missing, non-unique, or spelled inconsistently. By identifying the person at PERNUM 01 and seeing that PERNUM 03 and 04 both have a MOMLOC of 02, the system confirms them as biological siblings regardless of the household's last name. These variables form the static "DNA" of a record, providing the necessary foundation for deterministic intra-census matching.

##### 3\. Short-Term Linking: Intra-Census Sibling Identification

The highest confidence in sibling relationships is established through "co-residence identification." While siblings reside under the same SERIAL (Household) identifier, their relationship is structurally verifiable through "Deterministic Matching."

###### *Algorithmic Logic for Intra-Census Linking*

To identify a sibling group within a single census year (e.g., 1870), the software should execute the following logic:

1. **Group by Household:**  Collect all individuals sharing the same SERIAL and FAMUNIT.  
2. **Filter by Relationship:**  Identify individuals where RELATE is code 03 (Child) or RELATED falls within the 0301–0304 range.  
3. **Confirm Biological Link:**  Match the MOMLOC and POPLOC values. If multiple children in the same unit point to the same mother and father indices, they are identified as siblings.  
4. **Checksum Verification:**  Use the NSIBS (Number of siblings) count. Note that NSIBS is an "n-1" logic variable; it represents the number of siblings  *other than the individual* . For a sibling group of four, each member must show NSIBS \= 3 for the group to be validated as a complete set.The RELATED variable is particularly powerful for differentiating between biological and social kinship in your software. Detailed codes such as 0702 (Step/Half/Adopted Sibling) or 1033 (Step/Adopted Nephew/Niece) allow the architect to differentiate biological siblings from social siblings. While this intra-census linking is highly reliable, the true value of this data is the ability to maintain these links once the siblings disperse into the wider world.

##### 4\. Long-Term Tracking: Longitudinal Sibling Linking Across Decades

The primary technical challenge is "The Difficult Part": tracking siblings across the 1870, 1910, and 1940 censuses once they no longer live together. When individuals disperse, standard household pointers fail, requiring a shift to "Probabilistic Linkage."

###### *Heuristic Matching Protocol*

To track individuals over 10-to-30-year gaps, developers should implement a multi-step protocol:

* **Primary Filter (High Confidence):**  Candidates must match on SEX, BIRTHYR (allowing a \+/- 2 year variance for reporting errors), and the 5-digit BPLD string. Matching on the 3-digit BPL is insufficient for high-confidence linking when the more granular BPLD (e.g., code 01900 for Iowa) is available.  
* **Secondary Filter (Kinship Anchoring):**  Search for other family members simultaneously. If Sibling A and Sibling B are found in separate households in 1910, the software should use their shared MOMLOC/POPLOC data from the 1870 "anchor" record to validate the match. The probability of a match increases exponentially if two individuals in the subsequent census share the same specific birth years and birthplaces as the 1870 sibling group.  
* **Geographic Logic:**  Use STATEICP and COUNTYICP to narrow search parameters and improve processing efficiency, but prioritize BPLD for the match itself. BPLD is the only  **immutable**  geographic variable, whereas current residence is volatile.The search space challenge is mitigated in later years (such as 1940\) by the HISTID variable, which acts as a unique persistent identifier for individuals across full-count datasets. However, technical pitfalls like surname changes for females require further specialized logic.

##### 5\. Overcoming the "Surname Gap" in Dispersed Siblings

Tracking female siblings after marriage is a common point of failure because NAMELAST changes, breaking standard string-matching logic.

###### *The Parental Proxy Search Strategy*

To find a sister who moved out and changed her name, the software should employ a "Parental Proxy" search:

1. **Search for Parents:**  Locate the parents (MOMLOC/POPLOC) from the 1870 anchor in the next census.  
2. **Check for Residual Co-residence:**  If the sister is still in the parental home but listed with a new surname, she may be coded under RELATE code 10 (Other relatives).  
3. **Brother-Household Scan:**  If the parents cannot be found, the software should search the households of identified biological brothers. Married sisters frequently resided with or near their brothers; the software must scan for individuals with RELATE code 10 (Other relatives) in those households.  
4. **Verification:**  When an individual is found via code 10, the software must verify her 5-digit BPLD and BIRTHYR against the 1870 "anchor" record to confirm she is the target sibling and not a cousin or unrelated guest.The detailed birthplace (BPLD) acts as a unique "fingerprint" in these searches. If an individual in a different state has a rare BPLD (e.g., code 45312 for Bavaria) and matches the BIRTHYR and RACED values of an 1870 anchor record, she is a high-probability candidate for kinship reconstruction regardless of surname changes.

##### 6\. Gap Analysis and Data Requirements

High-value genealogical tools require absolute data integrity to function. Based on the IPUMS source context provided, a critical parity gap exists that users must address.**Primary Data Gaps:**

* **Surname and Given Name Availability:**  While NAMELAST and NAMEFRST are present in the 1870 and 1910 data, the provided 1940 dataset sample lacks these name strings.  
* **Critical Marital Status Failure:**  The MARST (Marital Status) variable is entirely absent from the provided 1870, 1910, and 1940 extracts. This is a critical failure point for tracking the "Surname Gap," as the software cannot confirm a change in marital status to trigger proxy search logic.**Checklist for Parity (Required Variables):**  To ensure full longitudinal parity, the following variables must be acquired for the 1940 dataset and verified for 1870/1910:  
* NAMELAST and NAMEFRST: Required for matching and brother-led proxy searches.  
* MARST: Essential for identifying potential name changes for female siblings.  
* BPLD: Essential for maintaining the 5-digit geographic "fingerprint" across all three decades.By meticulously applying these IPUMS codes and algorithmic strategies, software can transform raw census data into a sophisticated relational database of human lives, reconstructing family lineages across a century of historical change.

