from typing import Any

from fastembed import TextEmbedding


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

def preprocess_batch(batch: list[tuple[dict[str, Any], str]], embedding_model: TextEmbedding, index_name: str) -> list[dict[str, Any]]:
    embeddings = list(embedding_model.embed(list(map(lambda ele: ele[1], batch))))
    src_emb =  zip(list(map(lambda ele: ele[0], batch)), embeddings)
    return list(map(lambda ele: {"_op_type": "index", "_index": index_name, "_source": {**ele[0], 'emb': ele[1]}}, src_emb))
