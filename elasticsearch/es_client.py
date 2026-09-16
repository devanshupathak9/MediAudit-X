"""Connect to the local Elasticsearch. Every other script imports `es` from here."""
from pathlib import Path

from elasticsearch import Elasticsearch

ES_URL = "http://localhost:9200"

# Paths used by the scripts
ES_DIR = Path(__file__).parent
ROOT = ES_DIR.parent
MAPPINGS_DIR = ES_DIR / "mappings"
DATA_DIR = ROOT / "data"

es = Elasticsearch(ES_URL)
