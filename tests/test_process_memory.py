"""Asset integrity: the one place the stored bytes are compared to what the client declared.

The client sends its SHA-256 before it has an upload URL, so complete_upload can only compare sizes.
Without this check the embedding would be stored against a checksum that never described those bytes.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from app import process_memory
from app.process_memory import AssetIntegrityError

ASSET = {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "object_key": "private/asset"}
PAYLOAD = b"a image the client meant to save"


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> bytearray:
    box = bytearray(PAYLOAD)

    async def read_object(object_key: str) -> bytes:
        assert object_key == "private/asset"
        return bytes(box)

    monkeypatch.setattr(process_memory.storage, "read_object", read_object)
    return box


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def test_bytes_that_match_the_declared_checksum_are_returned(stored: bytearray) -> None:
    asset = {**ASSET, "checksum_sha256": digest(PAYLOAD)}
    assert await process_memory._read_verified_asset(asset) == PAYLOAD


async def test_bytes_that_do_not_match_are_refused_before_they_are_embedded(stored: bytearray) -> None:
    asset = {**ASSET, "checksum_sha256": digest(b"different bytes")}
    with pytest.raises(AssetIntegrityError):
        await process_memory._read_verified_asset(asset)


async def test_an_asset_uploaded_without_a_declared_checksum_is_still_returned(stored: bytearray) -> None:
    # checksum_sha256 is nullable: a capture from the offline queue may not carry one.
    asset: dict[str, Any] = {**ASSET, "checksum_sha256": None}
    assert await process_memory._read_verified_asset(asset) == PAYLOAD


async def test_a_declared_checksum_written_in_uppercase_still_matches(stored: bytearray) -> None:
    asset = {**ASSET, "checksum_sha256": digest(PAYLOAD).upper()}
    assert await process_memory._read_verified_asset(asset) == PAYLOAD


async def test_truncated_storage_bytes_fail_the_check(stored: bytearray) -> None:
    stored[:] = PAYLOAD[: len(PAYLOAD) // 2]
    asset = {**ASSET, "checksum_sha256": digest(PAYLOAD)}
    with pytest.raises(AssetIntegrityError):
        await process_memory._read_verified_asset(asset)
