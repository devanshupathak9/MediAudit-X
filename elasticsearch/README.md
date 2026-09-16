# Elasticsearch

## Run it (first time)

```bash
make up          # 1. start Elasticsearch in Docker  (wait ~30s)
make install     # 2. create .venv and install the Python client
make setup       # 3. create indexes + load data
make search Q="patient weight too high"
make smoke       # 9 demo queries
```

Without `make`, the same thing:

```bash
cd elasticsearch
docker compose up -d
python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
../.venv/bin/python create_indices.py
../.venv/bin/python index_data.py        # patients
../.venv/bin/python index_policies.py    # policies + vectors (downloads model once)
../.venv/bin/python search_policies.py "patient weight too high" --mode all
```

## Files

| file | what it does |
| --- | --- |
| `docker-compose.yml` + `.env` | runs Elasticsearch 9.2.0 at http://localhost:9200 (security off, local only) |
| `mappings/*.json` | the shape of each index: field names and types |
| `es_client.py` | connects to Elasticsearch; other scripts import from it |
| `create_indices.py` | creates empty indexes from `mappings/` (deletes old ones first) |
| `index_data.py` | loads patient history into `patient-events` |
| `embedder.py` | free local embedding model `BAAI/bge-small-en-v1.5` (384 numbers per text) |
| `index_policies.py` | reads policy `.txt`, splits into sections, extracts metadata with regex, embeds, indexes |
| `search_policies.py` | keyword / vector / hybrid search over policy sections, with exact filters `--cpt --date --type` |
| `smoke_test.sh` | 9 demo queries, including the bi-temporal verdict flip |
