from pathlib import Path

import pytest

from app.ingest import (
    chunk_pages,
    ingest_pdf,
    parse_pdf,
    sha256_of,
    verify_pdf_bytes,
)
from app.models import Chunk

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample.pdf"


def test_verify_pdf_bytes():
    assert verify_pdf_bytes(b"%PDF-1.7\n...")
    assert not verify_pdf_bytes(b"<html>not pdf</html>")
    assert not verify_pdf_bytes(b"")


def test_sha256_is_deterministic():
    assert sha256_of(b"x") == sha256_of(b"x")
    assert len(sha256_of(b"x")) == 64


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample.pdf missing")
def test_parse_pdf_returns_pages():
    pages = parse_pdf(SAMPLE)
    assert len(pages) > 0
    assert all(isinstance(p, int) and p >= 1 for p, _ in pages)
    assert any(text.strip() for _, text in pages)


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample.pdf missing")
def test_ingest_pdf_produces_chunks_with_pages():
    doc_id, chunks = ingest_pdf(SAMPLE)
    assert len(doc_id) == 64
    assert len(chunks) > 0
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.doc_id == doc_id
        assert c.text.strip()
        assert c.page >= 1


def test_chunk_pages_handles_empty_text():
    out = chunk_pages([(1, ""), (2, "   ")], doc_id="d")
    assert out == []


def test_ingest_rejects_non_pdf(tmp_path):
    fake = tmp_path / "bad.pdf"
    fake.write_bytes(b"definitely not a pdf")
    with pytest.raises(ValueError, match="magic byte"):
        ingest_pdf(fake)
