# PDF Agent

Strict-grounded chat over a PDF. Every answer cites the exact page + verbatim quote;
out-of-scope queries are refused with the closest related passage.

## Stack

- **Parse**: PyMuPDF (page text, paragraph-aware chunking, ~500 tokens / 60 overlap)
- **Embed**: OpenAI `text-embedding-3-large` (1024-dim Matryoshka)
- **Index**: Pinecone serverless (cosine)
- **Agent**: LangGraph — `rewrite → retrieve → rerank → generate → verify`
  - History-aware query rewrite (gpt-4o-mini)
  - Cohere `rerank-3.5` over top-20, keep top-5 (graceful fallback on rate-limit)
  - Generate with `gpt-4o` + structured output (`AgentAnswer`)
  - Verifier: normalized substring + bag-of-words grounding check
- **API**: FastAPI (`/upload`, `/chat`, `/chat/stream` SSE, `/pdf/{id}/raw|info|page`)
- **UI**: Next.js 15 + Tailwind + react-pdf with citation jump + sources collapse
- **Tracing**: LangSmith (auto-traces every node when `LANGSMITH_API_KEY` is set)

## Setup

1. `cp .env.example .env` and fill in `OPENAI_API_KEY`, `PINECONE_API_KEY`,
   optionally `COHERE_API_KEY` (reranker), `LANGSMITH_API_KEY` (tracing).
2. `uv sync` (Python deps).
3. `cd ui && npm install` (frontend deps).

## Run

```sh
make api      # FastAPI on :8000
make ui       # Next.js on :3000
```

## Test

```sh
make test     # pytest (ingest + smoke)
make eval     # 11-query suite: 5 valid + 3 OOS + 3 multilingual
```

## Eval set

`evals/test_queries.json` — Hindi/Marathi queries on the English sample PDF
(`data/sample.pdf`) test cross-lingual grounding with citations remaining
verbatim in the source language.
