import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth
from .config import get_settings
from .db import close_client, ensure_indexes, get_db
from .pipeline.ocr import ocr_status, tesseract_version
from .routers import budgets, categories, expenses, insights, receipts
from .services.classifier import get_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("spendlens")


async def _cleanup_loop():
    while True:
        with suppress(Exception):
            await receipts.cleanup_orphans()
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    get_model()          # load the classifier once (degrades, never crashes)
    tesseract_version()  # probe (and cache) Tesseract once
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    await close_client()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan,
              description="Receipt scanning, expense categorisation and spending insights. "
                          "Models are documented at GET /api/model.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    """One line per API request: method, path, status, duration. No bodies, no headers, no query strings."""
    t = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - t) * 1000)
    return response


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
    log.exception("unhandled error: %s", type(exc).__name__)
    return JSONResponse({"detail": "Something went wrong on our side", "status": 500}, status_code=500)


for r in (auth.router, receipts.router, expenses.router, budgets.router, insights.router, categories.router,
          categories.model_router):
    app.include_router(r)


@app.get("/api/health")
async def health():
    await get_db().command("ping")
    model = get_model()
    ocr = ocr_status()
    degraded = [n for n, ok in (("ocr", ocr["available"]), ("category_model", model.ready)) if not ok]
    return {"status": "degraded" if degraded else "ok", "degraded": degraded, "db": "connected", "ocr": ocr,
            "classifier": model.ready,
            "model": {"status": model.status, "version": (model.bundle or {}).get("version"), "error": model.error},
            "dev_secret": settings.jwt_ephemeral}
