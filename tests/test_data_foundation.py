"""Phases 3-6: database init, seeding, pipeline, dedup, verification, quality checks, readiness."""
import sqlite3

import pytest

from gcc_atlas import quality, readiness
from gcc_atlas.db import migrate, transaction
from gcc_atlas.ingest import pipeline
from gcc_atlas.ingest.fetch import _classify
from gcc_atlas.seed import seed_all
from gcc_atlas.verify import ReviewError, review

from .conftest import point_source_at


# ---------- database initialization ----------

def test_migrations_create_all_tables_and_are_idempotent(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ["companies", "entities", "company_entity_relationships", "cities", "gcc_centres", "sources", "claims",
              "cost_observations", "policies", "policy_versions", "incentives", "talent_observations",
              "scrape_jobs", "audit_log", "source_documents", "schema_migrations"]:
        assert t in tables
    assert migrate(conn) == []


def test_foreign_keys_and_status_checks_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO gcc_centres(company_id, city_id, name, operational_status) VALUES (999, 999, 'x', 'operating')")
    conn.execute("INSERT INTO cities(name, state, state_code) VALUES ('Pune','Maharashtra','MH')")
    conn.execute("INSERT INTO companies(slug, name, industry) VALUES ('a','A','x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO gcc_centres(company_id, city_id, name, operational_status, verification_status) "
                     "VALUES (1, 1, 'x', 'operating', 'probably_true')")


def test_transaction_rolls_back(conn):
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO cities(name, state, state_code) VALUES ('X','Y','Z')")
            raise RuntimeError
    assert conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0] == 0


# ---------- seeding / dedup ----------

def test_seed_is_idempotent(seeded):
    before = {t: seeded.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["sources", "claims", "gcc_centres", "companies", "policies", "policy_versions"]}
    out = seed_all(seeded)
    after = {t: seeded.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in before}
    assert before == after
    assert out["new_centre_claims"] == 0 and out["new_policy_claims"] == 0
    assert before["companies"] == 10 and before["sources"] == 41


def test_seed_leads_are_never_verified(seeded):
    statuses = {r[0] for r in seeded.execute("SELECT DISTINCT verification_status FROM claims")}
    assert statuses == {"discovered"}
    assert {r[0] for r in seeded.execute("SELECT DISTINCT operational_status FROM gcc_centres")} == {"unverified_lead"}


def test_reseed_preserves_retrieval_outcome(seeded, fixture_server):
    point_source_at(seeded, "S007", fixture_server + "/gs_hyderabad.html")
    pipeline.run(seeded, ["S007"])
    seed_all(seeded)
    assert seeded.execute("SELECT retrieval_status FROM sources WHERE source_key='S007'").fetchone()[0] == "retrieved"


# ---------- scraper execution ----------

def _claim(conn, key, city):
    return conn.execute(
        """SELECT c.* FROM claims c JOIN sources s ON s.id=c.source_id JOIN gcc_centres g ON g.id=c.subject_id
           JOIN cities ci ON ci.id=g.city_id WHERE s.source_key=? AND ci.name=? AND c.subject_type='gcc_centre'""",
        (key, city)).fetchone()


def test_pipeline_stores_document_and_flags_supported_claim(seeded, fixture_server):
    point_source_at(seeded, "S007", fixture_server + "/gs_hyderabad.html")
    _, out = pipeline.run(seeded, ["S007"])
    assert out == {"S007": "stored"}
    doc = seeded.execute("SELECT * FROM source_documents").fetchone()
    assert "var x" not in doc["text"] and "Menu Home" not in doc["text"]  # script/nav stripped
    c = _claim(seeded, "S007", "Hyderabad")
    assert c["evidence_match"] == 1
    assert c["verification_status"] == "needs_review"  # automated check never self-approves
    assert "Hyderabad" in c["evidence_excerpt"]
    stages = [r[0] for r in seeded.execute("SELECT stage FROM scrape_jobs ORDER BY id")]
    assert stages == ["fetch", "extract", "normalize", "dedupe", "validate", "store", "verify"]


def test_city_only_on_page_elsewhere_is_not_evidence(seeded, fixture_server):
    point_source_at(seeded, "S007", fixture_server + "/gs_hyderabad.html")
    pipeline.run(seeded, ["S007"])
    c = _claim(seeded, "S007", "Bengaluru")  # S007 also cited for Bengaluru; page does not support it
    assert c["evidence_match"] == 0 and c["verification_status"] == "unverified"


