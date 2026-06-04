"""
-----------------------------------
File: backup_source.py

Summary: Utility script to zip up the Python source code directory 
         with a timestamp. Makes daily backups to Google Drive (or local) 
         effortless.
-----------------------------------
"""

import os
import shutil
import datetime
import gen_logging

def create_backup(logger):
    source_dir = r"E:\Users\Andy\PycharmProjects\Genealogy\python"
    
    # Update this path to point directly to your Google Drive folder if you have it mapped!
    backup_dir = r"E:\Users\Andy\PycharmProjects\Genealogy\backups"
    
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_base_name = os.path.join(backup_dir, f"Genealogy_Python_Source_{timestamp}")
    
    logger.info(f"Zipping source code from: {source_dir}")
    shutil.make_archive(archive_base_name, 'zip', source_dir)
    logger.info(f"Backup created successfully: {archive_base_name}.zip")

if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="BACKUP")
    create_backup(main_logger)