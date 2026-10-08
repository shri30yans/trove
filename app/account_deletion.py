"""Seven-day account deletion window and retryable removal across Trove and Supabase."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app import storage, supabase_auth
from app.auth import Principal
from app.db import execute, fetch, fetchrow, fetchval, transaction
from app.errors import ApiError

logger = logging.getLogger("trove.account_deletion")


async def request_account_deletion(principal: Principal) -> dict[str, Any]:
    if await fetchval_deleted(principal.subject):
        raise ApiError(401, "account_deleted", "This account has already been deleted.")
    try:
        user_id = uuid.UUID(principal.id)
        uuid.UUID(principal.subject)
    except ValueError as error:
        raise ApiError(
            503, "account_deletion_unavailable", "This account cannot be deleted automatically. Contact support."
        ) from error
    row = await fetchrow(
        """INSERT INTO account_deletion_requests(auth_subject,user_id,delete_after)
           VALUES($1,$2,now()+interval '7 days')
           ON CONFLICT(auth_subject) DO UPDATE SET user_id=EXCLUDED.user_id
           RETURNING requested_at,delete_after,(delete_after > now()) AS deletion_cancellable""",
        principal.subject,
        user_id,
    )
    if row is None:
        raise ApiError(503, "account_deletion_unavailable", "Could not schedule account deletion. Try again.")
    return {
        "requestedAt": row["requested_at"],
        "deleteAfter": row["delete_after"],
        "deletionCancellable": row["deletion_cancellable"],
    }


async def fetchval_deleted(subject: str) -> bool:
    return bool(await fetchval("SELECT 1 FROM deleted_auth_subjects WHERE auth_subject=$1", subject))


async def account_deletion_status(subject: str) -> dict[str, Any]:
    row = await fetchrow(
        """SELECT requested_at,delete_after,(delete_after > now()) AS deletion_cancellable
           FROM account_deletion_requests WHERE auth_subject=$1""",
        subject,
    )
    if row is not None:
        return {
            "deletionScheduled": True,
            "deleteAfter": row["delete_after"],
            "deletionComplete": False,
            "deletionCancellable": row["deletion_cancellable"],
        }
    if await fetchval_deleted(subject):
        return {"deletionScheduled": True, "deleteAfter": None, "deletionComplete": True, "deletionCancellable": False}
    return {"deletionScheduled": False, "deleteAfter": None, "deletionComplete": False, "deletionCancellable": False}


async def cancel_account_deletion(subject: str) -> None:
    row = await fetchrow(
        """DELETE FROM account_deletion_requests
           WHERE auth_subject=$1 AND delete_after > now()
           RETURNING auth_subject""",
        subject,
    )
    if row is None:
        raise ApiError(
            409, "account_deletion_not_cancellable", "The deletion window has ended or no deletion is pending."
        )


async def process_due_account_deletions() -> int:
    requests = await fetch(
        """SELECT auth_subject,user_id FROM account_deletion_requests
           WHERE delete_after <= now() ORDER BY delete_after LIMIT 20"""
    )
    completed = 0
    for request in requests:
        subject = str(request["auth_subject"])
        user_id = uuid.UUID(str(request["user_id"]))
        try:
            # Tombstone first: a still-valid JWT must not recreate an empty app_users row.
            await execute(
                "INSERT INTO deleted_auth_subjects(auth_subject) VALUES($1) ON CONFLICT DO NOTHING",
                subject,
            )
            await storage.delete_user_objects(str(user_id))
            async with transaction() as connection:
                await connection.execute("DELETE FROM app_users WHERE id=$1", user_id)
            await supabase_auth.delete_user(subject)
            await execute("DELETE FROM account_deletion_requests WHERE auth_subject=$1", subject)
            completed += 1
            logger.info("Account deletion completed")
        except Exception as error:  # noqa: BLE001 - preserve the durable request and retry next interval
            logger.error("Account deletion retry scheduled; error_type=%s", type(error).__name__)
    return completed
