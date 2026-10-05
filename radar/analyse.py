"""Step 3a: understand. Two separate LLM passes per source (deliberately not
one giant prompt):
  1. classify + summarise  -> ai_outputs (summary, tags)
  2. extract claims        -> claims (forward-looking statements, with the
                              chunk they came from, for the promise tracker)
"""
from __future__ import annotations

import json
import logging

from .config import MODEL
from .db import session
from .llm import complete_json, untrusted

log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

TAG_VOCAB = [
    "results", "guidance", "margins", "dividend", "expansion", "capex",
    "new-product", "electric-vehicles", "exports", "demand", "pricing",
    "management-change", "new-orders", "partnership", "ai", "hiring",
    "risks", "regulation", "macro", "capital-return", "monthly-sales",
]

SUMMARISE_SYSTEM = f"""You are an equity-research assistant at an Indian asset manager.
You read one company disclosure (an exchange filing or a transcript of a management
interview) and produce:
- a plain-language summary of 3-5 sentences an analyst can read in 20 seconds,
  concrete numbers included where the document states them;
- a one-line headline (max 12 words);
- the document type as seen in the content, not the title;
- topic tags chosen ONLY from this vocabulary: {", ".join(TAG_VOCAB)}.
Pick 2-6 tags. Do not invent facts that are not in the document."""

SUMMARISE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "doc_type": {"type": "string",
                     "enum": ["results", "press-release", "regulatory-filing",
                              "transcript", "interview", "sales-update", "other"]},
        "tags": {"type": "array", "items": {"type": "string", "enum": TAG_VOCAB}},
        "suspicious_instructions_found": {"type": "boolean"},
    },
    "required": ["headline", "summary", "doc_type", "tags", "suspicious_instructions_found"],
    "additionalProperties": False,
}

CLAIMS_SYSTEM = """You extract forward-looking statements made by the company or its
management: commitments, targets, guidance, planned launches, capacity additions,
hiring plans, expected margins. Only statements about the FUTURE count; past results
do not. Each claim must quote the supporting sentence verbatim from the document and
name the segment marker (like [P3] or [T00:04:10]) it appears under. If the document
contains no forward-looking statements, return an empty list. Never invent claims."""

CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string", "description": "the promise, paraphrased in one sentence"},
                    "quote": {"type": "string", "description": "verbatim supporting text"},
                    "horizon": {"type": "string", "description": "e.g. FY27, Q3 FY27, by 2030, or 'unspecified'"},
                    "topic": {"type": "string", "enum": TAG_VOCAB},
                    "marker": {"type": "string", "description": "the [P..] or [T..] marker the quote sits under"},
                },
                "required": ["statement", "quote", "horizon", "topic", "marker"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


def _marker(chunk) -> str:
    if chunk["page"] is not None:
        return f"[P{chunk['page']}]"
    s = int(chunk["start_sec"] or 0)
    return f"[T{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}]"


def _source_text(conn, source_id: int) -> tuple[str, dict[str, int]]:
    """Full text of a source with page/timestamp markers; returns marker->chunk id."""
    rows = conn.execute("SELECT * FROM chunks WHERE source_id=? ORDER BY ordinal", (source_id,)).fetchall()
    parts, index = [], {}
    for r in rows:
        m = _marker(r)
        index.setdefault(m, r["id"])
        parts.append(f"{m}\n{r['text']}")
    return "\n\n".join(parts), index


def analyse_source(conn, src) -> dict:
    text, marker_index = _source_text(conn, src["id"])
    company = conn.execute("SELECT name FROM companies WHERE id=?", (src["company_id"],)).fetchone()[0]
    header = (f"Company: {company}\nSource kind: {src['kind']}\n"
              f"Title given by analyst: {src['title']}\nDate: {src['published_on']}\n\n")
    doc = untrusted(text, label=src["title"])

    # Pass 1 - classify & summarise
    out = complete_json(SUMMARISE_SYSTEM, header + doc, SUMMARISE_SCHEMA, effort="medium")
    conn.execute(
        """INSERT OR REPLACE INTO ai_outputs(source_id, prompt_version, model, summary, tags)
           VALUES (?,?,?,?,?)""",
        (src["id"], PROMPT_VERSION, MODEL,
         json.dumps({"headline": out["headline"], "summary": out["summary"],
                     "doc_type": out["doc_type"],
                     "suspicious": out["suspicious_instructions_found"]}),
         json.dumps(sorted(set(out["tags"])))),
    )

    # Pass 2 - extract forward-looking claims
    claims = complete_json(CLAIMS_SYSTEM, header + doc, CLAIMS_SCHEMA, effort="medium")["claims"]
    conn.execute("DELETE FROM claims WHERE source_id=?", (src["id"],))
    conn.executemany(
        "INSERT INTO claims(source_id, chunk_id, statement, quote, horizon, topic) VALUES (?,?,?,?,?,?)",
        [(src["id"], marker_index.get(c["marker"]), c["statement"], c["quote"], c["horizon"], c["topic"])
         for c in claims],
    )
    return {"tags": out["tags"], "claims": len(claims)}


def analyse_all(force: bool = False) -> dict[str, int]:
    counts = {"done": 0, "skipped": 0, "failed": 0}
    with session() as conn:
        rows = conn.execute("SELECT * FROM sources WHERE fetch_status='ok' ORDER BY id").fetchall()
    for src in rows:
        with session() as conn:
            have = conn.execute("SELECT 1 FROM ai_outputs WHERE source_id=? AND prompt_version=?",
                                (src["id"], PROMPT_VERSION)).fetchone()
            if have and not force:
                counts["skipped"] += 1
                continue
            try:
                res = analyse_source(conn, src)
                log.info("%-55s tags=%s claims=%d", src["title"][:55], res["tags"], res["claims"])
                counts["done"] += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("analysis failed for %s: %s", src["title"], exc)
                conn.rollback()
                counts["failed"] += 1
    return counts
