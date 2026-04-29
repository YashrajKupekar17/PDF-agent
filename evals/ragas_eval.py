"""Quantitative eval with Ragas: faithfulness + answer relevancy + context precision/recall.

Runs the agent on every 'valid' test query, captures the retrieved contexts,
then asks Ragas to score the (question, answer, contexts, ground_truth) tuples.
Out-of-scope queries are skipped — Ragas metrics aren't meaningful on refusals.

Usage:  uv run python -m evals.ragas_eval
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

from app.agent import ask_with_hits
from app.config import settings
from app.logging import configure_logging
from app.pipeline import ingest_and_index

ROOT = Path(__file__).resolve().parent.parent
QUERIES_FILE = Path(__file__).resolve().parent / "test_queries.json"


def collect_samples() -> dict[str, list]:
    """Run the agent on every valid query, return Ragas-shaped lists."""
    suite = json.loads(QUERIES_FILE.read_text())
    doc_path = ROOT / suite["doc_path"]
    doc_id, _ = ingest_and_index(doc_path)

    questions: list[str] = []
    answers: list[str] = []
    contexts: list[list[str]] = []
    references: list[str] = []

    valid = [q for q in suite["queries"] if q.get("type") == "valid"]
    for i, q in enumerate(valid, 1):
        if i > 1:
            time.sleep(7)  # respect Cohere trial 10 RPM
        ans, hits = ask_with_hits(q["q"], doc_id=doc_id, session_id=f"ragas-{i}")
        if ans.refused:
            print(f"  [skip] {q['q'][:60]} — agent refused")
            continue
        questions.append(q["q"])
        answers.append(ans.answer)
        contexts.append([h.text for h in hits])
        # Ground truth: use the expected_behavior text as a soft proxy. Ragas
        # `context_recall` needs reference to score; with our short queries
        # this is good enough for relative comparisons.
        references.append(q.get("expected_behavior", ""))
        print(f"  [ok]   {q['q'][:60]}")

    return {
        "user_input": questions,
        "response": answers,
        "retrieved_contexts": contexts,
        "reference": references,
    }


def main() -> int:
    configure_logging()
    if not os.environ.get("OPENAI_API_KEY"):
        from app.config import settings

        os.environ["OPENAI_API_KEY"] = settings.openai_api_key

    print("Collecting samples (running agent on every valid query)…")
    samples = collect_samples()
    n = len(samples["user_input"])
    if n == 0:
        print("No samples collected — aborting.")
        return 1
    print(f"\nCollected {n} samples. Running Ragas evaluation…")

    ds = Dataset.from_dict(samples)
    judge_llm = LangchainLLMWrapper(
        ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, temperature=0)
    )
    judge_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model="text-embedding-3-small", api_key=settings.openai_api_key
        )
    )
    result = evaluate(
        ds,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=judge_llm,
        embeddings=judge_embeddings,
    )

    print("\n" + "=" * 60)
    print("Ragas metrics  (mean over the eval set)")
    print("-" * 60)
    df = result.to_pandas()
    metric_cols = [
        c
        for c in df.columns
        if c not in ("user_input", "response", "retrieved_contexts", "reference")
    ]
    for col in metric_cols:
        vals = df[col].dropna()
        if len(vals):
            print(f"{col:30s} {vals.mean():.3f}   (n={len(vals)})")
    print("=" * 60)
    out_path = ROOT / "evals" / "ragas_report.json"
    df.to_json(out_path, orient="records", indent=2)
    print(f"\nFull per-row report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