def test_duplicate_fetch_is_skipped(seeded, fixture_server):
    point_source_at(seeded, "S007", fixture_server + "/gs_hyderabad.html")
    pipeline.run(seeded, ["S007"])
    _, out = pipeline.run(seeded, ["S007"])
    assert out["S007"] == "duplicate"
    assert seeded.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0] == 1


def test_unrelated_page_marks_claim_unverified(seeded, fixture_server):
    point_source_at(seeded, "S008", fixture_server + "/unrelated.html")
    pipeline.run(seeded, ["S008"])
    c = _claim(seeded, "S008", "Hyderabad")
    assert c["verification_status"] == "unverified"


def test_block_page_is_rejected_by_validation(seeded, fixture_server):
    point_source_at(seeded, "S008", fixture_server + "/blocked.html")
    _, out = pipeline.run(seeded, ["S008"])
    assert out["S008"] == "invalid"
    assert seeded.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0] == 0
    assert seeded.execute("SELECT status FROM scrape_jobs WHERE stage='validate'").fetchone()[0] == "incomplete"


def test_http_404_is_logged_as_failed(seeded, fixture_server):
    point_source_at(seeded, "S008", fixture_server + "/missing.html")
    _, out = pipeline.run(seeded, ["S008"])
    assert out["S008"] == "http_error"
    job = seeded.execute("SELECT * FROM scrape_jobs").fetchone()
    assert job["status"] == "failed" and job["http_status"] == 404
    src = seeded.execute("SELECT * FROM sources WHERE source_key='S008'").fetchone()
    assert src["last_retrieval_date"] is None


def test_manual_upload_inbox(seeded, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "S013.txt").write_text(
        "Test fixture, not real data. Mastercard opened its technology hub in Pune. " + "filler " * 40)
    _, out = pipeline.run(seeded, ["S013"], inbox=inbox)
    assert out["S013"] == "stored"
    assert seeded.execute("SELECT method FROM source_documents").fetchone()[0] == "manual_upload"
    assert _claim(seeded, "S013", "Pune")["evidence_match"] == 1


def test_proxy_errors_classified_as_blocked():
    assert _classify(Exception("Tunnel connection failed: 403 Forbidden")) == "network_blocked"
    assert _classify(Exception("Name or service not known")) == "failed"


# ---------- verification workflow ----------

def test_review_refuses_verification_without_evidence(seeded):
    cid = seeded.execute("SELECT id FROM claims LIMIT 1").fetchone()[0]
    with pytest.raises(ReviewError):
        review(seeded, cid, "verified_official", "tester")


def test_review_official_requires_official_tier(seeded, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "S014.txt").write_text("Test fixture. American Express opened a campus in Gurugram. " + "filler " * 40)
    pipeline.run(seeded, ["S014"], inbox=inbox)  # S014 is a tier-6 news source
    c = _claim(seeded, "S014", "Gurugram")
    with pytest.raises(ReviewError, match="tier"):
        review(seeded, c["id"], "verified_official", "tester")
    with pytest.raises(ReviewError, match="2\\+ independent"):
        review(seeded, c["id"], "verified_independent", "tester")


def test_review_official_succeeds_and_propagates(seeded, fixture_server):
    point_source_at(seeded, "S007", fixture_server + "/gs_hyderabad.html")
    pipeline.run(seeded, ["S007"])
    c = _claim(seeded, "S007", "Hyderabad")
    review(seeded, c["id"], "verified_official", "tester", operational_status="operating")
    g = seeded.execute("SELECT * FROM gcc_centres WHERE id=?", (c["subject_id"],)).fetchone()
    assert g["verification_status"] == "verified_official" and g["operational_status"] == "operating"
    assert seeded.execute("SELECT COUNT(*) FROM audit_log WHERE action='review:verified_official'").fetchone()[0] == 1


