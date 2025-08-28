#!/usr/bin/env -S uv run --script

import json
from pathlib import Path
from fastembed import TextEmbedding
import sys
from dotenv import load_dotenv
import os
from typing import Any

load_dotenv()

# setting path
sys.path.append("..")
sys.path.append("../..")

from src.utils.embedding_utils import get_embedding_text_from_fields, add_embeddings_to_source, SourceWithEmbeddingText

INDEX_NAME = os.environ.get('INDEX_NAME')
EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL')
if not INDEX_NAME or not EMBEDDING_MODEL:
    raise ValueError("Missing INDEX_NAME environment variable")

BATCH_SIZE = 1000
INPUT_DIR = Path('data/json')
OUTPUT_DIR = Path('data/json_with_embedding')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def write_source_with_embedding(src_with_emb:  list[tuple[dict[str, Any], Path]]) -> None:
    print(f'writing batch of {len(src_with_emb)}')
    for ele in src_with_emb:
        with open(f'{OUTPUT_DIR}/{os.path.basename(ele[1])}', 'w') as f:
            f.write(json.dumps(ele[0]))

batch = []
files: list[Path] = list(INPUT_DIR.rglob('*.json'))
embedding_transformer = TextEmbedding(model_name=EMBEDDING_MODEL)

for file in files:
    with open(file) as f:
        source = json.load(f)

    batch.append(SourceWithEmbeddingText(src=source, textToEmbed=get_embedding_text_from_fields(source), file=file))
    if len(batch) >= BATCH_SIZE:
        # calculate embeddings for batch
        source_with_embeddings = add_embeddings_to_source(batch, embedding_transformer)
        write_source_with_embedding(source_with_embeddings)
        batch = []

if len(batch) > 0:
    source_with_embeddings = add_embeddings_to_source(batch, embedding_transformer)
    write_source_with_embedding(source_with_embeddings)
