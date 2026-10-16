# GCC Atlas — Data Readiness Report

Generated 2026-10-16T10:12:57+00:00 from the live SQLite database. Every number below is a SQL query result.

## 1. Records per table

| Table | Rows |
|---|---|
| companies | 10 |
| entities | 0 |
| company_entity_relationships | 0 |
| cities | 6 |
| gcc_centres | 20 |
| sources | 41 |
| source_documents | 0 |
| claims | 45 |
| cost_observations | 0 |
| policies | 8 |
| policy_versions | 9 |
| incentives | 0 |
| talent_observations | 0 |
| scrape_jobs | 41 |
| audit_log | 21 |

## 2. Companies and GCC centres

* Unique companies with at least one centre record: **10**
* GCC centre records by operational status: {'unverified_lead': 20}

## 3. City coverage

| City | Centre records (any status) | Verified centres |
|---|---|---|
| Bengaluru | 7 | 0 |
| Chennai | 3 | 0 |
| Gurugram | 1 | 0 |
| Hyderabad | 4 | 0 |
| Noida | 3 | 0 |
| Pune | 2 | 0 |

## 4–10. Key counts

| Metric | Value |
|---|---|
| Sources in register | 41 |
| Sources successfully retrieved | 0 |
| Sources by retrieval status | {'network_blocked': 41} |
| Claims supported by primary (official) sources | 0 |
| Claims supported by independent secondary sources | 0 |
| Claims unverified, pending or conflicting | 45 |
| Claims by status | {'discovered': 45} |
| Cost observations with compatible units and periods | 0 |
| Policies with confirmed official sources | 0 |
| Failed or incomplete ingestion jobs | 41 |
| Jobs by status | {'blocked': 41} |

## 11. Examples of verified claims

**None.** No claim has been confirmed against retrieved source text.

## 12. Data quality flags

| Check | Severity | Flagged |
|---|---|---|
| Claims with no source URL | high | 0 |
| Source URLs that are not valid http(s) links | high | 0 |
| Same claim stored twice from the same source | medium | 0 |
| Dates that are malformed, in the future or out of order | medium | 0 |
| Numbers without a unit | high | 0 |
| Cost groups mixing currencies | high | 0 |
| Claim geography differs from the record's city | high | 0 |
| Numbers not found in their evidence excerpt | high | 0 |
| Sources disagree on the same fact | high | 0 |
| Policies expired or not checked recently | medium | 9 |
| Corporate relationships without verified evidence | high | 0 |
| Cost observations missing unit, period, currency, date or method | medium | 0 |
| Claims whose source has never been retrieved | high | 45 |

## Known limitations

See `docs/known_limitations.md`.

## Acceptance gate

| Criterion | Pass | Evidence |
|---|---|---|
| Database initializes reproducibly | PASS | two fresh databases + this one have identical schemas; re-running migrations is a no-op |
| Stable identifiers and relationships | PASS | 13 unique constraints; 0 foreign-key violations |
| Source provenance stored | PASS | 0 claims without a source |
| Failed ingestion is logged | PASS | 0 failed sources with no job record |
| Duplicate ingestion is controlled | PASS | 0 duplicate claims, 0 duplicate documents (unique keys on claim_hash and source+sha256) |
| Verification status is explicit | PASS | NOT NULL + CHECK constraint on every status column |
| Representative records checked against sources | FAIL | 0 claims confirmed against retrieved source text |
| Research limitations documented | PASS | docs/known_limitations.md |

**Gate result: FAIL**

The infrastructure criteria are tested and reported above. The data criteria fail because no source could be retrieved from this environment. APIs and UI built after this gate serve the bounded dataset as it is, with every record labelled by its real verification status.
