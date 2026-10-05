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
- **Default model `claude-opus-5`**, overridable by `RADAR_MODEL`. Analysis
  runs at `effort: medium`, answering at `effort: high`.

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

- The brief + CSV, verbatim, with "python, make a new folder for this".
- _(add the follow-ups you give it from here on — e.g. fixes you asked for
  after testing the chat with trick questions)_
