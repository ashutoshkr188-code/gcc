"""Data access layer. All queries are parameterized. Functions take an open connection."""
from .db import STATUS_LABELS

VERIFIED = ("verified_official", "verified_independent")


def _d(rows):
    return [dict(r) for r in rows]


def _label(item):
    if item and "verification_status" in item:
        item["verification_label"] = STATUS_LABELS.get(item["verification_status"], item["verification_status"])
    return item


def _labelled(rows):
    return [_label(dict(r)) for r in rows]


def city_names(conn):
    return [r[0] for r in conn.execute("SELECT name FROM cities ORDER BY name")]


def list_cities(conn):
    return _d(conn.execute("""
        SELECT ci.*, COUNT(g.id) AS centre_records,
               SUM(g.verification_status IN ('verified_official','verified_independent')) AS verified_centres
        FROM cities ci LEFT JOIN gcc_centres g ON g.city_id=ci.id GROUP BY ci.id ORDER BY ci.name"""))


def search_companies(conn, q=None, industry=None, city=None, limit=50):
    sql = """SELECT co.id, co.slug, co.name, co.industry, co.hq_country,
                    GROUP_CONCAT(DISTINCT ci.name) AS cities, COUNT(DISTINCT g.id) AS centre_records,
                    SUM(g.verification_status IN ('verified_official','verified_independent')) AS verified_centres
             FROM companies co LEFT JOIN gcc_centres g ON g.company_id=co.id LEFT JOIN cities ci ON ci.id=g.city_id
             WHERE 1=1"""
    p = []
    if q:
        sql += " AND (co.name LIKE ? OR co.aliases LIKE ?)"
        p += [f"%{q}%", f"%{q}%"]
    if industry:
        sql += " AND co.industry = ?"
        p.append(industry)
    if city:
        sql += " AND co.id IN (SELECT g2.company_id FROM gcc_centres g2 JOIN cities c2 ON c2.id=g2.city_id WHERE c2.name=?)"
        p.append(city)
    sql += " GROUP BY co.id ORDER BY co.name LIMIT ?"
    p.append(limit)
    return _d(conn.execute(sql, p))


