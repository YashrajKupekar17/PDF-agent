"""Run the eval suite: 5 valid + 3 out-of-scope queries.

Asserts:
- valid queries:   refused=False, at least one cited page in expected_pages,
                   and at least one of `must_contain_any` substrings appears
                   in the answer (case-insensitive).
- invalid queries: refused=True.

Prints a per-query table and overall pass-rate.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from app.agent import ask
from app.logging import configure_logging
from app.pipeline import ingest_and_index

ROOT = Path(__file__).resolve().parent.parent
QUERIES_FILE = Path(__file__).resolve().parent / "test_queries.json"


def load_queries() -> dict:
    return json.loads(QUERIES_FILE.read_text())


def ensure_indexed(doc_path: Path) -> str:
    doc_id, _ = ingest_and_index(doc_path)
    return doc_id


_SCRIPT_RANGES = {
    "devanagari": (0x0900, 0x097F),  # Hindi, Marathi, Sanskrit
    "tamil": (0x0B80, 0x0BFF),
    "bengali": (0x0980, 0x09FF),
}


def _has_script(text: str, script: str) -> bool:
    lo, hi = _SCRIPT_RANGES[script]
    return any(lo <= ord(ch) <= hi for ch in text)


def evaluate_valid(q: dict, ans) -> tuple[bool, str]:
    if ans.refused:
        return False, f"refused unexpectedly: {ans.refusal_reason!r}"
    cited_pages = {c.page for c in ans.citations}
    expected = set(q.get("expected_pages", []))
    if expected and not (cited_pages & expected):
        return False, f"page miss: cited {sorted(cited_pages)}, expected one of {sorted(expected)}"
    must = q.get("must_contain_any", [])
    if must:
        body = ans.answer.lower()
        if not any(s.lower() in body for s in must):
            return False, f"answer missing all of {must!r}: {ans.answer[:120]!r}"
    # Language check: if query was non-English, answer must be in that script
    script = q.get("script")
    if script and not _has_script(ans.answer, script):
        return False, f"answer not in expected {script} script: {ans.answer[:120]!r}"
    return True, "ok"


def evaluate_invalid(q: dict, ans) -> tuple[bool, str]:
    if not ans.refused:
        return False, f"answered instead of refusing: {ans.answer[:120]!r}"
    return True, "refused as expected"


def run() -> int:
    configure_logging()
    suite = load_queries()
    doc_path = ROOT / suite["doc_path"]
    if not doc_path.exists():
        print(f"missing PDF at {doc_path}", file=sys.stderr)
        return 2

    print(f"Indexing {doc_path}...")
    doc_id = ensure_indexed(doc_path)
    print(f"doc_id: {doc_id[:16]}...\n")

    rows = []
    valid_pass = invalid_pass = valid_total = invalid_total = 0
    multi_pass = multi_total = 0

    for i, q in enumerate(suite["queries"], 1):
        if i > 1:
            time.sleep(7)  # stay under Cohere trial 10 RPM
        t0 = time.time()
        ans = ask(q["q"], doc_id=doc_id, session_id=f"eval-{i}")
        elapsed = time.time() - t0
        if q["type"] == "valid":
            ok, why = evaluate_valid(q, ans)
            valid_total += 1
            valid_pass += int(ok)
        else:
            ok, why = evaluate_invalid(q, ans)
            invalid_total += 1
            invalid_pass += int(ok)
        if q.get("language") and q["language"] != "en":
            multi_total += 1
            multi_pass += int(ok)
        rows.append((i, q["type"], "PASS" if ok else "FAIL", elapsed, q["q"], why))

    # Print report
    print(f"\n{'='*88}")
    print(f"{'#':<3} {'TYPE':<8} {'STATUS':<6} {'TIME':>7}  QUERY")
    print(f"{'-'*88}")
    for i, kind, status, elapsed, q, why in rows:
        marker = "✅" if status == "PASS" else "❌"
        print(f"{i:<3} {kind:<8} {marker} {status:<4} {elapsed:>6.1f}s  {q[:60]}")
        if status == "FAIL":
            print(f"     ↳ {why}")
    print(f"{'='*88}")

    print(f"\nValid:        {valid_pass}/{valid_total} pass ({valid_pass/max(1,valid_total):.0%})")
    print(f"Invalid:      {invalid_pass}/{invalid_total} pass ({invalid_pass/max(1,invalid_total):.0%})")
    if multi_total:
        print(f"Multilingual: {multi_pass}/{multi_total} pass ({multi_pass/max(1,multi_total):.0%})")
    overall = (valid_pass + invalid_pass) / max(1, valid_total + invalid_total)
    print(f"Overall:      {valid_pass+invalid_pass}/{valid_total+invalid_total} pass ({overall:.0%})")
    return 0 if overall == 1.0 else 1


if __name__ == "__main__":
    sys.exit(run())
