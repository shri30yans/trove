"""Server-side Vertex AI adapter for Trove's shared text and image embedding space."""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from app.config import get_config
from app.vertex_auth import VertexCredentialError, vertex_auth

MODEL_ID = "google/gemini-embedding-2"
MODEL_REVISION = "provider-managed"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_SPACE_ID = f"{MODEL_ID}-{EMBEDDING_DIMENSIONS}d@{MODEL_REVISION}"
MAX_IMAGE_BYTES = 52_428_800
MAX_TEXT_CHARS = 24_000
logger = logging.getLogger("trove.embeddings")


class EmbeddingError(RuntimeError):
    """Embedding could not be produced; the job may be retried."""


class PermanentEmbeddingError(EmbeddingError):
    """Embedding input or configuration is invalid and retrying cannot fix it."""


class UnsupportedImage(PermanentEmbeddingError):
    """The image cannot be submitted to the embedding provider."""


@dataclass(frozen=True)
class Embedding:
    modality: str
    space_id: str
    model_id: str
    model_revision: str
    vector: list[float]


@dataclass(frozen=True)
class ModelSet:
    space_id: str
    text_model: str
    text_revision: str
    image_model: str
    image_revision: str


MODELS = ModelSet(
    space_id=EMBEDDING_SPACE_ID,
    text_model=MODEL_ID,
    text_revision=MODEL_REVISION,
    image_model=MODEL_ID,
    image_revision=MODEL_REVISION,
)


