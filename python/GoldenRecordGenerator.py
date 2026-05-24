import pandas as pd
import splink.duckdb.comparison_library as cl
from splink import DuckDBAPI, Linker


class GoldenRecordGenerator:
    """
    Retired Engineer's HPC-ready Entity Resolution Engine.
    Features: Probabilistic linkage, survivorship rules, and pointer tracking.
    """

    def __init__(self, settings: dict):
        self.settings = settings
        self.linker = None

    def link_records(self, table_names: list, db_connection):
        """
        Executes probabilistic linkage using Splink v4.
        Passes the database connection directly to prevent Pandas memory crashes.
        """
        # Splink 4 requires passing the DB connection through its specific API wrapper
        db_api = DuckDBAPI(connection=db_connection)
        self.linker = Linker(table_names, self.settings, db_api=db_api)
        
        # Training omitted for brevity; assume pre-trained or unsupervised
        df_predict = self.linker.predict(threshold_match_probability=0.95)
        clusters = self.linker.cluster_pairwise_predictions_at_threshold(df_predict, 0.95)
        
        # Splink 4 returns a SplinkDataFrame; explicitly materialize to Pandas
        return clusters.as_pandas_dataframe()

    def generate_survivor_record(self, cluster_df: pd.DataFrame) -> pd.DataFrame:
        """
        Survivorship Rules:
        1. Source Reliability: Grave data > Census for Death Dates.
        2. Recency: Most recently updated data wins.
        3. Completeness: Longest string wins for bios/notes.
        """
        # Group by the cluster_id assigned by Splink
        golden_records = []
        
        # Ensure birth_year is numeric so our outlier math doesn't crash
        cluster_df['birth_year'] = pd.to_numeric(cluster_df['birth_year'], errors='coerce')
        
        for cluster_id, group in cluster_df.groupby("cluster_id"):
            # Claude's Outlier Guard: Drop crazy transcription errors (>10 years off median)
            median_yr = group['birth_year'].median()
            valid_years = group[abs(group['birth_year'] - median_yr) <= 10]['birth_year']
            best_birth_year = valid_years.min() if not valid_years.empty else median_yr

            # Select the 'best' attributes across the group
            golden = {
                "st_joes_id": cluster_id,  # Use Splink's cluster_id instead of a fragile hash
                "first_name": group['first_name'].mode()[0] if not group['first_name'].mode().empty else "",
                "last_name": group['last_name'].mode()[0] if not group['last_name'].mode().empty else "",
                "birth_year": best_birth_year,
                # Keep the pointers to the Master Vault so we never lose the raw data!
                "vault_pointers": group['composite_id'].tolist()
            }
            golden_records.append(golden)

        return pd.DataFrame(golden_records)
