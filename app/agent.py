"""LangGraph agent: rewrite → retrieve → rerank → generate → verify → respond.

Strict grounding contract:
- Generate a `AgentAnswer` with citations[{page, quote}] using only retrieved chunks.
- Refuse explicitly when the answer isn't supported by retrieval.
- Verifier checks each citation against retrieved chunk text using normalized
  substring + bag-of-words fallback (to absorb PDF formatting noise).
"""
from __future__ import annotations

import re
from typing import Annotated, TypedDict

import cohere
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.config import settings
from app.index import Hit, query_index
from app.logging import get_logger
from app.models import AgentAnswer, Citation

log = get_logger(__name__)


SYSTEM_PROMPT = """You are a PDF-grounded assistant.

ABSOLUTE RULES:
1. Answer ONLY using facts from the SOURCE PASSAGES. Never use prior knowledge.
2. Be COMPLETE and SPECIFIC.
   - If the question asks for a list (deliverables, criteria, requirements), include EVERY relevant item from the source. Do NOT stop at "based on several criteria:". Spell them out.
   - For yes/no questions, lead with "Yes" or "No" then give the supporting detail.
   - Use the source's own bullet structure when listing.
3. Provide 1-3 citations max. Pick the MOST representative quotes; do not cite every bullet.
4. Each `quote` MUST be a literal substring of a SOURCE PASSAGE.
   - Copy character-for-character (including punctuation).
   - Do NOT paraphrase, summarize, or reformat. Do NOT add or drop words.
   - Quotes should be short and specific (5-25 words ideal).
5. Use related content liberally. If the user asks about "deliverables" and the doc says "submission must include", that IS the answer — don't refuse on terminology mismatch alone.
6. Refuse ONLY when NO passage contains the answer. If the question asks for a fact (date, number, name, list) and that fact appears verbatim in any passage, you MUST answer with it. Refusing a question whose answer is literally in the passages is a critical failure.
7. Keep prose tight. No "the document says...". No apologies.
8. LANGUAGE: Answer in the SAME language as the user's query.
   - If the query is in Hindi (Devanagari), answer in Hindi.
   - If Marathi, answer in Marathi. Etc.
   - Citation `quote` fields ALWAYS stay verbatim in the source language (do not translate quotes).
   - Refusal_reason should also match the user's language; the closest-quote inside it stays in source language.

EXAMPLE — completeness:
Source: "Your submission must include: • A short technical note • Test instructions • Demo video • A deployed interface (Optional)"
Good answer: "You must submit:\n• A short technical note (architecture, decisions, trade-offs)\n• Test instructions for evaluators\n• Demo video\n• A deployed interface (optional)"
Bad answer:  "Your submission must include several items."  # too vague — INVALID

REFUSAL EXAMPLE:
{refused: true, refusal_reason: "This isn't covered. Closest content on page 3: 'Quality and traceability of citations'. Want me to expand or rephrase?"}
"""


def _format_passages(hits: list[Hit]) -> str:
    parts = []
    for h in hits:
        parts.append(f"[page {h.page}]\n{h.text.strip()}")
    return "\n\n---\n\n".join(parts)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    query: str
    rewritten_query: str
    doc_id: str
    hits: list[Hit]
    answer: AgentAnswer | None


REWRITE_PROMPT = """Rewrite the user's latest message into a STANDALONE search query that captures their intent given the conversation so far. If the message already stands on its own, return it unchanged.

Rules:
- Resolve pronouns and references ("it", "that", "the second one") using the conversation.
- Keep proper nouns, numbers, and key terms verbatim.
- No preamble, no quotes — output only the rewritten query.
- Same language as the user's message.

Conversation:
{convo}

User's latest message: {query}

Rewritten standalone query:"""


