"""Request payloads for the Trove API, validated with Pydantic models."""

from __future__ import annotations

import re
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from starlette.requests import Request

from app.domain.enums import MemoryKind, ResurfacingCadence
from app.errors import ApiError
from app.times import parse_timestamp

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


Trimmed = Annotated[str, BeforeValidator(_strip)]
MaybeTrimmed = Annotated[str | None, BeforeValidator(_strip)]
# Only these fields are stripped; trimming a stored field would change what the client wrote.
OptionalText = str | None


class CreateMemoryRequest(BaseModel):
    kind: MemoryKind
    sourceApp: MaybeTrimmed = Field(default=None, max_length=120)
    sourceUrl: OptionalText = Field(default=None, max_length=4096)
    title: MaybeTrimmed = Field(default=None, max_length=500)
    description: OptionalText = Field(default=None, max_length=20_000)
    userNote: OptionalText = Field(default=None, max_length=20_000)
    contentText: OptionalText = Field(default=None, max_length=200_000)
    captureMetadata: dict[str, Any] = Field(default_factory=dict)
    capturedAt: OptionalText = None
    assetIds: list[str] = Field(default_factory=list)
    spaceIds: list[str] = Field(default_factory=list)

    @field_validator("sourceUrl")
    @classmethod
    def _check_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Only HTTP and HTTPS links are supported")
        return value

    @field_validator("capturedAt")
    @classmethod
    def _check_captured_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parse_timestamp(value, error_code="invalid_memory", require_offset=True)
        except ApiError as error:
            raise ValueError(error.message) from error
        return value

    @field_validator("assetIds", "spaceIds")
    @classmethod
    def _check_uuids(cls, value: list[str]) -> list[str]:
        for item in value:
            if not _UUID.match(item):
                raise ValueError("Each identifier must be a UUID")
        return value


class UpdateMemoryRequest(BaseModel):
    title: MaybeTrimmed = Field(default=None, max_length=500)
    userNote: OptionalText = Field(default=None, max_length=20_000)
    spaceIds: list[str] | None = None

    @field_validator("spaceIds")
    @classmethod
    def _check_uuids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for item in value:
            if not _UUID.match(item):
                raise ValueError("Each identifier must be a UUID")
        return value


class MoveMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fromSpaceId: UUID
    toSpaceId: UUID

    @model_validator(mode="after")
    def _distinct_spaces(self) -> MoveMemoryRequest:
        if self.fromSpaceId == self.toSpaceId:
            raise ValueError("Choose a different destination Space")
        return self


class SpaceFields(BaseModel):
    """The three optional Space attributes; create and patch share them, but not `name`."""

    description: MaybeTrimmed = Field(default=None, max_length=500)
    color: OptionalText = None
    icon: MaybeTrimmed = Field(default=None, max_length=40)

    @field_validator("color")
    @classmethod
    def _check_color(cls, value: str | None) -> str | None:
        if value is not None and not _COLOR.match(value):
            raise ValueError("Color must be a #rrggbb hex value")
        return value


class CreateSpaceRequest(SpaceFields):
    name: Trimmed = Field(min_length=1, max_length=80)


class UpdateSpaceRequest(SpaceFields):
    name: MaybeTrimmed = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> UpdateSpaceRequest:
        if not self.model_fields_set:
            raise ValueError("At least one Space field is required")
        return self


class CreateUploadRequest(BaseModel):
    filename: Trimmed = Field(min_length=1, max_length=240)
    mimeType: Trimmed = Field(min_length=3, max_length=160)
    byteSize: int = Field(gt=0, le=52_428_800)
    checksumSha256: OptionalText = None

    @field_validator("checksumSha256")
    @classmethod
    def _check_checksum(cls, value: str | None) -> str | None:
        if value is not None and not _HEX64.match(value):
            raise ValueError("checksumSha256 must be 64 hexadecimal characters")
        return value


class UpdatePreferencesRequest(BaseModel):
    resurfacingEnabled: bool | None = None
    resurfacingCadence: ResurfacingCadence | None = None
    embeddingsEnabled: bool | None = None

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> UpdatePreferencesRequest:
        if not self.model_fields_set:
            raise ValueError("At least one preference field is required")
        return self


class RelatedFeedbackRequest(BaseModel):
    isRelated: bool


class PasswordAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class PasswordUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=6, max_length=256)


class RefreshAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(min_length=1, max_length=4096)


async def parse_body(model: type[Any], request: Request, error_code: str, fallback: str) -> Any:
    """Read and validate a JSON body, raising the 400 envelope this API's clients expect."""
    try:
        payload = await request.json()
    except Exception as error:
        raise ApiError(400, error_code, fallback) from error
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ApiError(400, error_code, fallback)
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        first = error.errors()[0] if error.errors() else None
        message = str(first["msg"]) if first and first.get("msg") else fallback
        raise ApiError(400, error_code, message) from error


def parse_kind_param(value: str | None) -> str | None:
    """Validate a ?kind= filter. Shared by the memory list and search endpoints."""
    if not value:
        return None
    if MemoryKind.parse(value) is None:
        raise ApiError(400, "invalid_kind", "Unknown Memory type.")
    return value


def source_domain(url: str | None) -> str | None:
    if not url:
        return None
    hostname = urlparse(url).hostname
    if not hostname:
        return None
    lowered = hostname.lower()
    return lowered[4:] if lowered.startswith("www.") else lowered


def as_uuid_list(values: list[str]) -> list[UUID]:
    return [UUID(value) for value in values]
