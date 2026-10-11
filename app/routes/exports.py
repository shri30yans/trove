"""Portable Markdown exports of a user's library or one Space."""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app import storage
from app.auth import AUTH_SUBJECT_CTE, VerifiedSubject, as_uuid, require_subject, resolve_auth_state
from app.db import fetch, fetchrow
from app.errors import ApiError

router = APIRouter()
_PAGE_SIZE = 25
_MEMORY_EXPORT_QUERY = """SELECT m.id, m.kind, m.source_app, m.source_url, m.title, m.description, m.user_note,
          m.content_text, m.page_text,
          m.captured_at,
          COALESCE((SELECT json_agg(json_build_object('id',s.id,'name',s.name,'color',s.color,'icon',s.icon)
            ORDER BY s.name)
            FROM memory_spaces ms JOIN spaces s ON s.id=ms.space_id AND s.deleted_at IS NULL
            WHERE ms.memory_id=m.id AND ms.user_id=m.user_id), '[]'::json) AS spaces,
          COALESCE((SELECT json_agg(json_build_object('id',a.id,'filename',a.original_filename,
              'mime_type',a.mime_type,'object_key',a.object_key,'role',ma.role) ORDER BY ma.position)
            FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id AND a.user_id=ma.user_id
            WHERE ma.memory_id=m.id AND ma.user_id=m.user_id), '[]'::json) AS assets
   FROM memories m
   WHERE m.user_id=$1 AND m.deleted_at IS NULL
     AND ($2::uuid IS NULL OR EXISTS (
       SELECT 1 FROM memory_spaces selected WHERE selected.memory_id=m.id
         AND selected.user_id=m.user_id AND selected.space_id=$2::uuid))
     AND ($3::timestamptz IS NULL OR (m.captured_at,m.id)<($3::timestamptz,$4::uuid))
   ORDER BY m.captured_at DESC, m.id DESC LIMIT $5"""


def _slug(value: str, fallback: str = "memory") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:64] or fallback


def _markdown_text(value: Any) -> str:
    return str(value).replace("\r\n", "\n").strip()


def _markdown_label(value: Any) -> str:
    text = _markdown_text(value).replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", text)


def _memory_markdown(memory: dict[str, Any], attachment_paths: list[tuple[dict[str, Any], str]]) -> str:
    title = _markdown_label(memory["title"] or memory["content_text"] or "Saved memory")
    lines = [
        f"# {title}",
        "",
        f"- **Trove ID:** {memory['id']}",
        f"- **Saved:** {memory['captured_at'].isoformat()}",
        f"- **Type:** {memory['kind']}",
    ]
    if memory["source_url"]:
        lines.append(f"- **Source:** {memory['source_url']}")
    if memory["source_app"]:
        lines.append(f"- **Saved from:** {memory['source_app']}")
    if memory["spaces"]:
        lines.append(f"- **Spaces:** {', '.join(space['name'] for space in memory['spaces'])}")

    if memory["user_note"]:
        lines.extend(["", "## Your note", "", _markdown_text(memory["user_note"])])
    if memory["content_text"] and memory["content_text"] != memory["user_note"]:
        lines.extend(["", "## Content", "", _markdown_text(memory["content_text"])])

    for heading, key in (
        ("Description", "description"),
        ("Page text", "page_text"),
    ):
        value = _markdown_text(memory[key]) if memory[key] else ""
        if value:
            lines.extend(["", f"## {heading}", "", value])

    if attachment_paths:
        lines.extend(["", "## Attachments", ""])
        for asset, path in attachment_paths:
            filename = _markdown_label(asset["filename"] or "Attachment")
            if asset["mime_type"].startswith("image/"):
                lines.append(f"![{filename}](../{path})")
            else:
                lines.append(f"- [{filename}](../{path}) ({asset['mime_type']})")
    return "\n".join(lines) + "\n"


