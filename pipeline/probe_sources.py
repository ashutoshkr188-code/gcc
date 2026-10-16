"""Attempt to retrieve every source in research/source_register.csv and record what happened.

retrieval_status values:
  retrieved       - HTTP 2xx and non-empty body; raw bytes saved under data/raw/<id>.<ext>
  http_error      - server answered with a non-2xx status
  network_blocked - proxy refused the tunnel (environment network policy)
  failed          - any other error (DNS, TLS, timeout, ...)

last_retrieval_date is set only on success. last_retrieval_attempt is set on every try.
A JSON-lines log of every attempt is appended to data/logs/probe_log.jsonl.
"""
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "research" / "source_register.csv"
RAW_DIR = ROOT / "data" / "raw"
LOG = ROOT / "data" / "logs" / "probe_log.jsonl"
UA = "GCCAtlasResearchBot/0.1 (public-source research; contact: repo owner)"
TIMEOUT = 20


def classify_error(exc):
    msg = str(exc)
    if "Tunnel connection failed" in msg or "CONNECT tunnel failed" in msg or "403 Forbidden" in msg:
        return "network_blocked"
    return "failed"


def probe(row, session):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = {"source_id": row["source_id"], "url": row["url"], "attempted_at": now}
    try:
        r = session.get(row["url"], timeout=TIMEOUT, allow_redirects=True)
        result["http_status"] = r.status_code
        result["final_url"] = r.url
        if 200 <= r.status_code < 300 and r.content:
            ext = "pdf" if "pdf" in r.headers.get("content-type", "") else "html"
            (RAW_DIR / f"{row['source_id']}.{ext}").write_bytes(r.content)
            result["status"] = "retrieved"
            result["sha256"] = hashlib.sha256(r.content).hexdigest()
            result["bytes"] = len(r.content)
        else:
            result["status"] = "http_error"
    except requests.RequestException as exc:
        result["status"] = classify_error(exc)
        result["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return result


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with REGISTER.open() as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    session = requests.Session()
    session.headers["User-Agent"] = UA
    counts = {}
    with LOG.open("a") as log:
        for row in rows:
            res = probe(row, session)
            log.write(json.dumps(res) + "\n")
            row["last_retrieval_attempt"] = res["attempted_at"]
            row["retrieval_status"] = res["status"]
            row["http_status"] = res.get("http_status", "")
            row["retrieval_error"] = res.get("error", "")
            if res["status"] == "retrieved":
                row["last_retrieval_date"] = res["attempted_at"][:10]
                row["content_sha256"] = res["sha256"]
            counts[res["status"]] = counts.get(res["status"], 0) + 1
            print(f"{row['source_id']}  {res['status']:<16} {row['http_status']!s:<4} {row['url'][:90]}")

    with REGISTER.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("summary:", json.dumps(counts))
    return 0 if counts.get("retrieved") else 1


if __name__ == "__main__":
    sys.exit(main())
