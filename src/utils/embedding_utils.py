from typing import Any, NamedTuple

from fastembed import TextEmbedding

from .queue_utils import HarvestEventQueue


class SourceWithEmbeddingText(NamedTuple):
    src: dict[str, Any]  # 0, source document
    textToEmbed: str  # 1, text to be embedded
    event: HarvestEventQueue  # 2, original harvest event


class SourceWithEmbedding(NamedTuple):
    src: dict[str, Any]
    embedding: list[float]
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


def add_embeddings_to_source(
    batch: list[SourceWithEmbeddingText], embedding_model: TextEmbedding, embedding_field_name: str = 'emb'
) -> list[SourceWithEmbedding]:
    """
    Given a batch of `SourceWithEmbeddingText`, calculates the embeddings and returns the documents with the embeddings (integrated).

    :param batch: a batch of source documents with their embedding texts.
    :param embedding_model: the model to be used for embedding.
    :param embedding_field_name: name of the embedding field in the source document.
    """
    embedding_texts = [ele.textToEmbed for ele in batch]
    embeddings = list(embedding_model.embed(embedding_texts))

    if len(embeddings) != len(batch):
        raise ValueError('Embedding model returned an unexpected number of vectors.')

    return [
        SourceWithEmbedding(src=batch_ele.src, embedding=emb_ele.tolist(), harvest_event=batch_ele.event)
        for batch_ele, emb_ele in zip(
            batch,  # original batch
            embeddings,  # embeddings
        )
    ]
