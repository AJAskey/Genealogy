# AI Assistant Instructions for Genealogy Project

## 1. Golden Architecture Rules
- **Two-Tier DB:** The "Raw DB" is read-only. Only the "Clean DB" can be written to.
- **Thread Safety:** All SQLite writing must use WAL mode and be thread-safe.

## 2. Python Coding Standards
- Always use Python 3 f-strings.
- Always include Docstrings for new functions explaining Inputs and Outputs.
- Never use `print()` for production code; always use the `logging` module.
- I prefer over-commenting to under-commenting, so feel free to add all the comments you want. 
- I am familiar with python and have done quite a bit but I have never coded python in a large system environment. 

## 3. GEDCOM Specifics
- GEDCOM exports must ALWAYS be strictly 7.0.18 compliant.
- Always use UTF-8 encoding when opening or writing files.

## 4. Interaction Style
- I am a retired software engineer with 30+ years experience. I've done a lot of stuff but some things I have not done. 
- I have had two strokes in the last year, and so I'm not what I used to be. But I do my best.  
- Typing doesn't work for me anymore, so I mostly use a microphone and enter all commands through my voice. 
- Keep explanations brief and technical.
- If proposing file edits, ensure they match the surrounding code's formatting.

## Data Flow
- Data is downloaded from the IPUMS website. 
- Each download uses the IPUMS interface to determine which sources and which variables are downloaded. 
- Data is downloaded as CSV files from IPUMS and stored on my local hard drive.
- Census records are added to the database on my NVMe disk. 
- Records are read and processed and turned into GEDCOM files. 

## System Configuration
- The system uses SQLite for data storage on a NVMe drive, with WAL mode enabled for thread safety.
- The system is designed to handle large datasets efficiently, with parallel processing where possible.
- Error handling expected to be robust, with detailed logging and recovery mechanisms in place.
- CSV files are processed in parallel where possible to improve performance.

## Super Computer
  OS Name					Microsoft Windows 11 Pro
  System Name				ELLA5
  System Manufacturer		ASUS
  Processor	Intel 	    	Core Ultra 9 285K, 3700 Mhz, 24 Core(s), 24 Logical Processor(s)
  BIOS Version/Date		    American Megatrends Inc. 3002, 1/29/2026
  SMBIOS Version			3.8
  BaseBoard Manufacturer	ASUSTeK COMPUTER INC.
  BaseBoard Product	    	ProArt Z890-CREATOR WIFI
  Installed RAM			    128 GB
  Video				    	AMD Radeon RX 9070 XT : 16 GB (not enough for local AI)
  Disk D:       		    Samsung SSD 9100 PRO 3.67 TB5

  @./README.md
  