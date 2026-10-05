"""Step 1: fetch & read. Download PDFs and YouTube transcripts into the local
cache, then register them in the database. Safe to re-run: cached items are
not fetched twice, and a bad link marks the row 'failed' instead of crashing.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from pypdf import PdfReader
from youtube_transcript_api import YouTubeTranscriptApi

from .config import LINKS_CSV, PDF_CACHE, TRANSCRIPT_CACHE
from .db import session

log = logging.getLogger(__name__)

# BSE returns 403 to clients without a browser-like UA.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Referer": "https://www.bseindia.com/",
}
TIMEOUT = 30

COMPANY_META = {
    "Maruti Suzuki": {"ticker": "MARUTI", "sector": "Automobiles"},
    "Infosys": {"ticker": "INFY", "sector": "IT Services"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cache_name(url: str, suffix: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16] + suffix


def youtube_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------- registration

def load_links() -> list[dict]:
    with open(LINKS_CSV, newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row.get("url")]


def register_sources() -> None:
    """Upsert companies and sources from the CSV. Idempotent."""
    rows = load_links()
    with session() as conn:
        for row in rows:
            company = row["company"].strip()
            meta = COMPANY_META.get(company, {})
            conn.execute(
                "INSERT OR IGNORE INTO companies(name, ticker, sector) VALUES (?,?,?)",
                (company, meta.get("ticker"), meta.get("sector")),
            )
            cid = conn.execute("SELECT id FROM companies WHERE name=?", (company,)).fetchone()[0]
            kind = "video" if row["type"].strip().upper() == "YOUTUBE" else "pdf"
            conn.execute(
                """INSERT OR IGNORE INTO sources(company_id, kind, title, published_on, url)
                   VALUES (?,?,?,?,?)""",
                (cid, kind, row["title"].strip(), row["date"].strip(), row["url"].strip()),
            )


# --------------------------------------------------------------------- fetching

def fetch_pdf(url: str) -> Path:
    path = PDF_CACHE / _cache_name(url, ".pdf")
    if path.exists() and path.stat().st_size > 0:
        log.info("cache hit  %s", path.name)
        return path
    log.info("download   %s", url)
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise ValueError(f"not a PDF (content-type={resp.headers.get('content-type')})")
    path.write_bytes(resp.content)
    return path


def fetch_transcript(url: str) -> Path:
    vid = youtube_id(url)
    if not vid:
        raise ValueError("could not parse YouTube video id")
    path = TRANSCRIPT_CACHE / f"{vid}.json"
    if path.exists():
        log.info("cache hit  %s", path.name)
        return path
    log.info("transcript %s", vid)
    api = YouTubeTranscriptApi()
    fetched = api.fetch(vid, languages=["en", "en-IN", "en-US", "hi"])
    data = {
        "video_id": vid,
        "language": fetched.language_code,
        "is_generated": fetched.is_generated,
        "segments": [
            {"start": s.start, "duration": s.duration, "text": s.text}
            for s in fetched
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def fetch_all(force: bool = False) -> dict[str, int]:
    """Fetch every pending (or failed, or all if force) source. Never raises."""
    register_sources()
    counts = {"ok": 0, "failed": 0, "skipped": 0}
    with session() as conn:
        where = "" if force else "WHERE fetch_status != 'ok'"
        rows = conn.execute(f"SELECT * FROM sources {where} ORDER BY id").fetchall()
    for row in rows:
        try:
            if row["kind"] == "pdf":
                path = fetch_pdf(row["url"])
                pages = len(PdfReader(str(path)).pages)
                extra = {"page_count": pages, "duration_sec": None}
            else:
                path = fetch_transcript(row["url"])
                segs = json.loads(path.read_text(encoding="utf-8"))["segments"]
                dur = (segs[-1]["start"] + segs[-1]["duration"]) if segs else 0
                extra = {"page_count": None, "duration_sec": dur}
            with session() as conn:
                conn.execute(
                    """UPDATE sources SET local_path=?, fetch_status='ok', fetch_error=NULL,
                       fetched_at=?, page_count=?, duration_sec=? WHERE id=?""",
                    (str(path.relative_to(path.parents[3])), _now(),
                     extra["page_count"], extra["duration_sec"], row["id"]),
                )
            counts["ok"] += 1
        except Exception as exc:  # noqa: BLE001 - we want to survive any bad link
            log.warning("FAILED %s: %s", row["title"], exc)
            with session() as conn:
                conn.execute(
                    "UPDATE sources SET fetch_status='failed', fetch_error=?, fetched_at=? WHERE id=?",
                    (f"{type(exc).__name__}: {exc}"[:500], _now(), row["id"]),
                )
            counts["failed"] += 1
    return counts
