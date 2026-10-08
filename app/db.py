"""The single asyncpg connection pool shared by the API, the queue, and inference."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from app.config import get_config

_pool: asyncpg.Pool | None = None
MAX_DATABASE_CONNECTIONS = 5


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
    async with get_pool().acquire() as connection:
        return [dict(row) for row in await connection.fetch(sql, *args)]


async def fetchrow(sql: str, *args: Any) -> dict[str, Any] | None:
    async with get_pool().acquire() as connection:
        row = await connection.fetchrow(sql, *args)
        return None if row is None else dict(row)


async def fetchval(sql: str, *args: Any) -> Any:
    async with get_pool().acquire() as connection:
        return await connection.fetchval(sql, *args)


async def execute(sql: str, *args: Any) -> None:
    async with get_pool().acquire() as connection:
        await connection.execute(sql, *args)


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    """One pooled connection inside a transaction that commits unless the body raises."""
    async with get_pool().acquire() as connection, connection.transaction():
        yield connection
