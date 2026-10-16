"""Research Assistant: answers questions only from stored records, and cites each one.

It does not generate text with a language model. It recognizes cities, states,
companies and topics in the question, runs matching queries, and returns findings.
Each finding carries its source and verification status, and the answer says
plainly what the database does not contain.
"""
import re

from . import repository as repo
from .db import STATUS_LABELS

TOPICS = {
    "incentives": ["incentive", "subsidy", "subsidies", "policy", "policies", "benefit", "reimbursement", "scheme"],
    "costs": ["cost", "rent", "rental", "price", "expense", "fit-out", "fitout", "deposit", "salary", "salaries", "wage"],
    "regulation": ["regulation", "compliance", "labour", "labor", "law", "registration", "incorporat", "stpi", "sez"],
    "talent": ["talent", "skill", "hiring", "workforce", "engineer", "graduates"],
    "structure": ["subsidiary", "entity", "entities", "structure", "legal", "parent", "ownership"],
    "presence": ["gcc", "centre", "center", "office", "campus", "presence", "who", "which compan"],
}
VERIFIED = {"verified_official", "verified_independent"}


def _detect(question, conn):
    ql = question.lower()
    cities, states = [], []
    for r in conn.execute("SELECT name, state, aliases FROM cities"):
        names = [r["name"], *[a for a in r["aliases"].split(";") if a]]
        if any(re.search(r"\b" + re.escape(n.lower()) + r"\b", ql) for n in names):
            cities.append(r["name"])
            states.append(r["state"])
        elif r["state"].lower() in ql:
            states.append(r["state"])
    companies = []
    for r in conn.execute("SELECT slug, name, aliases FROM companies"):
        names = [r["name"], *[a for a in r["aliases"].split(";") if len(a) > 3]]
        if any(re.search(r"\b" + re.escape(n.lower()) + r"\b", ql) for n in names):
            companies.append(dict(r))
    topics = [t for t, kws in TOPICS.items() if any(k in ql for k in kws)]
    return cities, sorted(set(states)), companies, topics


def _cite(row):
    return {"source_key": row.get("source_key"), "url": row.get("url"), "publisher": row.get("publisher"),
            "status": row.get("verification_status"),
            "status_label": STATUS_LABELS.get(row.get("verification_status"), "")}


def answer(conn, question):
    question = (question or "").strip()
    cities, states, companies, topics = _detect(question, conn)
    if not topics:
        topics = ["presence"] if (cities or companies) else []
    findings, gaps = [], []

    if "presence" in topics or companies:
        centres = []
        if companies:
            for co in companies:
                centres += [c for c in repo.search_centres(conn, q=co["name"]) if not cities or c["city"] in cities]
        elif cities:
            for city in cities:
                centres += repo.search_centres(conn, city=city)
        for c in centres:
            for cl in repo.claims_for(conn, "gcc_centre", c["id"]):
                findings.append({
                    "type": "gcc_centre",
                    "text": f"{c['company']} — {c['city']}: recorded as '{c['operational_status'].replace('_', ' ')}'.",
                    "evidence": cl.get("evidence_excerpt"),
                    "citation": _cite(cl),
                })
        if centres and not any(f["citation"]["status"] in VERIFIED for f in findings if f["type"] == "gcc_centre"):
            gaps.append("None of these centre records has been verified against retrieved source text yet.")

    if "incentives" in topics or "regulation" in topics:
        wanted_states = states or [None]
        if "regulation" in topics:
            wanted_states = list(wanted_states) + ["Central"]
        seen = set()
        for st in wanted_states:
            for p in repo.list_policies(conn, state=st):
                if p["id"] in seen:
                    continue
                if "regulation" not in topics and p["policy_kind"] == "regulation":
                    continue
                seen.add(p["id"])
                for cl in repo.claims_for(conn, "policy", p["id"]):
                    findings.append({"type": "policy",
                                     "text": f"{p['state']}: {cl['value_text']} — status '{p['status']}'.",
                                     "evidence": cl.get("evidence_excerpt"), "citation": _cite(cl)})
                if p["incentive_count"] == 0:
                    gaps.append(f"No incentive terms are stored for '{p['name']}'. Amounts are only recorded from the official text.")

    if "costs" in topics:
        obs = []
        for city in cities or [None]:
            obs += repo.cost_observations(conn, city=city)
        for o in obs:
            findings.append({"type": "cost_observation",
                             "text": f"{o['category']} in {o['city'] or o['geographic_scope']}: {o['value_num']} {o['currency']} {o['unit']} {o['period']} ({o['period_start']}).",
                             "evidence": None, "citation": _cite(o)})
        if not obs:
            gaps.append("No cost observations are stored for this question.")

    if "talent" in topics:
        n = conn.execute("SELECT COUNT(*) FROM talent_observations").fetchone()[0]
        if not n:
            gaps.append("No talent or salary observations are stored yet.")

    if "structure" in topics:
        for co in companies:
            s = repo.company_structure(conn, co["slug"])
            if not s["relationships"]:
                gaps.append(f"No documented corporate relationships are stored for {co['name']}.")

    if not findings and not gaps:
        gaps.append("The question did not match any city, company or topic in the database. "
                    "Try naming a city (e.g. Pune), a company (e.g. Mastercard) or a topic (incentives, costs).")

    verified = sum(1 for f in findings if f["citation"]["status"] in VERIFIED)
    return {
        "question": question,
        "understood": {"cities": cities, "states": states, "companies": [c["name"] for c in companies], "topics": topics},
        "summary": (f"Found {len(findings)} stored record(s); {verified} verified against source text."
                    if findings else "No stored records answer this question."),
        "findings": findings[:100],
        "gaps": list(dict.fromkeys(gaps)),
        "disclaimer": "Answers come only from stored records. This is research, not legal, tax or investment advice.",
    }
