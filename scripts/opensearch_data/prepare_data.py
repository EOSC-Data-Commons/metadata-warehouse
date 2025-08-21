import json
from pathlib import Path
from fastembed import TextEmbedding
import sys
from dotenv import load_dotenv
import os
from typing import Any

load_dotenv()

def write_source_with_embedding(src_with_emb:  list[tuple[dict[str, Any], Path]]):
    print(f'writing batch of {len(batch)}')
    for ele in src_with_emb:
        with open(f'data/json_with_embedding/{os.path.basename(ele[1])}', 'w') as f:
            f.write(json.dumps(ele[0]))

embedding_model = os.environ['EMBEDDING_MODEL']
print(embedding_model)

# setting path
sys.path.append("..")
sys.path.append("../..")

from src.utils.embedding_utils import get_embedding_text_from_fields, add_embeddings_to_source

batch_size = 500
batch = []
files: list[Path] = (list(Path('data/json').rglob("*.json")))

embedding_transformer = TextEmbedding(model_name=embedding_model)

for file in files:
    source = json.load(open(file))

    batch.append((source, get_embedding_text_from_fields(source), file))
    if len(batch) == batch_size:
        # calculate embeddings for batch
        source_with_embeddings = add_embeddings_to_source(batch, embedding_transformer)
        write_source_with_embedding(source_with_embeddings)
        batch = []

if len(batch) > 0:
    source_with_embeddings = add_embeddings_to_source(batch, embedding_transformer)
    write_source_with_embedding(source_with_embeddings)
