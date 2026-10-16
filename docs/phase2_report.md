# GCC Atlas — Phase 1–2 Report (2026-10-16)

## What was implemented

| Artifact | Purpose |
|---|---|
| `docs/phase1_research_plan.md` | Decisions supported, data requirements matrix (categories A–H), source tiers, verification rules, refresh cadence |
| `research/company_shortlist.csv` | 10 candidate companies, their candidate cities, and the sources discovered for each |
| `research/build_register.py` → `research/source_register.csv` | Source register, 41 sources, with every field the brief requires plus tier, discovery method and retrieval hash |
| `pipeline/probe_sources.py` | Fetches each registered URL and writes the **real** outcome back to the register. Logs each attempt to `data/logs/probe_log.jsonl` |

## What actually ran

* About 20 web searches, used for discovery only. They found candidate URLs.
* `build_register.py`: wrote 41 rows (unique IDs and URLs asserted).
* `probe_sources.py`: attempted all 41 URLs.

## Actual results

| Metric | Count |
|---|---|
| Sources in register | 41 |
| Sources successfully retrieved | **0** |
| `network_blocked` (proxy returned 403 to CONNECT) | 41 |
| Official company sources (tier 1–2) discovered | 10 |
| Government sources (tier 3) discovered | 2 (one is a *draft* policy) |
| Companies shortlisted | 10 |
| Verified claims | **0** |

**Source URLs retrieved: none.** No source has been accessed, so no fact in this
repository is verified.

## Candidate city coverage (unverified, from discovery only)

| City | Candidate companies |
|---|---|
| Bengaluru | Microsoft, Adobe, Walmart, Goldman Sachs, JPMorgan Chase, Eli Lilly, Ford |
| Hyderabad | Microsoft, Goldman Sachs, JPMorgan Chase, Eli Lilly |
| Chennai | Walmart, Barclays, Ford |
| Pune | Barclays, Mastercard |
| Noida | Microsoft, Adobe, Barclays |
| Gurugram | American Express (single company, no official source yet) |

## Gaps found in the register

Official primary texts not yet discovered:
* Karnataka final GCC Policy 2024-29 (only the draft is on a government host)
* Maharashtra GCC Policy 2025 GR
* Uttar Pradesh GCC Policy notification (reported date 7 May 2025, unverified)
* Haryana GCC Policy 2026 gazette notification
* Tamil Nadu G.O. for its GCC scheme. Sources disagree on whether it is a "policy" or a "scheme".
* Telangana: the 2nd ICT Policy text. Reports say a new GCC policy is still being drafted.
* Labour Codes gazette notifications and the MCA fee schedule
* Official Adobe, Walmart, American Express and Eli Lilly releases
* Corporate structure sources (category B) such as 10-K Exhibit 21 and MCA master data. None discovered yet.
* Salary and talent sources (category G) beyond the gated NASSCOM report

## Blocker

The build environment's network policy denies outbound connections to every
source host. Container HTTPS fails with `CONNECT tunnel failed, response 403`, and
WebFetch fails with `getaddrinfo ENOTFOUND`. Phase 3 (fetch → extract → verify) cannot
produce real data until this changes.

**Fix (user action):** in the cloud environment settings, open
*Network access* and either choose a broader access level or add the source domains under
*Allowed domains*. Docs: https://code.claude.com/docs/en/cloud-environments#network-access.
Then re-run `python3 pipeline/probe_sources.py`.

## Acceptance criteria for Phase 3

| Criterion | Met? |
|---|---|
| Research requirements defined | Yes |
| Source register exists with required fields | Yes |
| Retrieval statuses reflect real attempts | Yes (all blocked) |
| At least the tier-1 and tier-3 sources retrievable | **No** |

**Phase 3 is blocked.** No synthetic or search-snippet data will be loaded in place of
retrieved sources.
