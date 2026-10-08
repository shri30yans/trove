"""Vertex AI native Gemini embeddings transport contract."""

import json
from types import SimpleNamespace

import httpx
import pytest

import app.embedding as embedding


@pytest.mark.asyncio
async def test_text_embedding_uses_vertex_embed_content_and_parses_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    request_body: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://aiplatform.googleapis.com/v1/projects/test-project/locations/us/"
            "publishers/google/models/gemini-embedding-2:embedContent"
        )
        assert request.headers["Authorization"] == "Bearer test-oauth-token"
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"embedding": {"values": [1.0] * embedding.EMBEDDING_DIMENSIONS}},
        )

    config = SimpleNamespace(
        VERTEX_SERVICE_ACCOUNT_JSON_B64="eyJ0ZXN0Ijp0cnVlfQ==",
        GOOGLE_APPLICATION_CREDENTIALS=None,
        VERTEX_PROJECT_ID="test-project",
        VERTEX_LOCATION="us",
    )
    monkeypatch.setattr(embedding, "get_config", lambda: config)

    async def get_access_token() -> str:
        return "test-oauth-token"

    monkeypatch.setattr(embedding.vertex_auth, "access_token", get_access_token)
    service = embedding.EmbeddingService()
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async def get_client() -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(service, "_http_client", get_client)

    try:
        result = await service.embed_text("synthetic test query")
    finally:
        await client.aclose()

    assert request_body == {
        "outputDimensionality": embedding.EMBEDDING_DIMENSIONS,
        "content": {"parts": [{"text": "synthetic test query"}]},
    }
    assert result.model_id == "google/gemini-embedding-2"
    assert len(result.vector) == embedding.EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_image_embedding_uses_inline_image_data(monkeypatch: pytest.MonkeyPatch) -> None:
    request_body: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"embedding": {"values": [1.0] * embedding.EMBEDDING_DIMENSIONS}},
        )

    config = SimpleNamespace(
        VERTEX_SERVICE_ACCOUNT_JSON_B64="eyJ0ZXN0Ijp0cnVlfQ==",
        GOOGLE_APPLICATION_CREDENTIALS=None,
        VERTEX_PROJECT_ID="test-project",
        VERTEX_LOCATION="us",
    )
    monkeypatch.setattr(embedding, "get_config", lambda: config)

    async def get_access_token() -> str:
        return "test-oauth-token"

    monkeypatch.setattr(embedding.vertex_auth, "access_token", get_access_token)
    service = embedding.EmbeddingService()
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async def get_client() -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(service, "_http_client", get_client)

    try:
        result = await service.embed_image(b"synthetic-image-bytes", "image/jpeg")
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
