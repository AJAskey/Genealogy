"""
-----------------------------------
File: identity_registry.py

Summary: Manages permanent Golden IDs (St. Joe's IDs).
         Ensures that once a raw census/GEDCOM row is assigned a Golden ID,
         that ID is remembered and reused in all future AI runs.
-----------------------------------
"""

import sqlite3
import os
import uuid
import pandas as pd

if os.name == 'nt':
    CLEAN_DB = r"D:\Data\Genealogy_Data\CleanVault.db"
else:
    CLEAN_DB = os.path.expanduser("~/Genealogy_Data/CleanVault.db")


class IdentityRegistry:
    def __init__(self, logger):
        self.logger = logger
        self.db_path = CLEAN_DB
        self._setup_db()
        self.pointer_to_golden = self._load_registry()
        self.dirty = False
        self.new_mappings = []

    def _setup_db(self):
        """Ensure the identity tracking table exists in the CleanVault."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS identity_registry (
                    source_pointer TEXT PRIMARY KEY,
                    golden_id TEXT,
                    full_name TEXT
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_golden_id ON identity_registry(golden_id)')

    def _load_registry(self):
        self.logger.info("  Loading Identity Registry to maintain persistent IDs...")
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql("SELECT source_pointer, golden_id FROM identity_registry", conn)
            return dict(zip(df['source_pointer'], df['golden_id']))

    def get_or_mint_master_id(self, all_pointers: list, full_name: str) -> str:
        """
        Looks up existing pointers to find a saved Golden ID.
        If multiple exist (a merge), it picks the oldest.
        If none exist, it mints a new one.
        """
        existing_ids = set()
        for ptr in all_pointers:
            if ptr in self.pointer_to_golden:
                existing_ids.add(self.pointer_to_golden[ptr])
                
        if len(existing_ids) == 1:
            # We already know who this is, reuse their permanent ID
            golden_id = existing_ids.pop()
        elif len(existing_ids) > 1:
            # The AI clustered previously distinct people together. Pick one ID to survive.
            golden_id = sorted(list(existing_ids))[0]
        else:
            # Brand new person! Mint a permanent St. Joe's ID.
            golden_id = f"SJ_{uuid.uuid4().hex[:8].upper()}"

        # Register all raw pointers to this ID in memory
        for ptr in all_pointers:
            if ptr not in self.pointer_to_golden or self.pointer_to_golden[ptr] != golden_id:
                self.pointer_to_golden[ptr] = golden_id
                self.new_mappings.append((ptr, golden_id, full_name))
                self.dirty = True

        return golden_id

    def save_registry(self):
        """Writes new identity mappings permanently to the CleanVault."""
        if self.dirty and self.new_mappings:
            self.logger.info(f"  Saving {len(self.new_mappings):,} new identity mappings to the registry...")
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany('''
                    INSERT OR REPLACE INTO identity_registry (source_pointer, golden_id, full_name)
                    VALUES (?, ?, ?)
                ''', self.new_mappings)
            self.dirty = False
            self.new_mappings = []