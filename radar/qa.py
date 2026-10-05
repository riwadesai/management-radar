"""Step 3b: answer. Retrieve the most relevant chunks for a question (SQLite
FTS5, scoped to a company), then ask the LLM to answer ONLY from those chunks
and cite them by id. Citations are validated against what was actually
retrieved, so the model cannot cite a chunk it never saw."""
from __future__ import annotations

import json
import logging
import re

from .db import session
from .llm import complete_json, untrusted

log = logging.getLogger(__name__)

STOPWORDS = set("""a an and are as at be by for from has have how in is it of on or that the
this to was were what when where which who why will with about did does do said say
management company their they there these those been being its into than then any
promise promised promises mention mentioned comment commented tell told""".split())

# Analyst vocabulary -> words that actually appear in filings and interviews.
# Keys and values are matched as FTS prefixes (plan -> plan, plans, planning, plant).
SYNONYMS = {
    "expansion": ["expan", "capacity", "plant", "line", "production", "capex", "invest", "facility"],
    "expand": ["expan", "capacity", "plant", "line", "production", "capex", "invest"],
    "capacity": ["capacity", "plant", "line", "production"],
    "margin": ["margin", "profitab", "ebitda", "ebit", "cost", "commodit", "operating"],
    "margins": ["margin", "profitab", "ebitda", "ebit", "cost", "commodit", "operating"],
    "guidance": ["guidance", "outlook", "expect", "target", "guide", "forecast"],
    "outlook": ["outlook", "expect", "guidance", "forecast", "growth"],
    "growth": ["growth", "grow", "increase", "expect", "target"],
    "demand": ["demand", "order", "booking", "wait", "inventory", "sales"],
    "dividend": ["dividend", "payout", "buyback", "capital"],
    "ceo": ["ceo", "chief", "success", "designate", "appoint", "step"],
    "succession": ["success", "ceo", "designate", "appoint", "step", "term"],
    "exports": ["export", "overseas", "international"],
    "export": ["export", "overseas", "international"],
    "ev": ["electric", "bev", "vitara", "battery"],
    "electric": ["electric", "bev", "vitara", "battery"],
    "ai": ["ai", "artificial", "agentic", "automation", "generative"],
    "hiring": ["hire", "hiring", "recruit", "graduate", "headcount", "engineer"],
    "risk": ["risk", "uncertain", "headwind", "pressure", "impact"],
    "risks": ["risk", "uncertain", "headwind", "pressure", "impact"],
    "order": ["order", "deal", "contract", "tcv", "win"],
    "orders": ["order", "deal", "contract", "tcv", "win"],
    "price": ["price", "pricing", "discount", "cost"],
    "pricing": ["price", "pricing", "discount"],
}

TOP_K = 12
CANDIDATES = 40
MAX_PER_SOURCE = 6
TAG_BONUS = 2.0      # bm25 scores are negative; subtracting improves the rank
CLAIM_BONUS = 1.5


def query_terms(question: str) -> list[str]:
    raw = [t for t in re.findall(r"[a-zA-Z0-9]+", question.lower()) if t not in STOPWORDS and len(t) > 1]
    out: list[str] = []
    for t in raw:
        out.append(t)
        out.extend(SYNONYMS.get(t, []))
    return list(dict.fromkeys(out))


def fts_query(question: str) -> str:
    terms = query_terms(question)
    if not terms:
        return ""
    # Prefix match for words long enough to be meaningful, exact for short tokens.
    return " OR ".join(f'"{t}"*' if len(t) >= 4 else f'"{t}"' for t in terms)


def retrieve(conn, question: str, company_id: int | None, k: int = TOP_K) -> list:
    q = fts_query(question)
    if not q:
        return []
    sql = """
        SELECT c.id, c.page, c.start_sec, c.end_sec, c.text,
               s.id AS source_id, s.kind, s.title, s.url, s.published_on, s.company_id,
               COALESCE(a.tags, '[]') AS tags,
               EXISTS (SELECT 1 FROM claims cl WHERE cl.chunk_id = c.id) AS has_claim,
               bm25(chunks_fts) AS score
        FROM chunks_fts f
        JOIN chunks c ON c.id = f.rowid
        JOIN sources s ON s.id = c.source_id
        LEFT JOIN ai_outputs a ON a.source_id = s.id
        WHERE chunks_fts MATCH ?
    """
    args: list = [q]
    if company_id:
        sql += " AND s.company_id = ?"
        args.append(company_id)
    sql += " ORDER BY score LIMIT ?"
    args.append(CANDIDATES)
    rows = conn.execute(sql, args).fetchall()

    # Re-rank: a chunk from a source the model tagged with a topic in the
    # question, or a chunk that backs an extracted claim, moves up.
    asked = set(query_terms(question))
    scored = []
    for r in rows:
        tags = set(json.loads(r["tags"]))
        bonus = 0.0
        if any(t.split("-")[0] in asked or t in asked for t in tags):
            bonus -= TAG_BONUS
        if r["has_claim"]:
            bonus -= CLAIM_BONUS
        scored.append((r["score"] + bonus, r))
    scored.sort(key=lambda x: x[0])
    picked, per_source = [], {}
    for sc, r in scored:
        if per_source.get(r["source_id"], 0) >= MAX_PER_SOURCE:
            continue
        per_source[r["source_id"]] = per_source.get(r["source_id"], 0) + 1
        picked.append(r)
        if len(picked) >= k:
            break
    return picked


