import json
import os
from pathlib import Path

from fastembed import TextEmbedding
from celery import Celery, Task
from jsonschema.exceptions import ValidationError
from jsonschema.validators import validate
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, BulkIndexError
import xmltodict
from utils.embedding_utils import preprocess_batch, add_embeddings_to_source, SourceWithEmbeddingText, \
    get_embedding_text_from_fields
from utils import normalize_datacite_json
from typing import Any
import logging

logger = logging.getLogger(__name__)

OAI_METADATA = 'http://www.openarchives.org/OAI/2.0/:metadata'
DATACITE_RESOURCE = 'http://datacite.org/schema/kernel-4:resource'
HAL_RESOURCE = 'http://www.openarchives.org/OAI/2.0/:resource'

EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL')
if not EMBEDDING_MODEL:
    raise ValueError('Missing EMBEDDING_MODEL environment variable')

celery_app = Celery('tasks')
# celery_app.task_serializer = 'json'
# celery_app.ignore_result = False

class TransformTask(Task): # type: ignore

    embedding_transformer: TextEmbedding
    client: OpenSearch
    schema: dict[Any, Any]

    def __init__(self) -> None:

        if EMBEDDING_MODEL:
            self.embedding_transformer = TextEmbedding(model_name=EMBEDDING_MODEL)
            logger.info(f'Setting up embedding transformer with model {EMBEDDING_MODEL}')

        self.client = OpenSearch(
            hosts=[{'host': 'opensearch', 'port': 9200}],
            http_auth=None,
            use_ssl=False
        )

        with open('config/schema.json') as f:
            self.schema = json.load(f)


@celery_app.task(base=TransformTask, bind=True)
def transform_batch(self: Any, batch: list[str], index_name: str) -> Any:
    # transform to JSON and normalize

    logger.info(f'Starting processing batch of {len(batch)}')

    normalized = []
    for ele in batch:
        converted = xmltodict.parse(ele, process_namespaces=True)

        if OAI_METADATA in converted:
            metadata = converted[OAI_METADATA]
        else:
            # Converted JSON cannot be processed, log this
            logger.debug(f'Cannot access {OAI_METADATA} in : {converted}')
            continue

        if DATACITE_RESOURCE in metadata:
            resource = metadata[DATACITE_RESOURCE]
        elif HAL_RESOURCE in metadata:
            # HAL
            resource = metadata[HAL_RESOURCE]
        else:
            # JSON cannot be processed, log this
            logger.debug(f'Cannot access {DATACITE_RESOURCE} or {HAL_RESOURCE} in : {metadata}')
            continue

        # Catch and log errors
        try:
            normalized_record = normalize_datacite_json.normalize_datacite_json(resource)
            validate(instance=normalized_record, schema=self.schema)
            normalized.append(SourceWithEmbeddingText(src=normalized_record,
                                                      textToEmbed=get_embedding_text_from_fields(normalized_record),
                                                      file=Path('')))
        except Exception as e:
            logger.debug(f'An error occurred during transformation: {e}')
        except ValidationError as e:
            logger.debug(f'Validation failed: {e.message}')
        finally:
            continue

    try:
        logger.info(f'About to Calculate embeddings for {len(normalized)}')
        src_with_emb: list[tuple[dict[str, Any], Path]] = add_embeddings_to_source(normalized, self.embedding_transformer)
        logger.info(f'Calculated embeddings for {len(src_with_emb)}')
        preprocessed = preprocess_batch(list(map(lambda el: el[0], src_with_emb)), index_name)
    except Exception as e:
        logger.error(f'Could not calculate embeddings: {e}')
        raise e

    try:
        success, failed = bulk(self.client, preprocessed)
        logger.info(f'Bulk results: success {success} failed: {failed}')
    except BulkIndexError as e:
        logger.error(f'Bulk failed: {e}')
        raise e

    return success
