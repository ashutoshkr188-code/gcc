"""Evidence checking and the human review workflow.

Automated checks never mark a claim verified. They look for supporting text in the
retrieved document, record what they found, and move the claim to 'needs_review'
(evidence found) or 'unverified' (document retrieved but no supporting text).
A person then confirms with review(). review() refuses a verified status the
evidence cannot support.
"""
import re
from datetime import datetime, timezone

from .db import audit

STOPWORDS = {"the", "of", "and", "for", "in", "on", "a", "an", "to", "policy", "reported", "final",
             "draft", "version", "name", "unconfirmed", "as", "under", "preparation", "scheme"}
STATUS_RANK = ["verified_official", "verified_independent", "needs_review", "conflicting",
               "possibly_outdated", "extracted", "unverified", "discovered", "rejected"]


def _aliases(s):
    return [a.strip() for a in (s or "").split(";") if a.strip()]


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def _contains(hay, needle):
    return re.search(r"(?<![A-Za-z])" + re.escape(needle.lower()) + r"(?![A-Za-z])", hay.lower()) is not None


def find_centre_evidence(text, company_names, city_names):
    """Return (excerpt, locator) where a company name and a city name occur in the same
    sentence, else None. A city mentioned anywhere on a company page is not enough."""
    page = None
    for i, sent in enumerate(_sentences(text)):
        m = re.match(r"\[page (\d+)\]", sent)
        if m:
            page = m.group(1)
            continue
        if any(_contains(sent, c) for c in company_names) and any(_contains(sent, c) for c in city_names):
            return sent[:600], (f"page {page}, " if page else "") + f"sentence {i + 1}"
    return None


def find_policy_evidence(text, policy_name, state):
    tokens = [t for t in re.findall(r"[A-Za-z0-9-]+", policy_name.lower()) if t not in STOPWORDS]
    if state != "Central":
        tokens.append(state.lower())
    for i, sent in enumerate(_sentences(text)):
        low = sent.lower()
        hits = sum(1 for t in set(tokens) if t in low)
        if tokens and hits / len(set(tokens)) >= 0.7:
            return sent[:600], f"sentence {i + 1}"
    return None


def check_claims_for_source(conn, source_id):
    """Run evidence matching for every claim citing this source against its latest document."""
    doc = conn.execute(
        "SELECT text FROM source_documents WHERE source_id=? ORDER BY retrieved_at DESC, id DESC LIMIT 1", (source_id,)
    ).fetchone()
    if not doc:
        return {"checked": 0}
    text = doc["text"]
    stats = {"checked": 0, "matched": 0, "unmatched": 0}
    claims = conn.execute(
        "SELECT * FROM claims WHERE source_id=? AND verification_status NOT IN "
        "('verified_official','verified_independent','rejected')", (source_id,)
    ).fetchall()
    for c in claims:
        found = None
        if c["subject_type"] == "gcc_centre":
            row = conn.execute(
                """SELECT co.name, co.aliases, ci.name AS city, ci.aliases AS city_aliases
                   FROM gcc_centres g JOIN companies co ON co.id=g.company_id JOIN cities ci ON ci.id=g.city_id
                   WHERE g.id=?""", (c["subject_id"],)).fetchone()
            found = find_centre_evidence(text, [row["name"], *_aliases(row["aliases"])],
                                         [row["city"], *_aliases(row["city_aliases"])])
        elif c["subject_type"] == "policy":
            p = conn.execute("SELECT name, state FROM policies WHERE id=?", (c["subject_id"],)).fetchone()
            found = find_policy_evidence(text, p["name"], p["state"])
        else:
            continue
        stats["checked"] += 1
        if found:
            stats["matched"] += 1
            conn.execute(
                """UPDATE claims SET evidence_excerpt=?, evidence_locator=?, evidence_match=1,
                       verification_status='needs_review',
                       verification_note='Automated: supporting sentence found in retrieved text. Awaiting human review.'
                   WHERE id=?""", (found[0], found[1], c["id"]))
        else:
            stats["unmatched"] += 1
            conn.execute(
                """UPDATE claims SET evidence_excerpt=NULL, evidence_locator=NULL, evidence_match=0,
                       verification_status='unverified',
                       verification_note='Automated: source retrieved but no sentence supports this claim.'
                   WHERE id=?""", (c["id"],))
        audit(conn, "verifier", "evidence_check", "claims", c["id"], "match" if found else "no_match")
        refresh_subject_status(conn, c["subject_type"], c["subject_id"])
    return stats


class ReviewError(ValueError):
    pass


def review(conn, claim_id, status, reviewer, note="", operational_status=None):
    """Human review. Enforces evidence rules for verified statuses."""
    c = conn.execute(
        "SELECT c.*, s.tier, s.publisher FROM claims c LEFT JOIN sources s ON s.id=c.source_id WHERE c.id=?", (claim_id,)
    ).fetchone()
    if not c:
        raise ReviewError(f"claim {claim_id} not found")
    if not reviewer:
        raise ReviewError("reviewer name is required")
    if status in ("verified_official", "verified_independent"):
        if c["evidence_match"] != 1 or not c["evidence_excerpt"]:
            raise ReviewError("cannot verify: no supporting excerpt from a retrieved document")
        if status == "verified_official" and (c["tier"] is None or c["tier"] > 3):
            raise ReviewError(f"cannot mark 'verified_official': source tier {c['tier']} is not an official source")
        if status == "verified_independent":
            pubs = conn.execute(
                """SELECT COUNT(DISTINCT s.publisher) FROM claims c2 JOIN sources s ON s.id=c2.source_id
                   WHERE c2.subject_type=? AND c2.subject_id=? AND c2.field=? AND c2.value_text=? AND c2.evidence_match=1""",
                (c["subject_type"], c["subject_id"], c["field"], c["value_text"])).fetchone()[0]
            if pubs < 2:
                raise ReviewError("cannot mark 'verified_independent': needs matched evidence from 2+ independent publishers")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE claims SET verification_status=?, verification_note=?, reviewed_by=?, reviewed_at=? WHERE id=?",
        (status, note or f"Reviewed by {reviewer}", reviewer, now, claim_id))
    audit(conn, reviewer, f"review:{status}", "claims", claim_id, note)
    if operational_status and c["subject_type"] == "gcc_centre":
        if status not in ("verified_official", "verified_independent"):
            raise ReviewError("operational status can only be set together with a verified claim")
        conn.execute("UPDATE gcc_centres SET operational_status=? WHERE id=?", (operational_status, c["subject_id"]))
        audit(conn, reviewer, "set_operational_status", "gcc_centres", c["subject_id"], operational_status)
    refresh_subject_status(conn, c["subject_type"], c["subject_id"])


def refresh_subject_status(conn, subject_type, subject_id):
    """A centre or policy takes the strongest status among its claims; conflicts win over verification."""
    table = {"gcc_centre": "gcc_centres", "policy": "policies"}.get(subject_type)
    if not table:
        return
    statuses = [r[0] for r in conn.execute(
        "SELECT verification_status FROM claims WHERE subject_type=? AND subject_id=?", (subject_type, subject_id))]
    if not statuses:
        return
    best = "conflicting" if "conflicting" in statuses else min(statuses, key=STATUS_RANK.index)
    conn.execute(f"UPDATE {table} SET verification_status=? WHERE id=?", (best, subject_id))