def rewrite_node(state: AgentState) -> dict:
    """History-aware query rewrite. Skips on the first turn."""
    history = [m for m in state.get("messages", []) if isinstance(m, dict) and m.get("content")]
    history = history[:-1]  # exclude the current user message (last in list)
    if len(history) < 2:
        return {"rewritten_query": state["query"]}
    convo = "\n".join(f"{m['role'].upper()}: {m['content'][:400]}" for m in history[-6:])
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        temperature=0,
        seed=42,
    )
    out = llm.invoke(REWRITE_PROMPT.format(convo=convo, query=state["query"]))
    rewritten = (out.content if isinstance(out.content, str) else str(out.content)).strip()
    log.info("agent.rewrote", original=state["query"][:80], rewritten=rewritten[:80])
    return {"rewritten_query": rewritten}


def retrieve_node(state: AgentState) -> dict:
    q = state.get("rewritten_query") or state["query"]
    hits = query_index(q, doc_id=state["doc_id"], top_k=settings.fetch_top_k)
    return {"hits": hits}


def rerank_node(state: AgentState) -> dict:
    """Cohere rerank-3.5: rerank top-N candidates → keep top-K. Graceful fallback on errors."""
    hits = state["hits"]
    if not hits:
        return {}
    if not settings.cohere_api_key:
        return {"hits": hits[: settings.rerank_top_k]}
    q = state.get("rewritten_query") or state["query"]
    try:
        co = cohere.ClientV2(api_key=settings.cohere_api_key)
        resp = co.rerank(
            model=settings.rerank_model,
            query=q,
            documents=[h.text for h in hits],
            top_n=min(settings.rerank_top_k, len(hits)),
        )
    except cohere.errors.TooManyRequestsError:
        log.warning("agent.rerank_rate_limited", n_hits=len(hits))
        return {"hits": hits[: settings.rerank_top_k]}
    except Exception as e:
        log.warning("agent.rerank_failed", error=str(e)[:200])
        return {"hits": hits[: settings.rerank_top_k]}
    new_hits = [
        Hit(
            chunk_id=hits[r.index].chunk_id,
            doc_id=hits[r.index].doc_id,
            text=hits[r.index].text,
            page=hits[r.index].page,
            score=r.relevance_score,
        )
        for r in resp.results
    ]
    log.info(
        "agent.reranked",
        n_in=len(hits),
        n_out=len(new_hits),
        top_score=round(new_hits[0].score, 3) if new_hits else None,
    )
    return {"hits": new_hits}


def generate_node(state: AgentState) -> dict:
    hits = state["hits"]
    if not hits:
        ans = AgentAnswer(
            answer="",
            refused=True,
            refusal_reason="No content was retrieved from the document for this query.",
        )
        return {"answer": ans}

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
        seed=42,
    ).with_structured_output(AgentAnswer)

    history = state.get("messages", [])
    user_block = (
        f"SOURCE PASSAGES:\n\n{_format_passages(hits)}\n\n"
        f"USER QUERY: {state['query']}"
    )
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history[-6:]:  # last 3 turns of (user, assistant)
        msgs.append(m)
    msgs.append({"role": "user", "content": user_block})
    ans: AgentAnswer = llm.invoke(msgs)
    log.info(
        "agent.generated",
        refused=ans.refused,
        n_citations=len(ans.citations),
        answer_chars=len(ans.answer),
    )
    # Append assistant response to the conversation memory so future
    # rewrite_node calls can resolve references like "it" / "that".
    summary = ans.refusal_reason if ans.refused else ans.answer
    return {
        "answer": ans,
        "messages": [{"role": "assistant", "content": (summary or "")[:1000]}],
    }


_HYPHEN_BREAK = re.compile(r"(\w)-\s+(\w)")
_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+")


def _norm(s: str) -> str:
    """Collapse PDF formatting: heal hyphenated line-breaks, normalize whitespace, lowercase."""
    s = _HYPHEN_BREAK.sub(r"\1\2", s)  # "real- world" -> "realworld"
    s = _WS.sub(" ", s).strip().lower()
    return s