class EmbeddingService:
    """Call Gemini on demand without loading a model or storing provider inputs."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._start_lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        config = get_config()
        has_credentials = bool(config.VERTEX_SERVICE_ACCOUNT_JSON_B64 or config.GOOGLE_APPLICATION_CREDENTIALS)
        return bool(has_credentials and config.VERTEX_PROJECT_ID and config.VERTEX_LOCATION)

    @property
    def embeddings_url(self) -> str:
        config = get_config()
        if not config.VERTEX_PROJECT_ID or not config.VERTEX_LOCATION:
            raise PermanentEmbeddingError("Vertex AI embeddings require a project ID and location.")
        return (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{config.VERTEX_PROJECT_ID}/locations/{config.VERTEX_LOCATION}/publishers/google/"
            "models/gemini-embedding-2:embedContent"
        )

    @property
    def status(self) -> dict[str, object]:
        configured = self.ready
        return {
            "ready": configured,
            "provider": "vertex_ai",
            "dimensions": EMBEDDING_DIMENSIONS,
            "spaceId": MODELS.space_id,
            "textModel": MODELS.text_model,
            "textRevision": MODELS.text_revision,
            "imageModel": MODELS.image_model,
            "imageRevision": MODELS.image_revision,
            "configurationError": None
            if configured
            else "Vertex AI embedding credentials or project configuration are missing",
        }

    def models(self) -> ModelSet | None:
        return MODELS if self.ready else None

    def is_ready(self) -> bool:
        return self.ready

    def start(self) -> None:
        """Keep the existing lifecycle hook; the API client is created lazily on first use."""

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            async with self._start_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(45.0, connect=8.0),
                        follow_redirects=False,
                    )
        return self._client

    async def embed_text(self, text: str, purpose: str = "query", title: str | None = None) -> Embedding:
        if purpose not in ("query", "document"):
            raise PermanentEmbeddingError("Text embeddings require a query or document purpose.")
        if not text.strip() and not (purpose == "document" and title and title.strip()):
            raise PermanentEmbeddingError("Text embeddings require non-empty text.")

        content = text[:MAX_TEXT_CHARS].strip()
        if purpose == "document":
            document_title = title.strip() if title and title.strip() else "none"
            content = f"title: {document_title} | text: {content}"

        vector = await self._request_vector(
            {"content": {"parts": [{"text": content}]}},
            modality="text",
        )
        return Embedding(
            modality="text",
            space_id=MODELS.space_id,
            model_id=MODELS.text_model,
            model_revision=MODELS.text_revision,
            vector=vector,
        )

    async def embed_image(self, image_bytes: bytes, mime_type: str) -> Embedding:
        if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
            raise UnsupportedImage("Image embeddings require a non-empty image under 50 MiB.")
        if not mime_type.startswith("image/"):
            raise UnsupportedImage("Image embeddings require an image MIME type.")

        vector = await self._request_vector(
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        }
                    ]
                }
            },
            modality="image",
        )
        return Embedding(
            modality="image",
            space_id=MODELS.space_id,
            model_id=MODELS.image_model,
            model_revision=MODELS.image_revision,
            vector=vector,
        )

    async def _request_vector(self, request_input: dict[str, object], *, modality: str) -> list[float]:
        config = get_config()
        if not (config.VERTEX_SERVICE_ACCOUNT_JSON_B64 or config.GOOGLE_APPLICATION_CREDENTIALS):
            raise PermanentEmbeddingError("Vertex AI embeddings are not configured on the Trove API.")

        try:
            access_token = await vertex_auth.access_token()
        except VertexCredentialError as error:
            raise PermanentEmbeddingError("Vertex AI OAuth credentials could not be loaded.") from error

        client = await self._http_client()
        started_at = time.perf_counter()
        try:
            response = await client.post(
                self.embeddings_url,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={
                    "outputDimensionality": EMBEDDING_DIMENSIONS,
                    **request_input,
                },
            )
        except httpx.TimeoutException as error:
            logger.warning(
                "embedding_provider provider=vertex_ai modality=%s outcome=timeout elapsed_ms=%s",
                modality,
                round((time.perf_counter() - started_at) * 1000),
            )
            raise EmbeddingError("Vertex AI embedding request timed out.") from error
        except httpx.HTTPError as error:
            logger.warning(
                "embedding_provider provider=vertex_ai modality=%s outcome=transport_error error=%s elapsed_ms=%s",
                modality,
                type(error).__name__,
                round((time.perf_counter() - started_at) * 1000),
            )
            raise EmbeddingError("Vertex AI embedding request failed.") from error

        if not response.is_success:
            logger.warning(
                "embedding_provider provider=vertex_ai modality=%s outcome=http_error status=%s elapsed_ms=%s",
                modality,
                response.status_code,
                round((time.perf_counter() - started_at) * 1000),
            )
            message = f"Vertex AI embedding request returned HTTP {response.status_code}."
            if response.status_code == 429 or response.status_code == 408 or response.status_code >= 500:
                raise EmbeddingError(message)
            raise PermanentEmbeddingError(message)
        logger.info(
            "embedding_provider provider=vertex_ai modality=%s outcome=success status=%s elapsed_ms=%s",
            modality,
            response.status_code,
            round((time.perf_counter() - started_at) * 1000),
        )

        try:
            payload = response.json()
        except ValueError as error:
            raise PermanentEmbeddingError("Vertex AI returned invalid embedding JSON.") from error
        embedding = payload.get("embedding") if isinstance(payload, dict) else None
        values = embedding.get("values") if isinstance(embedding, dict) else None
        if not isinstance(values, Sequence) or isinstance(values, str | bytes):
            raise PermanentEmbeddingError("Vertex AI returned an invalid embedding response.")
        return _validated(values)


def _validated(vector: Sequence[object]) -> list[float]:
    values: list[float] = []
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise PermanentEmbeddingError("Vertex AI returned a non-numeric embedding.")
        values.append(float(value))
    if len(values) != EMBEDDING_DIMENSIONS or not all(math.isfinite(value) for value in values):
        raise PermanentEmbeddingError(f"Expected a finite {EMBEDDING_DIMENSIONS}-dimensional vector.")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0 or not math.isfinite(norm):
        raise PermanentEmbeddingError("Vertex AI returned a zero vector or invalid vector norm.")
    return [value / norm for value in values]


def vector_literal(embedding: Embedding) -> str:
    return "[" + ",".join(repr(value) for value in embedding.vector) + "]"


embeddings = EmbeddingService()
