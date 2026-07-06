"""FastAPI app for the read-only digest web page (Phase 7 slice 1)."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from digest.web.loader import latest_digest_path, load_view_model

_HERE = Path(__file__).parent
app = FastAPI(title="AI Trends Digest")
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=str(_HERE / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    path = latest_digest_path()
    view = None if path is None else load_view_model(path)
    # Starlette >=0.29 signature: (request, name, context).
    return templates.TemplateResponse(request, "digest.html", {"view": view})
