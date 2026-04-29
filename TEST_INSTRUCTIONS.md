# Test Instructions

## What you need

- Python 3.11+
- Node 20+
- API keys: **OpenAI** (required), **Pinecone** (required, free tier OK), **Cohere** (optional — reranker; the agent works without it), **LangSmith** (optional — tracing)
- About 5 minutes for setup

## Setup

```sh
# 1. Clone and enter the repo
git clone <repo-url> pdf-agent
cd pdf-agent

# 2. Configure environment
cp .env.example .env
# Edit .env and fill in OPENAI_API_KEY and PINECONE_API_KEY at minimum.

# 3. Python deps (uv handles the venv)
uv sync

# 4. Frontend deps
cd ui && npm install && cd ..
```

## Run

In one terminal:

```sh
make api    # FastAPI on http://localhost:8000
```

In a second terminal:

```sh
make ui     # Next.js on http://localhost:3000
```

Open http://localhost:3000 in a browser.

## What to try

### Sample PDF

The repo ships with `data/sample.pdf` — the assignment brief itself, 5 pages. Upload it from the empty-state card.

After upload you'll see an auto-generated overview and 5 suggested questions in the empty chat state.

### 5 valid queries (should answer with a citation)

1. *What is the date of this assignment?*
   Expected: page 1, quotes "Date: 22nd April 2026".
2. *What submission deliverables are required?*
   Expected: page 1, lists technical note + test instructions + demo video + optional deployed interface.
3. *What evaluation criteria are listed for the narrative-to-visual story task?*
   Expected: page 1-2, mentions coherence / scene breakdown / determinism / reproducibility.
4. *How many valid and out-of-scope queries do I need to provide for the PDF agent's test set?*
   Expected: page 4, "5 valid queries" and "3 invalid / out-of-scope queries".
5. *Does the assignment offer bonus credit for multilingual support?*
   Expected: page 4, "yes" with the bonus criteria quoted.

For each, you should see:
- An answer with markdown formatting
- A page chip like `[p.4]` you can click to jump the PDF viewer
- A "Show N sources" toggle that expands the verbatim quotes
- The cited text highlighted in yellow on the PDF preview

### 3 out-of-scope queries (should refuse)

1. *Who is the CEO of OpenAI?*
2. *What is 17 squared?*
3. *Summarise the latest news about Indian elections.*

For each, you should see:
- An amber refusal box, not an answer
- A "closest related passage" pointer

The agent will not hallucinate even if you push hard ("just guess", "your best estimate"). It refuses.

### Multilingual

Try one of these:

- Hindi: `इस असाइनमेंट की तारीख क्या है?`
- Hindi: `क्या मल्टीलिंगुअल सपोर्ट के लिए बोनस अंक मिलते हैं?`
- Marathi: `या असाइनमेंटसाठी कोणते डिलिव्हरेबल्स आवश्यक आहेत?`

Expected: answer in the same language (Devanagari script), citations stay verbatim in the English source.

### Conversation memory

After asking a question, ask a follow-up that uses a pronoun:

- *What's the deadline?*
- *And what about the bonus?* ← uses "the" without restating

The rewrite node should resolve the reference. Open LangSmith to see the rewritten query.

## Reproducing the eval numbers

```sh
make eval     # 11-query binary pass/fail suite (~90 seconds)
make ragas    # Ragas faithfulness / context precision / recall (~3 minutes)
```

Both write reports to `evals/`. The Ragas run prints a summary table and saves per-row JSON to `evals/ragas_report.json`.

## Try with your own PDF

Click "Switch document" in the header, drag in any PDF (max 25 MB). Anything that holds digital text will work. Heavily scanned image-only PDFs aren't supported in this build (no OCR fallback).

## Inspecting what the agent did

If you set `LANGSMITH_API_KEY`, every turn is traced. Open https://smith.langchain.com → project `pdf-agent`. Each trace is a tree showing the rewrite, retrieve, rerank, generate, and verify nodes with their inputs, outputs, latency, tokens, and cost.

## Known limitations

- Cohere trial key is rate-limited to 10 calls per minute. The eval suite spaces queries 7 seconds apart to stay under the limit. The agent itself catches the rate-limit error and falls back to the unranked top-K, so a single user won't notice.
- `gpt-4o-mini` returns 1 generation per request even when Ragas asks for 3, which inflates `answer_relevancy` variance. The other Ragas metrics are unaffected.
- Conversation memory lives in process memory (LangGraph `MemorySaver`) keyed by `session_id`. A backend restart drops it. The frontend persists the message log to `localStorage` so the user-visible chat survives a page refresh.
- No auth, no rate limiting on the API. Don't expose this to the public internet without putting it behind something.
