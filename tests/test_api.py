"""Phase 7: API routes against a seeded SQLite database."""
import pytest
from fastapi.testclient import TestClient

from gcc_atlas.ingest import pipeline
from gcc_atlas.verify import review


@pytest.fixture
def client(seeded, tmp_path, monkeypatch):
    db = seeded.execute("PRAGMA database_list").fetchone()["file"]
    monkeypatch.setenv("GCC_ATLAS_DB", db)
    from gcc_atlas.api import app
    return TestClient(app)


@pytest.fixture
def verified_gs(seeded, tmp_path):
    """One claim verified through the real pipeline + review path, using a local fixture file."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "S007.txt").write_text("Test fixture. Goldman Sachs opened an office in Hyderabad. " + "filler " * 40)
    pipeline.run(seeded, ["S007"], inbox=inbox)
    cid = seeded.execute("""SELECT c.id FROM claims c JOIN sources s ON s.id=c.source_id
                            WHERE s.source_key='S007' AND c.evidence_match=1""").fetchone()[0]
    review(seeded, cid, "verified_official", "tester", operational_status="operating")
    seeded.commit()
    return cid


def test_health_and_overview(client):
    assert client.get("/api/health").json() == {"ok": True}
    o = client.get("/api/overview").json()
    assert o["companies"] == 10 and o["cities"] == 6 and o["sources"] == 41


def test_company_search(client):
    r = client.get("/api/companies", params={"q": "master"}).json()
    assert [c["name"] for c in r] == ["Mastercard"]
    r = client.get("/api/companies", params={"city": "Gurugram"}).json()
    assert [c["name"] for c in r] == ["American Express"]
    assert client.get("/api/companies", params={"q": "zzzz"}).json() == []


def test_company_search_matches_aliases(client):
    assert [c["name"] for c in client.get("/api/companies", params={"q": "J.P. Morgan"}).json()] == ["JPMorgan Chase"]


def test_input_validation(client):
    assert client.get("/api/companies", params={"city": "Mumbai"}).status_code == 422
    assert client.get("/api/companies", params={"q": "x" * 101}).status_code == 422
    assert client.get("/api/centres", params={"verification": "maybe"}).status_code == 422
    assert client.get("/api/cities/compare", params={"cities": ["Pune"]}).status_code == 422
    assert client.get("/api/cities/compare", params={"cities": ["Pune", "Pune"]}).status_code == 422
    assert client.get("/api/sources", params={"tier": 9}).status_code == 422
    assert client.post("/api/research", json={"question": ""}).status_code == 422


def test_centre_search_filters(client):
    all_c = client.get("/api/centres").json()
    assert len(all_c) == 20
    pune = client.get("/api/centres", params={"city": "Pune"}).json()
    assert {c["company"] for c in pune} == {"Barclays", "Mastercard"}
    assert all(c["verification_label"] == "Discovered" for c in all_c)
    assert client.get("/api/centres", params={"status": "operating"}).json() == []


def test_company_profile_and_404(client):
    p = client.get("/api/companies/goldman-sachs").json()
    assert {c["city"] for c in p["centres"]} == {"Bengaluru", "Hyderabad"}
    assert all(cl["url"].startswith("https://") for c in p["centres"] for cl in c["claims"])
    assert client.get("/api/companies/nope").status_code == 404


def test_group_structure_empty_but_valid(client):
    s = client.get("/api/companies/ford/structure").json()
    assert s == {"company": "Ford", "entities": [], "relationships": []}
    assert len(client.get("/api/groups").json()) == 10


def test_city_comparison(client):
    r = client.get("/api/cities/compare", params={"cities": ["Bengaluru", "Pune"]}).json()
    assert [c["name"] for c in r["cities"]] == ["Bengaluru", "Pune"]
    assert {p["name"] for p in r["cities"][1]["policies"]} == {"Maharashtra GCC Policy 2025"}
    assert r["comparable_cost_groups"] == []  # no verified, compatible cost data -> nothing to chart


def test_city_comparison_only_groups_compatible_costs(client, seeded):
    ids = {r["name"]: r["id"] for r in seeded.execute("SELECT id, name FROM cities")}
    rows = [(ids["Pune"], "INR", "per_month"), (ids["Chennai"], "INR", "per_month"), (ids["Chennai"], "INR", "per_year")]
    for city_id, cur, per in rows:
        seeded.execute("""INSERT INTO cost_observations(cost_stage, category, city_id, geographic_scope, value_num, currency,
                          unit, period, period_start, verification_status) VALUES ('recurring','office_rent',?, 'city',
                          100, ?, 'per sq ft', ?, '2026-04-01', 'verified_official')""", (city_id, cur, per))
    seeded.commit()
    r = client.get("/api/cities/compare", params={"cities": ["Pune", "Chennai"]}).json()
    assert len(r["comparable_cost_groups"]) == 1
    assert r["comparable_cost_groups"][0]["period"] == "per_month"
    assert r["noncomparable_cost_observations"] == 1


def test_policies(client):
    ps = client.get("/api/policies").json()
    assert len(ps) == 8 and all(p["status"] == "unconfirmed" for p in ps)
    assert ps[-1]["state"] == "Central"
    ka = [p for p in ps if p["state"] == "Karnataka"][0]
    d = client.get(f"/api/policies/{ka['id']}").json()
    assert {v["version_label"] for v in d["versions"]} == {"draft", "final (reported)"}
    assert client.get("/api/policies/9999").status_code == 404


def test_costs_empty(client):
    assert client.get("/api/costs").json() == []


def test_sources_and_evidence(client):
    s = client.get("/api/sources", params={"tier": 1}).json()
    assert s and all(x["tier"] == 1 for x in s)
    d = client.get("/api/sources/S013").json()
    assert d["url"].startswith("https://www.mastercard.com/")
    assert client.get("/api/sources/S999").status_code == 404
    claim = client.get("/api/claims").json()[0]
    c = client.get(f"/api/claims/{claim['id']}").json()
    assert c["url"] and c["verification_label"] == "Discovered"


def test_source_links_are_valid_urls(client):
    from urllib.parse import urlparse
    for s in client.get("/api/sources").json():
        u = urlparse(s["url"])
        assert u.scheme == "https" and "." in u.netloc


def test_verification_summary(client):
    v = client.get("/api/verification/summary").json()
    counts = {x["status"]: x["count"] for x in v["claims_by_status"]}
    assert counts["discovered"] == 45 and sum(counts.values()) == 45
    assert len(v["claims_by_status"]) == 9


def test_quality_endpoint_matches_sql(client, seeded):
    q = {x["check"]: x["count"] for x in client.get("/api/quality").json()}
    assert q["claims_citing_unretrieved_sources"] == seeded.execute(
        "SELECT COUNT(*) FROM claims c JOIN sources s ON s.id=c.source_id WHERE s.retrieval_status<>'retrieved'").fetchone()[0]


def test_readiness_endpoint(client):
    r = client.get("/api/readiness").json()
    assert r["metrics"]["table_counts"]["claims"] == 45
    assert any(not g["pass"] for g in r["gate"])


def test_review_endpoint_requires_token(client, monkeypatch):
    cid = client.get("/api/claims").json()[0]["id"]
    body = {"status": "rejected", "reviewer": "tester"}
    assert client.post(f"/api/claims/{cid}/review", json=body).status_code == 403
    monkeypatch.setenv("GCC_ATLAS_REVIEW_TOKEN", "secret")
    assert client.post(f"/api/claims/{cid}/review", json=body).status_code == 401
    h = {"x-review-token": "secret"}
    r = client.post(f"/api/claims/{cid}/review", json={"status": "verified_official", "reviewer": "tester"}, headers=h)
    assert r.status_code == 409  # no evidence -> refused
    r = client.post(f"/api/claims/{cid}/review", json=body, headers=h)
    assert r.status_code == 200 and r.json()["verification_status"] == "rejected"


def test_verified_record_flows_through_api(client, verified_gs):
    c = client.get(f"/api/claims/{verified_gs}").json()
    assert c["verification_status"] == "verified_official" and "Hyderabad" in c["evidence_excerpt"]
    assert [h["action"] for h in c["history"]][-1] == "review:verified_official"
    op = client.get("/api/centres", params={"status": "operating"}).json()
    assert [(x["company"], x["city"]) for x in op] == [("Goldman Sachs", "Hyderabad")]


# ---------- Research Assistant ----------

def test_assistant_cites_every_finding(client):
    r = client.post("/api/research", json={"question": "Which companies have GCCs in Pune?"}).json()
    assert r["understood"]["cities"] == ["Pune"]
    assert r["findings"]
    for f in r["findings"]:
        assert f["citation"]["url"].startswith("https://") and f["citation"]["status_label"]
    assert any(g.startswith("None of these centre records has been verified") for g in r["gaps"])


def test_assistant_reports_missing_cost_data(client):
    r = client.post("/api/research", json={"question": "What is office rent in Bangalore?"}).json()
    assert r["understood"]["cities"] == ["Bengaluru"] and "costs" in r["understood"]["topics"]
    assert any("No cost observations" in g for g in r["gaps"])


def test_assistant_incentives_by_state(client):
    r = client.post("/api/research", json={"question": "What incentives does Haryana offer?"}).json()
    assert r["understood"]["states"] == ["Haryana"]
    assert all(f["type"] == "policy" for f in r["findings"]) and r["findings"]
    assert any("No incentive terms" in g for g in r["gaps"])


def test_assistant_unknown_question(client):
    r = client.post("/api/research", json={"question": "hello there"}).json()
    assert r["findings"] == [] and r["gaps"]


def test_assistant_uses_verified_evidence(client, verified_gs):
    r = client.post("/api/research", json={"question": "Goldman Sachs Hyderabad"}).json()
    v = [f for f in r["findings"] if f["citation"]["status"] == "verified_official"]
    assert len(v) == 1 and "Hyderabad" in v[0]["evidence"]
