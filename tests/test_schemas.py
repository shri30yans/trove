"""Request validation: what the API accepts, trims, and rejects with a 400."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.enums import MemoryKind
from app.errors import ApiError
from app.schemas import (
    CreateMemoryRequest,
    CreateSpaceRequest,
    CreateUploadRequest,
    RelatedFeedbackRequest,
    UpdateMemoryRequest,
    UpdatePreferencesRequest,
    UpdateSpaceRequest,
    as_uuid_list,
    parse_body,
    parse_kind_param,
    source_domain,
)


class FakeRequest:
    """The one Request behaviour parse_body uses."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    async def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_a_capture_accepts_each_memory_kind_and_rejects_anything_else() -> None:
    for kind in MemoryKind:
        assert CreateMemoryRequest(kind=kind.value).kind is kind
    with pytest.raises(ValidationError):
        CreateMemoryRequest(kind="receipt")


def test_the_wire_names_are_camelcase_because_the_client_sends_them() -> None:
    payload = CreateMemoryRequest.model_validate(
        {
            "kind": "link",
            "sourceApp": "  Slack  ",
            "sourceUrl": "https://example.com/a#frag",
            "description": "  kept verbatim  ",
            "capturedAt": "2026-03-05T12:00:00Z",
            "assetIds": ["11111111-1111-1111-1111-111111111111"],
        }
    )
    assert payload.sourceApp == "Slack"
    assert payload.description == "  kept verbatim  "
    assert payload.assetIds == ["11111111-1111-1111-1111-111111111111"]


def test_stripping_only_applies_to_the_fields_the_api_has_always_trimmed() -> None:
    payload = CreateMemoryRequest.model_validate({"kind": "text", "userNote": "  note  "})
    assert payload.userNote == "  note  "


def test_captured_at_must_carry_an_offset() -> None:
    with pytest.raises(ValidationError, match="UTC offset"):
        CreateMemoryRequest.model_validate({"kind": "text", "capturedAt": "2026-03-05T12:00:00"})
    assert CreateMemoryRequest.model_validate({"kind": "text", "capturedAt": "2026-03-05T12:00:00+02:00"})


def test_source_url_is_limited_to_http_and_https() -> None:
    for url in ("javascript:alert(1)", "file:///etc/passwd", "https://", "not a url"):
        with pytest.raises(ValidationError):
            CreateMemoryRequest.model_validate({"kind": "link", "sourceUrl": url})


def test_asset_and_space_lists_reject_non_uuids() -> None:
    with pytest.raises(ValidationError, match="UUID"):
        CreateMemoryRequest.model_validate({"kind": "text", "spaceIds": ["1"]})
    with pytest.raises(ValidationError, match="UUID"):
        UpdateMemoryRequest.model_validate({"spaceIds": ["nope"]})


def test_update_memory_treats_an_explicit_null_and_an_absent_field_differently() -> None:
    empty = UpdateMemoryRequest.model_validate({})
    cleared = UpdateMemoryRequest.model_validate({"userNote": None})
    assert empty.model_fields_set == set()
    assert cleared.model_fields_set == {"userNote"}
    assert cleared.userNote is None


def test_space_name_is_required_on_create_and_optional_on_patch() -> None:
    assert CreateSpaceRequest.model_validate({"name": " Reading "}).name == "Reading"
    with pytest.raises(ValidationError):
        CreateSpaceRequest.model_validate({"description": "no name"})
    assert UpdateSpaceRequest.model_validate({"description": "only a description"}).name is None
    with pytest.raises(ValidationError, match="At least one Space field"):
        UpdateSpaceRequest.model_validate({})


@pytest.mark.parametrize("color", ["#a1B2c3", None])
def test_space_color_is_a_hex_triplet_or_nothing(color: str | None) -> None:
    assert CreateSpaceRequest.model_validate({"name": "s", "color": color}).color == color


@pytest.mark.parametrize("color", ["#abc", "abc123", "#aabbccdd", "rebeccapurple"])
def test_a_malformed_space_color_is_rejected(color: str) -> None:
    with pytest.raises(ValidationError):
        CreateSpaceRequest.model_validate({"name": "s", "color": color})


