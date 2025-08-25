from pathlib import Path
from typing import Any, NamedTuple
from fastembed import TextEmbedding

class SourceWithEmbeddingText(NamedTuple):
    src: dict[str, Any] # 0
    textToEmbed: str # 1
    file: Path # 2

def get_embedding_text_from_fields(source: dict[str, Any]) -> str:
    return ' '.join(extract_fields_from_source(source, 'titles', 'title') + extract_fields_from_source(source, 'subjects',
                                                                                       'subject') + extract_fields_from_source(
        source, 'descriptions', 'description'))


def extract_fields_from_source(source: dict[str, Any], field_name: str, subfield_name: str) -> list[str]:
    # check if field exists
    if field_name in source:
        return list(map(lambda title: title[subfield_name], source[field_name]))
    else:
        return []

def add_embeddings_to_source(batch: list[SourceWithEmbeddingText], embedding_model: TextEmbedding) -> list[tuple[dict[str, Any], Path]]:
    embeddings = list(embedding_model.embed(list(map(lambda ele: ele[1], batch))))
    src_emb = zip(list(map(lambda ele: ele[0], batch)), embeddings, list(map(lambda ele: ele[2], batch)))
    return list(map(lambda ele: ({**ele[0], 'emb': ele[1].tolist()}, ele[2]), src_emb))


def preprocess_batch(batch: list[dict[str, Any]], index_name: str) -> list[dict[str, Any]]:
    return list(map(lambda ele: {"_op_type": "index", "_index": index_name, "_source": ele}, batch))
