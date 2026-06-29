"""
-----------------------------------
File: ProjectRules.py

Summary: This genealogy project is used to merge all the digital nameless census records
            into one large family tree andthen overlay an existing GEDCOM on top of that
            to add names to the family tree.

These are the rules of work that we have agreed to over the past couple months.

1. All census data is truth. All people and families entered into our
    linked tree begin at the census.

2. The GEDCOM data is used to overlay names onto the linked census tree.

3. The census data is used to create the family tree.

4. No individuals or families are ever added purely from the GEDCOM; they must map to an
    existing census golden record.

5. Auxiliary data such as names, marriage information, additional residences, military services,
    and deaths are added from the GEDCOM and other sources.

6. Logging is a major part of the project and is required.

7. All requirements are to be tested via the logging data and analytic routines written to read
     and analyze the output of the log data.

 8. Andy's job is to provide the logging data and JSON data from program execution
   so that the AI can have access to it.

 9. Gemini Code Assist's job is to write the code and analyze the logging data and Database
    data in JSON format. AI will then make changes to the code based that analysis.

10. Scoring must be deterministic and transparent. Tie-breakers (like county matches) should 
    heavily favor high-fidelity data over generic state-level matches to prevent "clone wars."

11. It is far better to have an Individual without a name than it is to give an individual
    the wrong name.

12. The parts of this project that are related directly to the IPUMS database are completely
    deterministic. There is no randomness. IPUMS has figured out all the matches, all the families, and
    ovides the data to us. We don't need to do a probabilistic survey to find out who the father was.
    We know that from looking at the census data.

13. Processing GEDCOMs created by crazy grandmothers is probabilistic because they often fudge the
    numbers they don't really know. They don't get the birth dates correct and sometimes they change
    correct data because they don't like the way it sounds.  Maybe they don't want the record to show
    that their daughter was actually pregnant before they got married so they changed the date
    to match their fantasy but that's not reality.  Humans hallucinate constantly in GEDCOMs.

Design:
    Andy uses the IPUMS interface to download the most recent CSV data representing census files.

    The script DatabaseVault.py reads the CSV files and creates a SQLite database of that information.

    The script LinkFamiliesByDemographics.py uses duck DB to link the appropriate DB fields from
    the census data and creates one large linked web of census data individuals and families.
    The census data from IPUMS provides all the information necessary to link families across
    decades. It is actually a very simple process but we have to make sure our algorithms
    match that process.

    The script GedcomNameOverlay.py matches data fields up with the database and a JSON file
    created from a GEDCOM to overlay the names onto the nameless census data.
    
    Script gedcom_analysis.py is used to parse the GEDCOM and provide names, facts, and 
    parent birthplaces to be compared to the database for matching criteria.

    Census data is filtered through a DuckDB SQL query to extract only couples with known 
    birth places, preventing low-resolution "ghost" matches.

    All other display filtering, strict 1-to-1 Highlander enforcement, and scoring 
    is done using Python in the source code.

    The concept of a geographical area has been added. This is generally a set of
     ounties with common borders. In the GEDCOM, the county itself might be off,
     but they might actually mean one county over.
     For example:  central Pennsylvania, you create an area of a number of counties for
     central Pennsylvania counties. Matching based on central Pennsylvania [Clearfield, Centre,
     Clinton and Lycoming] and not a pecific county. This design overcomes errors in sloppy
     GEDCOM building.

--------------------------------

"""
print("git er done")