def _remove_file(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@router.get("/export/markdown")
async def export_markdown(
    spaceId: str | None = None, subject: VerifiedSubject = Depends(require_subject)
) -> FileResponse:
    auth_args: tuple[object, ...] = (subject.subject, subject.email, subject.display_name)
    selected_space = None
    if spaceId:
        selected_space = await fetchrow(
            f"""WITH {AUTH_SUBJECT_CTE}, chosen AS (
                 SELECT id, name FROM spaces
                 WHERE id=$4 AND user_id=(SELECT user_id FROM auth) AND deleted_at IS NULL
                   AND NOT (SELECT deleted FROM auth) AND NOT (SELECT deletion_pending FROM auth)
               )
               SELECT (SELECT deleted FROM auth) AS deleted,
                 (SELECT deletion_pending FROM auth) AS deletion_pending,
                 (SELECT user_id FROM auth) AS user_id,
                 chosen.id, chosen.name
               FROM auth LEFT JOIN chosen ON TRUE""",
            *auth_args,
            as_uuid(spaceId),
        )
        if selected_space is None:  # pragma: no cover - the auth anchor always yields exactly one row
            raise ApiError(500, "internal_error", "The request could not be completed.")
        user_id = resolve_auth_state(selected_space)
        if selected_space["id"] is None:
            raise ApiError(404, "space_not_found", "Space not found.")

    if selected_space:
        indexed_spaces = {str(selected_space["id"]): {"id": selected_space["id"], "name": selected_space["name"]}}
    else:
        all_spaces = await fetch(
            f"""WITH {AUTH_SUBJECT_CTE}
                SELECT a.deleted, a.deletion_pending, a.user_id, listed.id, listed.name
                FROM auth a
                LEFT JOIN LATERAL (
                  SELECT id, name FROM spaces WHERE user_id=a.user_id AND deleted_at IS NULL ORDER BY name
                ) listed ON NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL""",
            *auth_args,
        )
        if not all_spaces:  # pragma: no cover - the auth anchor always yields at least one row
            raise ApiError(500, "internal_error", "The request could not be completed.")
        user_id = resolve_auth_state(all_spaces[0])
        indexed_spaces = {str(space["id"]): space for space in all_spaces if space["id"] is not None}

    file_descriptor, archive_path = tempfile.mkstemp(prefix="trove-export-", suffix=".zip")
    os.close(file_descriptor)
    try:
        space_paths: dict[str, str] = {}
        space_members: dict[str, list[tuple[str, str]]] = {space_id: [] for space_id in indexed_spaces}
        for space in indexed_spaces.values():
            space_paths[str(space["id"])] = f"spaces/{_slug(space['name'])}-{str(space['id'])[:8]}/README.md"

        with zipfile.ZipFile(archive_path, "w", allowZip64=True) as archive:
            exported_at = datetime.now(UTC).isoformat()
            export_title = selected_space["name"] if selected_space else "Trove library"
            memory_index: list[tuple[str, str]] = []
            cursor_at = None
            cursor_id = None
            while True:
                page = await fetch(
                    _MEMORY_EXPORT_QUERY,
                    user_id,
                    selected_space["id"] if selected_space else None,
                    cursor_at,
                    cursor_id,
                    _PAGE_SIZE,
                )
                if not page:
                    break
                for memory in page:
                    title = memory["title"] or memory["content_text"] or "Saved memory"
                    memory_path = f"memories/{_slug(title)}-{str(memory['id'])[:8]}.md"
                    memory_index.append((title, memory_path))
                    for space in memory["spaces"]:
                        space_id = str(space["id"])
                        if space_id in space_members:
                            space_members[space_id].append((title, memory_path))

                    attachment_paths: list[tuple[dict[str, Any], str]] = []
                    for asset in memory["assets"]:
                        filename = _slug(os.path.splitext(asset["filename"] or "attachment")[0], "attachment")
                        extension = os.path.splitext(asset["filename"] or "")[1]
                        extension = extension if re.fullmatch(r"\.[a-zA-Z0-9]{1,12}", extension) else ""
                        safe_name = f"attachments/{str(asset['id'])[:8]}-{filename}{extension}"
                        info = zipfile.ZipInfo(safe_name)
                        info.compress_type = zipfile.ZIP_STORED
                        with archive.open(info, "w", force_zip64=True) as target:
                            await storage.copy_object_to_file(asset["object_key"], target)
                        attachment_paths.append((asset, safe_name))
                    archive.writestr(memory_path, _memory_markdown(memory, attachment_paths))

                cursor_at = page[-1]["captured_at"]
                cursor_id = page[-1]["id"]
                if len(page) < _PAGE_SIZE:
                    break

            readme = [f"# {_markdown_label(export_title)}", "", f"Exported from Trove on {exported_at}.", ""]
            if not memory_index:
                readme.extend(["This export contains no saved memories yet.", ""])
            if selected_space:
                readme.extend([f"Space: **{_markdown_label(selected_space['name'])}**", ""])
            else:
                readme.extend([f"{len(memory_index)} memories across {len(indexed_spaces)} Spaces.", ""])
                if indexed_spaces:
                    readme.extend(["## Spaces", ""])
                    for space in sorted(indexed_spaces.values(), key=lambda item: item["name"].lower()):
                        readme.append(f"- [{_markdown_label(space['name'])}]({space_paths[str(space['id'])]})")
                    readme.append("")
            if memory_index:
                readme.extend(["## Memories", ""])
                readme.extend(f"- [{_markdown_label(title)}]({path})" for title, path in memory_index)
                readme.append("")
            archive.writestr("README.md", "\n".join(readme))

            for space_id, space_path in space_paths.items():
                space = indexed_spaces[space_id]
                readme_lines = [f"# {_markdown_label(space['name'])}", "", "Memories saved in this Space:", ""]
                members = space_members[space_id]
                for member in members:
                    title, memory_path = member
                    readme_lines.append(f"- [{_markdown_label(title)}](../../{memory_path})")
                if not members:
                    readme_lines.append("This Space has no exported memories.")
                archive.writestr(space_path, "\n".join(readme_lines) + "\n")

        filename = f"trove-{_slug(export_title)}-{datetime.now(UTC):%Y%m%d}.zip"
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(_remove_file, archive_path),
        )
    except Exception:
        _remove_file(archive_path)
        raise
