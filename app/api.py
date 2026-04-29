"""FastAPI backend: /upload, /chat, /chat/stream, /pdf rendering."""
from __future__ import annotations

import json
import uuid

import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.agent import GRAPH, ask
from app.config import settings
from app.ingest import sha256_of, verify_pdf_bytes
from app.logging import configure_logging, get_logger
from app.models import AgentAnswer
from app.pipeline import ingest_and_index

configure_logging()
log = get_logger(__name__)

UPLOAD_DIR = settings.data_dir / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PDF Agent", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class UploadResponse(BaseModel):
    doc_id: str
    n_chunks: int
    filename: str


class ChatRequest(BaseModel):
    query: str
    doc_id: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    answer: AgentAnswer
    session_id: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "must be a PDF file")
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "PDF too large (max 25 MB)")
    if not verify_pdf_bytes(data):
        raise HTTPException(400, "not a valid PDF (magic byte check failed)")
    doc_id = sha256_of(data)
    saved = UPLOAD_DIR / f"{doc_id}.pdf"
    if not saved.exists():
        saved.write_bytes(data)
    try:
        doc_id_check, n = ingest_and_index(saved)
    except ValueError as e:
        raise HTTPException(400, str(e))
    assert doc_id == doc_id_check
    return UploadResponse(doc_id=doc_id, n_chunks=n, filename=file.filename)


@app.get("/pdf/{doc_id}/page/{page_no}")
def render_page(doc_id: str, page_no: int, dpi: int = 120):
    """Render one page of a previously-uploaded PDF as PNG."""
    if "/" in doc_id or ".." in doc_id:
        raise HTTPException(400, "bad doc_id")
    path = UPLOAD_DIR / f"{doc_id}.pdf"
    if not path.exists():
        raise HTTPException(404, "doc not found")
    with pymupdf.open(path) as doc:
        if page_no < 1 or page_no > len(doc):
            raise HTTPException(404, f"page {page_no} out of range (1..{len(doc)})")
        pix = doc[page_no - 1].get_pixmap(dpi=dpi)
        png = pix.tobytes("png")
    return Response(content=png, media_type="image/png")


@app.get("/pdf/{doc_id}/info")
def pdf_info(doc_id: str):
    if "/" in doc_id or ".." in doc_id:
        raise HTTPException(400, "bad doc_id")
    path = UPLOAD_DIR / f"{doc_id}.pdf"
    if not path.exists():
        raise HTTPException(404, "doc not found")
    with pymupdf.open(path) as doc:
        return {"doc_id": doc_id, "n_pages": len(doc)}


@app.get("/pdf/{doc_id}/raw")
def pdf_raw(doc_id: str):
    """Stream the raw PDF file bytes for in-browser viewers (react-pdf etc.)."""
    if "/" in doc_id or ".." in doc_id:
        raise HTTPException(400, "bad doc_id")
    path = UPLOAD_DIR / f"{doc_id}.pdf"
    if not path.exists():
        raise HTTPException(404, "doc not found")
    return Response(content=path.read_bytes(), media_type="application/pdf")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(400, "query is empty")
    session_id = req.session_id or str(uuid.uuid4())
    answer = ask(req.query, doc_id=req.doc_id, session_id=session_id)
    return ChatResponse(answer=answer, session_id=session_id)


_STAGE_LABELS = {
    "rewrite": "Rewriting query",
    "retrieve": "Searching",
    "rerank": "Ranking results",
    "generate": "Reading & writing",
    "verify": "Verifying citations",
}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events: emits stage updates per LangGraph node, then final answer."""
    if not req.query.strip():
        raise HTTPException(400, "query is empty")
    session_id = req.session_id or str(uuid.uuid4())

    async def event_stream():
        state = {
            "query": req.query,
            "rewritten_query": "",
            "doc_id": req.doc_id,
            "hits": [],
            "answer": None,
            "messages": [{"role": "user", "content": req.query}],
        }
        config = {"configurable": {"thread_id": session_id}}
        latest_answer: AgentAnswer | None = None
        try:
            async for chunk in GRAPH.astream(
                state, config=config, stream_mode="updates"
            ):
                for node, update in chunk.items():
                    label = _STAGE_LABELS.get(node, node)
                    yield f"data: {json.dumps({'type': 'stage', 'node': node, 'label': label})}\n\n"
                    if update and "answer" in update and update["answer"] is not None:
                        latest_answer = update["answer"]
            if latest_answer is not None:
                payload = {
                    "type": "answer",
                    "answer": latest_answer.model_dump(),
                    "session_id": session_id,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:  # noqa: BLE001
            log.error("chat_stream.error", error=str(e)[:200])
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=False)
