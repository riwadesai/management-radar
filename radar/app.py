"""Step 4: show. FastAPI backend serving JSON to a single static page."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .config import ANTHROPIC_API_KEY, MODEL, ROOT
from .db import init_db, session
from .llm import LLMUnavailable

log = logging.getLogger(__name__)
app = FastAPI(title="Management Radar", docs_url="/api/docs")
STATIC = Path(__file__).resolve().parent.parent / "static"

init_db()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "llm_configured": bool(ANTHROPIC_API_KEY), "model": MODEL}


@app.get("/api/companies")
def companies():
    with session() as conn:
        rows = conn.execute("""
            SELECT c.*, 
                   SUM(s.kind='pdf')   AS pdfs,
                   SUM(s.kind='video') AS videos,
                   SUM(s.fetch_status='failed') AS failed
            FROM companies c LEFT JOIN sources s ON s.company_id=c.id
            GROUP BY c.id ORDER BY c.name""").fetchall()
        return [dict(r) for r in rows]


def _ts(sec):
    s = int(sec or 0)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


@app.get("/api/companies/{company_id}/timeline")
def timeline(company_id: int):
    with session() as conn:
        if not conn.execute("SELECT 1 FROM companies WHERE id=?", (company_id,)).fetchone():
            raise HTTPException(404, "unknown company")
        rows = conn.execute("""
            SELECT s.*, a.summary AS ai_summary, a.tags AS ai_tags, a.model AS ai_model,
                   (SELECT COUNT(*) FROM chunks WHERE source_id=s.id) AS chunk_count,
                   (SELECT COUNT(*) FROM claims WHERE source_id=s.id) AS claim_count
            FROM sources s LEFT JOIN ai_outputs a ON a.source_id=s.id
            WHERE s.company_id=? ORDER BY s.published_on DESC, s.id DESC""", (company_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        ai = json.loads(d.pop("ai_summary")) if d.get("ai_summary") else None
        d["ai"] = ai
        d["tags"] = json.loads(d.pop("ai_tags")) if d.get("ai_tags") else []
        d["open_href"] = (f"/api/sources/{r['id']}/file" if r["kind"] == "pdf" else r["url"])
        d["duration"] = _ts(r["duration_sec"]) if r["duration_sec"] else None
        out.append(d)
    return out


@app.get("/api/companies/{company_id}/claims")
def claims(company_id: int):
    with session() as conn:
        rows = conn.execute("""
            SELECT cl.*, s.title, s.kind, s.url, c.page, c.start_sec
            FROM claims cl JOIN sources s ON s.id=cl.source_id
            LEFT JOIN chunks c ON c.id=cl.chunk_id
            WHERE s.company_id=? ORDER BY s.published_on DESC, cl.id""", (company_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if r["kind"] == "pdf":
            d["href"] = f"/api/sources/{r['source_id']}/file#page={r['page']}" if r["page"] else f"/api/sources/{r['source_id']}/file"
            d["where"] = f"p.{r['page']}" if r["page"] else "PDF"
        else:
            start = int(r["start_sec"] or 0)
            d["href"] = f"{r['url']}&t={start}s"
            d["where"] = _ts(start)
        out.append(d)
    return out


@app.get("/api/sources/{source_id}/file")
def source_file(source_id: int):
    with session() as conn:
        r = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if not r or r["kind"] != "pdf" or not r["local_path"]:
        raise HTTPException(404, "no cached file for this source")
    path = (ROOT / r["local_path"]).resolve()
    if ROOT not in path.parents or not path.exists():   # never serve outside the project
        raise HTTPException(404, "file missing")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


class ChatIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    company_id: int | None = None


@app.post("/api/chat")
def chat(body: ChatIn):
    from .qa import answer
    try:
        return answer(body.question, body.company_id)
    except LLMUnavailable as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        log.exception("chat failed")
        return JSONResponse(status_code=502, content={"error": f"The model call failed: {type(exc).__name__}"})