def _byte_size_limit() -> int:
    """Read the ceiling off the model instead of restating it, so the test cannot drift."""
    bounds = [item for item in CreateUploadRequest.model_fields["byteSize"].metadata if hasattr(item, "le")]
    assert len(bounds) == 1
    return int(bounds[0].le)


def test_upload_declared_size_is_bounded_and_the_checksum_is_hex() -> None:
    limit = _byte_size_limit()
    payload = CreateUploadRequest.model_validate(
        {"filename": "photo.jpg", "mimeType": "image/jpeg", "byteSize": limit, "checksumSha256": "a" * 64}
    )
    assert payload.byteSize == limit
    with pytest.raises(ValidationError):
        CreateUploadRequest.model_validate({"filename": "p", "mimeType": "image/jpeg", "byteSize": limit + 1})
    with pytest.raises(ValidationError):
        CreateUploadRequest.model_validate(
            {"filename": "p", "mimeType": "image/jpeg", "byteSize": 1, "checksumSha256": "abc"}
        )
    with pytest.raises(ValidationError):
        CreateUploadRequest.model_validate({"filename": "p", "mimeType": "image/jpeg", "byteSize": 0})


def test_preferences_accept_only_the_declared_cadences() -> None:
    assert UpdatePreferencesRequest.model_validate({"resurfacingCadence": "monthly"}).resurfacingCadence
    with pytest.raises(ValidationError):
        UpdatePreferencesRequest.model_validate({"resurfacingCadence": "daily"})
    with pytest.raises(ValidationError, match="At least one preference field"):
        UpdatePreferencesRequest.model_validate({})


def test_related_feedback_only_carries_a_verdict() -> None:
    assert RelatedFeedbackRequest.model_validate({"isRelated": False}).isRelated is False
    with pytest.raises(ValidationError):
        RelatedFeedbackRequest.model_validate({})


async def test_parse_body_reports_the_first_validation_message_as_the_error() -> None:
    request = FakeRequest({"kind": "receipt"})
    with pytest.raises(ApiError) as caught:
        await parse_body(CreateMemoryRequest, request, "invalid_memory", "Invalid Memory.")
    assert caught.value.status_code == 400
    assert caught.value.code == "invalid_memory"
    assert caught.value.message != "Invalid Memory."


async def test_parse_body_uses_the_fallback_for_a_missing_or_non_object_body() -> None:
    for payload in (ValueError("not json"), [1, 2], "text"):
        request = FakeRequest(payload)
        with pytest.raises(ApiError) as caught:
            await parse_body(UpdateMemoryRequest, request, "invalid_memory_update", "Invalid update.")
        assert caught.value.message == "Invalid update."


async def test_parse_body_accepts_an_explicit_null_as_an_empty_object() -> None:
    payload = await parse_body(UpdateMemoryRequest, FakeRequest(None), "invalid_memory_update", "Invalid update.")
    assert payload.model_fields_set == set()


def test_source_domain_normalises_the_host() -> None:
    assert source_domain("https://WWW.Example.com/a/b") == "example.com"
    assert source_domain("https://sub.example.co.uk") == "sub.example.co.uk"
    assert source_domain("not-a-url") is None
    assert source_domain(None) is None
    assert source_domain("") is None


def test_parse_kind_param_passes_valid_filters_through() -> None:
    assert parse_kind_param(None) is None
    assert parse_kind_param("") is None
    assert parse_kind_param("audio") == "audio"
    with pytest.raises(ApiError) as caught:
        parse_kind_param("receipt")
    assert (caught.value.status_code, caught.value.code) == (400, "invalid_kind")


def test_as_uuid_list_converts_every_entry() -> None:
    values = ["11111111-1111-1111-1111-111111111111"]
    assert [str(item) for item in as_uuid_list(values)] == values


def test_the_schema_bound_still_matches_the_configured_upload_limit() -> None:
    """The upload ceiling is enforced twice: as a 400 here and as upload_too_large in the route.

    Raising MAX_UPLOAD_BYTES in the environment without changing the schema silently turns
    every oversized upload from a 413 into a generic 400, so the two must move together.
    """
    from app.config import get_config

    assert _byte_size_limit() == get_config().MAX_UPLOAD_BYTES
