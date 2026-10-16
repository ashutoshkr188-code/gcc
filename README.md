# GCC Atlas

India GCC ecosystem intelligence for MNC expansion teams. The build is data-first:
research → sources → ingestion → verification → SQLite → APIs → UI.

Current phase: **1–2 (research plan and source register)**. See `docs/phase2_report.md`.

```
python3 research/build_register.py    # (re)build source register from discovery list
python3 pipeline/probe_sources.py     # attempt retrieval, record real status
```
