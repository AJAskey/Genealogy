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
-----------------------------------
"""

import pandas as pd
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on


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
        ],
        blocking_rules_to_generate_predictions=[
            block_on("first_name", "last_name"),  # 1. Exact name match
            block_on("last_name", "birth_year"),  # 2. Catches first-name typos (e.g. Wm vs William)
            "l.first_name = r.first_name AND l.birth_year = r.birth_year AND substr(l.last_name, 1, 1) = substr(r.last_name, 1, 1)", # 3. Catches last-name typos, safely bounded to the same first letter!
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

    def run(self, output_table: str = "clean.golden_records"):
        """
        Full pipeline: train -> predict -> cluster -> survivorship -> write.

        Parameters
        ----------
        output_table : str
            Fully qualified DuckDB table name to write golden records into.
            Must use the 'clean.' prefix so it lands in CleanVault.db.
        """
        self.logger.info("=" * 60)
        self.logger.info("GoldenRecordGenerator: Starting pipeline")
        self.logger.info("=" * 60)

        self.logger.info("Step 1/5: Initializing Splink linker...")
        db_api = DuckDBAPI(connection=self.con)
        
        import os
        model_path = r"E:\Data\Genealogy_Data\splink_model.json"
        
        if os.path.exists(model_path):
            self.logger.info(f"Step 2/5: Found saved model. Loading brain from '{model_path}'...")
            self.linker = Linker(
                "population_for_splink",
                model_path,
                db_api=db_api,
            )
        else:
            self.logger.info("Step 2/5: Extracting 500k sample to prevent EM training Cartesian explosion...")
            self.con.execute("DROP TABLE IF EXISTS sample_for_splink;")
            self.con.execute("CREATE TABLE sample_for_splink AS SELECT * FROM population_for_splink USING SAMPLE 500000 ROWS;")

            self.linker = Linker(
                "sample_for_splink",
                self.SPLINK_SETTINGS,
                db_api=db_api,
            )
            self.logger.info("Step 2/5: Training match weights on sample (unsupervised EM)...")
            self._train()
            
            self.logger.info(f"          Saving AI brain to '{model_path}' for future runs...")
            self.linker.misc.save_model_to_json(model_path, overwrite=True)

            self.logger.info("          Reloading Linker with full dataset for predictions...")
            self.linker = Linker(
                "population_for_splink",
                model_path,
                db_api=db_api,
            )

        self.logger.info("Step 3/5: Predicting match scores and clustering...")
        cluster_df = self._predict_and_cluster()

        self.logger.info(f"Step 4/5: Applying survivorship rules to {len(cluster_df):,} clustered rows...")
        golden_df = self._generate_survivor_records(cluster_df)
        self.logger.info(f"          Produced {len(golden_df):,} unique golden records.")

        self.logger.info(f"Step 5/5: Writing golden records to {output_table}...")
        self._write_golden_records(golden_df, output_table)
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
        # Session 1: train on people with identical last name + birth year
        self.linker.training.estimate_u_using_random_sampling(max_pairs=1e7)
        self.linker.training.estimate_parameters_using_expectation_maximisation(
            block_on("last_name", "birth_year")
        )
        # Session 2: second pass with first name + birth year to sharpen weights
        self.linker.training.estimate_parameters_using_expectation_maximisation(
            block_on("first_name", "birth_year")
        )
        self.logger.info("          Training complete.")

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
        self.logger.info(f"          Clustering yielded {cluster_df['cluster_id'].nunique():,} unique clusters.")
        return cluster_df

    def _generate_survivor_records(self, cluster_df: pd.DataFrame) -> pd.DataFrame:
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
            birls_rows  = group[group["source_db"] == "birls"].copy()

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
            last_name  = census_winner("last_name")

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

            birls_dod = None
            birls_dob = None
            if not birls_rows.empty:
                if "dod" in birls_rows.columns:
                    dod_vals = birls_rows["dod"].dropna()
                    birls_dod = dod_vals.iloc[0] if len(dod_vals) > 0 else None
                if "dob" in birls_rows.columns:
                    dob_vals = birls_rows["dob"].dropna()
                    birls_dob = dob_vals.iloc[0] if len(dob_vals) > 0 else None

            if best_birth_year is None and birls_dob is not None:
                try:
                    birls_year = int(str(birls_dob).strip()[-4:])
                    if 1800 <= birls_year <= 1945:
                        best_birth_year = birls_year
                except (ValueError, TypeError):
                    pass

            all_pointers = group["unique_id"].astype(str).tolist()

            golden = {
                "cluster_id":    cluster_id,
                "first_name":    first_name,
                "last_name":     last_name,
                "birth_year":    best_birth_year,
                "state":         state,
                "death_date":    birls_dod,
                "record_count":  len(group),
                "census_count":  len(census_rows),
                "birls_count":   len(birls_rows),
                "vault_pointers": "|".join(all_pointers),
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
                cluster_id      VARCHAR,
                first_name      VARCHAR,
                last_name       VARCHAR,
                birth_year      INTEGER,
                state           VARCHAR,
                death_date      VARCHAR,   -- from BIRLS only; census has none
                record_count    INTEGER,   -- total rows merged (census + BIRLS)
                census_count    INTEGER,   -- how many census rows contributed
                birls_count     INTEGER,   -- how many BIRLS rows contributed
                vault_pointers  VARCHAR    -- pipe-delimited list of all source unique_ids
            );
        """)

        self.con.execute(f"""
            INSERT INTO {output_table}
            SELECT
                cluster_id,
                first_name,
                last_name,
                birth_year,
                state,
                death_date,
                record_count,
                census_count,
                birls_count,
                vault_pointers
            FROM golden_records_staging
            WHERE cluster_id NOT IN (
                SELECT cluster_id FROM {output_table}
            );
        """)

        self.logger.info(f"          Write to {output_table} complete.")
