import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gcc_atlas.api import app as fastapi_app
from fastapi.responses import FileResponse, JSONResponse

@fastapi_app.get("/", include_in_schema=False)
def root():
    for p in [ROOT / "public" / "index.html", ROOT / "web" / "index.html"]:
        if p.exists():
            return FileResponse(p)
    return JSONResponse({"ok": True, "name": "GCC Atlas API"})

@fastapi_app.get("/api", include_in_schema=False)
@fastapi_app.get("/api/", include_in_schema=False)
def api_root():
    return JSONResponse({"ok": True, "name": "GCC Atlas API", "docs": "/docs"})

class PathFixerMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if not path.startswith("/api") and path not in ("/", ""):
                scope["path"] = "/api" + path
        await self.app(scope, receive, send)

app = PathFixerMiddleware(fastapi_app)
