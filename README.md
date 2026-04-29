# PDF Agent

Chat with a PDF. Every answer cites the exact page and a verbatim quote. If the answer isn't in the document, the agent refuses and points to the closest related passage.

![Architecture](docs/architecture.png)

## Run it

```sh
cp .env.example .env       # fill in OPENAI_API_KEY and PINECONE_API_KEY
uv sync                    # backend deps
cd ui && npm install && cd ..   # frontend deps

make api    # FastAPI on :8000
make ui     # Next.js on :3000
```

Open http://localhost:3000.

## Eval

```sh
make eval     # 11 queries, binary pass/fail
make ragas    # Ragas metrics
```

Latest run on `data/sample.pdf`:

```
Binary suite     11/11 pass   (5 valid + 3 OOS + 3 multilingual)

Ragas (n=8)
  faithfulness        0.948
  context_precision   0.951
  context_recall      1.000
```

## Layout

```
app/    backend (FastAPI, LangGraph agent, Pinecone, OpenAI)
ui/     Next.js 15 frontend (PDF viewer + streaming chat)
evals/  binary suite + Ragas
data/   sample.pdf
```

## Deploy

`render.yaml` ships a two-service Render blueprint (API + UI, both free tier).
The instructions are in `SUBMISSION.pdf`.

## Submission docs

- [`SUBMISSION.pdf`](SUBMISSION.pdf) — problem, architecture, eval, future work
- [`TECHNICAL_NOTE.pdf`](TECHNICAL_NOTE.pdf) — architecture, decisions, trade-offs
- [`TEST_INSTRUCTIONS.pdf`](TEST_INSTRUCTIONS.pdf) — what to try, eval reproduction
