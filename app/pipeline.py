"""End-to-end ingest pipeline: parse → chunk → embed → upsert."""
from __future__ import annotations

import time
from pathlib import Path

from app.index import upsert_chunks
from app.ingest import ingest_pdf
from app.logging import get_logger

log = get_logger(__name__)


def ingest_and_index(path: Path) -> tuple[str, int]:
    t0 = time.time()
    doc_id, chunks = ingest_pdf(path)
    t1 = time.time()
    n = upsert_chunks(chunks)
    log.info(
        "pipeline.done",
        doc_id=doc_id[:12],
        n_chunks=n,
        parse_s=round(t1 - t0, 2),
        index_s=round(time.time() - t1, 2),
    )
    return doc_id, n


if __name__ == "__main__":
    import sys

    from app.logging import configure_logging

    configure_logging()
    p = Path(sys.argv[1] if len(sys.argv) > 1 else "data/sample.pdf")
    doc_id, n = ingest_and_index(p)
    print(f"\ndoc_id: {doc_id}\nindexed: {n} chunks")
