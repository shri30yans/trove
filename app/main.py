"""The Trove backend: HTTP API, memory queue, and provider-backed embeddings."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, Response

from app import db
from app.config import get_config
from app.deletion_worker import account_deletion_worker
from app.embedding import embeddings
from app.errors import ApiError, ApiJSONResponse, not_found
from app.mcp import app as mcp_app
from app.mcp import server as mcp_server
from app.middleware.body_limit import MAX_BODY_BYTES, RequestBodyLimitMiddleware
from app.middleware.rate_limit import apply_limits
from app.routes import accounts, auth, exports, mcp_oauth, media, memories, search, spaces, uploads
from app.storage import ensure_bucket
from app.worker import memory_queue

logger = logging.getLogger("trove.api")


def _configure_logging() -> None:
    config = get_config()
    level = logging.INFO if config.RUN_ENV == "local" else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _check_storage(run_env: str) -> None:
    """Verify the bucket. Only local development may boot without it, so uploads can fail loudly
    instead of taking the Postgres-backed features with them."""
    try:
        await ensure_bucket()
    except Exception as error:
        if run_env != "local":
            raise
        logger.warning("Storage unavailable, uploads will fail: %s: %s", type(error).__name__, error)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    config = get_config()
    try:
        await db.open_pool()
        await db.fetchval("SELECT 1")
        await _check_storage(config.RUN_ENV)
        embeddings.start()
        memory_queue.start()
        account_deletion_worker.start()
    except Exception as error:
        logger.error("Could not start Trove API: %s: %s", type(error).__name__, error)
        try:
            await db.close_pool()
        except Exception:  # noqa: BLE001 - the startup failure below is what matters
            pass
        raise
    logger.info("Trove API listening on %s:%s", config.API_HOST, config.API_PORT)
    try:
        async with mcp_server.session_manager.run():
            yield
    finally:
        await account_deletion_worker.stop()
        await memory_queue.stop()
        await embeddings.stop()
        await db.close_pool()


app = FastAPI(
    title="Trove API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    default_response_class=ApiJSONResponse,
    lifespan=lifespan,
)
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=MAX_BODY_BYTES)

_config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["*"]
        if _config.CORS_ORIGIN == "*"
        else [origin.strip() for origin in _config.CORS_ORIGIN.split(",") if origin.strip()]
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.middleware("http")(apply_limits)


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, error: ApiError) -> ApiJSONResponse:
    return error.to_response()


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, error: StarletteHTTPException) -> ApiJSONResponse:
    if error.status_code == 404:
        return not_found("Route not found.").to_response()
    code = "request_error" if 400 <= error.status_code < 500 else "internal_error"
    message = (
        error.detail
        if isinstance(error.detail, str) and error.status_code < 500
        else "The request could not be completed."
    )
    return ApiJSONResponse(status_code=error.status_code, content={"error": {"code": code, "message": message}})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, error: RequestValidationError) -> ApiJSONResponse:
    errors = error.errors()
    message = str(errors[0]["msg"]) if errors else "Invalid request."
    return ApiError(400, "invalid_request", message).to_response()


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, error: Exception) -> ApiJSONResponse:
    logger.error("Request failed: %s %s (%s)", request.method, request.url.path, type(error).__name__)
    return ApiError(500, "internal_error", "The request could not be completed.").to_response()


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/brand/trove.png", include_in_schema=False)
async def trove_brand_image() -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "assets" / "trove-logo.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/health/ready")
async def health_ready() -> Response:
    try:
        await db.fetchval("SELECT 1")
    except Exception:  # noqa: BLE001 - readiness is the signal itself
        return ApiJSONResponse(status_code=503, content={"status": "not_ready"})
    return ApiJSONResponse(content={"status": "ready"})


@app.get("/health/embeddings")
async def health_embeddings() -> dict[str, Any]:
    return embeddings.status


_configure_logging()

for router in (
    auth.router,
    accounts.router,
    spaces.router,
    memories.router,
    uploads.router,
    media.router,
    search.router,
    exports.router,
):
    app.include_router(router, prefix="/v1")

app.include_router(mcp_oauth.router)
app.mount("/", mcp_app, name="mcp")
