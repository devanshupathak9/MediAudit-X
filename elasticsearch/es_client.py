"""Shared settings and the Elasticsearch connection. Every script imports from here."""
import os
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

ES_DIR = Path(__file__).parent
ROOT = ES_DIR.parent
MAPPINGS_DIR = ES_DIR / "mappings"
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env")  # reads OPENAI_API_KEY, EMBEDDING_PROVIDER, ...

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
es = Elasticsearch(ES_URL)
