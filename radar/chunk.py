"""Turn cached PDFs and transcripts into searchable chunks with a page or
timestamp. Re-chunking a source wipes its old chunks first."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pypdf import PdfReader

from .config import MAX_CHUNK_CHARS, ROOT, TRANSCRIPT_WINDOW_SECONDS
from .db import session

log = logging.getLogger(__name__)


def _clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_long(text: str, limit: int) -> list[str]:
    """Split on paragraph, then sentence boundaries so pieces stay under limit."""
    if len(text) <= limit:
        return [text]
    pieces, buf = [], ""
    for para in re.split(r"\n\s*\n", text):
        for sent in re.split(r"(?<=[.!?])\s+", para):
            if len(buf) + len(sent) + 1 > limit and buf:
                pieces.append(buf.strip())
                buf = ""
            buf += sent + " "
        buf += "\n"
    if buf.strip():
        pieces.append(buf.strip())
    return pieces


def pdf_chunks(path: Path) -> list[dict]:
    out = []
    reader = PdfReader(str(path))
    for pno, page in enumerate(reader.pages, start=1):
        text = _clean(page.extract_text() or "")
        if len(text) < 40:          # blank / scanned page
            continue
        for piece in _split_long(text, MAX_CHUNK_CHARS):
            out.append({"page": pno, "start_sec": None, "end_sec": None, "text": piece})
    return out


def transcript_chunks(path: Path) -> list[dict]:
    segs = json.loads(path.read_text(encoding="utf-8"))["segments"]
    out, buf, win_start = [], [], None
    for s in segs:
        if win_start is None:
            win_start = s["start"]
        buf.append(s["text"].replace("\n", " "))
        if s["start"] + s["duration"] - win_start >= TRANSCRIPT_WINDOW_SECONDS:
            out.append({"page": None, "start_sec": win_start,
                        "end_sec": s["start"] + s["duration"], "text": _clean(" ".join(buf))})
            buf, win_start = [], None
    if buf:
        last = segs[-1]
        out.append({"page": None, "start_sec": win_start,
                    "end_sec": last["start"] + last["duration"], "text": _clean(" ".join(buf))})
    return out


def chunk_all(force: bool = False) -> int:
    total = 0
    with session() as conn:
        rows = conn.execute("SELECT * FROM sources WHERE fetch_status='ok'").fetchall()
    for row in rows:
        with session() as conn:
            have = conn.execute("SELECT COUNT(*) FROM chunks WHERE source_id=?", (row["id"],)).fetchone()[0]
            if have and not force:
                continue
            path = ROOT / row["local_path"]
            try:
                pieces = pdf_chunks(path) if row["kind"] == "pdf" else transcript_chunks(path)
            except Exception as exc:  # noqa: BLE001
                log.warning("chunking failed for %s: %s", row["title"], exc)
                continue
            conn.execute("DELETE FROM chunks WHERE source_id=?", (row["id"],))
            conn.executemany(
                "INSERT INTO chunks(source_id, ordinal, page, start_sec, end_sec, text) VALUES (?,?,?,?,?,?)",
                [(row["id"], i, p["page"], p["start_sec"], p["end_sec"], p["text"]) for i, p in enumerate(pieces)],
            )
            log.info("%-60s %3d chunks", row["title"][:60], len(pieces))
            total += len(pieces)
    return total
