"""Data Quality Center: automated checks run as SQL against the live database.

Checks only flag. None of them changes a verification status.
"""
import re
from datetime import date, datetime
from urllib.parse import urlparse

ISO_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
POLICY_STALE_DAYS = 90


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params)]


def check_missing_source_urls(conn):
    return _rows(conn, """SELECT c.id AS claim_id, c.subject_type, c.field, c.value_text
                          FROM claims c LEFT JOIN sources s ON s.id=c.source_id
                          WHERE c.source_id IS NULL OR s.url IS NULL OR trim(s.url)=''""")


def check_invalid_urls(conn):
    bad = []
    for r in conn.execute("SELECT source_key, url FROM sources"):
        u = urlparse(r["url"])
        if u.scheme not in ("http", "https") or not u.netloc or " " in r["url"]:
            bad.append({"source_key": r["source_key"], "url": r["url"]})
    return bad


def check_duplicate_claims(conn):
    return _rows(conn, """SELECT subject_type, subject_id, field, value_text, source_id, COUNT(*) AS n
                          FROM claims GROUP BY 1,2,3,4,5 HAVING n > 1""")


def check_inconsistent_dates(conn):
    out = []
    today = date.today().isoformat()
    date_cols = [("gcc_centres", "id", ["announced_date", "established_date"]),
                 ("policy_versions", "id", ["effective_date", "expiry_date"]),
                 ("cost_observations", "id", ["period_start", "period_end", "publication_date", "retrieval_date"]),
                 ("talent_observations", "id", ["period_start", "period_end", "publication_date", "retrieval_date"]),
                 ("claims", "id", ["as_of_date"])]
    for table, pk, cols in date_cols:
        for r in conn.execute(f"SELECT {pk}, {', '.join(cols)} FROM {table}"):
            for col in cols:
                v = r[col]
                if v and not ISO_DATE.match(v):
                    out.append({"table": table, "id": r[pk], "problem": f"{col} not ISO date: {v}"})
                elif v and col in ("announced_date", "established_date", "publication_date", "retrieval_date") and v > today:
                    out.append({"table": table, "id": r[pk], "problem": f"{col} in the future: {v}"})
    out += [{"table": "policy_versions", "id": r["id"], "problem": "expiry before effective date"}
            for r in conn.execute("SELECT id FROM policy_versions WHERE expiry_date < effective_date")]
    for t in ("cost_observations", "talent_observations"):
        out += [{"table": t, "id": r["id"], "problem": "period_end before period_start"}
                for r in conn.execute(f"SELECT id FROM {t} WHERE period_end < period_start")]
        out += [{"table": t, "id": r["id"], "problem": "retrieved before it was published"}
                for r in conn.execute(f"SELECT id FROM {t} WHERE retrieval_date < publication_date")]
    return out


def check_missing_units(conn):
    return (_rows(conn, "SELECT 'claims' AS tbl, id FROM claims WHERE value_num IS NOT NULL AND (unit IS NULL OR unit='')")
            + _rows(conn, """SELECT 'cost_observations' AS tbl, id FROM cost_observations
                             WHERE (value_num IS NOT NULL OR value_low IS NOT NULL) AND (unit IS NULL OR unit='')""")
            + _rows(conn, """SELECT 'talent_observations' AS tbl, id FROM talent_observations
                             WHERE value_num IS NOT NULL AND (unit IS NULL OR unit='')"""))


def check_incompatible_currencies(conn):
    return _rows(conn, """SELECT category, unit, period, GROUP_CONCAT(DISTINCT currency) AS currencies, COUNT(*) AS n
                          FROM cost_observations WHERE currency IS NOT NULL
                          GROUP BY category, unit, period HAVING COUNT(DISTINCT currency) > 1""")


def check_geographic_mismatches(conn):
    return _rows(conn, """SELECT c.id AS claim_id, c.geography, ci.name AS centre_city
                          FROM claims c JOIN gcc_centres g ON c.subject_type='gcc_centre' AND g.id=c.subject_id
                          JOIN cities ci ON ci.id=g.city_id
                          WHERE c.geography IS NOT NULL AND c.geography <> ci.name""")


