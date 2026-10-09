"""The single asyncpg connection pool shared by the API, the queue, and inference."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import Any

import asyncpg

from app.config import get_config
from app.domain.retrieval import HNSW_EF_SEARCH, HNSW_ITERATIVE_SCAN

_pool: asyncpg.Pool | None = None
MAX_DATABASE_CONNECTIONS = 5
logger = logging.getLogger("trove.api.database")
_request_id: ContextVar[str] = ContextVar("trove_request_id", default="-")


def set_request_id(request_id: str) -> Token[str]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


def current_request_id() -> str:
    return _request_id.get()


def _log_timing(operation: str, acquire_ms: float, work_ms: float) -> None:
    logger.info(
        "db_operation request_id=%s operation=%s acquire_ms=%.1f work_ms=%.1f",
        _request_id.get(),
        operation,
        acquire_ms,
        work_ms,
    )


async def _apply_codecs(connection: asyncpg.Connection) -> None:
    # Keep JSON as decoded Python values, like the previous node-pg client did. UUIDs stay
    # native so that uuid[] bind parameters use asyncpg's built-in array codec.
    for type_name in ("json", "jsonb"):
        await connection.set_type_codec(
            type_name,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
            format="text",
        )
    # Register pgvector's GUCs on each pooled session once. The Session pooler keeps these
    # settings with the connection; vector queries can then avoid a SET LOCAL round trip and
    # transaction solely for search tuning.
    await connection.fetchval("SELECT '[0]'::vector")
    await connection.execute(
        "SELECT set_config('hnsw.ef_search', $1, false), set_config('hnsw.iterative_scan', $2, false)",
        str(HNSW_EF_SEARCH),
        HNSW_ITERATIVE_SCAN,
    )


async def open_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    config = get_config()
    _pool = await asyncpg.create_pool(
        dsn=config.DATABASE_URL,
        min_size=1,
        max_size=MAX_DATABASE_CONNECTIONS,
        timeout=5,
        command_timeout=120,
        server_settings={"application_name": "trove-api"},
        init=_apply_codecs,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("The PostgreSQL pool is not open yet")
    return _pool


async def fetch(sql: str, *args: Any) -> list[dict[str, Any]]:
    started = time.perf_counter()
    async with get_pool().acquire() as connection:
        acquired = time.perf_counter()
        try:
            return [dict(row) for row in await connection.fetch(sql, *args)]
        finally:
            finished = time.perf_counter()
            _log_timing("fetch", (acquired - started) * 1000, (finished - acquired) * 1000)


async def fetchrow(sql: str, *args: Any) -> dict[str, Any] | None:
    started = time.perf_counter()
    async with get_pool().acquire() as connection:
        acquired = time.perf_counter()
        try:
            row = await connection.fetchrow(sql, *args)
            return None if row is None else dict(row)
        finally:
            finished = time.perf_counter()
            _log_timing("fetchrow", (acquired - started) * 1000, (finished - acquired) * 1000)


async def fetchval(sql: str, *args: Any) -> Any:
    started = time.perf_counter()
    async with get_pool().acquire() as connection:
        acquired = time.perf_counter()
        try:
            return await connection.fetchval(sql, *args)
        finally:
            finished = time.perf_counter()
            _log_timing("fetchval", (acquired - started) * 1000, (finished - acquired) * 1000)


async def execute(sql: str, *args: Any) -> None:
    started = time.perf_counter()
    async with get_pool().acquire() as connection:
        acquired = time.perf_counter()
        try:
            await connection.execute(sql, *args)
        finally:
            finished = time.perf_counter()
            _log_timing("execute", (acquired - started) * 1000, (finished - acquired) * 1000)


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    """One pooled connection inside a transaction that commits unless the body raises."""
    started = time.perf_counter()
    async with get_pool().acquire() as connection:
        acquired = time.perf_counter()
        try:
            async with connection.transaction():
                yield connection
        finally:
            finished = time.perf_counter()
            _log_timing("transaction", (acquired - started) * 1000, (finished - acquired) * 1000)
