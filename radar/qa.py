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
management company their they there these those been being its into than then""".split())

TOP_K = 12

ANSWER_SYSTEM = """You are an equity-research assistant. Answer the analyst's question using
ONLY the numbered passages provided. Rules:
- Every factual sentence must end with one or more citations like [C12] using the ids given.
- If the passages do not contain the answer, say exactly that in one sentence, set
  grounded=false, and cite nothing. Do not guess, do not use outside knowledge.
- Quote exact figures and wording where the passage states them.
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


def fts_query(question: str) -> str:
    terms = [t for t in re.findall(r"[a-zA-Z0-9]+", question.lower())
             if t not in STOPWORDS and len(t) > 2]
    if not terms:
        return ""
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))


def retrieve(conn, question: str, company_id: int | None, k: int = TOP_K) -> list:
    q = fts_query(question)
    if not q:
        return []
    sql = """
        SELECT c.id, c.page, c.start_sec, c.end_sec, c.text,
               s.id AS source_id, s.kind, s.title, s.url, s.published_on, s.company_id,
               bm25(chunks_fts) AS score
        FROM chunks_fts f
        JOIN chunks c ON c.id = f.rowid
        JOIN sources s ON s.id = c.source_id
        WHERE chunks_fts MATCH ?
    """
    args: list = [q]
    if company_id:
        sql += " AND s.company_id = ?"
        args.append(company_id)
    sql += " ORDER BY score LIMIT ?"
    args.append(k)
    return conn.execute(sql, args).fetchall()


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

        passages = "\n\n".join(
            f"[C{r['id']}] ({r['title']}; "
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
