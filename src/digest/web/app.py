"""FastAPI app for the read-only digest web page (Phase 7 slices 1-2)."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from digest.web.loader import (
    latest_digest_path, digest_path_for, neighbors, load_archive, load_view_model,
)

_HERE = Path(__file__).parent
app = FastAPI(title="AI Trends Digest")
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=str(_HERE / "templates"))


def _digest_response(request: Request, path, stamp):
    """Shared render for '/' and '/d/{stamp}': view + newer/older nav."""
    view = None if path is None else load_view_model(path)
    newer, older = neighbors(stamp) if stamp else (None, None)
    # Starlette >=0.29 signature: (request, name, context).
    return templates.TemplateResponse(
        request, "digest.html",
        {"view": view, "nav": {"newer": newer, "older": older}},
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    path = latest_digest_path()
    stamp = path.stem if path else None
    return _digest_response(request, path, stamp)


@app.get("/archive", response_class=HTMLResponse)
def archive(request: Request):
    return templates.TemplateResponse(request, "archive.html", {"rows": load_archive()})


@app.get("/d/{stamp}", response_class=HTMLResponse)
def permalink(request: Request, stamp: str):
    path = digest_path_for(stamp)
    if path is None:
        return templates.TemplateResponse(
            request, "not_found.html", {"stamp": stamp}, status_code=404,
        )
    return _digest_response(request, path, stamp)
