"""Server-side OAuth credentials for Vertex AI API requests."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from typing import Any

from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from app.config import VertexConfig

SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)


class VertexCredentialError(RuntimeError):
    """Vertex AI OAuth credentials could not be loaded or refreshed."""


class VertexAuth:
    def __init__(self) -> None:
        self._credentials: Credentials | None = None
        self._lock = asyncio.Lock()

    async def access_token(self, vertex: VertexConfig) -> str:
        async with self._lock:
            try:
                if self._credentials is None:
                    self._credentials = await asyncio.to_thread(self._load_credentials, vertex)
                credentials = self._credentials
                if not credentials.valid:
                    await asyncio.to_thread(credentials.refresh, Request())
                if not credentials.token:
                    raise VertexCredentialError("Vertex AI OAuth credentials did not provide an access token.")
                return credentials.token
            except VertexCredentialError:
                raise
            except Exception as error:
                raise VertexCredentialError("Vertex AI OAuth credentials could not be loaded or refreshed.") from error

    @staticmethod
    def _load_credentials(vertex: VertexConfig) -> Credentials:
        try:
            service_account_info: Any = json.loads(
                base64.b64decode(vertex.service_account_json_b64, validate=True).decode("utf-8")
            )
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise VertexCredentialError("VERTEX_SERVICE_ACCOUNT_JSON_B64 is not valid base64-encoded JSON.") from error
        if not isinstance(service_account_info, dict):
            raise VertexCredentialError("Vertex service account JSON must be an object.")
        return service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )


vertex_auth = VertexAuth()
