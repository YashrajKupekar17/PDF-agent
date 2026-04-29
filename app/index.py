"""Pinecone serverless index — upsert + query."""
from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

from pinecone import Pinecone, ServerlessSpec

from app.config import settings
from app.embeddings import embed_query, embed_texts
from app.logging import get_logger
from app.models import Chunk

log = get_logger(__name__)


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    text: str
    page: int
    score: float


@lru_cache(maxsize=1)
def _pc() -> Pinecone:
    if not settings.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is not set in .env")
    return Pinecone(api_key=settings.pinecone_api_key)


def ensure_index() -> None:
    pc = _pc()
    name = settings.pinecone_index
    existing = {i["name"] for i in pc.list_indexes()}
    if name in existing:
        return
    log.info("index.creating", name=name, dim=settings.embedding_dim)
    pc.create_index(
        name=name,
        dimension=settings.embedding_dim,
        metric="cosine",
        spec=ServerlessSpec(
            cloud=settings.pinecone_cloud,
            region=settings.pinecone_region,
        ),
    )
    while not pc.describe_index(name).status.get("ready"):
        time.sleep(1)
    log.info("index.created", name=name)


def _index():
    return _pc().Index(settings.pinecone_index)


def upsert_chunks(chunks: list[Chunk]) -> int:
    if not chunks:
        return 0
    ensure_index()
    vectors = embed_texts([c.text for c in chunks])
    payload = [
        {
            "id": c.chunk_id,
            "values": v,
            "metadata": {"doc_id": c.doc_id, "page": c.page, "text": c.text},
        }
        for c, v in zip(chunks, vectors)
    ]
    idx = _index()
    BATCH = 100
    for i in range(0, len(payload), BATCH):
        idx.upsert(vectors=payload[i : i + BATCH])
    log.info("index.upserted", n=len(payload), doc_id=chunks[0].doc_id[:12])
    return len(payload)


def query_index(
    query: str, doc_id: str | None = None, top_k: int = 5
) -> list[Hit]:
    qv = embed_query(query)
    flt = {"doc_id": {"$eq": doc_id}} if doc_id else None
    res = _index().query(
        vector=qv,
        top_k=top_k,
        filter=flt,
        include_metadata=True,
    )
    hits = [
        Hit(
            chunk_id=m["id"],
            doc_id=m["metadata"]["doc_id"],
            text=m["metadata"]["text"],
            page=int(m["metadata"]["page"]),
            score=float(m["score"]),
        )
        for m in res.get("matches", [])
    ]
    log.info("index.queried", q=query[:60], n=len(hits))
    return hits


def delete_doc(doc_id: str) -> None:
    _index().delete(filter={"doc_id": {"$eq": doc_id}})
    log.info("index.deleted_doc", doc_id=doc_id[:12])
