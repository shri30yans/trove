"""Vector search settings are per pooled session so each search needs only one DB statement."""

from __future__ import annotations

from typing import Any

import pytest

from app import db, vector_search
from app.domain.retrieval import HNSW_EF_SEARCH, HNSW_ITERATIVE_SCAN


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def set_type_codec(self, type_name: str, **_kwargs: Any) -> None:
        self.calls.append(("codec", type_name))

    async def fetchval(self, sql: str) -> None:
        self.calls.append(("fetchval", sql))

    async def execute(self, sql: str, *args: Any) -> None:
        self.calls.append(("execute", (sql, args)))


@pytest.mark.asyncio
async def test_pooled_connection_loads_vector_extension_before_setting_search_gucs() -> None:
    connection = _Connection()

    await db._apply_codecs(connection)  # type: ignore[arg-type]

    assert connection.calls[2] == ("fetchval", "SELECT '[0]'::vector")
    sql, args = connection.calls[3][1]
    assert "set_config('hnsw.ef_search', $1, false)" in sql
    assert "set_config('hnsw.iterative_scan', $2, false)" in sql
    assert args == (str(HNSW_EF_SEARCH), HNSW_ITERATIVE_SCAN)


@pytest.mark.asyncio
async def test_vector_query_uses_one_fetch_without_opening_a_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_fetch(sql: str, *args: Any) -> list[dict[str, Any]]:
        calls.append((sql, args))
        return [{"memory_id": "sample"}]

    monkeypatch.setattr(vector_search, "fetch", fake_fetch)

    result = await vector_search._vector_query("SELECT memory_id FROM embeddings WHERE user_id=$1", ("user",))

    assert result == [{"memory_id": "sample"}]
    assert calls == [("SELECT memory_id FROM embeddings WHERE user_id=$1", ("user",))]
