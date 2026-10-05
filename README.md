# Management Radar

Digest a company's stock-exchange announcements and its management's video
interviews, then ask questions and get answers that cite the exact PDF page or
the video timestamp.

Built for the HDFC AMC "Management Radar" intern challenge. Covers Maruti
Suzuki and Infosys (the 10 links in `disclosure_links.csv`).

## Run it in five minutes

Requires Python 3.10+ and a Gemini API key (free tier from Google AI Studio works; an Anthropic key works too).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then paste your key into .env
```

The repo ships with the populated database (`data/radar.db`) and the cached
PDFs and transcripts (`data/cache/`), so you can go straight to:

```bash
python -m radar serve           # open http://127.0.0.1:8000
```

To rebuild from scratch (re-downloads only what is not cached):

```bash
python -m radar ingest          # fetch PDFs + transcripts, chunk, index
python -m radar analyse         # LLM summaries, tags, forward-looking claims
python -m radar stats           # row counts + per-source fetch status
```

Free-tier note: Gemini allows about 20 requests per day per model. `analyse`
needs 2 calls per source and walks a fallback chain of models when one runs
dry (see `RADAR_FALLBACK_MODELS` in `radar/config.py`), so a full re-run of
10 sources fits in a day. The shipped database already contains the output.

Chat works without running `analyse` (it only needs the chunks), but the
timeline will show "AI summary not run yet" until you do.

## How it is put together

```
disclosure_links.csv
        │  python -m radar ingest
        ▼
radar/fetch.py   download PDF / pull YouTube captions → data/cache/ (sha1-named, never fetched twice)
radar/chunk.py   PDF page → chunk(s) with page no.;  captions → ~60 s windows with start/end seconds
        │
        ▼
data/radar.db (SQLite, FTS5)
        │  python -m radar analyse
        ▼
radar/analyse.py pass 1: headline + summary + tags       → ai_outputs
                 pass 2: forward-looking claims + quote   → claims
        │  python -m radar serve
        ▼
radar/qa.py      question → FTS5 top-12 chunks (company-scoped) → LLM answers
                 ONLY from those chunks, cites [C<id>]; citations validated
radar/app.py     FastAPI JSON API + serves static/index.html
```

### Schema (`radar/db.py`)

| table | one row per | why it exists |
|---|---|---|
| `companies` | company | the entity an analyst picks |
| `sources` | PDF or video | title, date, URL, cached path, fetch status / error, page count or duration |
| `chunks` | searchable passage | text + `page` (PDF) or `start_sec`/`end_sec` (video); `chunks_fts` is the FTS5 index over it |
| `ai_outputs` | source × prompt version | LLM headline/summary/doc-type JSON + tags JSON; versioned so re-prompting never overwrites silently |
| `claims` | forward-looking statement | promise tracker; points at the chunk it was quoted from |
| `qa_log` | chat question | what was asked, what was answered, which chunk ids were cited, grounded or not |

Raw text and AI output never share a table, so an AI re-run touches only
`ai_outputs` and `claims`.

### API

| route | purpose |
|---|---|
| `GET /api/health` | is a key configured, which model |
| `GET /api/companies` | list with filing / interview counts |
| `GET /api/companies/{id}/timeline` | sources newest-first with summary + tags |
| `GET /api/companies/{id}/claims` | promise tracker |
| `GET /api/sources/{id}/file` | cached PDF, so citations open at `#page=N` |
| `POST /api/chat` `{question, company_id}` | grounded answer with citations |

Interactive docs at `/api/docs`.

## Configuration

Everything is read from `.env` (see `.env.example`). Set `GEMINI_API_KEY`
(free tier from Google AI Studio) or `ANTHROPIC_API_KEY`; the provider is
picked from whichever is present. Optional: `RADAR_MODEL` (default
`gemini-3.5-flash` or `claude-opus-5`), `RADAR_DB`.

## Demo recording

_(link to the 3-minute screen recording goes here)_
