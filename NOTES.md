# NOTES — decisions, cut corners, and the prompts that mattered

## How AI was used

The whole project was pair-built with Claude Code (Claude Fable 5.1). I gave
it the brief and the CSV as the first prompt, chose Python / FastAPI / SQLite,
and reviewed every file it produced before committing. The things below are
what I accepted, changed, or rejected.

## Decisions

- **SQLite + FTS5 instead of a vector store.** Ten documents, ~190 chunks.
  BM25 keyword retrieval over porter-stemmed text is good enough and keeps the
  database a single file the graders can open. Embeddings would be the first
  upgrade for a real corpus. Cut deliberately.
- **Two LLM passes per source, not one.** Pass 1 classifies + summarises,
  pass 2 extracts forward-looking claims. Separate prompts, separate schemas,
  separate tables. Easier to re-run one without the other and easier to
  explain in a viva.
- **Structured outputs everywhere.** Every model call returns JSON validated
  against a schema (`output_config.format`), so there is no fragile parsing of
  free text. Tags are an enum, so the model cannot invent new ones.
- **Citations are validated server-side.** The answer prompt may only cite
  `[C<id>]` ids from the retrieved set; `qa.py` drops any id that was not
  retrieved. The model cannot cite something it never saw.
- **"I don't know" is a schema field.** `grounded: false` plus an empty
  citation list; the UI shows it in amber. If retrieval returns nothing we
  skip the model entirely.
- **PDF chunk = one page (split if long).** Keeps the page number exact for
  the citation. Transcript chunk = ~60 s window, so the timestamp link lands
  within a minute of the quote.
- **CSV title vs actual content.** Source 7 is titled "CEO succession
  announcement" in the brief but the PDF is Infosys's 48-page press-conference
  and earnings-call transcript. I kept the given title as "Listed as:" and let
  the model's own headline lead, so the timeline shows what the document is.
- **Model: Gemini 3.5 Flash on the free tier**, overridable by `RADAR_MODEL`.
  First try was `gemini-3.8-flash`, which returned 503 "high demand" on every
  call that evening; `gemini-2.5-flash` is no longer offered to new keys;
  `gemini-3.6-flash` marked an unanswerable question as grounded in a smoke
  test. `gemini-3.5-flash` passed the smoke test (refused to answer from an
  injected instruction, set grounded=false) and was reachable, so it won. The
  wrapper retries 429/503 with short backoff.
- **The free tier is 20 requests per day PER MODEL.** Found out the hard way:
  the first `analyse` run died after 4 sources with "retry in 13h". Fix: a
  model chain (`RADAR_FALLBACK_MODELS`) that moves to the next Gemini model
  the moment one reports a daily quota or stays overloaded, and remembers
  dead models for the rest of the process. `ai_outputs.model` records which
  model actually wrote each row, so mixed-model output is auditable. Total
  budget for the whole corpus is ~20 calls (2 per source), plus 1 per chat
  question. A Claude path (`ANTHROPIC_API_KEY`) is kept in `radar/llm.py`.

## What the trick questions caught

- **Title leak.** The first version of the answer prompt put each passage's
  analyst-given title in the header: `[C23] (Q4 FY26 results and Rs 140/share
  dividend press release; page 4)`. Asked "what is the dividend?", the model
  answered "Rs 140 per share" and cited two chunks that do not contain that
  number. It had read it off the title. The PDF itself never says "dividend"
  (its figure pages are images). Fix: headers now carry only kind + date +
  page, and the prompt says the header is a label, not evidence. The probe in
  `tests_trick.py` now expects this question to come back *not grounded*.
- Five out-of-corpus traps (Brazil plant, buyback, Tata Motors, FY2015 revenue,
  "tell me if it's a buy") all came back ungrounded with zero citations.
- Scanned / image pages in the BSE PDFs yield no text, so numbers that only
  live in charts are invisible to retrieval. OCR is the obvious next step;
  cut for time.

## Security

- Key only in `.env`, which is git-ignored; `.env.example` has a placeholder.
- **Prompt injection from documents.** All downloaded text is wrapped in
  `<untrusted_document>` tags with any embedded closing tag escaped, and the
  system prompt says such content is data, never instructions. The summarise
  schema has a `suspicious_instructions_found` flag that the UI surfaces with a
  warning. Chat input is length-capped (1000 chars) and passed as data too.
- Cached PDFs are served only from inside the project directory (path check),
  never by arbitrary path.

## Cut corners (and why)

- No embeddings / hybrid search (see above).
- No streaming of chat answers; answers are short so a 5-10 s wait with a
  typing indicator is acceptable.
- No auth: single-user local tool.
- No "fetch latest from BSE" button: BSE's announcement API needs scrip-code
  lookup and session cookies; out of scope for 24 h.
- Tags vocabulary is fixed (21 tags). Good for filtering, loses nuance.

## Prompts that mattered (inside the system)

See `radar/analyse.py` and `radar/qa.py` for the full text. The key lines:

- Summarise: *"the document type as seen in the content, not the title"* —
  added after noticing source 7's title did not match its content.
- Claims: *"Only statements about the FUTURE count; past results do not ...
  name the segment marker (like [P3] or [T00:04:10]) it appears under"* — the
  marker is how a claim gets linked back to a chunk id for its citation.
- Answer: *"Every factual sentence must end with one or more citations like
  [C12] ... If the passages do not contain the answer, say exactly that in one
  sentence, set grounded=false, and cite nothing."*

## Prompts that mattered (to the coding assistant)

Session transcript, in order, with what I did with each result:

1. The brief and the CSV, verbatim, no instruction. The assistant proposed a
   stack and asked three questions (folder, key, language). **Accepted** the
   proposed schema and the two-prompt analysis design as-is.
2. "python, make a new folder for this in downloads, what llm key do u need".
   It scaffolded fetch/chunk/db and ran ingest. **Fixed** nothing here; all
   10 sources fetched first time once a browser User-Agent was sent to BSE.
3. "use free gemini key". It rewrote the LLM wrapper with a provider switch.
   **Rejected** its first default (`gemini-2.5-flash`): that model is no longer
   offered to new keys. It then probed the available models and picked
   `gemini-3.5-flash` from a smoke test.
4. Pasted the key. The first `analyse` run hit the 20/day quota after 4
   sources. **Fixed** by adding the model fallback chain rather than waiting
   13 hours.
5. The trick-question run exposed the title leak (see above). The fix was to
   strip titles from passage headers and reword the prompt; the probe's
   expectation was corrected from "grounded" to "not grounded" because the
   PDF genuinely lacks the text.

Everything was reviewed and run locally before each commit; commits are
co-authored to make the AI involvement visible in the Git diary.
