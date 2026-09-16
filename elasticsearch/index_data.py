"""Step 2: load the patient history into patient-events.

Policies are indexed separately by index_policies.py (they need embeddings).

    python index_data.py
"""
import json

from elasticsearch import helpers

from es_client import DATA_DIR, es

# which file goes into which index, and which field is the document's id
FILES = [
    ("patient-events", DATA_DIR / "patients" / "demo-patients.events.jsonl", "event_id"),
]

for index_name, path, id_field in FILES:
    # a .jsonl file has one JSON document per line
    docs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    actions = [{"_index": index_name, "_id": doc[id_field], "_source": doc} for doc in docs]
    ok, errors = helpers.bulk(es, actions, raise_on_error=False)

    es.indices.refresh(index=index_name)  # make the docs searchable right away
    count = es.count(index=index_name)["count"]
    print(f"{index_name:<16} indexed {ok} docs, errors: {len(errors)}, total in index: {count}")
    for err in errors[:3]:
        print("   error:", err)
