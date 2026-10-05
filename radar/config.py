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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Provider is chosen by which key is present; Gemini wins if both are set.
if GEMINI_API_KEY:
    PROVIDER = "gemini"
    MODEL = os.getenv("RADAR_MODEL", "gemini-3.5-flash")
elif ANTHROPIC_API_KEY:
    PROVIDER = "anthropic"
    MODEL = os.getenv("RADAR_MODEL", "claude-opus-5")
else:
    PROVIDER = None
    MODEL = os.getenv("RADAR_MODEL", "none")

LLM_CONFIGURED = PROVIDER is not None

# Chunking: PDFs are chunked per page, then split further if a page is long.
MAX_CHUNK_CHARS = 1800
# Transcript chunks are grouped into windows of roughly this many seconds.
TRANSCRIPT_WINDOW_SECONDS = 60

for d in (PDF_CACHE, TRANSCRIPT_CACHE):
    d.mkdir(parents=True, exist_ok=True)
