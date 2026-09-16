"""Free local embedding model. Downloads once (~130 MB), then works offline.

BAAI/bge-small-en-v1.5 turns text into 384 numbers that represent its meaning,
so "patient weight" ends up close to "body mass index".
"""
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMS = 384  # must match "dims" in mappings/payer-policies.json

_model = None


def embed(texts: list[str]) -> list[list[float]]:
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME)
    return [vector.tolist() for vector in _model.embed(texts)]
