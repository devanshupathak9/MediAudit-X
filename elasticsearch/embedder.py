"""Pick the embedding model from .env and return it as a LangChain `Embeddings`.

  EMBEDDING_PROVIDER=openai  -> OpenAI text-embedding-3-small (1536 dims), needs OPENAI_API_KEY
  EMBEDDING_PROVIDER=local   -> BAAI/bge-small-en-v1.5 (384 dims), free, offline backup

Indexing and searching MUST use the same model. The model name is saved on the
index when it is created, and search refuses to run if they don't match.
"""
import os

from langchain_core.embeddings import Embeddings

import es_client  # noqa: F401  (loads .env)

PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai").lower()

if PROVIDER == "openai":
    MODEL_NAME = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}[MODEL_NAME]
elif PROVIDER == "local":
    MODEL_NAME = "BAAI/bge-small-en-v1.5"
    DIMS = 384
else:
    raise SystemExit(f"EMBEDDING_PROVIDER must be 'openai' or 'local', got {PROVIDER!r}")


class LocalEmbeddings(Embeddings):
    """fastembed wrapped in LangChain's Embeddings interface."""

    def __init__(self):
        from fastembed import TextEmbedding
        self.model = TextEmbedding(MODEL_NAME)

    def embed_documents(self, texts):
        return [v.tolist() for v in self.model.embed(texts)]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


def get_embeddings() -> Embeddings:
    if PROVIDER == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY missing. Add it to .env in the project root "
                             "(or set EMBEDDING_PROVIDER=local).")
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=MODEL_NAME)
    return LocalEmbeddings()
