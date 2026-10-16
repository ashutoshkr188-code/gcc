"""SQLite connection handling and versioned migrations."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
DEFAULT_DB = Path(os.environ.get("GCC_ATLAS_DB", ROOT / "data" / "gcc_atlas.sqlite"))

STATUSES = (
    "discovered", "extracted", "verified_official", "verified_independent", "needs_review",
    "conflicting", "possibly_outdated", "unverified", "rejected",
)
STATUS_LABELS = {
    "discovered": "Discovered",
    "extracted": "Extracted",
    "verified_official": "Verified — Official source",
    "verified_independent": "Verified — Independent source",
    "needs_review": "Needs review",
    "conflicting": "Conflicting information",
    "possibly_outdated": "Possibly outdated",
    "unverified": "Unverified",
    "rejected": "Rejected",
}


def _resolve_db_path(path=None):
    if path:
        return Path(path)
    if "GCC_ATLAS_DB" in os.environ:
        return Path(os.environ["GCC_ATLAS_DB"])
    candidates = [
        ROOT / "data" / "gcc_atlas.sqlite",
        Path(__file__).resolve().parent / "gcc_atlas.sqlite",
        ROOT / "gcc_atlas" / "gcc_atlas.sqlite",
    ]
    bundled = next((c for c in candidates if c.exists()), candidates[0])
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        tmp_db = Path("/tmp/gcc_atlas.sqlite")
        if not tmp_db.exists():
            if bundled.exists():
                import shutil
                tmp_db.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bundled, tmp_db)
            else:
                try:
                    from .seed import seed_all
                    tmp_db.parent.mkdir(parents=True, exist_ok=True)
                    init_conn = sqlite3.connect(tmp_db)
                    migrate(init_conn)
                    seed_all(init_conn)
                    init_conn.close()
                except Exception:
                    pass
        if tmp_db.exists():
            return tmp_db
    return bundled


def connect(path=None, check_same_thread=True):
    path = _resolve_db_path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    return conn


@contextmanager
def transaction(conn):
    """Commit on success, roll back on any exception."""
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def migrate(conn):
    """Apply each migrations/NNN_*.sql exactly once, in order. Returns versions applied."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = f.stem
        if version in done:
            continue
        sql = f.read_text()
        # executescript commits implicitly, so wrap the script in its own transaction
        conn.executescript(
            "BEGIN;\n" + sql + f"\nINSERT INTO schema_migrations(version) VALUES ('{version}');\nCOMMIT;"
        )
        applied.append(version)
    return applied


def audit(conn, actor, action, table, record_id=None, detail=""):
    conn.execute(
        "INSERT INTO audit_log(actor, action, table_name, record_id, detail) VALUES (?,?,?,?,?)",
        (actor, action, table, record_id, detail),
    )