def test_independent_verification_with_two_publishers(seeded, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for key in ("S014", "S015"):  # different publishers, both cite Amex Gurugram
        (inbox / f"{key}.txt").write_text("Test fixture. American Express has a campus in Gurugram. " + "filler " * 40)
    pipeline.run(seeded, ["S014", "S015"], inbox=inbox)
    c = _claim(seeded, "S014", "Gurugram")
    review(seeded, c["id"], "verified_independent", "tester")
    assert seeded.execute("SELECT verification_status FROM claims WHERE id=?", (c["id"],)).fetchone()[0] == "verified_independent"


# ---------- data quality checks ----------

def _counts(conn):
    return {r["check"]: r["count"] for r in quality.run_all(conn, include_rows=False)}


def test_quality_baseline_on_seeded_db(seeded):
    q = _counts(seeded)
    assert q["claims_citing_unretrieved_sources"] == seeded.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    assert q["missing_source_urls"] == 0 and q["invalid_urls"] == 0 and q["duplicate_claims"] == 0


def test_quality_flags_bad_records(seeded):
    sid = seeded.execute("SELECT id FROM sources LIMIT 1").fetchone()[0]
    pune = seeded.execute("SELECT id FROM cities WHERE name='Pune'").fetchone()[0]
    seeded.execute("INSERT INTO claims(subject_type, subject_id, field, value_text, value_num, source_id, claim_hash) "
                   "VALUES ('company', 1, 'headcount', '5000', 5000, ?, 'h1')", (sid,))
    seeded.execute("INSERT INTO cost_observations(cost_stage, category, city_id, geographic_scope, value_num, currency, unit, period) "
                   "VALUES ('recurring','office_rent',?, 'city', 90, 'INR','per sq ft','per_month')", (pune,))
    seeded.execute("INSERT INTO cost_observations(cost_stage, category, city_id, geographic_scope, value_num, currency, unit, period) "
                   "VALUES ('recurring','office_rent',?, 'city', 1.1, 'USD','per sq ft','per_month')", (pune,))
    centre = seeded.execute("SELECT g.id FROM gcc_centres g JOIN cities c ON c.id=g.city_id WHERE c.name='Pune' LIMIT 1").fetchone()[0]
    seeded.execute("INSERT INTO claims(subject_type, subject_id, field, value_text, geography, source_id, claim_hash) "
                   "VALUES ('gcc_centre', ?, 'presence_in_city', 'Chennai', 'Chennai', ?, 'h2')", (centre, sid))
    seeded.execute("INSERT INTO sources(source_key, name, publisher, url, source_type, tier, access_method, discovered_via, discovery_date) "
                   "VALUES ('BAD','b','b','ftp://x y','news',6,'html','test','2026-01-01')")
    seeded.execute("INSERT INTO policy_versions(policy_id, version_label, effective_date, expiry_date) VALUES (1,'t','2026-01-01','2025-01-01')")
    for i, v in enumerate(("1000", "1500")):
        seeded.execute("INSERT INTO claims(subject_type, subject_id, field, value_text, source_id, evidence_match, claim_hash) "
                       "VALUES ('company', 2, 'planned_hires', ?, ?, 1, ?)", (v, sid, f"c{i}"))
    q = _counts(seeded)
    assert q["missing_units"] == 1
    assert q["unsupported_numbers"] == 1
    assert q["incompatible_currencies"] == 1
    assert q["noncomparable_costs"] == 2  # no period_start / methodology
    assert q["geographic_mismatches"] == 1
    assert q["invalid_urls"] == 1
    assert q["inconsistent_dates"] >= 1
    assert q["conflicting_sources"] == 1


def test_unsupported_relationship_flagged(seeded):
    seeded.execute("INSERT INTO entities(name, jurisdiction) VALUES ('Parent Inc','US')")
    seeded.execute("INSERT INTO entities(name, jurisdiction) VALUES ('Parent India Pvt Ltd','IN')")
    seeded.execute("INSERT INTO company_entity_relationships(parent_entity_id, child_entity_id, relationship_type) VALUES (1,2,'subsidiary')")
    assert _counts(seeded)["unsupported_relationships"] == 1


# ---------- readiness report ----------

def test_readiness_counts_match_sql(seeded):
    m = readiness.metrics(seeded)
    for t, n in m["table_counts"].items():
        assert n == seeded.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    assert m["sources_retrieved"] == 0
    assert sum(c["centres_any_status"] for c in m["city_coverage"]) == m["table_counts"]["gcc_centres"]


def test_readiness_gate_fails_without_verified_records(seeded):
    g = dict((n, ok) for n, ok, _ in readiness.gate(seeded))
    assert g["Database initializes reproducibly"]
    assert g["Source provenance stored"]
    assert not g["Representative records checked against sources"]
