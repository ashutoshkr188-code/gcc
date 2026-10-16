# Deployment

**Status: not deployed.** No hosting environment was available to this build, so no
deployed instance has been tested. Nothing below has been verified on a live host.

## Hosting requirement: persistent SQLite storage

SQLite is a file. The host must keep `GCC_ATLAS_DB` on storage that survives restarts
and redeploys, and it must run **one** application instance writing to that file.

| Host type | Suitable? |
|---|---|
| VM or VPS (any cloud) with a local disk | Yes |
| Container platform with a persistent volume (Fly.io volumes, Railway volumes, Render disks, Kubernetes PVC) | Yes, with a single replica |
| Serverless functions / ephemeral containers (Vercel, Lambda, Cloud Run without a volume) | **No**: the database would be lost |
| Network file shares (NFS/SMB) | Avoid: SQLite locking is unreliable on them |

Check this on the chosen host **before** deploying: write a row, restart the service, and
confirm the row is still there.

## Option A: Docker with a volume

```
docker build -t gcc-atlas .
docker run -d -p 8000:8000 -v gcc_atlas_data:/data --name gcc-atlas gcc-atlas
```
The container runs migrations and seeding (both idempotent), then serves on port 8000.
This image has **not** been built in the development environment (no Docker daemon was available).

## Option B: plain Python

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export GCC_ATLAS_DB=/var/lib/gcc-atlas/gcc_atlas.sqlite
python -m gcc_atlas.cli seed
python -m gcc_atlas.cli serve --host 0.0.0.0 --port 8000
```
Put a reverse proxy (nginx or Caddy) with TLS in front of it.

## Post-deploy acceptance test (run on the live URL)

```
for p in / /api/health /api/overview /api/centres /api/readiness; do
  curl -s -o /dev/null -w "%{http_code} $p\n" https://YOUR-HOST$p; done
```
Then restart the service and confirm `/api/overview` returns the same counts.
Only then report the deployment as successful.

## Operations

* **Refresh data:** `python -m gcc_atlas.cli ingest` (needs outbound access to the source hosts),
  or drop files into `data/inbox/<source_key>.pdf|html|txt` and run ingest.
* **Review claims:** `python -m gcc_atlas.cli review <claim_id> verified_official --reviewer "Name"`,
  or call `POST /api/claims/{id}/review` with header `X-Review-Token` (requires `GCC_ATLAS_REVIEW_TOKEN`).
* **Backup:** `sqlite3 $GCC_ATLAS_DB ".backup backup.sqlite"`. It is safe while the app is running.
* **Readiness report:** `python -m gcc_atlas.cli readiness` → `docs/data_readiness_report.md`