ANSWER_SYSTEM = """You are an equity-research assistant. Answer the analyst's question using
ONLY the numbered passages provided. Rules:
- Every factual sentence must end with one or more citations like [C12] using the ids given.
- If the passages do not contain the answer, say exactly that in one sentence, set
  grounded=false, and cite nothing. Do not guess, do not use outside knowledge.
- Quote exact figures and wording where the passage states them. Only the text
  inside the passages is evidence; the header in parentheses is a label.
- Keep the answer under 180 words. Plain prose, no headings."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "grounded": {"type": "boolean"},
        "citations": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answer", "grounded", "citations"],
    "additionalProperties": False,
}


def _ts(sec: float | None) -> str:
    s = int(sec or 0)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def citation_view(row) -> dict:
    """What the UI needs to render a clickable citation."""
    if row["kind"] == "pdf":
        return {"chunk_id": row["id"], "source_id": row["source_id"], "kind": "pdf",
                "title": row["title"], "page": row["page"],
                "href": f"/api/sources/{row['source_id']}/file#page={row['page']}",
                "label": f"{row['title']} - p.{row['page']}"}
    start = int(row["start_sec"] or 0)
    return {"chunk_id": row["id"], "source_id": row["source_id"], "kind": "video",
            "title": row["title"], "start_sec": start, "timestamp": _ts(start),
            "href": f"{row['url']}&t={start}s",
            "label": f"{row['title']} - {_ts(start)}"}


def answer(question: str, company_id: int | None) -> dict:
    question = question.strip()[:1000]
    with session() as conn:
        rows = retrieve(conn, question, company_id)
        if not rows:
            result = {"answer": "I could not find anything in the stored documents or "
                                "interviews that relates to this question.",
                      "grounded": False, "citations": []}
            _log(conn, company_id, question, result)
            return result

        # The header names the source for context only. The analyst-written
        # title is deliberately left out: in testing the model lifted a number
        # from a title ("Rs 140/share dividend press release") and cited it as
        # if it came from the document text.
        passages = "\n\n".join(
            f"[C{r['id']}] ({'filing' if r['kind'] == 'pdf' else 'interview'} dated {r['published_on']}; "
            f"{'page ' + str(r['page']) if r['kind'] == 'pdf' else 'at ' + _ts(r['start_sec'])})\n"
            + untrusted(r["text"])
            for r in rows
        )
        user = f"Question: {question}\n\nPassages:\n{passages}"
        out = complete_json(ANSWER_SYSTEM, user, ANSWER_SCHEMA, effort="high", max_tokens=4000)

        valid = {r["id"]: r for r in rows}
        # Keep only citations that were actually retrieved; also harvest [Cnn]
        # written inline in case the model forgot to list one.
        inline = {int(x) for grp in re.findall(r"\[C\d+(?:\s*,\s*C?\d+)*\]", out["answer"]) for x in re.findall(r"\d+", grp)}
        cited = [cid for cid in dict.fromkeys(list(out["citations"]) + sorted(inline)) if cid in valid]
        result = {
            "answer": out["answer"],
            "grounded": bool(out["grounded"]) and bool(cited),
            "citations": [citation_view(valid[c]) for c in cited],
        }
        _log(conn, company_id, question, result)
        return result


def _log(conn, company_id, question, result) -> None:
    conn.execute(
        "INSERT INTO qa_log(company_id, question, answer, cited_ids, grounded) VALUES (?,?,?,?,?)",
        (company_id, question, result["answer"],
         json.dumps([c["chunk_id"] for c in result["citations"]]), int(result["grounded"])),
    )
