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
from app.ingest import parse_pdf, sha256_of, verify_pdf_bytes
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


# ---- Studio: overview + suggested questions on upload -----------------------
class StudioOutput(BaseModel):
    overview: str
    suggested_questions: list[str]


_STUDIO_CACHE: dict[str, dict] = {}


def _generate_studio(doc_id: str) -> dict:
    from langchain_openai import ChatOpenAI

    path = UPLOAD_DIR / f"{doc_id}.pdf"
    pages = parse_pdf(path)
    full_text = "\n\n".join(t for _, t in pages if t.strip())
    if len(full_text) > 30000:
        full_text = full_text[:30000] + "\n\n[truncated]"

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        temperature=0,
        seed=42,
    ).with_structured_output(StudioOutput)
    prompt = (
        "Read the document below and produce:\n"
        "1. overview: 2-3 neutral sentences describing what the document is about.\n"
        "2. suggested_questions: exactly 5 short, specific questions a reader might "
        "ask whose answers are contained in the document. Phrase them naturally "
        "and concretely; avoid generic prompts.\n\n"
        f"<document>\n{full_text}\n</document>"
    )
    out: StudioOutput = llm.invoke(prompt)
    return out.model_dump()


@app.get("/studio/{doc_id}", response_model=StudioOutput)
def studio(doc_id: str):
    if "/" in doc_id or ".." in doc_id:
        raise HTTPException(400, "bad doc_id")
    path = UPLOAD_DIR / f"{doc_id}.pdf"
    if not path.exists():
        raise HTTPException(404, "doc not found")
    if doc_id in _STUDIO_CACHE:
        return _STUDIO_CACHE[doc_id]
    try:
        result = _generate_studio(doc_id)
    except Exception as e:
        log.error("studio.failed", doc_id=doc_id[:12], error=str(e)[:200])
        raise HTTPException(500, f"studio generation failed: {e}")
    _STUDIO_CACHE[doc_id] = result
    log.info("studio.generated", doc_id=doc_id[:12], n_questions=len(result["suggested_questions"]))
    return result


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
    """SSE: emits stage updates, token deltas during `generate`, then final answer."""
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
            async for event in GRAPH.astream_events(
                state, config=config, version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")
                metadata = event.get("metadata", {}) or {}
                node = metadata.get("langgraph_node")

                # Stage event: when each node begins.
                if kind == "on_chain_start" and name in _STAGE_LABELS:
                    yield f"data: {json.dumps({'type': 'stage', 'node': name, 'label': _STAGE_LABELS[name]})}\n\n"

                # Token streaming inside the `generate` node:
                # with_structured_output streams the JSON object as `content`.
                elif kind == "on_chat_model_stream" and node == "generate":
                    chunk = event["data"].get("chunk")
                    content = getattr(chunk, "content", "") or ""
                    if content:
                        yield f"data: {json.dumps({'type': 'args_delta', 'delta': content})}\n\n"

                # Capture the final (verified) answer.
                elif kind == "on_chain_end" and name in ("generate", "verify"):
                    output = event["data"].get("output")
                    if isinstance(output, dict) and output.get("answer") is not None:
                        latest_answer = output["answer"]

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
