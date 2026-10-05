"""CLI:  python -m radar ingest | analyse | serve | stats"""
from __future__ import annotations

import argparse
import logging
import sys

from .db import init_db, session

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


def cmd_ingest(args):
    from .fetch import fetch_all
    from .chunk import chunk_all
    init_db()
    print("fetch:", fetch_all(force=args.force))
    print("chunks written:", chunk_all(force=args.force))


def cmd_analyse(args):
    from .analyse import analyse_all
    init_db()
    print(analyse_all(force=args.force))


def cmd_serve(args):
    import uvicorn
    init_db()
    uvicorn.run("radar.app:app", host="127.0.0.1", port=args.port, reload=args.reload)


def cmd_stats(args):
    init_db()
    with session() as conn:
        for t in ("companies", "sources", "chunks", "ai_outputs", "claims", "qa_log"):
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"{t:12s} {n}")
        for r in conn.execute("SELECT id, kind, fetch_status, title, fetch_error FROM sources"):
            print(f"  [{r['id']:2d}] {r['kind']:5s} {r['fetch_status']:7s} {r['title'][:60]}"
                  + (f"  -- {r['fetch_error']}" if r['fetch_error'] else ""))


def main(argv=None):
    p = argparse.ArgumentParser(prog="radar")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ingest", help="fetch PDFs/transcripts and chunk them"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("analyse", help="LLM summaries, tags, claims"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_analyse)
    s = sub.add_parser("serve", help="run the web app"); s.add_argument("--port", type=int, default=8000); s.add_argument("--reload", action="store_true"); s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("stats"); s.set_defaults(fn=cmd_stats)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