def _grounded(quote: str, source: str, threshold: float = 0.85) -> bool:
    """True if quote can be found in source (strict substring or fuzzy bag-of-words)."""
    nq, ns = _norm(quote), _norm(source)
    if not nq:
        return False
    if nq in ns:
        return True
    # Fallback: ≥threshold fraction of quote tokens appear in source
    qt = _TOKEN.findall(nq)
    if not qt:
        return False
    src_tokens = set(_TOKEN.findall(ns))
    matched = sum(1 for t in qt if t in src_tokens)
    return matched / len(qt) >= threshold


def _dedupe_citations(cites: list[Citation], cap: int = 3) -> list[Citation]:
    """Keep the first citation per (page, normalized-quote) pair, capped."""
    seen: set[tuple[int, str]] = set()
    out: list[Citation] = []
    for c in cites:
        key = (c.page, _norm(c.quote))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= cap:
            break
    return out


def verify_node(state: AgentState) -> dict:
    """Verify every citation. If any quote isn't found, refuse with closest-match."""
    ans = state["answer"]
    if ans is None or ans.refused:
        return {}
    if not ans.citations:
        return {
            "answer": AgentAnswer(
                answer="",
                refused=True,
                refusal_reason="The model produced an answer with no citations, so it cannot be grounded in the document.",
            )
        }
    all_text = " ".join(h.text for h in state["hits"])
    bad: list[Citation] = []
    for c in ans.citations:
        if not _grounded(c.quote, all_text):
            bad.append(c)
    if bad:
        log.warning("agent.ungrounded", n_bad=len(bad), bad_quotes=[c.quote[:80] for c in bad])
        closest = state["hits"][0]
        return {
            "answer": AgentAnswer(
                answer="",
                refused=True,
                refusal_reason=(
                    f"I couldn't ground this in the document. "
                    f"Closest related content on page {closest.page}: "
                    f"\"{closest.text[:160].strip()}…\". Try rephrasing your question."
                ),
            )
        }
    # Dedupe + cap citations on the way out (UI clutter prevention)
    return {"answer": ans.model_copy(update={"citations": _dedupe_citations(ans.citations)})}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("rewrite", rewrite_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("rerank", rerank_node)
    g.add_node("generate", generate_node)
    g.add_node("verify", verify_node)
    g.add_edge(START, "rewrite")
    g.add_edge("rewrite", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "generate")
    g.add_edge("generate", "verify")
    g.add_edge("verify", END)
    return g.compile(checkpointer=MemorySaver())


GRAPH = build_graph()


def ask(query: str, doc_id: str, session_id: str = "default") -> AgentAnswer:
    return ask_with_hits(query, doc_id, session_id)[0]


def ask_with_hits(
    query: str, doc_id: str, session_id: str = "default"
) -> tuple[AgentAnswer, list[Hit]]:
    """Like `ask` but also returns the retrieved hits used to ground the answer."""
    state = {
        "query": query,
        "rewritten_query": "",
        "doc_id": doc_id,
        "hits": [],
        "answer": None,
        "messages": [{"role": "user", "content": query}],
    }
    result = GRAPH.invoke(state, config={"configurable": {"thread_id": session_id}})
    return result["answer"], result.get("hits", []) or []


if __name__ == "__main__":
    import sys

    from app.logging import configure_logging

    configure_logging()
    doc_id = sys.argv[1] if len(sys.argv) > 1 else "a4d5c5b89b18456fe1eda98c84f39235c48cc402d696a9898fd442361c35b92a"
    queries = [
        "What deliverables must I submit for this assignment?",
        "What's the deadline for this submission?",  # out of scope (no deadline in PDF)
    ]
    for q in queries:
        print(f"\n=== Q: {q} ===")
        a = ask(q, doc_id=doc_id, session_id="cli")
        print(f"refused: {a.refused}")
        if a.refused:
            print(f"reason:  {a.refusal_reason}")
        else:
            print(f"answer:  {a.answer}")
            for c in a.citations:
                print(f"  [p.{c.page}] {c.quote[:120]}")