def check_unsupported_numbers(conn):
    out = []
    for r in conn.execute("SELECT id, value_num, evidence_excerpt FROM claims WHERE value_num IS NOT NULL"):
        ex = (r["evidence_excerpt"] or "").replace(",", "")
        n = r["value_num"]
        txt = str(int(n)) if float(n).is_integer() else str(n)
        if not ex or txt not in ex:
            out.append({"claim_id": r["id"], "value_num": n, "problem": "number not present in evidence excerpt"})
    return out


def check_conflicting_sources(conn):
    return _rows(conn, """SELECT subject_type, subject_id, field, GROUP_CONCAT(DISTINCT value_text) AS values_seen,
                                 COUNT(DISTINCT value_text) AS n_values
                          FROM claims WHERE evidence_match=1 AND field <> 'presence_in_city' AND field <> 'existence'
                          GROUP BY subject_type, subject_id, field HAVING n_values > 1""") + \
        _rows(conn, "SELECT subject_type, subject_id, field, value_text AS values_seen, 1 AS n_values "
                    "FROM claims WHERE verification_status='conflicting'")


def check_outdated_policies(conn):
    today = date.today()
    out = []
    for r in conn.execute("""SELECT p.id, p.name, p.state, p.status, v.version_label, v.expiry_date, v.last_checked
                             FROM policies p JOIN policy_versions v ON v.policy_id=p.id"""):
        if r["expiry_date"] and r["expiry_date"] < today.isoformat():
            out.append({**dict(r), "problem": "expiry date has passed"})
        elif not r["last_checked"]:
            out.append({**dict(r), "problem": "never checked against an official source"})
        elif (today - datetime.fromisoformat(r["last_checked"][:10]).date()).days > POLICY_STALE_DAYS:
            out.append({**dict(r), "problem": f"last checked more than {POLICY_STALE_DAYS} days ago"})
    return out


def check_unsupported_relationships(conn):
    return _rows(conn, """SELECT r.id, r.relationship_type, r.verification_status
                          FROM company_entity_relationships r LEFT JOIN claims c ON c.id=r.claim_id
                          WHERE r.source_id IS NULL OR r.claim_id IS NULL
                             OR c.verification_status NOT IN ('verified_official','verified_independent')""")


def check_noncomparable_costs(conn):
    return _rows(conn, """SELECT id, category, unit, period, currency, period_start, methodology
                          FROM cost_observations
                          WHERE unit IS NULL OR period IS NULL OR currency IS NULL OR period_start IS NULL
                             OR methodology IS NULL OR geographic_scope IS NULL""")


def check_claims_citing_unretrieved_sources(conn):
    return _rows(conn, """SELECT c.id AS claim_id, s.source_key, s.retrieval_status
                          FROM claims c JOIN sources s ON s.id=c.source_id
                          WHERE s.retrieval_status <> 'retrieved'""")


CHECKS = [
    ("missing_source_urls", "Claims with no source URL", "high", check_missing_source_urls),
    ("invalid_urls", "Source URLs that are not valid http(s) links", "high", check_invalid_urls),
    ("duplicate_claims", "Same claim stored twice from the same source", "medium", check_duplicate_claims),
    ("inconsistent_dates", "Dates that are malformed, in the future or out of order", "medium", check_inconsistent_dates),
    ("missing_units", "Numbers without a unit", "high", check_missing_units),
    ("incompatible_currencies", "Cost groups mixing currencies", "high", check_incompatible_currencies),
    ("geographic_mismatches", "Claim geography differs from the record's city", "high", check_geographic_mismatches),
    ("unsupported_numbers", "Numbers not found in their evidence excerpt", "high", check_unsupported_numbers),
    ("conflicting_sources", "Sources disagree on the same fact", "high", check_conflicting_sources),
    ("outdated_policies", "Policies expired or not checked recently", "medium", check_outdated_policies),
    ("unsupported_relationships", "Corporate relationships without verified evidence", "high", check_unsupported_relationships),
    ("noncomparable_costs", "Cost observations missing unit, period, currency, date or method", "medium", check_noncomparable_costs),
    ("claims_citing_unretrieved_sources", "Claims whose source has never been retrieved", "high", check_claims_citing_unretrieved_sources),
]


def run_all(conn, include_rows=True, row_limit=50):
    results = []
    for key, label, severity, fn in CHECKS:
        rows = fn(conn)
        item = {"check": key, "label": label, "severity": severity, "count": len(rows)}
        if include_rows:
            item["rows"] = rows[:row_limit]
        results.append(item)
    return results
