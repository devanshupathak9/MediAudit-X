"""One Elasticsearch client for everyone."""
from elasticsearch import Elasticsearch

from shared.config import ES_URL

es = Elasticsearch(ES_URL)


def index_model(index: str) -> str | None:
    """The embedding model an index was created for (saved in the mapping _meta)."""
    return es.indices.get_mapping(index=index)[index]["mappings"].get("_meta", {}).get("embedding_model")
