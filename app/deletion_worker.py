"""Poll and complete account deletions after their disclosed recovery period."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from app.account_deletion import process_due_account_deletions

POLL_INTERVAL_SECONDS = 60.0
logger = logging.getLogger("trove.account_deletion_worker")


class AccountDeletionWorker:
    def __init__(self) -> None:
        self._stopping: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = asyncio.Event()
        self._task = asyncio.create_task(self._run(self._stopping))

    async def stop(self) -> None:
        if self._task is None or self._stopping is None:
            return
        self._stopping.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._stopping = None

    @staticmethod
    async def _run(stopping: asyncio.Event) -> None:
        while not stopping.is_set():
            try:
                await process_due_account_deletions()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - a later poll retries transient database failures
                logger.error("Account deletion polling failed; error_type=%s", type(error).__name__)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stopping.wait(), timeout=POLL_INTERVAL_SECONDS)


account_deletion_worker = AccountDeletionWorker()
