import logging
import time
from pathlib import Path
from typing import Any, NamedTuple, Optional

import requests
from fastembed import TextEmbedding
from numpy import ndarray

from .queue_utils import HarvestEventQueue


class SourceWithEmbeddingText(NamedTuple):
    src: dict[str, Any]  # 0, source document
    textToEmbed: str  # 1, text to be embedded
    event: HarvestEventQueue  # 2, original harvest event


class OpenSearchSourceWithEmbedding(NamedTuple):
    src: dict[str, Any]
    harvest_event: HarvestEventQueue


def get_embedding_text_from_fields(source: dict[str, Any]) -> str:
    """
    Given a source document, extracts the text fields to be embedded and joins them to a single string.

    :param source: the source document.
    :return: the string to be embedded.
    """
    return ' '.join(
        extract_fields_from_source(source, 'titles', 'title')
        + extract_fields_from_source(source, 'subjects', 'subject')
        + extract_fields_from_source(source, 'descriptions', 'description')
    )


def extract_fields_from_source(source: dict[str, Any], field_name: str, subfield_name: str) -> list[str]:
    """
    Given a source document, extracts the subfields for a given field name.

    :param source: the source document.
    :param field_name: name of the field.
    :param subfield_name: name of the subfield.
    :return: the subfield's values.
    """
    # check if field exists
    if field_name in source:
        return list(map(lambda title: title[subfield_name], source[field_name]))
    else:
        return []


def create_opensearch_source(
    src: dict[str, Any], embedding: list[float], batch_ele: SourceWithEmbeddingText, embedding_field_name: str
) -> OpenSearchSourceWithEmbedding:
    """


    :param src: document to be indexed
    :param embedding: embeddings to be added to source
    :param batch_ele: original element in batch
    :param embedding_field_name: name to be used for embedding field
    """

    return OpenSearchSourceWithEmbedding(
        src={
            **src,
            embedding_field_name: embedding,
            '_additional_metadata': batch_ele.event.additional_metadata,
            '_repo': batch_ele.event.code,
            '_harvest_url': batch_ele.event.harvest_url,
        },
        harvest_event=batch_ele.event,
    )


def _embed(
    texts: list[str],
    api_key: str,
    base_url: str,
    logger: logging.Logger,
    model: str = 'nomic-embed-text-v2-moe',
    prefix: str = 'search_document: ',
    batch_size: int = 16,
    max_chars: int = 1000,
    retries: int = 4,
    timeout: int = 120,
) -> list[list[float]]:
    """Embed a list of texts, returning one vector per text, in the same order.

    prefix: 'search_document: ' for things you store, 'search_query: ' for a user query.
            nomic needs it, and the wrong one silently degrades retrieval.
    max_chars: the model window is 512 tokens; longer texts are cut, and cut harder if the
               endpoint still rejects them (it ignores truncate_prompt_tokens).
    """
    session = requests.Session()
    session.headers['Authorization'] = f'Bearer {api_key}'
    vectors: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        cap = max_chars
        for attempt in range(retries):
            try:
                response = session.post(
                    f'{base_url}/embeddings',
                    json={'model': model, 'input': [prefix + text[:cap] for text in batch]},
                    timeout=timeout,
                )
                if response.status_code == 400 and 'context length' in response.text:
                    cap //= 2  # too long even cut, try harder before giving up
                    logger.info(f'Reducing max chars to {cap}')
                    continue
                if not response.ok:
                    request_headers = dict(response.request.headers)
                    request_headers['Authorization'] = 'Bearer ***'

                    logger.error(
                        f'Embedding request failed (batch start={start}, attempt={attempt}): '
                        f'{response.status_code} {response.reason}\n'
                        f'Request URL: {response.request.url}\n'
                        f'Request headers: {request_headers}\n'
                        f'Response headers: {dict(response.headers)}\n'
                        f'Response body: {response.text}'
                    )
                response.raise_for_status()
                # the API may answer out of order, so sort by index before taking the vectors
                data = sorted(response.json()['data'], key=lambda item: item['index'])
                vectors.extend(item['embedding'] for item in data)
                break
            except requests.RequestException:
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt)  # 1s, 2s, 4s
        else:
            raise RuntimeError(f'embeddings failed for batch at {start} after {retries} attempts')

    return vectors


def _embed_locally(texts: list[str], embedding_model: TextEmbedding) -> list[list[float]]:
    """Embed texts using the local model, returning plain Python lists (not ndarrays)."""
    embeddings_ndarr = list(embedding_model.embed(texts))
    return [emb.tolist() for emb in embeddings_ndarr]


def add_embeddings_to_source(
    batch: list[SourceWithEmbeddingText],
    embedding_model: TextEmbedding,
    model_name: str | None,
    embedding_field_name: str = 'emb',
    api_key: str | None = None,
    base_url: str | None = None,
    logger: logging.Logger | None = None,
) -> list[OpenSearchSourceWithEmbedding]:
    """
    Given a batch of `SourceWithEmbeddingText`, calculates the embeddings and returns the documents with the embeddings (integrated).

    :param batch: a batch of source documents with their embedding texts.
    :param embedding_model: the model to be used for embedding (used only if `api_key` is not set).
    :param model_name: name of the embedding model
    :param embedding_field_name: name of the embedding field in the source document.
    :param api_key: optional API key. If set, embeddings are calculated via a remote API call
        instead of locally.
    :param base_url: base URL of the embedding API (only used if `api_key` is set).
    :param logger: optional logger for reporting fallback/errors. If not set, a module-level logger is used.
    """
    logger = logger or logging.getLogger(__name__)
    embedding_texts = [ele.textToEmbed for ele in batch]

    if api_key and base_url and model_name:
        name_parts = model_name.split('/')
        embedding_model_name = name_parts[-1] if len(name_parts) > 1 else name_parts[0]
        try:
            embeddings = _embed(
                embedding_texts,
                logger=logger,
                api_key=api_key,
                base_url=base_url,
                model=embedding_model_name,
                batch_size=len(batch),
            )
            logger.info(f'Embeddings calculated for {embedding_model_name} from with API')
        except (requests.RequestException, RuntimeError):
            logger.exception('Embedding API failed after retries with, falling back to local model.')
            embeddings = _embed_locally(embedding_texts, embedding_model)
    else:
        logger.info(f'calculating embeddings locally')
        embeddings = _embed_locally(embedding_texts, embedding_model)

    if len(embeddings) != len(batch):
        raise ValueError('Embedding model returned an unexpected number of vectors.')

    return [
        create_opensearch_source(batch_ele.src, emb_ele, batch_ele, embedding_field_name)
        for batch_ele, emb_ele in zip(
            batch,  # original batch
            embeddings,  # embeddings
        )
    ]


def preprocess_batch(batch: list[dict[str, Any]], index_name: str) -> list[dict[str, Any]]:
    """
    Given a list of source documents, builds the structure for OpenSearch.

    :param batch: batch of source documents.
    :param index_name: name of the OpenSearch index.
    :return: a list of prepared documents for import.
    """
    return [{'_op_type': 'index', '_id': ele['id'], '_index': index_name, '_source': ele} for ele in batch]
