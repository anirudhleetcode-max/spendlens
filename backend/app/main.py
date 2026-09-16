import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth
from .config import get_settings
from .db import close_client, ensure_indexes, get_db
from .routers import budgets, categories, expenses, insights, receipts
from .services.classifier import get_model
from .pipeline.ocr import ocr_status, tesseract_version

log = logging.getLogger("spendlens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    get_model()          # load the classifier once
    tesseract_version()  # probe (and cache) Tesseract once
    yield
    await close_client()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


# consistent error body everywhere: {"detail": <str | list>, "status": <int>}
@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail, "status": exc.status_code}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    detail = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse({"detail": detail, "status": 422}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error: %s", exc)
    return JSONResponse({"detail": "Something went wrong on our side", "status": 500}, status_code=500)


for r in (auth.router, receipts.router, expenses.router, budgets.router, insights.router, categories.router):
    app.include_router(r)


@app.get("/api/health")
async def health():
    await get_db().command("ping")
    return {"status": "ok", "db": "connected", "ocr": ocr_status(), "classifier": get_model().ready}
