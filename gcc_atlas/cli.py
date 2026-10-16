"""Command line: python -m gcc_atlas.cli <command>"""
import argparse
import json
import sys

from . import quality, readiness
from .db import DEFAULT_DB, connect, migrate, transaction
from .ingest import pipeline
from .seed import seed_all
from .verify import ReviewError, review


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gcc_atlas")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="apply migrations")
    sub.add_parser("seed", help="load source register and discovery leads")
    p = sub.add_parser("ingest", help="run the ingestion pipeline")
    p.add_argument("--sources", nargs="*", help="source keys, e.g. S001 S007 (default: all)")
    p.add_argument("--playwright", action="store_true", help="fall back to a headless browser")
    p = sub.add_parser("review", help="record a human review of a claim")
    p.add_argument("claim_id", type=int)
    p.add_argument("status")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--operational-status", choices=["operating", "announced", "general_office", "closed"])
    sub.add_parser("quality", help="print Data Quality Center results")
    sub.add_parser("readiness", help="write docs/data_readiness_report.md")
    p = sub.add_parser("serve", help="run the API and web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    conn = connect(a.db)
    if a.cmd == "init":
        print("applied:", migrate(conn) or "nothing (up to date)")
    elif a.cmd == "seed":
        migrate(conn)
        print(json.dumps(seed_all(conn)))
    elif a.cmd == "ingest":
        run_id, outcomes = pipeline.run(conn, a.sources, use_playwright=a.playwright)
        summary = {}
        for k, v in outcomes.items():
            summary[v] = summary.get(v, 0) + 1
            print(f"{k}  {v}")
        print("run", run_id, json.dumps(summary))
    elif a.cmd == "review":
        try:
            with transaction(conn):
                review(conn, a.claim_id, a.status, a.reviewer, a.note, a.operational_status)
        except ReviewError as e:
            print("refused:", e, file=sys.stderr)
            return 2
        print("ok")
    elif a.cmd == "quality":
        for r in quality.run_all(conn, include_rows=False):
            print(f"{r['count']:>4}  [{r['severity']}] {r['label']}")
    elif a.cmd == "readiness":
        path, passed = readiness.write_report(conn)
        print(path, "PASS" if passed else "FAIL")
    elif a.cmd == "serve":
        import uvicorn
        import os
        os.environ["GCC_ATLAS_DB"] = a.db
        uvicorn.run("gcc_atlas.api:app", host=a.host, port=a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
