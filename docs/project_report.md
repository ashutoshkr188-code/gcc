# GCC Atlas — End-of-Phase Reports (2026-10-16)

Counts come from `python -m gcc_atlas.cli readiness` on the live database.
Test results come from `scripts/build_check.sh`.

## Headline

All software for Phases 1–9 is built and tested (64 tests passing). The **data**
is not: no source could be retrieved from this environment, so 0 claims are verified.
The readiness gate passes 7 of 8 criteria and **fails** "representative records checked
against sources". Later phases were built because you asked to complete every phase.
They show the bounded dataset with its real status and never present a lead as a fact.

| Phase | Implemented | Ran | Result |
|---|---|---|---|
| 1 Research plan | Decisions, data matrix A–H, tiers, verification rules, refresh cadence | — | Done |
| 2 Source register | 41 sources, retrieval probe | Probe on all 41 | 0 retrieved, 41 `network_blocked` |
| 3 Ingestion | Discover→Fetch→Extract→Normalize→Dedupe→Validate→Verify→Store. HTTP, Playwright fallback, manual inbox | `ingest` on all 41 | 41 blocked jobs logged; pipeline proven on local fixtures |
| 4 SQLite | Migration 001: 15 tables + migrations table, FKs, CHECKs, unique keys, indexes | `init`, `seed` ×2 | Second seed added 0 rows |
| 5 Verification / DQ | Evidence matcher, review rules, 13 quality checks | `quality` | 45 claims flagged as citing unretrieved sources; 9 policies never checked |
| 6 Readiness gate | Report generated from SQL | `readiness` | **FAIL** (7/8) |
| 7 API | 22 routes, validation, token-gated review, Research Assistant | API tests | Pass |
| 8 UI | 7 pages | Playwright, 1280px and 390px | Pass; no console errors, no horizontal scroll |
| 9 Test / deploy | Build check, Dockerfile, deployment guide | `build_check.sh` | Passed locally. **Not deployed**; Docker image not built (no daemon) |

## Actual record counts

| Table | Rows | Note |
|---|---|---|
| sources | 41 | All `network_blocked` |
| source_documents | 0 | Nothing retrieved |
| companies | 10 | |
| cities | 6 | Reference data |
| gcc_centres | 20 | All `unverified_lead` |
| claims | 45 | All `discovered` (28 centre, 17 policy) |
| policies / policy_versions | 8 / 9 | All `unconfirmed` |
| incentives | 0 | Amounts recorded only from official text |
| cost_observations | 0 | |
| talent_observations | 0 | |
| entities / relationships | 0 / 0 | Never inferred from names |
| scrape_jobs | 41 | All `blocked` |

City coverage (leads only): Bengaluru 7, Hyderabad 4, Chennai 3, Noida 3, Pune 2, Gurugram 1.

## Source URLs actually retrieved

None.

## Tests (64 passing)

* Data foundation (23): migrations idempotent; foreign keys and CHECKs enforced; transaction rollback; seed idempotent;
  leads never auto-verified; full pipeline on local fixtures (script and nav stripped, every stage logged);
  same-sentence evidence rule; duplicate document skipped; block page rejected; 404 logged; manual inbox;
  review rules (no evidence → refused; tier-6 → cannot be official; independent needs 2 publishers);
  each quality check fires on bad data; readiness counts equal raw SQL; gate fails without verified records.
* API (23): search, aliases, filters, profiles, 404s, input validation (422), group structures, city comparison
  (only compatible cost groups compared), policies, sources and link validity, verification summary, DQ counts,
  readiness, review token, verified record end to end, Research Assistant citations and gaps.
* UI (18): 7 pages × 2 viewports, Explorer filter → company drawer → evidence record, top search,
  Assistant citations, city toggle.

## Bug found and fixed during browser testing

FastAPI runs a sync dependency's setup and teardown on different threads. SQLite then
raised `ProgrammingError` and every API call returned 500. TestClient did not catch this;
the real browser test did. Fixed in `api.get_conn`.

## To reach a passing gate

1. Allow the source domains in the environment's network settings, or put downloaded files in `data/inbox/`.
2. Run `python -m gcc_atlas.cli ingest`.
3. Review each `needs_review` claim (`cli review …`).
4. Find the missing official texts listed in `docs/known_limitations.md`.
5. Run `python -m gcc_atlas.cli readiness` again.
6. Deploy to a host with persistent storage and run the post-deploy test in `docs/deployment.md`.
