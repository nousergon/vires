"""Embedding pipeline — FastEmbed with bge-small-en-v1.5 (ONNX, 384-d).

Adapted from the author's mnemon project. ~13MB model, auto-downloaded on
first use to ``settings.fastembed_cache_dir``. No PyTorch, no GPU, no API key.
"""

from __future__ import annotations

import numpy as np

from api.config import get_settings

# bge-small-en-v1.5 is asymmetric: queries need this instruction prefix for
# good search relevance; indexed passages are embedded as-is.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None


def _get_model():
    """Lazy-load the embedding model (singleton)."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        s = get_settings()
        _model = TextEmbedding(model_name=s.embed_model, cache_dir=s.fastembed_cache_dir)
    return _model


def embed(text: str) -> np.ndarray:
    """Embed a single string. Returns ndarray of shape (dim,), float32."""
    model = _get_model()
    result = list(model.embed([text]))
    return np.asarray(result[0], dtype=np.float32)


def embed_batch(texts: list[str]) -> list[np.ndarray]:
    """Embed many passage strings in one pass (no query prefix)."""
    model = _get_model()
    return [np.asarray(r, dtype=np.float32) for r in model.embed(texts)]


def embed_query(text: str) -> np.ndarray:
    """Embed a search/dedup query with the bge instruction prefix."""
    return embed(QUERY_PREFIX + text)
