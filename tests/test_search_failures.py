from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.auth import VerifiedSubject
from app.embedding import EmbeddingError
from app.errors import ApiError
from app.routes import search

USER_ID = UUID("00000000-0000-4000-8000-000000000001")
SUBJECT = VerifiedSubject(subject="synthetic")
ANCHOR = {"deleted": False, "deletion_pending": False, "user_id": USER_ID}


def _flag(embeddings_enabled: bool) -> AsyncMock:
    return AsyncMock(return_value={**ANCHOR, "embeddings_enabled": embeddings_enabled})


def _no_hits() -> AsyncMock:
    return AsyncMock(return_value=[{**ANCHOR, "id": None}])


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
    fetch = _no_hits()
    monkeypatch.setattr(search, "fetch", fetch)
    monkeypatch.setattr(search, "fetchrow", _flag(False))

    result = await search.search_memories_for_user(
        SUBJECT,
        {"q": "  project ideas  ", "limit": "3", "spaceId": "00000000-0000-4000-8000-000000000002"},
    )

    assert result == search.SearchResults(query="project ideas", semanticSearch=False, memories=[])
    assert fetch.await_args.args[1:4] == ("synthetic", None, None)
    assert fetch.await_args.args[4] == "project ideas"
    assert fetch.await_args.args[11] == 3


async def test_hybrid_search_ranks_vector_and_text_hits_in_one_database_call(monkeypatch):
    from app.domain.retrieval import candidate_limit_for
    from app.embedding import Embedding

    embedding = Embedding(
        modality="text",
        space_id="synthetic-space",
        model_id="synthetic-model",
        model_revision="synthetic-revision",
        vector=[0.25] * 768,
    )
    monkeypatch.setattr(search.embeddings, "embed_text", AsyncMock(return_value=embedding))
    fetch = _no_hits()
    monkeypatch.setattr(search, "fetch", fetch)
    monkeypatch.setattr(search, "fetchrow", _flag(True))

    result = await search.search_memories_for_user(SUBJECT, {"q": "project ideas"})

    assert result.semanticSearch is True
    fetch.assert_awaited_once()
    sql = fetch.await_args.args[0]
    assert "vector_memory_hits AS" in sql
    assert "semantic_hits AS" in sql
    assert "row_number() OVER (ORDER BY lexical_score DESC" in sql
    assert fetch.await_args.args[-3:] == (
        "[" + ",".join(["0.25"] * 768) + "]",
        "synthetic-space",
        candidate_limit_for(20),
    )


async def test_raw_search_skips_embeddings_and_scopes_tag_filter(monkeypatch):
    embed = AsyncMock(side_effect=AssertionError("raw search must not call the embedding service"))
    fetch = _no_hits()
    monkeypatch.setattr(search.embeddings, "embed_text", embed)
    monkeypatch.setattr(search, "fetch", fetch)

    result = await search.search_memories_for_user(
        SUBJECT,
        {"q": "  project ideas  ", "mode": "raw", "tag": "  Reading ", "limit": "3"},
    )

    assert result.semanticSearch is False
    embed.assert_not_awaited()
    assert fetch.await_args.args[-2:] == ("reading", 3)
    assert "mt.tag=$10" in fetch.await_args.args[0]
    assert "LIMIT $11" in fetch.await_args.args[0]
    assert "ORDER BY e.embedding <=>" not in fetch.await_args.args[0]


async def test_tag_only_search_lists_all_memories_with_tag_without_embedding(monkeypatch):
    embed = AsyncMock(side_effect=AssertionError("tag browsing must not call the embedding service"))
    fetch = _no_hits()
    monkeypatch.setattr(search.embeddings, "embed_text", embed)
    monkeypatch.setattr(search, "fetch", fetch)

    result = await search.search_memories_for_user(SUBJECT, {"tag": " Reading "})

    assert result.query == ""
    assert result.semanticSearch is False
    embed.assert_not_awaited()
    assert fetch.await_args.args[4] == ""
    assert fetch.await_args.args[-2:] == ("reading", 20)


async def test_search_requires_text_or_tag():
    from app.errors import ApiError

    with pytest.raises(ApiError) as error:
        await search.search_memories_for_user(SUBJECT, {})

    assert error.value.code == "invalid_query"


async def test_raw_search_answers_in_a_single_database_round_trip(monkeypatch):
    fetchrow = AsyncMock(side_effect=AssertionError("raw search must not resolve the account twice"))
    fetch = AsyncMock(return_value=[{**ANCHOR, "id": None, "lexical_score": 0.0, "semantic_score": 0.0}])
    monkeypatch.setattr(search, "fetchrow", fetchrow)
    monkeypatch.setattr(search, "fetch", fetch)

    result = await search.search_memories_for_user(SUBJECT, {"q": "page", "mode": "raw"})

    assert result == search.SearchResults(query="page", semanticSearch=False, memories=[])
    fetch.assert_awaited_once()
    fetchrow.assert_not_awaited()
    assert "FROM deleted_auth_subjects WHERE auth_subject=$1" in fetch.await_args.args[0]


async def test_relation_feedback_checks_ownership_and_writes_in_one_round_trip(monkeypatch):
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": b'{"isRelated": true}', "more_body": False}

    request = Request({"type": "http", "method": "PUT", "headers": [(b"content-type", b"application/json")]}, receive)
    fetchrow = AsyncMock(
        return_value={**ANCHOR, "pair_count": 0, "user_id": USER_ID},
    )
    monkeypatch.setattr(search, "fetchrow", fetchrow)

    with pytest.raises(ApiError) as error:
        await search.save_relation_feedback(request, str(USER_ID), str(USER_ID), SUBJECT)

    assert error.value.code == "memory_not_found"
    fetchrow.assert_awaited_once()
    sql = fetchrow.await_args.args[0]
    assert "INSERT INTO memory_relation_feedback" in sql
    assert "FROM deleted_auth_subjects WHERE auth_subject=$1" in sql
