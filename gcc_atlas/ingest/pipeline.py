"""Discover -> Fetch -> Extract -> Normalize -> Deduplicate -> Validate -> Verify -> Store.

Discovery happens upstream: sources come from the register, loaded by seed.py.
Every stage writes a scrape_jobs row, so a failed or partial run stays visible.
Each source is processed in its own transaction: one bad source cannot leave
another half-written.
"""
import uuid
from datetime import datetime, timezone

import requests

from ..db import audit, transaction
from ..verify import check_claims_for_source
from .extract import extract_text, normalize_text, validate_text
from .fetch import INBOX, fetch


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job(conn, source_id, run_id, stage, status, started, **kw):
    conn.execute(
        """INSERT INTO scrape_jobs(source_id, run_id, stage, status, method, http_status, error, content_sha256,
               started_at, finished_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (source_id, run_id, stage, status, kw.get("method"), kw.get("http_status"), kw.get("error"),
         kw.get("sha256"), started, _now()))


def ingest_source(conn, src, run_id, inbox=INBOX, use_playwright=False, session=None):
    """Process one source row. Returns the final outcome string."""
    sid = src["id"]
    t0 = _now()
    res = fetch(src["source_key"], src["url"], inbox=inbox, use_playwright=use_playwright, session=session)
    with transaction(conn):
        conn.execute(
            "UPDATE sources SET last_retrieval_attempt=?, retrieval_status=?, http_status=? WHERE id=?",
            (t0, res.status, res.http_status, sid))
        if not res.ok:
            _job(conn, sid, run_id, "fetch", "blocked" if res.status == "network_blocked" else "failed", t0,
                 method=res.method, http_status=res.http_status, error=res.error)
            return res.status
        conn.execute("UPDATE sources SET last_retrieval_date=?, content_sha256=? WHERE id=?",
                     (t0[:10], res.sha256, sid))
        _job(conn, sid, run_id, "fetch", "success", t0, method=res.method, http_status=res.http_status, sha256=res.sha256)

        t = _now()
        try:
            raw_text = extract_text(res.content, res.content_type)
        except Exception as exc:  # malformed PDF/HTML: log and stop for this source
            _job(conn, sid, run_id, "extract", "failed", t, error=f"{type(exc).__name__}: {exc}"[:300])
            return "extract_failed"
        _job(conn, sid, run_id, "extract", "success", t)

        t = _now()
        text = normalize_text(raw_text)
        _job(conn, sid, run_id, "normalize", "success", t)

        t = _now()
        if conn.execute("SELECT 1 FROM source_documents WHERE source_id=? AND sha256=?", (sid, res.sha256)).fetchone():
            _job(conn, sid, run_id, "dedupe", "skipped", t, sha256=res.sha256, error="identical content already stored")
            return "duplicate"
        _job(conn, sid, run_id, "dedupe", "success", t, sha256=res.sha256)

        t = _now()
        problems = validate_text(text)
        if problems:
            _job(conn, sid, run_id, "validate", "incomplete", t, error="; ".join(problems))
            return "invalid"
        _job(conn, sid, run_id, "validate", "success", t)

        t = _now()
        conn.execute(
            "INSERT INTO source_documents(source_id, retrieved_at, method, content_type, sha256, text) VALUES (?,?,?,?,?,?)",
            (sid, t0, res.method, res.content_type or "unknown", res.sha256, text))
        audit(conn, "pipeline", "store_document", "sources", sid, f"run={run_id} sha256={res.sha256}")
        _job(conn, sid, run_id, "store", "success", t, sha256=res.sha256)

        t = _now()
        stats = check_claims_for_source(conn, sid)
        _job(conn, sid, run_id, "verify", "success", t, error=None if stats["checked"] else "no claims cite this source")
        return "stored"


def run(conn, source_keys=None, inbox=INBOX, use_playwright=False):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    q = "SELECT * FROM sources"
    params = ()
    if source_keys:
        q += f" WHERE source_key IN ({','.join('?' * len(source_keys))})"
        params = tuple(source_keys)
    sources = conn.execute(q + " ORDER BY source_key", params).fetchall()
    session = requests.Session()
    outcomes = {}
    for src in sources:
        outcome = ingest_source(conn, src, run_id, inbox=inbox, use_playwright=use_playwright, session=session)
        outcomes[src["source_key"]] = outcome
    return run_id, outcomes
