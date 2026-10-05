"""Central configuration. Secrets come only from the environment / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = ROOT / os.getenv("RADAR_DB", "data/radar.db")
CACHE_DIR = ROOT / "data" / "cache"
PDF_CACHE = CACHE_DIR / "pdf"
TRANSCRIPT_CACHE = CACHE_DIR / "transcripts"
LINKS_CSV = ROOT / "disclosure_links.csv"

MODEL = os.getenv("RADAR_MODEL", "claude-sonnet-5")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Chunking: PDFs are chunked per page, then split further if a page is long.
MAX_CHUNK_CHARS = 1800
# Transcript chunks are grouped into windows of roughly this many seconds.
TRANSCRIPT_WINDOW_SECONDS = 60

for d in (PDF_CACHE, TRANSCRIPT_CACHE):
    d.mkdir(parents=True, exist_ok=True)
