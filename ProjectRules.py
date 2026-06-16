"""
-----------------------------------
File: ProjectRules.py

Summary: This genealogy project is used to merge all the digital nameless census records
            into one large family tree and
            then overlay an existing GEDCOM on top of that to add names to the family tree.

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

Design:
    Andy uses the IPUMS interface to download the most recent CSV data representing census files.

    The script DatabaseVault.py reads the CSV files and creates a SQLite database of that information.

    The script LinkFamiliesByDemographics.py uses duck DB to link the appropriate DB fields from
    the census data and creates one large linked web of census data individuals and families.

    The script GedcomNameOverlay.py matches data fields up with the database and a CSV file
    created from a GEDCOM to overlay the names onto the nameless census data.
    Script gedcom_analysis.py is used To provide names and facts to be compared to the database
    for matching criteria

--------------------------------

"""
print("git er done")
