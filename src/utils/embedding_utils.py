from pathlib import Path
from typing import Any, NamedTuple, Optional
from fastembed import TextEmbedding
from .queue_utils import HarvestEventQueue

class SourceWithEmbeddingText(NamedTuple):
    src: dict[str, Any] # 0, source document
    textToEmbed: str # 1, text to be embedded
    file: Path # 2, name of the original source file
    event: Optional[HarvestEventQueue] # 3, original harvest event

def get_embedding_text_from_fields(source: dict[str, Any]) -> str:
    """
    Given a source document, extracts the text fields to be embedded and joins them to a single string.

    :param source: the source document.
    :return: the string to be embedded.
    """
    return ' '.join(extract_fields_from_source(source, 'titles', 'title') + extract_fields_from_source(source, 'subjects',
                                                                                       'subject') + extract_fields_from_source(
        source, 'descriptions', 'description'))


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

def add_embeddings_to_source(batch: list[SourceWithEmbeddingText], embedding_model: TextEmbedding, embedding_field_name: str = 'emb') -> list[tuple[dict[str, Any], SourceWithEmbeddingText]]:
    """
    Given a batch of `SourceWithEmbeddingText`, calculates the embeddings and returns the documents with the embeddings (integrated).

    :param batch: a batch of source documents with their embedding texts.
    :param embedding_model: the model to be used for embedding.
    :param embedding_field_name: name of the embedding field in the source document.
    :return: a tuple of source documents with embeddings (0) and the original file name (1).
    """
    embeddings = list(embedding_model.embed(list(map(lambda ele: ele[1], batch))))
    src_emb = zip(
        list(map(lambda ele: ele[0], batch)),
        embeddings, batch
    )
    return list(map(lambda ele: ({**ele[0], embedding_field_name: ele[1].tolist()}, ele[2]), src_emb))


def preprocess_batch(batch: list[dict[str, Any]], index_name: str) -> list[dict[str, Any]]:
    """
    Given a list of source documents, builds the structure for OpenSearch.

    :param batch: batch of source documents.
    :param index_name: name of the OpenSearch index.
    :return: a list of prepared documents for import.
    """
    return list(map(lambda ele: {'_op_type': 'index', '_id': ele['id'], '_index': index_name, '_source': ele}, batch))
