"""Turn one queued memory into a ready memory: extract text, embed, and store."""

from __future__ import annotations

import hashlib
import logging
import uuid

import anyio

from app import storage
from app.db import fetch, fetchrow, transaction
from app.embedding import Embedding, embeddings
from app.link_extract import Page, fetch_public_page
from app.queue import ClaimedJob, complete_job, complete_missing_memory_job
from app.vector_search import save_asset_embedding, save_memory_embedding

logger = logging.getLogger("trove.process")


class AssetIntegrityError(RuntimeError):
    """The stored bytes are not the bytes the client declared; no retry can fix that."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _read_verified_asset(asset: dict) -> bytes:
    """Read an asset and prove its bytes are the ones the client declared when it asked to upload.

    Upload completion verifies size. Processing also checks the declared checksum when present.
    """
    data = await storage.read_object(asset["object_key"])
    declared = asset["checksum_sha256"]
    if declared is not None and await anyio.to_thread.run_sync(_sha256, data) != declared.lower():
        raise AssetIntegrityError(f"Asset {asset['id']} does not match its declared checksum")
    return data


async def process_memory(job: ClaimedJob) -> None:
    memory_id = uuid.UUID(job.memory_id)
    user_id = uuid.UUID(job.user_id)

    memory = await fetchrow(
        """SELECT m.id, m.kind, m.title, m.description, m.user_note, m.content_text, m.page_text,
                  m.source_url,
                  m.source_domain, COALESCE(p.embeddings_enabled, false) AS embeddings_enabled
           FROM memories m LEFT JOIN user_preferences p ON p.user_id = m.user_id
           WHERE m.id = $1 AND m.user_id = $2 AND m.deleted_at IS NULL""",
        memory_id,
        user_id,
    )
    if memory is None:
        resolution = await complete_missing_memory_job(job)
        logger.info("Memory %s is gone; job %s", job.memory_id, resolution.value)
        return

    page: Page | None = None
    if not job.reindex_only and memory["source_url"] and memory["kind"] == "link":
        page = await fetch_public_page(memory["source_url"])

    assets = await fetch(
        """SELECT a.id, a.object_key, a.original_filename, a.mime_type, a.checksum_sha256
           FROM assets a JOIN memory_assets ma ON ma.asset_id = a.id
           WHERE ma.memory_id = $1 AND ma.user_id = $2 ORDER BY ma.position""",
        memory_id,
        user_id,
    )
    # Keep one attachment in memory at a time; image bytes can be large.
    cached: tuple[str, bytes] | None = None

    async def read_asset(asset: dict) -> bytes:
        nonlocal cached
        key = str(asset["id"])
        if cached is not None and cached[0] == key:
            return cached[1]
        data = await _read_verified_asset(asset)
        cached = (key, data)
        return data

    page_text = page.text if page else memory["page_text"] if job.reindex_only else None
    content_text = "\n\n".join(part for part in (memory["content_text"], page_text) if part) or None
    memory_embedding: Embedding | None = None
    asset_embeddings: list[tuple[dict, Embedding]] = []
    if memory["embeddings_enabled"]:
        searchable = "\n".join(
            part
            for part in (
                memory["description"] or (page.description if page else None),
                memory["user_note"],
                content_text,
            )
            if part
        ).strip()
        title = memory["title"] or (page.title if page else None)
        if searchable or title:
            memory_embedding = await embeddings.embed_text(searchable, purpose="document", title=title)
        for asset in assets:
            if not asset["mime_type"].startswith("image/"):
                continue
            data = await read_asset(asset)
            asset_embeddings.append((asset, await embeddings.embed_image(data, asset["mime_type"])))

    async with transaction() as connection:
        lease = await connection.fetchrow(
            """SELECT 1 FROM memory_processing_jobs
               WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid
               FOR UPDATE""",
            memory_id,
            user_id,
            uuid.UUID(job.lease_token),
        )
        if lease is None:
            logger.info("Memory %s lease was reassigned before writing results", job.memory_id)
            return

        updated = await connection.fetchrow(
            """UPDATE memories SET status = 'ready', title = COALESCE(title,$3), description = COALESCE(description,$4),
                 page_text = $5,
                 processing_error = NULL, updated_at = now()
               WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL RETURNING id""",
            memory_id,
            user_id,
            page.title if page else None,
            page.description if page else None,
            page_text,
        )
        if updated is None:
            # The memory was soft-deleted while it was being processed, so there is nothing to write.
            await complete_job(connection, job)
            return

        if memory_embedding is not None:
            await save_memory_embedding(connection, user_id, memory_id, memory_embedding)
        for asset, embedding in asset_embeddings:
            await save_asset_embedding(
                connection, user_id, uuid.UUID(str(asset["id"])), asset["checksum_sha256"], embedding
            )

        await complete_job(connection, job)
