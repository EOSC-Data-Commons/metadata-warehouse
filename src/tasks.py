import json
from pathlib import Path

from fastembed import TextEmbedding
from celery import Celery
from jsonschema.exceptions import ValidationError
from jsonschema.validators import validate
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
import xmltodict
from utils.embedding_utils import preprocess_batch, add_embeddings_to_source, SourceWithEmbeddingText, get_embedding_text_from_fields
from utils import normalize_datacite_json
from typing import Any

OAI_METADATA = 'http://www.openarchives.org/OAI/2.0/:metadata'
DATACITE_RESOURCE = 'http://datacite.org/schema/kernel-4:resource'
HAL_RESOURCE = 'http://www.openarchives.org/OAI/2.0/:resource'

def flush_bulk(client: OpenSearch, batch: list[dict[str, Any]]) -> None:
    success, failed = bulk(client, batch)
    print(success, failed)

celery_app = Celery('tasks')
#celery_app.task_serializer = 'json'
#celery_app.ignore_result = False

host = 'opensearch'
client = OpenSearch(
    hosts=[{'host': host, 'port': 9200}],
    http_auth=None,
    use_ssl=False
)

# TODO: make dedicated class for models, register with https://docs.celeryq.dev/en/stable/userguide/tasks.html#instantiation
embedding_transformer = TextEmbedding(model_name='snowflake/snowflake-arctic-embed-xs')

with open('config/schema.json') as f:
    schema = json.load(f)

@celery_app.task
def transform_batch(batch: list[str], index_name: str) -> int:
    # transform to JSON and normalize

    normalized = []
    for ele in batch:
        converted = xmltodict.parse(ele, process_namespaces=True)

        if OAI_METADATA in converted:
            metadata = converted[OAI_METADATA]
        else:
            # TODO: XML cannot be processed, log this
            continue

        if DATACITE_RESOURCE in metadata:
            resource = metadata[DATACITE_RESOURCE]
        elif HAL_RESOURCE in metadata:
            # HAL
            resource = metadata[HAL_RESOURCE]
        else:
            # TODO: XML cannot be processed, log this
            continue

        # Catch and log errors
        try:
            normalized_record = normalize_datacite_json.normalize_datacite_json(resource)
            validate(instance=normalized_record, schema=schema)
            normalized.append(SourceWithEmbeddingText(src=normalized_record, textToEmbed=get_embedding_text_from_fields(normalized_record), file=Path('')))
        except Exception as e:
            print(f'An error occurred during transformation: {e}')
            # TODO: use logger
        except ValidationError as e:
            print(f'Validation failed: {e.message}')
        finally:
            continue

    src_with_emb: list[tuple[dict[str, Any], Path]] = add_embeddings_to_source(normalized, embedding_transformer)
    preprocessed = preprocess_batch(list(map(lambda el: el[0], src_with_emb)), index_name)

    flush_bulk(client, preprocessed)

    return len(normalized)