def industries(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT industry FROM companies ORDER BY 1")]


def search_centres(conn, q=None, city=None, status=None, verification=None, industry=None, limit=200):
    sql = """SELECT g.id, g.name, g.operational_status, g.functions, g.announced_date, g.established_date,
                    g.verification_status, co.name AS company, co.slug AS company_slug, co.industry,
                    ci.name AS city, ci.state,
                    (SELECT COUNT(*) FROM claims c WHERE c.subject_type='gcc_centre' AND c.subject_id=g.id) AS claim_count
             FROM gcc_centres g JOIN companies co ON co.id=g.company_id JOIN cities ci ON ci.id=g.city_id WHERE 1=1"""
    p = []
    if q:
        sql += " AND (co.name LIKE ? OR co.aliases LIKE ? OR g.name LIKE ? OR g.functions LIKE ?)"
        p += [f"%{q}%"] * 4
    for col, val in (("ci.name", city), ("g.operational_status", status),
                     ("g.verification_status", verification), ("co.industry", industry)):
        if val:
            sql += f" AND {col} = ?"
            p.append(val)
    sql += " ORDER BY ci.name, co.name LIMIT ?"
    p.append(limit)
    return _labelled(conn.execute(sql, p))


def claims_for(conn, subject_type, subject_id):
    return _labelled(conn.execute("""
        SELECT c.id, c.field, c.value_text, c.value_num, c.unit, c.as_of_date, c.geography,
               c.evidence_excerpt, c.evidence_locator, c.evidence_match, c.verification_status, c.verification_note,
               c.reviewed_by, c.reviewed_at, s.source_key, s.name AS source_name, s.publisher, s.url,
               s.tier, s.retrieval_status, s.last_retrieval_date, s.publication_date
        FROM claims c LEFT JOIN sources s ON s.id=c.source_id
        WHERE c.subject_type=? AND c.subject_id=? ORDER BY s.tier, c.id""", (subject_type, subject_id)))


def company_profile(conn, slug):
    co = conn.execute("SELECT * FROM companies WHERE slug=?", (slug,)).fetchone()
    if not co:
        return None
    co = dict(co)
    co["centres"] = search_centres_for_company(conn, co["id"])
    co["structure"] = company_structure(conn, slug)
    return co


def search_centres_for_company(conn, company_id):
    rows = _labelled(conn.execute("""
        SELECT g.*, ci.name AS city, ci.state FROM gcc_centres g JOIN cities ci ON ci.id=g.city_id
        WHERE g.company_id=? ORDER BY ci.name""", (company_id,)))
    for r in rows:
        r["claims"] = claims_for(conn, "gcc_centre", r["id"])
    return rows


def company_structure(conn, slug):
    co = conn.execute("SELECT id, name FROM companies WHERE slug=?", (slug,)).fetchone()
    if not co:
        return None
    entities = _d(conn.execute("SELECT * FROM entities WHERE company_id=? ORDER BY jurisdiction, name", (co["id"],)))
    ids = [e["id"] for e in entities]
    rels = []
    if ids:
        ph = ",".join("?" * len(ids))
        rels = _labelled(conn.execute(f"""
            SELECT r.*, pe.name AS parent_name, pe.jurisdiction AS parent_jurisdiction,
                   ce.name AS child_name, ce.jurisdiction AS child_jurisdiction,
                   s.source_key, s.url, c.evidence_excerpt
            FROM company_entity_relationships r
            JOIN entities pe ON pe.id=r.parent_entity_id JOIN entities ce ON ce.id=r.child_entity_id
            LEFT JOIN sources s ON s.id=r.source_id LEFT JOIN claims c ON c.id=r.claim_id
            WHERE r.parent_entity_id IN ({ph}) OR r.child_entity_id IN ({ph})""", ids + ids))
    return {"company": co["name"], "entities": entities, "relationships": rels}


def groups_overview(conn):
    return _d(conn.execute("""
        SELECT co.slug, co.name, co.industry, COUNT(DISTINCT e.id) AS entities,
               (SELECT COUNT(*) FROM company_entity_relationships r JOIN entities e2 ON e2.id IN (r.parent_entity_id, r.child_entity_id)
                WHERE e2.company_id=co.id) AS relationships
        FROM companies co LEFT JOIN entities e ON e.company_id=co.id GROUP BY co.id ORDER BY co.name"""))


def cost_observations(conn, city=None, category=None, stage=None, verified_only=False):
    sql = """SELECT o.*, ci.name AS city, s.source_key, s.url, s.publisher FROM cost_observations o
             LEFT JOIN cities ci ON ci.id=o.city_id LEFT JOIN sources s ON s.id=o.source_id WHERE 1=1"""
    p = []
    for col, val in (("ci.name", city), ("o.category", category), ("o.cost_stage", stage)):
        if val:
            sql += f" AND {col}=?"
            p.append(val)
    if verified_only:
        sql += " AND o.verification_status IN ('verified_official','verified_independent')"
    return _labelled(conn.execute(sql + " ORDER BY o.category, ci.name, o.period_start", p))


def compare_cities(conn, cities):
    out = {"cities": [], "comparable_cost_groups": [], "noncomparable_cost_observations": 0}
    for name in cities:
        c = dict(conn.execute("SELECT * FROM cities WHERE name=?", (name,)).fetchone())
        c["centres_by_status"] = {r[0]: r[1] for r in conn.execute(
            "SELECT operational_status, COUNT(*) FROM gcc_centres WHERE city_id=? GROUP BY 1", (c["id"],))}
        c["centres_by_verification"] = {r[0]: r[1] for r in conn.execute(
            "SELECT verification_status, COUNT(*) FROM gcc_centres WHERE city_id=? GROUP BY 1", (c["id"],))}
        c["companies"] = [r[0] for r in conn.execute(
            "SELECT DISTINCT co.name FROM gcc_centres g JOIN companies co ON co.id=g.company_id WHERE g.city_id=? ORDER BY 1",
            (c["id"],))]
        c["policies"] = _labelled(conn.execute(
            "SELECT id, name, status, verification_status FROM policies WHERE state=? ORDER BY name", (c["state"],)))
        c["talent_observations"] = _labelled(conn.execute(
            "SELECT * FROM talent_observations WHERE city_id=? ORDER BY indicator, period_start", (c["id"],)))
        out["cities"].append(c)
    # Only verified observations sharing category, unit, period, currency and building grade are comparable,
    # and only when at least two of the selected cities have one.
    ph = ",".join("?" * len(cities))
    groups = conn.execute(f"""
        SELECT o.category, o.unit, o.period, o.currency, COALESCE(o.building_category,'') AS building_category,
               COUNT(DISTINCT o.city_id) AS n_cities
        FROM cost_observations o JOIN cities ci ON ci.id=o.city_id
        WHERE ci.name IN ({ph}) AND o.verification_status IN ('verified_official','verified_independent')
          AND o.unit IS NOT NULL AND o.period IS NOT NULL AND o.currency IS NOT NULL AND o.period_start IS NOT NULL
        GROUP BY 1,2,3,4,5 HAVING n_cities >= 2""", cities).fetchall()
    for g in groups:
        obs = _labelled(conn.execute(f"""
            SELECT ci.name AS city, o.value_num, o.value_low, o.value_high, o.period_start, o.period_end,
                   o.publication_date, o.methodology, o.verification_status, s.source_key, s.url
            FROM cost_observations o JOIN cities ci ON ci.id=o.city_id LEFT JOIN sources s ON s.id=o.source_id
            WHERE ci.name IN ({ph}) AND o.category=? AND o.unit=? AND o.period=? AND o.currency=?
              AND COALESCE(o.building_category,'')=? AND o.verification_status IN ('verified_official','verified_independent')
            ORDER BY ci.name, o.period_start""", [*cities, g["category"], g["unit"], g["period"], g["currency"],
                                                  g["building_category"]]))
        out["comparable_cost_groups"].append({**dict(g), "observations": obs})
    out["noncomparable_cost_observations"] = conn.execute(f"""
        SELECT COUNT(*) FROM cost_observations o JOIN cities ci ON ci.id=o.city_id WHERE ci.name IN ({ph})""",
        cities).fetchone()[0] - sum(len(g["observations"]) for g in out["comparable_cost_groups"])
    return out


def list_policies(conn, state=None, kind=None):
    sql = "SELECT p.*, s.source_key AS official_source_key, s.url AS official_url FROM policies p LEFT JOIN sources s ON s.id=p.official_source_id WHERE 1=1"
    p = []
    if state:
        sql += " AND p.state=?"
        p.append(state)
    if kind:
        sql += " AND p.policy_kind=?"
        p.append(kind)
    rows = _labelled(conn.execute(sql + " ORDER BY p.state='Central', p.state, p.name", p))
    for r in rows:
        r["incentive_count"] = conn.execute(
            "SELECT COUNT(*) FROM incentives i JOIN policy_versions v ON v.id=i.policy_version_id WHERE v.policy_id=?",
            (r["id"],)).fetchone()[0]
    return rows


def policy_detail(conn, policy_id):
    p = conn.execute("SELECT * FROM policies WHERE id=?", (policy_id,)).fetchone()
    if not p:
        return None
    p = _label(dict(p))
    p["versions"] = _labelled(conn.execute("""
        SELECT v.*, s.source_key, s.url, s.publisher, s.tier, s.retrieval_status
        FROM policy_versions v LEFT JOIN sources s ON s.id=v.source_id WHERE v.policy_id=? ORDER BY v.id""", (policy_id,)))
    for v in p["versions"]:
        v["incentives"] = _labelled(conn.execute("""
            SELECT i.*, s.source_key, s.url FROM incentives i LEFT JOIN sources s ON s.id=i.source_id
            WHERE i.policy_version_id=?""", (v["id"],)))
    p["claims"] = claims_for(conn, "policy", policy_id)
    return p


def list_sources(conn, status=None, tier=None):
    sql = "SELECT * FROM sources WHERE 1=1"
    p = []
    if status:
        sql += " AND retrieval_status=?"
        p.append(status)
    if tier:
        sql += " AND tier=?"
        p.append(tier)
    return _d(conn.execute(sql + " ORDER BY tier, source_key", p))


def source_detail(conn, key):
    s = conn.execute("SELECT * FROM sources WHERE source_key=?", (key,)).fetchone()
    if not s:
        return None
    s = dict(s)
    s["jobs"] = _d(conn.execute(
        "SELECT run_id, stage, status, method, http_status, error, started_at FROM scrape_jobs WHERE source_id=? ORDER BY id DESC LIMIT 50",
        (s["id"],)))
    s["documents"] = _d(conn.execute(
        "SELECT id, retrieved_at, method, content_type, sha256, length(text) AS chars FROM source_documents WHERE source_id=?",
        (s["id"],)))
    s["claims"] = _labelled(conn.execute(
        "SELECT id, subject_type, subject_id, field, value_text, verification_status FROM claims WHERE source_id=?",
        (s["id"],)))
    return s


def claim_detail(conn, claim_id):
    c = conn.execute("""
        SELECT c.*, s.source_key, s.name AS source_name, s.publisher, s.url, s.tier, s.source_type,
               s.retrieval_status, s.last_retrieval_date, s.publication_date, s.publication_date_basis
        FROM claims c LEFT JOIN sources s ON s.id=c.source_id WHERE c.id=?""", (claim_id,)).fetchone()
    if not c:
        return None
    c = _label(dict(c))
    c["history"] = _d(conn.execute(
        "SELECT ts, actor, action, detail FROM audit_log WHERE table_name='claims' AND record_id=? ORDER BY id",
        (claim_id,)))
    return c


def list_claims(conn, status=None, subject_type=None, limit=200):
    sql = """SELECT c.id, c.subject_type, c.subject_id, c.field, c.value_text, c.geography, c.verification_status,
                    c.evidence_match, s.source_key, s.url, s.tier, s.retrieval_status
             FROM claims c LEFT JOIN sources s ON s.id=c.source_id WHERE 1=1"""
    p = []
    if status:
        sql += " AND c.verification_status=?"
        p.append(status)
    if subject_type:
        sql += " AND c.subject_type=?"
        p.append(subject_type)
    sql += " ORDER BY c.id LIMIT ?"
    p.append(limit)
    return _labelled(conn.execute(sql, p))


def verification_summary(conn):
    by_status = {r[0]: r[1] for r in conn.execute("SELECT verification_status, COUNT(*) FROM claims GROUP BY 1")}
    return {
        "claims_by_status": [{"status": k, "label": STATUS_LABELS[k], "count": by_status.get(k, 0)} for k in STATUS_LABELS],
        "claims_by_subject": {r[0]: r[1] for r in conn.execute("SELECT subject_type, COUNT(*) FROM claims GROUP BY 1")},
        "sources_by_retrieval_status": {r[0]: r[1] for r in conn.execute(
            "SELECT retrieval_status, COUNT(*) FROM sources GROUP BY 1")},
        "sources_by_tier": {r[0]: r[1] for r in conn.execute("SELECT tier, COUNT(*) FROM sources GROUP BY 1")},
        "last_ingest_run": (conn.execute("SELECT run_id, MAX(started_at) FROM scrape_jobs").fetchone() or [None])[0],
    }


def overview(conn):
    one = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "companies": one("SELECT COUNT(*) FROM companies"),
        "centre_records": one("SELECT COUNT(*) FROM gcc_centres"),
        "centres_verified": one("SELECT COUNT(*) FROM gcc_centres WHERE verification_status IN ('verified_official','verified_independent')"),
        "cities": one("SELECT COUNT(*) FROM cities"),
        "sources": one("SELECT COUNT(*) FROM sources"),
        "sources_retrieved": one("SELECT COUNT(*) FROM sources WHERE retrieval_status='retrieved'"),
        "claims": one("SELECT COUNT(*) FROM claims"),
        "claims_verified": one("SELECT COUNT(*) FROM claims WHERE verification_status IN ('verified_official','verified_independent')"),
        "policies": one("SELECT COUNT(*) FROM policies"),
        "cost_observations": one("SELECT COUNT(*) FROM cost_observations"),
        "talent_observations": one("SELECT COUNT(*) FROM talent_observations"),
        "failed_jobs": one("SELECT COUNT(*) FROM scrape_jobs WHERE status IN ('failed','blocked','incomplete')"),
    }
