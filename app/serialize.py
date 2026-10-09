"""Wire shapes shared by more than one route, declared once as typed read models.

Each model states the projection its query selects. `from_row` names the column and the client field
together, so a rename on either border fails while the API builds the response instead of arriving on
the phone as an undefined. Shapes only one route serves stay with that route; anything two routes
would spell by hand lives here.

Serialization stays in `app.errors`: responses go through the API's single ISO-Z and UUID encoder, so
no model declares a JSON format of its own. Field names are the wire names, which is how the request
models in `app.schemas` already spell client fields.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict

from app.domain.enums import AssetStatus, MemoryKind, MemoryStatus

Row = Mapping[str, Any]


class WireModel(BaseModel):
    """A response shape: immutable once built, and closed to a column the projection never asked for.

    `frozen` lives in the config rather than the base list so mypy does not read these models as
    dataclasses, which would forbid the projection subclasses that add their query's columns.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


def preview_url(memory_id: str | uuid.UUID, preview_key: str | None) -> str | None:
    """The API path that serves a Memory's thumbnail, or None when it has no previewable image.

    A Storage key never leaves the backend, so this path is the only form a preview is handed out in.
    """
    return f"/v1/memories/{memory_id}/preview" if preview_key else None


class MemoryCard(WireModel):
    """The fields every Memory projection carries."""

    id: str
    kind: MemoryKind
    status: MemoryStatus
    sourceApp: str | None
    sourceUrl: str | None
    sourceDomain: str | None
    title: str | None
    capturedAt: dt.datetime

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(
            id=str(row["id"]),
            kind=row["kind"],
            status=row["status"],
            sourceApp=row["source_app"],
            sourceUrl=row["source_url"],
            sourceDomain=row["source_domain"],
            title=row["title"],
            capturedAt=row["captured_at"],
        )


class MemorySpace(WireModel):
    """A Space as it is embedded in a Memory, built by the query's json_agg."""

    id: str
    name: str
    color: str | None
    icon: str | None


class MemoryAsset(WireModel):
    """One attachment, with the API path that serves its bytes."""

    id: str
    filename: str | None
    mimeType: str
    byteSize: int | None
    status: AssetStatus
    role: str
    createdAt: str
    url: str

    @classmethod
    def from_json(cls, asset: Row) -> Self:
        asset_id = str(asset["id"])
        return cls(
            id=asset_id,
            filename=asset["filename"],
            mimeType=asset["mimeType"],
            byteSize=asset["byteSize"],
            status=asset["status"],
            role=asset["role"],
            # json_build_object encodes this column to ISO-8601 text inside the row, unlike the
            # Memory's own timestamps, which arrive as datetimes and are encoded on the way out.
            createdAt=asset["createdAt"],
            url=f"/v1/assets/{asset_id}/content",
        )


class MemoryListItem(MemoryCard):
    """One row of the Memory list."""

    description: str | None
    userNote: str | None
    pageText: str | None
    createdAt: dt.datetime
    previewUrl: str | None

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(
            **MemoryCard.from_row(row).model_dump(),
            description=row["description"],
            userNote=row["user_note"],
            pageText=row["page_text"],
            createdAt=row["created_at"],
            previewUrl=preview_url(row["id"], row["preview_key"]),
        )


class MemoryListPage(WireModel):
    memories: list[MemoryListItem]
    nextCursor: str | None


class MemoryDetail(MemoryCard):
    """Everything one Memory holds, including the Spaces and attachments it belongs to."""

    processingError: str | None
    description: str | None
    userNote: str | None
    contentText: str | None
    pageText: str | None
    captureMetadata: dict[str, Any]
    occurredAt: dt.datetime | None
    createdAt: dt.datetime
    updatedAt: dt.datetime
    spaces: list[MemorySpace]
    tags: list[str]
    assets: list[MemoryAsset]

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(
            **MemoryCard.from_row(row).model_dump(),
            processingError=row["processing_error"],
            description=row["description"],
            userNote=row["user_note"],
            contentText=row["content_text"],
            pageText=row["page_text"],
            captureMetadata=row["capture_metadata"],
            occurredAt=row["occurred_at"],
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
            spaces=[MemorySpace(**space) for space in row["spaces"]],
            tags=row["tags"],
            assets=[MemoryAsset.from_json(asset) for asset in row["assets"]],
        )
