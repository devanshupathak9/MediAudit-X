"""Step 1: create the empty indexes (like creating empty tables in a database).

Each file in mappings/ becomes one index with the same name.
Running it again deletes the old index and creates a fresh one.

    python create_indices.py
"""
import json

from es_client import MAPPINGS_DIR, es

for mapping_file in sorted(MAPPINGS_DIR.glob("*.json")):
    index_name = mapping_file.stem  # "patient-events.json" -> "patient-events"
    body = json.loads(mapping_file.read_text())

    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"deleted old index: {index_name}")

    es.indices.create(index=index_name, settings=body["settings"], mappings=body["mappings"])
    print(f"created index:     {index_name}")
