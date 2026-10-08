"""Apply migrations/NNN_name.sql in order, guarded by a PostgreSQL advisory lock."""

from __future__ import annotations

import asyncio
import pathlib
import sys

from app.config import get_config
from app.db import close_pool, open_pool

MIGRATION_LOCK = (730_013_604, 42_001)


def _migration_files(directory: pathlib.Path) -> list[pathlib.Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Migration directory {directory} does not exist")
    return sorted(path for path in directory.glob("*.sql") if path.is_file())


async def migrate() -> None:
    pool = await open_pool()
    async with pool.acquire() as connection:
        lock_held = False
        release_error: BaseException | None = None
        try:
            await connection.execute("SELECT pg_advisory_lock($1, $2)", *MIGRATION_LOCK)
            lock_held = True
            await connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                     id text PRIMARY KEY,
                     applied_at timestamptz NOT NULL DEFAULT now()
                   )"""
            )
            directory = pathlib.Path.cwd() / "migrations"
            for path in _migration_files(directory):
                applied = await connection.fetchval("SELECT 1 FROM schema_migrations WHERE id = $1", path.name)
                if applied:
                    continue
                sql = path.read_text(encoding="utf-8")
                try:
                    async with connection.transaction():
                        await connection.execute(sql)
                        await connection.execute("INSERT INTO schema_migrations (id) VALUES ($1)", path.name)
                except Exception:
                    print(f"Migration {path.name} failed and was rolled back", file=sys.stderr)
                    raise
                print(f"Applied migration {path.name}", flush=True)
        finally:
            if lock_held:
                try:
                    await connection.execute("SELECT pg_advisory_unlock($1, $2)", *MIGRATION_LOCK)
                except Exception as error:  # noqa: BLE001 - reported after the main outcome
                    release_error = error
                    print(f"Could not release the migration lock: {error}", file=sys.stderr)
        if release_error is not None:
            raise release_error


def main() -> int:
    get_config()
    try:
        asyncio.run(_run())
    except Exception as error:  # noqa: BLE001 - the CLI reports the failure as an exit code
        print(f"Database migration failed: {error}", file=sys.stderr)
        return 1
    return 0


async def _run() -> None:
    try:
        await migrate()
    finally:
        await close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
