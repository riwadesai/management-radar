"""SQLite schema and helpers.

Tables (one concern each):
  companies   - the entities we track.
  sources     - one row per announcement PDF or video interview (the "document").
  chunks      - searchable text pieces, each pinned to a page (PDF) or a
                start/end second (video). FTS5 index `chunks_fts` sits on top.
  ai_outputs  - LLM-generated summary + tags per source, versioned by prompt.
  claims      - forward-looking statements extracted by the LLM, each pointing
                at the chunk it came from (stretch goal: promise tracker).
  qa_log      - every chat question, the answer, and the chunk ids cited.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    ticker      TEXT,
    sector      TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id            INTEGER PRIMARY KEY,
    company_id    INTEGER NOT NULL REFERENCES companies(id),
    kind          TEXT NOT NULL CHECK (kind IN ('pdf', 'video')),
    title         TEXT NOT NULL,
    published_on  TEXT,                -- ISO date or YYYY-MM as given in the brief
    url           TEXT NOT NULL UNIQUE,
    local_path    TEXT,                -- cached PDF / transcript JSON
    fetch_status  TEXT NOT NULL DEFAULT 'pending'
                  CHECK (fetch_status IN ('pending', 'ok', 'failed')),
    fetch_error   TEXT,
    fetched_at    TEXT,
    page_count    INTEGER,             -- PDFs
    duration_sec  REAL                 -- videos
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,       -- order within the source
    page        INTEGER,                -- PDFs: 1-based page number
    start_sec   REAL,                   -- videos: window start
    end_sec     REAL,                   -- videos: window end
    text        TEXT NOT NULL,
    UNIQUE (source_id, ordinal)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TABLE IF NOT EXISTS ai_outputs (
    id              INTEGER PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    prompt_version  TEXT NOT NULL,
    model           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    tags            TEXT NOT NULL,      -- JSON array of strings
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_id, prompt_version)
);

CREATE TABLE IF NOT EXISTS claims (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    chunk_id    INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    statement   TEXT NOT NULL,          -- the forward-looking promise, paraphrased
    quote       TEXT,                   -- verbatim supporting text
    horizon     TEXT,                   -- e.g. "FY27", "Q3", "by 2030", or null
    topic       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS qa_log (
    id          INTEGER PRIMARY KEY,
    company_id  INTEGER REFERENCES companies(id),
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    cited_ids   TEXT NOT NULL,          -- JSON array of chunk ids
    grounded    INTEGER NOT NULL,       -- 1 if answered from sources, 0 if "don't know"
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
