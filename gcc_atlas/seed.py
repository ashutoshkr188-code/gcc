"""Load the research register and discovery leads into SQLite.

Everything loaded here starts at verification_status 'discovered'. Only the ingestion
pipeline plus a human review can move a record beyond that.
"""
import csv
import hashlib
import re

from .db import ROOT, audit, transaction

RESEARCH = ROOT / "research"
LEAD_NOTE = ("Lead from web-search discovery on 2026-10-16. The source has not been retrieved "
             "and the claim has not been checked against source text.")

# Reference data: city -> state. Aliases are used to match city names in source text.
CITIES = [
    ("Bengaluru", "Karnataka", "KA", "Bangalore"),
    ("Hyderabad", "Telangana", "TG", "Cyberabad;Gachibowli;HITEC City"),
    ("Chennai", "Tamil Nadu", "TN", "Madras"),
    ("Pune", "Maharashtra", "MH", "Poona"),
    ("Noida", "Uttar Pradesh", "UP", "Gautam Buddh Nagar;Gautam Buddha Nagar"),
    ("Gurugram", "Haryana", "HR", "Gurgaon"),
]


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def claim_hash(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _int_or_none(v):
    return int(v) if v not in (None, "") else None


def load_cities(conn):
    for name, state, code, aliases in CITIES:
        conn.execute(
            "INSERT INTO cities(name, state, state_code, aliases) VALUES (?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET state=excluded.state, state_code=excluded.state_code, aliases=excluded.aliases",
            (name, state, code, aliases),
        )


def load_sources(conn, path=None):
    """Upsert register metadata. Retrieval fields are copied only for new rows: after that the
    pipeline owns them, so re-seeding never overwrites a real retrieval outcome."""
    path = path or RESEARCH / "source_register.csv"
    n = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            conn.execute(
                """INSERT INTO sources(source_key, name, publisher, url, source_type, tier, data_categories,
                       related_entities, access_method, publication_date, publication_date_basis,
                       access_restrictions, discovered_via, discovery_date, last_retrieval_attempt,
                       last_retrieval_date, retrieval_status, http_status, content_sha256, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source_key) DO UPDATE SET
                       name=excluded.name, publisher=excluded.publisher, url=excluded.url,
                       source_type=excluded.source_type, tier=excluded.tier,
                       data_categories=excluded.data_categories, related_entities=excluded.related_entities,
                       access_method=excluded.access_method, publication_date=excluded.publication_date,
                       publication_date_basis=excluded.publication_date_basis,
                       access_restrictions=excluded.access_restrictions, notes=excluded.notes""",
                (r["source_key"] if "source_key" in r else r["source_id"], r["source_name"], r["publisher"],
                 r["url"], r["source_type"], int(r["tier"]), r["data_categories"], r["related_entities"],
                 r["access_method"], r["publication_date"] or None, r["publication_date_basis"],
                 r["access_restrictions"], r["discovered_via"], r["discovery_date"],
                 r["last_retrieval_attempt"] or None, r["last_retrieval_date"] or None,
                 r["retrieval_status"], _int_or_none(r["http_status"]), r["content_sha256"] or None, r["notes"]),
            )
            n += 1
    return n


def _source_id(conn, key):
    row = conn.execute("SELECT id FROM sources WHERE source_key=?", (key,)).fetchone()
    if not row:
        raise ValueError(f"lead references unknown source {key}")
    return row[0]


def load_centre_leads(conn, path=None):
    path = path or RESEARCH / "centre_leads.csv"
    added = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            slug = slugify(r["company"])
            conn.execute(
                "INSERT INTO companies(slug, name, aliases, industry, hq_country) VALUES (?,?,?,?,?) "
                "ON CONFLICT(slug) DO UPDATE SET aliases=excluded.aliases, industry=excluded.industry, hq_country=excluded.hq_country",
                (slug, r["company"], r["aliases"], r["industry"], r["hq_country"]),
            )
            company_id = conn.execute("SELECT id FROM companies WHERE slug=?", (slug,)).fetchone()[0]
            city = conn.execute("SELECT id FROM cities WHERE name=?", (r["city"],)).fetchone()
            if not city:
                raise ValueError(f"unknown city {r['city']}")
            name = f"{r['company']} – {r['city']}"
            cur = conn.execute(
                "INSERT OR IGNORE INTO gcc_centres(company_id, city_id, name, operational_status) VALUES (?,?,?, 'unverified_lead')",
                (company_id, city[0], name),
            )
            centre_id = conn.execute(
                "SELECT id FROM gcc_centres WHERE company_id=? AND city_id=? AND name=?", (company_id, city[0], name)
            ).fetchone()[0]
            if cur.rowcount:
                audit(conn, "seed", "insert", "gcc_centres", centre_id, "unverified lead from discovery")
            for key in r["source_keys"].split(";"):
                sid = _source_id(conn, key)
                h = claim_hash("gcc_centre", slug, r["city"], "presence_in_city", r["city"], key)
                cur = conn.execute(
                    """INSERT OR IGNORE INTO claims(subject_type, subject_id, field, value_text, geography,
                           source_id, verification_status, verification_note, claim_hash)
                       VALUES ('gcc_centre', ?, 'presence_in_city', ?, ?, ?, 'discovered', ?, ?)""",
                    (centre_id, r["city"], r["city"], sid, LEAD_NOTE, h),
                )
                added += cur.rowcount
    return added


def load_policy_leads(conn, path=None):
    path = path or RESEARCH / "policy_leads.csv"
    added = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            conn.execute(
                """INSERT INTO policies(name, state, issuing_authority, policy_kind, status, notes)
                   VALUES (?,?,?,?, 'unconfirmed', ?)
                   ON CONFLICT(state, name) DO UPDATE SET issuing_authority=excluded.issuing_authority,
                       policy_kind=excluded.policy_kind""",
                (r["policy_name"], r["state"], r["issuing_authority"], r["policy_kind"], r["note"]),
            )
            pid = conn.execute("SELECT id FROM policies WHERE state=? AND name=?", (r["state"], r["policy_name"])).fetchone()[0]
            keys = r["source_keys"].split(";")
            conn.execute(
                """INSERT INTO policy_versions(policy_id, version_label, amendment_note, source_id)
                   VALUES (?,?,?,?) ON CONFLICT(policy_id, version_label) DO UPDATE SET amendment_note=excluded.amendment_note""",
                (pid, r["version_label"], r["note"], _source_id(conn, keys[0])),
            )
            for key in keys:
                h = claim_hash("policy", r["state"], r["policy_name"], "existence", r["version_label"], key)
                cur = conn.execute(
                    """INSERT OR IGNORE INTO claims(subject_type, subject_id, field, value_text, geography,
                           source_id, verification_status, verification_note, claim_hash)
                       VALUES ('policy', ?, 'existence', ?, ?, ?, 'discovered', ?, ?)""",
                    (pid, f"{r['policy_name']} ({r['version_label']})", r["state"], _source_id(conn, key), LEAD_NOTE, h),
                )
                added += cur.rowcount
    return added


def seed_all(conn):
    with transaction(conn):
        load_cities(conn)
        n_src = load_sources(conn)
        n_centre_claims = load_centre_leads(conn)
        n_policy_claims = load_policy_leads(conn)
        audit(conn, "seed", "seed_all", "*", None,
              f"sources={n_src} new_centre_claims={n_centre_claims} new_policy_claims={n_policy_claims}")
    return {"sources": n_src, "new_centre_claims": n_centre_claims, "new_policy_claims": n_policy_claims}
