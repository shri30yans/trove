"""Supabase Storage access over the S3 protocol."""

from __future__ import annotations

import datetime as dt
import functools
import re
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

import anyio
import boto3
from botocore.config import Config as BotoConfig
from botocore.response import StreamingBody

from app.config import get_config

_EXTENSION_CLEAN = re.compile(r"[^a-z0-9]")

_T = TypeVar("_T")
# boto3 builds its client classes at import time, so no concrete client type can be named here.
S3Client = Any


def _make_client(endpoint: str) -> S3Client:
    config = get_config()
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=config.S3_REGION,
        aws_access_key_id=config.S3_ACCESS_KEY,
        aws_secret_access_key=config.S3_SECRET_KEY,
        config=BotoConfig(
            s3={"addressing_style": "path" if config.S3_FORCE_PATH_STYLE else "auto"},
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=120,
            retries={"max_attempts": 2},
        ),
    )


@functools.lru_cache(maxsize=1)
def _internal_client() -> S3Client:
    return _make_client(get_config().S3_ENDPOINT)


async def _run(func: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
    return await anyio.to_thread.run_sync(functools.partial(func, *args, **kwargs))


async def ensure_bucket() -> None:
    await _run(_internal_client().head_bucket, Bucket=get_config().S3_BUCKET)


def new_object_key(user_id: str, filename: str) -> str:
    extension = ""
    if "." in filename:
        extension = _EXTENSION_CLEAN.sub("", filename.rsplit(".", 1)[-1].lower())[:12]
    suffix = f".{extension}" if extension else ""
    now = dt.datetime.now(dt.UTC)
    return f"{user_id}/{now.year}/{now.month:02d}/{uuid.uuid4()}{suffix}"


async def upload_file(path: str, object_key: str, mime_type: str) -> None:
    def upload() -> None:
        with open(path, "rb") as body:
            _internal_client().put_object(
                Bucket=get_config().S3_BUCKET,
                Key=object_key,
                Body=body,
                ContentType=mime_type,
            )

    await _run(upload)


async def head_object_size(object_key: str) -> int:
    bucket = get_config().S3_BUCKET
    head = await _run(_internal_client().head_object, Bucket=bucket, Key=object_key)
    return int(head.get("ContentLength") or 0)


async def read_object(object_key: str) -> bytes:
    bucket = get_config().S3_BUCKET

    def download() -> bytes:
        result = _internal_client().get_object(Bucket=bucket, Key=object_key)
        with result["Body"] as stream:
            return stream.read()

    return await _run(download)


async def copy_object_to_file(object_key: str, destination: Any) -> None:
    """Copy a private object to an already-open binary file without buffering the whole asset."""
    bucket = get_config().S3_BUCKET

    def copy() -> None:
        result = _internal_client().get_object(Bucket=bucket, Key=object_key)
        with result["Body"] as stream:
            while chunk := stream.read(1024 * 1024):
                destination.write(chunk)

    await _run(copy)


async def open_object_stream(object_key: str, byte_range: str | None = None) -> tuple[StreamingBody, int]:
    """Open a private object; the HTTP delivery owner must close the returned body."""
    params: dict[str, Any] = {"Bucket": get_config().S3_BUCKET, "Key": object_key}
    if byte_range is not None:
        params["Range"] = byte_range
    result = await _run(_internal_client().get_object, **params)
    return result["Body"], int(result["ContentLength"])


async def delete_user_objects(user_id: str) -> None:
    """Remove every object under a user's private UUID prefix, including abandoned uploads."""
    bucket = get_config().S3_BUCKET
    prefix = f"{user_id}/"

    def delete() -> None:
        client = _internal_client()
        continuation: str | None = None
        while True:
            params: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
            if continuation:
                params["ContinuationToken"] = continuation
            page = client.list_objects_v2(**params)
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                result = client.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
                if result.get("Errors"):
                    raise RuntimeError("Storage rejected one or more account object deletions")
            if not page.get("IsTruncated"):
                return
            continuation = page.get("NextContinuationToken")
            if not continuation:
                raise RuntimeError("Storage returned a truncated page without a continuation token")

    await _run(delete)
