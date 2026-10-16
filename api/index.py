import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gcc_atlas.api import app
from fastapi.responses import FileResponse, JSONResponse

# Root endpoints
@app.get("/", include_in_schema=False)
def root():
    for p in [ROOT / "public" / "index.html", ROOT / "web" / "index.html"]:
        if p.exists():
            return FileResponse(p)
    return JSONResponse({"ok": True, "name": "GCC Atlas API"})

@app.get("/api", include_in_schema=False)
@app.get("/api/", include_in_schema=False)
def api_root():
    return JSONResponse({"ok": True, "name": "GCC Atlas API", "docs": "/docs"})

# Alias all /api/* routes to /* so requests match regardless of whether /api prefix is stripped
for r in list(app.routes):
    if hasattr(r, "path") and r.path.startswith("/api/"):
        alt_path = r.path[4:]  # e.g. /health, /overview
        app.add_api_route(
            alt_path,
            r.endpoint,
            methods=list(r.methods or ["GET"]),
            include_in_schema=False
        )
