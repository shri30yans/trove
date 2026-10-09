from unittest.mock import AsyncMock

import pytest

from app.embedding import EmbeddingError
from app.errors import ApiError
from app.routes import search


async def test_disabled_embeddings_do_not_call_embedding_service(monkeypatch):
    embed = AsyncMock()
    monkeypatch.setattr(search.embeddings, "embed_text", embed)
    assert await search._embed_search_query("synthetic", False) is None
    embed.assert_not_awaited()


async def test_failed_semantic_search_is_explicit_not_keyword_fallback(monkeypatch):
    failure = EmbeddingError("synthetic inference outage")
    monkeypatch.setattr(search.embeddings, "embed_text", AsyncMock(side_effect=failure))
    with pytest.raises(ApiError) as error:
        await search._embed_search_query("synthetic", True)
    assert error.value.status_code == 503
    assert error.value.code == "embeddings_unavailable"
    assert error.value.__cause__ is failure


async def test_unexpected_inference_defect_is_not_disguised_as_success(monkeypatch):
    monkeypatch.setattr(search.embeddings, "embed_text", AsyncMock(side_effect=TypeError("synthetic defect")))
    with pytest.raises(TypeError):
        await search._embed_search_query("synthetic", True)


async def test_search_service_accepts_plain_query_values(monkeypatch):
    from app.auth import Principal

    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(search, "_embeddings_enabled_for_user", AsyncMock(return_value=False))
    monkeypatch.setattr(search, "fetch", fetch)

    result = await search.search_memories_for_user(
        Principal(id="00000000-0000-4000-8000-000000000001", subject="synthetic"),
        {"q": "  project ideas  ", "limit": "3", "spaceId": "00000000-0000-4000-8000-000000000002"},
    )

    assert result == search.SearchResults(query="project ideas", semanticSearch=False, memories=[])
    assert fetch.await_args.args[2] == "project ideas"
    assert fetch.await_args.args[-1] == 3


async def test_raw_search_skips_embeddings_and_scopes_tag_filter(monkeypatch):
    from app.auth import Principal

    enabled = AsyncMock(side_effect=AssertionError("raw search must not inspect embedding availability"))
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(search, "_embeddings_enabled_for_user", enabled)
    monkeypatch.setattr(search, "fetch", fetch)

    result = await search.search_memories_for_user(
        Principal(id="00000000-0000-4000-8000-000000000001", subject="synthetic"),
        {"q": "  project ideas  ", "mode": "raw", "tag": "  Reading ", "limit": "3"},
    )

    assert result.semanticSearch is False
    enabled.assert_not_awaited()
    assert fetch.await_args.args[-2:] == ("reading", 3)
    assert "mt.tag=$10" in fetch.await_args.args[0]
    assert "LIMIT $11" in fetch.await_args.args[0]


async def test_tag_only_search_lists_all_memories_with_tag_without_embedding(monkeypatch):
    from app.auth import Principal

    enabled = AsyncMock(side_effect=AssertionError("tag browsing must not request embeddings"))
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(search, "_embeddings_enabled_for_user", enabled)
    monkeypatch.setattr(search, "fetch", fetch)

    result = await search.search_memories_for_user(
        Principal(id="00000000-0000-4000-8000-000000000001", subject="synthetic"),
        {"tag": " Reading "},
    )

    assert result.query == ""
    assert result.semanticSearch is False
    enabled.assert_not_awaited()
    assert fetch.await_args.args[2] == ""
    assert fetch.await_args.args[-2:] == ("reading", 20)


async def test_search_requires_text_or_tag():
    from app.auth import Principal
    from app.errors import ApiError

    with pytest.raises(ApiError) as error:
        await search.search_memories_for_user(
            Principal(id="00000000-0000-4000-8000-000000000001", subject="synthetic"),
            {},
        )

    assert error.value.code == "invalid_query"
