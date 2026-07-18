"""FastAPI app factory and HTML page routes. Thin layer per Constitution IV:
all business logic lives in engine/, this module only wires HTTP to it."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from engine import db

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def create_app() -> FastAPI:
    app = FastAPI(title="Personalized AI Job Engine")
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.on_event("startup")
    def _startup() -> None:
        db.init_db()

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(
            "base.html", {"request": request, "title": "Job Engine"}
        )

    return app


app = create_app()
