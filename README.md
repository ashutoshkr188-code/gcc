# GCC Atlas

Evidence-backed research on Global Capability Centres (GCCs) in Bengaluru, Hyderabad,
Chennai, Pune, Noida and Gurugram, for MNC expansion teams. Built data-first:
research → sources → ingestion → verification → SQLite → API → UI.

> **Data status:** the build environment could not reach any source website, so **no fact is
> verified yet**. The database holds 41 registered sources, 10 companies, 20 centre *leads*
> and 8 policy *leads*, all labelled `Discovered`. See `docs/data_readiness_report.md`
> and `docs/known_limitations.md`.

## Quick start

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m gcc_atlas.cli seed          # create DB, load register and leads
python -m gcc_atlas.cli ingest        # fetch sources (needs network access)
python -m gcc_atlas.cli quality       # Data Quality Center
python -m gcc_atlas.cli readiness     # regenerate readiness report
python -m gcc_atlas.cli serve         # http://127.0.0.1:8000
scripts/build_check.sh                # full test + build + smoke test
```

No network? Save a source as `data/inbox/S007.html` (or `.pdf`/`.txt`) and run `ingest`.
The pipeline stores it as a `manual_upload` and checks claims against it.

## Layout

| Path | What |
|---|---|
| `docs/phase1_research_plan.md` | Research requirements (Phase 1) |
| `research/` | Source register, company shortlist, discovery leads (Phase 2) |
| `gcc_atlas/ingest/` | Fetch → extract → normalize → dedupe → validate → store → verify (Phase 3) |
| `gcc_atlas/migrations/` | Versioned SQLite schema (Phase 4) |
| `gcc_atlas/verify.py`, `quality.py` | Evidence checks, review rules, Data Quality Center (Phase 5) |
| `gcc_atlas/readiness.py` | Readiness report and acceptance gate (Phase 6) |
| `gcc_atlas/repository.py`, `api.py`, `assistant.py` | Data access layer, API, Research Assistant (Phase 7) |
| `web/` | Seven-page UI (Phase 8) |
| `tests/`, `scripts/build_check.sh`, `Dockerfile`, `docs/deployment.md` | Testing and deployment (Phase 9) |
| `docs/project_report.md` | End-of-phase reports |
