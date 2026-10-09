"""Vertex AI native Gemini embeddings transport contract, and the one place that decides whether
the capability exists at all.

The service is pointed at a real `Config` built by the shared fixture rather than a stand-in with
raw `VERTEX_*` keys: the derivation it relies on (`Config.vertex`) is what these tests are about.
"""

import json
from collections.abc import Callable

import httpx
import pytest

import app.embedding as embedding
from tests.config_fixture import synthetic_config

VERTEX_CONFIG = synthetic_config(
    VERTEX_SERVICE_ACCOUNT_JSON_B64="eyJ0ZXN0Ijp0cnVlfQ==",
    VERTEX_PROJECT_ID="test-project",
    VERTEX_LOCATION="us",
)


@pytest.fixture
def configured_service(monkeypatch: pytest.MonkeyPatch) -> embedding.EmbeddingService:
    """A service whose transport is mocked and whose OAuth is a fixed token."""

    async def get_access_token(vertex: object) -> str:
        return "test-oauth-token"

    monkeypatch.setattr(embedding, "get_config", lambda: VERTEX_CONFIG)
    monkeypatch.setattr(embedding.vertex_auth, "access_token", get_access_token)
    return embedding.EmbeddingService()


async def _use_mocked_transport(
    monkeypatch: pytest.MonkeyPatch,
    service: embedding.EmbeddingService,
    respond: Callable[[httpx.Request], httpx.Response],
) -> httpx.AsyncClient:
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async def get_client() -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(service, "_http_client", get_client)
    return client


async def test_text_embedding_uses_vertex_embed_content_and_parses_vector(
    monkeypatch: pytest.MonkeyPatch, configured_service: embedding.EmbeddingService
) -> None:
    request_body: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://aiplatform.googleapis.com/v1/projects/test-project/locations/us/"
            "publishers/google/models/gemini-embedding-2:embedContent"
        )
        assert request.headers["Authorization"] == "Bearer test-oauth-token"
        request_body.update(json.loads(request.content))
        return httpx.Response(200, json={"embedding": {"values": [1.0] * embedding.EMBEDDING_DIMENSIONS}})

    client = await _use_mocked_transport(monkeypatch, configured_service, respond)
    try:
        result = await configured_service.embed_text("synthetic test query")
    finally:
        await client.aclose()

    assert request_body == {
        "outputDimensionality": embedding.EMBEDDING_DIMENSIONS,
        "content": {"parts": [{"text": "synthetic test query"}]},
    }
    assert result.model_id == "google/gemini-embedding-2"
    assert len(result.vector) == embedding.EMBEDDING_DIMENSIONS


async def test_image_embedding_uses_inline_image_data(
    monkeypatch: pytest.MonkeyPatch, configured_service: embedding.EmbeddingService
) -> None:
    request_body: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(200, json={"embedding": {"values": [1.0] * embedding.EMBEDDING_DIMENSIONS}})

    client = await _use_mocked_transport(monkeypatch, configured_service, respond)
    try:
        result = await configured_service.embed_image(b"synthetic-image-bytes", "image/jpeg")
    finally:
        await client.aclose()

    assert request_body == {
        "outputDimensionality": embedding.EMBEDDING_DIMENSIONS,
        "content": {
            "parts": [
                {
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": "c3ludGhldGljLWltYWdlLWJ5dGVz",
                    }
                }
            ]
        },
    }
    assert result.modality == "image"
    assert len(result.vector) == embedding.EMBEDDING_DIMENSIONS


async def test_a_deployment_without_vertex_credentials_never_reaches_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"embedding": {"values": [1.0] * embedding.EMBEDDING_DIMENSIONS}})

    monkeypatch.setattr(embedding, "get_config", lambda: synthetic_config())
    service = embedding.EmbeddingService()
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async def get_client() -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(service, "_http_client", get_client)
    with pytest.raises(embedding.PermanentEmbeddingError):
        await service.embed_text("synthetic test query")
    assert calls == 0
    await client.aclose()


async def test_the_absent_capability_is_reported_as_what_to_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(embedding, "get_config", lambda: synthetic_config())
    service = embedding.EmbeddingService()
    assert service.ready is False
    assert service.models() is None
    status = service.status
    assert status["ready"] is False
    error = status["configurationError"]
    assert isinstance(error, str)
    assert "VERTEX_PROJECT_ID" in error
