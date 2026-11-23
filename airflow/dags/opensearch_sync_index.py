"""Fill a NEW OpenSearch index from the records table.

Use case: OpenSearch got out of sync with the database (e.g. records were deleted manually in the DB). Instead of
reindexing every harvest run (`warehouse_reindex_provider`), the records table is copied as it is:

    create_index  ->  sync_records

* `create_index` creates the index (mapping from config/opensearch_mapping.json). If the index already exists the DAG
  run fails, nothing is changed.
* `sync_records` reads the records table with keyset pagination in batches of `batch_size` rows and bulk-indexes them.
  Nothing is calculated (embeddings and normalized metadata are stored in the table) and the table is not modified.

No retries: if the sync fails the index is left partially filled and a new run aborts because the index exists.
Delete the index and trigger the DAG again (there is no resume).
"""

import os
from datetime import timedelta

from airflow.sdk import Param, dag, get_current_context, task

DEFAULT_BATCH_SIZE = int(os.environ.get('CELERY_BATCH_SIZE', '250'))
# read when the DAG file is parsed; without it the parameter is required
DEFAULT_EMBEDDING_DIMS = {'default': int(os.environ['EMBEDDING_DIMS'])} if os.environ.get('EMBEDDING_DIMS') else {}


@dag(
    dag_id='warehouse_opensearch_sync_index',
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['warehouse'],
    params={
        'index_name': Param(
            type='string', minLength=1, description='Name of the NEW OpenSearch index (must not exist)'
        ),
        'batch_size': Param(DEFAULT_BATCH_SIZE, type='integer', minimum=1, description='Records per batch'),
        'embedding_dims': Param(
            **DEFAULT_EMBEDDING_DIMS,
            type='integer',
            minimum=1,
            description='Dimension of the embeddings (depends on EMBEDDING_MODEL)',
        ),
    },
)
def opensearch_sync_index() -> None:
    @task(retries=0)
    def create_index() -> None:
        from planning import opensearch_sync

        params = get_current_context()['params']
        opensearch_sync.create_index(params['index_name'], params['embedding_dims'])
        print(f'Created index {params["index_name"]}')

    # No retries: see the docstring of this file.
    @task(retries=0, execution_timeout=timedelta(days=14))
    def sync_records() -> None:
        from planning import opensearch_sync

        params = get_current_context()['params']
        indexed = opensearch_sync.sync_records(params['index_name'], params['batch_size'])
        print(f'Indexed {indexed} records in {params["index_name"]}')

    create_index() >> sync_records()


opensearch_sync_index()
