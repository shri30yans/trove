"""Wire shapes shared by more than one route.

Four endpoints spell the same ten Memory fields by hand, so a rename that reached three of them
would leave the fourth serving an older shape to the same client type. The card carries only what all
four select, so no caller has to pass a placeholder for a column its query never asked for.
"""

from __future__ import annotations

from typing import Any


def memory_card(row: dict[str, Any]) -> dict[str, Any]:
    """The fields every Memory card carries, in the camelCase spelling the client reads."""
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "status": row["status"],
        "sourceApp": row["source_app"],
        "sourceUrl": row["source_url"],
        "sourceDomain": row["source_domain"],
        "title": row["title"],
        "capturedAt": row["captured_at"],
    }
