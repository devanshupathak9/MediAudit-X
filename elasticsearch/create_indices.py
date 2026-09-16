"""Step 1: create the empty indexes (like creating empty tables in a database).

Each file in mappings/ becomes one index with the same name.
Running it again deletes the old index and creates a fresh one.

For payer-policies, the vector size comes from the embedding model in .env,
and the model name is saved on the index so search can check it later.

    python create_indices.py
"""
import json

from embedder import DIMS, MODEL_NAME
from es_client import MAPPINGS_DIR, es

for mapping_file in sorted(MAPPINGS_DIR.glob("*.json")):
    index_name = mapping_file.stem  # "patient-events.json" -> "patient-events"
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
