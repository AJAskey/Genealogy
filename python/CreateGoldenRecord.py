"""
-----------------------------------
File: GoldenRecordGenerator.py

Summary: Entity resolution engine using Splink 4.
         Takes a prepared DuckDB view of census population data,
         runs probabilistic deduplication, applies survivorship rules,
         and writes Golden Records to the CleanVault.

IMPORTANT - Splink version requirement:
    pip install splink>=4.0
    The old splink.duckdb.linker import path (Splink 3) will NOT work.

Design notes:
    - Splink receives a DuckDB view called 'population_for_splink', which
      is prepared by run_analyst.py before this class is called.
    - Column names entering Splink are standardized:
        unique_id, first_name, last_name, birth_year, state, source_db
    - Survivorship picks the most-frequent name spelling and the earliest
      plausible birth year (outliers beyond 10 years from median are ignored).
    - All raw vault pointers are preserved so no original data is ever lost.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import pandas as pd
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on

from identity_registry import IdentityRegistry


class CreateGoldenRecord:
    """
    Probabilistic entity resolution and Golden Record builder.

    Usage:
        gen = GoldenRecordGenerator(db_connection=con, logger=logger)
        gen.run(output_table="clean.golden_records")
    """

    # Splink settings live here so they are easy to tune in one place.
    # Blocking rule: only compare people with the same last name AND birth year.
    # This keeps the comparison count manageable on 844M rows.
    SPLINK_SETTINGS = SettingsCreator(
        link_type="dedupe_only",
        comparisons=[
            cl.LevenshteinAtThresholds("first_name", [1, 2]),
            cl.JaroWinklerAtThresholds("last_name", [0.88, 0.95]),
            cl.ExactMatch("birth_year"),
            cl.ExactMatch("state"),
            cl.ExactMatch("birth_place"),
        ],
        blocking_rules_to_generate_predictions=[
            # 1. Exact name match, safely bounded to a 10-year birth difference to prevent multi-generational Cartesian explosions
            "l.first_name = r.first_name AND l.last_name = r.last_name AND (abs(l.birth_year - r.birth_year) <= 10 OR l.birth_year IS NULL OR r.birth_year IS NULL)",
            # 2. Catches first-name typos: Exact last name, exact birth year, bounded to same first initial
            "l.last_name = r.last_name AND l.birth_year = r.birth_year AND substr(l.first_name, 1, 1) = substr(r.first_name, 1, 1)",
            # 3. Catches last-name typos: Exact first name, exact birth year, bounded to same last initial
            "l.first_name = r.first_name AND l.birth_year = r.birth_year AND substr(l.last_name, 1, 1) = substr(r.last_name, 1, 1)",
        ],
        max_iterations=10,
        em_convergence=0.0001,
    )

    # Match probability threshold: 0.95 means we are 95% confident two rows
    # are the same person before we merge them. Raise to 0.98 to be more
    # conservative (fewer merges, less risk of accidentally combining two
    # different people). Lower to 0.90 to catch more near-misses.
    MATCH_THRESHOLD = 0.95

    def __init__(self, db_connection, logger):
        """
        Parameters
        ----------
        db_connection : duckdb.DuckDBPyConnection
            The active DuckDB connection with census and clean vaults attached.
        logger : logging.Logger
            The gen_logging logger passed in from run_analyst.py
        """
        self.con = db_connection
        self.logger = logger
        self.linker = None

    # ------------------------------------------------------------------
    # PUBLIC ENTRY POINT
    # ------------------------------------------------------------------

    def run(self, mode: str = "link", output_table: str = "clean.golden_records", model_path: str = None):
        """
        Runs the specified parts of the pipeline.

        Parameters
        ----------
        mode : str
            'train' to only train and save the model.
            'link' to load a saved model, cluster, and write.
            'both' to train, predict, cluster, and write.
        output_table : str
            Fully qualified DuckDB table name to write golden records into.
        model_path : str
            File path to the trained Splink JSON model.
        """
        self.logger.info("=" * 60)
        self.logger.info(f"GoldenRecordGenerator: Starting pipeline (Mode: {mode.upper()})")
        self.logger.info("=" * 60)

        db_api = DuckDBAPI(connection=self.con)
        import os

        if mode in ("train", "both"):
            self.logger.info("Phase: TRAINING")
            self.logger.info("  Extracting 100k skewed sample (67% male) for EM training...")
            self.con.execute("DROP TABLE IF EXISTS sample_for_splink;")
            self.con.execute("""
                             CREATE TABLE sample_for_splink AS
                             (SELECT *
                              FROM population_for_splink
                              WHERE sex = '1' AND SPLIT_PART(unique_id, '_', 3) = '1' USING SAMPLE 67000 ROWS)
                             UNION ALL
                             (SELECT *
                              FROM population_for_splink
                              WHERE (sex != '1' OR sex IS NULL)
                                AND SPLIT_PART(unique_id, '_', 3) = '1' USING SAMPLE 33000 ROWS);
                             """)

            self.linker = Linker(
                "sample_for_splink",
                self.SPLINK_SETTINGS,
                db_api=db_api,
            )
            self.logger.info("  Training match weights on sample (unsupervised EM)...")
            self._train()

            if model_path:
                self.logger.info(f"  Saving AI brain to '{model_path}' for future runs...")
                self.linker.misc.save_model_to_json(model_path, overwrite=True)

            if mode == "train":
                self.logger.info("GoldenRecordGenerator: Training complete. Exiting as requested.")
                return

        if mode in ("link", "both"):
            self.logger.info("Phase: LINKING")

            if mode == "link" and model_path and os.path.exists(model_path):
                self.logger.info(f"  Loading saved model from '{model_path}'...")
                self.linker = Linker("population_for_splink", model_path, db_api=db_api)
            else:
                if mode == "link":
                    self.logger.warning(f"  Model not found at '{model_path}', falling back to default settings.")
                self.linker = Linker("population_for_splink", model_path if (
                            model_path and os.path.exists(model_path)) else self.SPLINK_SETTINGS, db_api=db_api)

            self.logger.info("  Predicting match scores and clustering...")
            cluster_df = self._predict_and_cluster()

            self.logger.info(f"  Applying survivorship rules to {len(cluster_df):,} clustered rows...")
            registry = IdentityRegistry(self.logger)
            golden_df = self._generate_survivor_records(cluster_df, registry)
            self.logger.info(f"  Produced {len(golden_df):,} unique golden records.")

            if not golden_df.empty:
                self.logger.info(f"  Writing golden records to {output_table}...")
                self._write_golden_records(golden_df, output_table)
            else:
                self.logger.warning("  No golden records to write. Skipping database insertion.")

            registry.save_registry()
            self.logger.info("GoldenRecordGenerator: Pipeline complete.")

    # ------------------------------------------------------------------
    # PRIVATE STEPS
    # ------------------------------------------------------------------

    def _train(self):
        """
        Unsupervised training using the Expectation-Maximisation algorithm.
        We use two training sessions with different blocking rules so the
        model gets a good sample of both matches and non-matches.
        """
        self.logger.info("    -> EM Pass 1/3 (Blocking on Last Name & Birth Year)...")
        # Session 1: train on people with identical last name + birth year
        self.linker.training.estimate_u_using_random_sampling(max_pairs=1e7)
        self.linker.training.estimate_parameters_using_expectation_maximisation(
            block_on("last_name", "birth_year")
        )

        self.logger.info("    -> EM Pass 2/3 (Blocking on First Name & Birth Year)...")
        # Session 2: second pass with first name + birth year to sharpen weights
        self.linker.training.estimate_parameters_using_expectation_maximisation(
            block_on("first_name", "birth_year")
        )

        self.logger.info("    -> EM Pass 3/3 (Blocking on First Name & Last Name)...")
        # Session 3: third pass with full name to safely train the birth_year weights
        self.linker.training.estimate_parameters_using_expectation_maximisation(
            block_on("first_name", "last_name")
        )

        self.logger.info("    -> Training complete.")

    def _predict_and_cluster(self) -> pd.DataFrame:
        """
        Generate pairwise match scores, then group matched pairs into clusters.
        Returns a pandas DataFrame with one row per original record, each
        annotated with its cluster_id.
        """
        predictions = self.linker.inference.predict(
            threshold_match_probability=self.MATCH_THRESHOLD
        )
        clusters = self.linker.clustering.cluster_pairwise_predictions_at_threshold(
            predictions,
            threshold_match_probability=self.MATCH_THRESHOLD,
        )
        # Materialize to pandas. This is the only point where data
        # comes off DuckDB into RAM — only the clustered subset, not all 844M rows.
        cluster_df = clusters.as_pandas_dataframe()
        self.logger.info(f"    -> Clustering yielded {cluster_df['cluster_id'].nunique():,} unique clusters.")
        return cluster_df

    def _generate_survivor_records(self, cluster_df: pd.DataFrame, registry: IdentityRegistry) -> pd.DataFrame:
        """
        Survivorship Rules — Census is primary, BIRLS only fills blanks.
        
        For every field, the logic is:
        STEP 1 — Gather only the census rows in this cluster.
        STEP 2 — Pick the best census value using frequency + recency.
        STEP 3 — BIRLS patches only NULLs.
        STEP 4 — Preserve all vault pointers.
        """
        golden_records = []

        for cluster_id, group in cluster_df.groupby("cluster_id"):

            # Split into census rows and BIRLS rows
            census_rows = group[group["source_db"] == "census"].copy()
            death_rows = group[group["source_db"] == "death_index"].copy()
            gedcom_rows = group[group["source_db"] == "gedcom"].copy()

            # ----------------------------------------------------------
            # STEP 2: Best census value via frequency + recency tiebreak
            # ----------------------------------------------------------
            def census_winner(col: str):
                if census_rows.empty or col not in census_rows.columns:
                    return None

                valid = census_rows[[col, "census_year"]].dropna(subset=[col])
                if valid.empty:
                    return None

                freq = valid[col].value_counts()
                max_freq = freq.iloc[0]
                top_spellings = freq[freq == max_freq].index.tolist()

                if len(top_spellings) == 1:
                    return top_spellings[0]

                tied_rows = valid[valid[col].isin(top_spellings)]
                latest_row = tied_rows.sort_values("census_year", ascending=False).iloc[0]
                return latest_row[col]

            first_name = census_winner("first_name")
            last_name = census_winner("last_name")

            census_birth_years = pd.to_numeric(
                census_rows["birth_year"], errors="coerce"
            ).dropna() if not census_rows.empty else pd.Series(dtype=float)

            if len(census_birth_years) > 0:
                median_yr = census_birth_years.median()
                plausible = census_birth_years[abs(census_birth_years - median_yr) <= 10]
                if len(plausible) > 0:
                    best_birth_year = int(plausible.value_counts().index[0])
                else:
                    best_birth_year = int(median_yr)
            else:
                best_birth_year = None

            state = census_winner("state")
            birth_place = census_winner("birth_place")
            father_ptr = census_winner("father_pointer")
            mother_ptr = census_winner("mother_pointer")

            death_dod = None
            death_dob = None
            if not death_rows.empty:
                if "dod" in death_rows.columns:
                    dod_vals = death_rows["dod"].dropna()
                    death_dod = dod_vals.iloc[0] if len(dod_vals) > 0 else None
                if "dob" in death_rows.columns:
                    dob_vals = death_rows["dob"].dropna()
                    death_dob = dob_vals.iloc[0] if len(dob_vals) > 0 else None

            if not gedcom_rows.empty:
                if "death_date" in gedcom_rows.columns:
                    dod_vals = gedcom_rows["death_date"].dropna()
                    death_dod = dod_vals.iloc[0] if len(dod_vals) > 0 else death_dod

            if best_birth_year is None and death_dob is not None:
                try:
                    death_year = int(str(death_dob).strip()[-4:])
                    if 1800 <= death_year <= 1945:
                        best_birth_year = death_year
                except (ValueError, TypeError):
                    pass

            # Collect all unique census years this person appeared in
            if not census_rows.empty and "census_year" in census_rows.columns:
                years_list = sorted(census_rows["census_year"].dropna().unique().tolist())
                census_years_str = "|".join(str(int(y)) for y in years_list)
            else:
                census_years_str = None

            all_pointers = group["unique_id"].astype(str).tolist()

            # ----------------------------------------------------------
            # PERMANENT HUMAN ID (The Registry Anchor Strategy)
            # ----------------------------------------------------------
            full_name = f"{first_name or ''} {last_name or ''}".strip().upper()
            permanent_golden_id = registry.get_or_mint_master_id(all_pointers, full_name)

            golden = {
                "golden_id": permanent_golden_id,
                "first_name": first_name,
                "last_name": last_name,
                "birth_year": best_birth_year,
                "birth_place": birth_place,
                "state": state,
                "death_date": death_dod,
                "census_years": census_years_str,
                "record_count": len(group),
                "census_count": len(census_rows),
                "death_record_count": len(death_rows),
                "gedcom_count": len(gedcom_rows),
                "vault_pointers": "|".join(all_pointers),
                "father_pointer": father_ptr,
                "mother_pointer": mother_ptr,
                "st_joes_patrilineal_id": None,
                "st_joes_matrilineal_id": None
            }
            golden_records.append(golden)

        return pd.DataFrame(golden_records)

    def _write_golden_records(self, golden_df: pd.DataFrame, output_table: str):
        """
        Writes the golden records DataFrame into the CleanVault SQLite database
        via DuckDB.  Creates the table if it doesn't exist; appends if it does
        (so you can run one state at a time and accumulate results).
        """
        self.con.register("golden_records_staging", golden_df)

        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS {output_table} (
                golden_id       VARCHAR PRIMARY KEY,
                first_name      VARCHAR,
                last_name       VARCHAR,
                birth_year      INTEGER,
                birth_place     VARCHAR,
                state           VARCHAR,
                death_date      VARCHAR,   -- from Death Index only; census has none
                census_years    VARCHAR,   -- pipe-delimited list of all census years found
                record_count    INTEGER,   -- total rows merged (census + Death Index)
                census_count    INTEGER,   -- how many census rows contributed
                death_record_count INTEGER, -- how many Death Index rows contributed
                gedcom_count    INTEGER,   -- how many GEDCOM rows contributed
                vault_pointers  VARCHAR,   -- pipe-delimited list of all source unique_ids
                father_pointer  VARCHAR,
                mother_pointer  VARCHAR,
                st_joes_patrilineal_id VARCHAR, -- The Patrilineal Lineage Clan ID (Y-DNA)
                st_joes_matrilineal_id VARCHAR  -- The Matrilineal Lineage Clan ID (mtDNA)
            );
        """)

        self.con.execute(f"""
            INSERT INTO {output_table}
            SELECT
                golden_id,
                first_name,
                last_name,
                birth_year,
                birth_place,
                state,
                death_date,
                census_years,
                record_count,
                census_count,
                death_record_count,
                gedcom_count,
                vault_pointers,
                father_pointer,
                mother_pointer,
                st_joes_patrilineal_id,
                st_joes_matrilineal_id
            FROM (
                -- Deduplicate the batch before insertion in case IdentityRegistry issued the same ID twice
                SELECT *, ROW_NUMBER() OVER (PARTITION BY golden_id ORDER BY record_count DESC) as dedupe_rn
                FROM golden_records_staging
            ) deduplicated
            WHERE dedupe_rn = 1
              AND golden_id NOT IN (
                SELECT golden_id FROM {output_table}
            );
        """)

        self.logger.info(f"    -> Write to {output_table} complete.")
