"""FastAPI app — thin HTTP over the WorkbenchService, plus the static front.

Routes map one-to-one onto service methods; all domain logic lives in the
service and the flow spine. The front (prototype made real) is served from
static/. Nothing here touches the DD engine directly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.flow.config import Config, load_config
from src.webapp.service import WorkbenchService

_STATIC = Path(__file__).parent / "static"


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    service = WorkbenchService(config)
    app = FastAPI(title="Minorh Title Workbench", version="2.0")
    app.state.config = config
    app.state.service = service

    def _guard(fn):
        try:
            return fn()
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ---- config / board ----
    @app.get("/api/config")
    def api_config() -> dict[str, Any]:
        return {
            "project_root": config.project_root,
            "manifests_dir": config.manifests_dir,
            "units_dir": config.units_dir,
            "tesseract": config.tesseract_status(),
            "ocr_window_seconds": config.ocr_window_seconds,
        }

    @app.get("/api/units")
    def api_units() -> dict[str, Any]:
        return {"units": service.list_units(), "openable": service.openable_units()}

    @app.post("/api/units/{unit}/open")
    def api_open(unit: str) -> dict[str, Any]:
        return _guard(lambda: service.open_unit(unit))

    @app.get("/api/units/{unit}")
    def api_unit(unit: str) -> dict[str, Any]:
        return _guard(lambda: service.get_unit(unit))

    @app.post("/api/units/{unit}/stage")
    def api_stage(unit: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _guard(lambda: service.set_stage(unit, body["to"], body.get("note", "")))

    # ---- drop / evidence ----
    @app.post("/api/units/{unit}/drop/seed")
    def api_seed(unit: str) -> dict[str, Any]:
        return _guard(lambda: service.seed_from_record(unit))

    @app.post("/api/units/{unit}/evidence")
    def api_evidence(unit: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _guard(lambda: service.add_evidence(unit, body.get("entries", [])))

    # ---- run: gates ----
    @app.post("/api/units/{unit}/run/structural")
    def api_run_structural(unit: str) -> dict[str, Any]:
        return _guard(lambda: service.run_structural(unit))

    @app.post("/api/units/{unit}/run/source-truth")
    def api_run_truth(unit: str) -> dict[str, Any]:
        return _guard(lambda: service.start_source_truth(unit))

    @app.get("/api/units/{unit}/run/status")
    def api_run_status(unit: str) -> dict[str, Any]:
        return _guard(lambda: service.run_status(unit))

    # ---- review ----
    @app.get("/api/units/{unit}/review")
    def api_review(unit: str) -> dict[str, Any]:
        return _guard(lambda: service.review(unit))

    @app.get("/api/units/{unit}/trace")
    def api_trace(unit: str, tab: str, cell: str) -> dict[str, Any]:
        tr = _guard(lambda: service.trace(unit, tab, cell))
        if tr is None:
            raise HTTPException(status_code=404, detail="no trace for that cell")
        return tr

    @app.post("/api/units/{unit}/verdict")
    def api_verdict(unit: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _guard(lambda: service.record_verdict(
            unit, body["tab"], body["cell"], body["verdict"], body.get("reason", "")))

    # ---- ship ----
    @app.post("/api/units/{unit}/ship")
    def api_ship(unit: str) -> dict[str, Any]:
        return _guard(lambda: service.ship(unit))

    # ---- static front ----
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    return app
