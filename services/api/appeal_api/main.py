"""FastAPI app: /v1 REST + SSE, Problem Details errors, correlation IDs, CORS, request size limits."""

from __future__ import annotations

import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from appeal_core.settings import get_settings
from appeal_core.state_machine import IllegalTransition
from appeal_core.telemetry import get_logger
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from appeal_api import admin, cases
from appeal_api.deps import Problem

log = get_logger("api")
MAX_BODY = 64 * 1024  # JSON bodies only; files go to blob storage, never through the API
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    stop = threading.Event()
    if s.worker_mode == "inprocess":
        from appeal_worker.orchestrator import run_worker

        def loop():
            while not stop.is_set():
                try:
                    run_worker(stop_after_idle=1.0, worker_id="inprocess")
                except Exception as e:
                    log.error("inprocess worker crashed", extra={"error": type(e).__name__})

        threading.Thread(target=loop, daemon=True, name="inprocess-worker").start()
    yield
    stop.set()


app = FastAPI(title="Appeal Assistant API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin, "http://localhost:3100", "http://127.0.0.1:3100"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["ETag", "X-Correlation-ID"],
)


@app.middleware("http")
async def correlation_and_limits(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        resp = JSONResponse({"type": "about:blank", "title": "Request too large", "status": 413, "detail": "Upload files with POST /v1/uploads."}, status_code=413, media_type="application/problem+json")
    else:
        resp = await call_next(request)
    resp.headers["X-Correlation-ID"] = cid
    return resp


def _problem(status: int, title: str, detail: str = "", type_: str = "about:blank", request: Request | None = None, **extra) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, "detail": detail, **extra}
    if request is not None:
        body["instance"] = str(request.url.path)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


@app.exception_handler(Problem)
async def problem_handler(request: Request, exc: Problem):
    return _problem(exc.status_code, exc.title, str(exc.detail), exc.type_, request, **exc.extra)


@app.exception_handler(IllegalTransition)
async def illegal_handler(request: Request, exc: IllegalTransition):
    return _problem(409, "Illegal state transition", str(exc), request=request)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return _problem(422, "Invalid request", "Some fields are missing or invalid.", request=request, errors=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()])


app.include_router(cases.router)
app.include_router(admin.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/readyz")
def readyz() -> JSONResponse:
    from appeal_core.adapters import get_blob_store, get_progress_bus
    from appeal_core.db import get_engine

    checks = {}
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        checks["db"] = True
    except Exception:
        checks["db"] = False
    checks["redis"] = get_progress_bus().ping()
    checks["blob"] = get_blob_store().ping()
    ok = all(checks.values())
    return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)


@app.get("/demo", include_in_schema=False)
def demo():
    return FileResponse(STATIC / "demo.html")
