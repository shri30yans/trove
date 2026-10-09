"""The Trove backend: HTTP API, memory queue, and provider-backed embeddings.

The app object is built at import, which is deliberate: `get_config()` reads and validates the whole
configuration here, so a deployment with an integration missing fails when the platform imports this
module instead of after it has accepted traffic. Import constructs and validates; it opens nothing.
The pool, the bucket check, and the background workers belong to the lifespan, which is the only
place that knows a process is actually starting to serve -- and logging is configured there for the
same reason.

Everything the lifespan opens is released by `_release_resources()`, on clean shutdown and on a boot
that failed partway through.
"""

from __future__ import annotations

import logging
import time
import uuid
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
from app.routes import (
    accounts,
    auth,
    exports,
    mcp_oauth,
    media,
    memories,
    memory_lifecycle,
    search,
    spaces,
    uploads,
)
from app.storage import ensure_bucket
from app.worker import memory_queue

logger = logging.getLogger("trove.api")


def _configure_logging() -> None:
    level = logging.INFO if get_config().policy.verbose_logging else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _check_storage() -> None:
    """Report whether the bucket is reachable at startup.

    A deployment that must not serve uploads without it stops here; local development continues,
    because uploads enforce reachability at their own boundary and return an actionable failure.
    """
    try:
        await ensure_bucket()
    except Exception as error:
        if get_config().policy.require_reachable_storage:
            raise
        logger.warning("Storage unavailable, uploads will fail: %s: %s", type(error).__name__, error)


async def _release_resources() -> None:
    """Release everything the process may have opened.

    Each worker's stop is a no-op when it never started, so the startup-failure path can call the
    whole list without tracking how far startup got. One resource refusing to close must not strand
    the rest -- a leaked pool or an uncancelled worker outlives the error that stopped the boot.
    """
    for name, stop in (
        ("deletion worker", account_deletion_worker.stop),
        ("memory queue", memory_queue.stop),
        ("embedding client", embeddings.stop),
        ("database pool", db.close_pool),
    ):
        try:
            await stop()
        except Exception as error:  # noqa: BLE001 - the remaining resources still need their attempt
            logger.error("Could not release %s: %s: %s", name, type(error).__name__, error)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    config = get_config()
    try:
        await db.open_pool()
        await db.fetchval("SELECT 1")
        await _check_storage()
        memory_queue.start()
        account_deletion_worker.start()
    except Exception as error:
        logger.error("Could not start Trove API: %s: %s", type(error).__name__, error)
        await _release_resources()
        raise
    logger.info("Trove API listening on %s:%s", config.API_HOST, config.API_PORT)
    try:
        async with mcp_server.session_manager.run():
            yield
    finally:
        await _release_resources()


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


@app.middleware("http")
async def measure_request(request: Request, call_next: Any) -> Response:
    """Record safe route-level latency and attach a per-request correlation ID."""
    request_id = uuid.uuid4().hex
    started = time.perf_counter()
    status_code = 500
    endpoint = "unmatched"
    try:
        response = await call_next(request)
        status_code = response.status_code
        route = request.scope.get("route")
        endpoint = getattr(route, "path", "unmatched")
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.info(
            "http_request request_id=%s method=%s endpoint=%s status=%s elapsed_ms=%.1f",
            request_id,
            request.method,
            endpoint,
            status_code,
            (time.perf_counter() - started) * 1000,
        )


_config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_config.cors_origins,
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


for router in (
    auth.router,
    accounts.router,
    spaces.router,
    memories.router,
    memory_lifecycle.router,
    uploads.router,
    media.router,
    search.router,
    exports.router,
):
    app.include_router(router, prefix="/v1")

app.include_router(mcp_oauth.router)
app.mount("/", mcp_app, name="mcp")
# A path this API does not serve falls through to the root-mounted MCP app, which answers it with
# its own plain-text 404. Registering the same handler keeps one error contract on every path.
# Starlette types a registered handler as taking any Exception even though the key narrows it.
mcp_app.add_exception_handler(StarletteHTTPException, handle_http_exception)  # type: ignore[arg-type]
