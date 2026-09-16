"""Create the empty indexes from mappings/ (deletes existing ones first).

For payer-policies, the vector size comes from the embedding model in .env,
and the model name is saved on the index so indexing and search can check it.

    python elasticsearch/create_indices.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, for `shared`

from shared.config import MAPPINGS_DIR  # noqa: E402
from shared.embeddings import DIMS, MODEL_NAME  # noqa: E402
from shared.es import es  # noqa: E402

for mapping_file in sorted(MAPPINGS_DIR.glob("*.json")):
    index_name = mapping_file.stem
    body = json.loads(mapping_file.read_text())
    mappings = body["mappings"]

    if "chunk_vector" in mappings["properties"]:
        mappings["properties"]["chunk_vector"]["dims"] = DIMS
        mappings["_meta"] = {"embedding_model": MODEL_NAME}

    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"deleted old index: {index_name}")

    es.indices.create(index=index_name, settings=body["settings"], mappings=mappings)
    extra = f"  (vectors: {MODEL_NAME}, {DIMS} dims)" if "_meta" in mappings else ""
    print(f"created index:     {index_name}{extra}")
