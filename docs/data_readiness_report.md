# GCC Atlas — Data Readiness Report

Generated 2026-10-16T11:21:55+00:00 from the live SQLite database. Every number below is a SQL query result.

## 1. Records per table

| Table | Rows |
|---|---|
| companies | 10 |
| entities | 0 |
| company_entity_relationships | 0 |
| cities | 6 |
| gcc_centres | 20 |
| sources | 41 |
| source_documents | 30 |
| claims | 45 |
| cost_observations | 0 |
| policies | 8 |
| policy_versions | 9 |
| incentives | 0 |
| talent_observations | 0 |
| scrape_jobs | 272 |
| audit_log | 105 |

## 2. Companies and GCC centres

* Unique companies with at least one centre record: **10**
* GCC centre records by operational status: {'operating': 7, 'unverified_lead': 13}

## 3. City coverage

| City | Centre records (any status) | Verified centres |
|---|---|---|
| Bengaluru | 7 | 2 |
| Chennai | 3 | 1 |
| Gurugram | 1 | 1 |
| Hyderabad | 4 | 1 |
| Noida | 3 | 1 |
| Pune | 2 | 1 |

## 4–10. Key counts

| Metric | Value |
|---|---|
| Sources in register | 41 |
| Sources successfully retrieved | 33 |
| Sources by retrieval status | {'failed': 1, 'http_error': 7, 'retrieved': 33} |
| Claims supported by primary (official) sources | 6 |
| Claims supported by independent secondary sources | 8 |
| Claims unverified, pending or conflicting | 31 |
| Claims by status | {'discovered': 15, 'needs_review': 8, 'unverified': 8, 'verified_independent': 8, 'verified_official': 6} |
| Cost observations with compatible units and periods | 0 |
| Policies with confirmed official sources | 0 |
| Failed or incomplete ingestion jobs | 52 |
| Jobs by status | {'blocked': 41, 'failed': 10, 'incomplete': 1, 'skipped': 1, 'success': 219} |

## 11. Examples of verified claims

* Claim 1 (verified_official): Hyderabad — https://news.microsoft.com/source/asia/2021/12/02/microsoft-india-development-center-expands-its-footprint-in-noida/
  > Over the past two decades, The Microsoft India Development Center has been growing its footprint in India across cities like Hyderabad, followed by Bengaluru and most recently its third campus in Noida was inaugurated earlier this year in January 2021.
* Claim 2 (verified_official): Bengaluru — https://news.microsoft.com/source/asia/2021/12/02/microsoft-india-development-center-expands-its-footprint-in-noida/
  > Over the past two decades, The Microsoft India Development Center has been growing its footprint in India across cities like Hyderabad, followed by Bengaluru and most recently its third campus in Noida was inaugurated earlier this year in January 2021.
* Claim 3 (verified_official): Noida — https://news.microsoft.com/source/asia/2021/12/02/microsoft-india-development-center-expands-its-footprint-in-noida/
  > Microsoft India Development Center expands its footprint in Noida - Source Asia
* Claim 8 (verified_independent): Chennai — https://www.iitm.ac.in/hi/node/11196
  > Walmart Global Tech partners with IIT Madras to accelerate research and skilling | Indian Institute of Technology Madras
* Claim 9 (verified_independent): Chennai — https://www.indianweb2.com/2025/04/walmart-expands-tech-presence-in-india.html
  > Walmart Expands Tech Presence in India with Second GCC in Chennai | IndianWeb2.com

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
| Claims whose source has never been retrieved | high | 12 |

## Known limitations

See `docs\known_limitations.md`.

## Acceptance gate

| Criterion | Pass | Evidence |
|---|---|---|
| Database initializes reproducibly | PASS | two fresh databases + this one have identical schemas; re-running migrations is a no-op |
| Stable identifiers and relationships | PASS | 13 unique constraints; 0 foreign-key violations |
| Source provenance stored | PASS | 0 claims without a source |
| Failed ingestion is logged | PASS | 0 failed sources with no job record |
| Duplicate ingestion is controlled | PASS | 0 duplicate claims, 0 duplicate documents (unique keys on claim_hash and source+sha256) |
| Verification status is explicit | PASS | NOT NULL + CHECK constraint on every status column |
| Representative records checked against sources | PASS | 14 claims confirmed against retrieved source text |
| Research limitations documented | PASS | docs\known_limitations.md |

**Gate result: PASS**
