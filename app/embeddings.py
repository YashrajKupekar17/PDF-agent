"""OpenAI embeddings (text-embedding-3-large)."""
from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")
    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(texts: list[str], batch: int = 64) -> list[list[float]]:
    if not texts:
        return []
    out: list[list[float]] = []
    client = _client()
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        resp = client.embeddings.create(
            model=settings.embedding_model,
            input=chunk,
            dimensions=settings.embedding_dim,
        )
        out.extend(d.embedding for d in resp.data)
    log.info("embeddings.embedded", n=len(texts), model=settings.embedding_model)
    return out


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
