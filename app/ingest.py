"""PyMuPDF-based PDF ingestion: parse → chunk per page with paragraph-aware grouping."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pymupdf  # fitz
import tiktoken

from app.logging import get_logger
from app.models import Chunk

log = get_logger(__name__)

PDF_MAGIC = b"%PDF-"

# Chunking knobs.
CHUNK_TOKENS = 500
OVERLAP_TOKENS = 60
_ENC = tiktoken.get_encoding("cl100k_base")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def verify_pdf_bytes(data: bytes) -> bool:
    return len(data) >= 5 and data[:5] == PDF_MAGIC


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split_tokens(text: str, size: int, overlap: int) -> list[str]:
    """Hard token-window split — used as a fallback for monster paragraphs."""
    if not text.strip():
        return []
    toks = _ENC.encode(text)
    if len(toks) <= size:
        return [text]
    out: list[str] = []
    step = max(1, size - overlap)
    for start in range(0, len(toks), step):
        window = toks[start : start + size]
        if not window:
            break
        out.append(_ENC.decode(window))
        if start + size >= len(toks):
            break
    return out


def _chunk_paragraph_aware(
    text: str, max_tokens: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS
) -> list[str]:
    """Greedy pack paragraphs up to max_tokens.

    Respects natural paragraph boundaries (blank lines). Falls back to
    token-window split for paragraphs that exceed max_tokens on their own.
    """
    paragraphs = [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_toks = 0
    for p in paragraphs:
        p_toks = len(_ENC.encode(p))
        if p_toks > max_tokens:
            if current:
                chunks.append("\n\n".join(current))
                current, current_toks = [], 0
            chunks.extend(_split_tokens(p, max_tokens, overlap))
            continue
        if current_toks + p_toks <= max_tokens:
            current.append(p)
            current_toks += p_toks
        else:
            chunks.append("\n\n".join(current))
            current = [p]
            current_toks = p_toks
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def parse_pdf(path: Path) -> list[tuple[int, str]]:
    """Returns [(page_number_1_indexed, text), ...]."""
    pages: list[tuple[int, str]] = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append((i, text.strip()))
    return pages


def _chunk_id(doc_id: str, page: int, idx: int) -> str:
    """Deterministic ID so re-ingests overwrite, not duplicate."""
    return hashlib.sha1(f"{doc_id}|p{page}|i{idx}".encode()).hexdigest()


def chunk_pages(pages: list[tuple[int, str]], doc_id: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_no, text in pages:
        for idx, piece in enumerate(_chunk_paragraph_aware(text)):
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(doc_id, page_no, idx),
                    doc_id=doc_id,
                    text=piece,
                    page=page_no,
                )
            )
    return chunks


def ingest_pdf(path: Path) -> tuple[str, list[Chunk]]:
    data = path.read_bytes()
    if not verify_pdf_bytes(data):
        raise ValueError(f"{path}: not a valid PDF (magic byte check failed)")
    doc_id = sha256_of(data)
    log.info("ingest.start", path=str(path), doc_id=doc_id[:12], bytes=len(data))
    pages = parse_pdf(path)
    chunks = chunk_pages(pages, doc_id)
    log.info(
        "ingest.done",
        doc_id=doc_id[:12],
        n_pages=len(pages),
        n_chunks=len(chunks),
    )
    return doc_id, chunks


if __name__ == "__main__":
    import sys

    from app.logging import configure_logging

    configure_logging()
    p = Path(sys.argv[1] if len(sys.argv) > 1 else "data/sample.pdf")
    doc_id, chunks = ingest_pdf(p)
    print(f"\ndoc_id: {doc_id}")
    print(f"chunks: {len(chunks)}\n")
    for i, c in enumerate(chunks[:3]):
        print(f"--- chunk {i} | page={c.page} ---")
        print(c.text[:240])
        print()
