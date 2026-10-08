"""Bound inbound file transfers and admit paid-plan uploads before free-plan uploads."""

from __future__ import annotations

import asyncio
import heapq
import time
from dataclasses import dataclass, field

MAX_ACTIVE_UPLOAD_TRANSFERS = 2
MAX_WAITING_UPLOAD_TRANSFERS = 8


class UploadAdmissionFull(RuntimeError):
    """The bounded wait queue is full; the client should retry its durable capture later."""


@dataclass(order=True)
class _Waiter:
    priority: int
    sequence: int
    rejected: bool = field(default=False, compare=False)


class UploadAdmission:
    """One-process priority gate shared by every authenticated upload on this web dyno."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._waiters: list[_Waiter] = []
        self._active = 0
        self._sequence = 0

    async def acquire(self, *, paid_plan: bool) -> float:
        """Wait for a transfer slot and return queue delay in milliseconds."""
        started = time.monotonic()
        async with self._condition:
            if self._active < MAX_ACTIVE_UPLOAD_TRANSFERS and not self._waiters:
                self._active += 1
                return (time.monotonic() - started) * 1000
            if len(self._waiters) >= MAX_WAITING_UPLOAD_TRANSFERS:
                free_waiters = [waiter for waiter in self._waiters if waiter.priority > 0]
                if not paid_plan or not free_waiters:
                    raise UploadAdmissionFull
                displaced = max(free_waiters, key=lambda waiter: waiter.sequence)
                self._waiters.remove(displaced)
                heapq.heapify(self._waiters)
                displaced.rejected = True
                self._condition.notify_all()

            self._sequence += 1
            waiter = _Waiter(priority=0 if paid_plan else 1, sequence=self._sequence)
            heapq.heappush(self._waiters, waiter)
            try:
                while True:
                    if waiter.rejected:
                        raise UploadAdmissionFull
                    if self._active < MAX_ACTIVE_UPLOAD_TRANSFERS and self._waiters[0] is waiter:
                        break
                    await self._condition.wait()
                heapq.heappop(self._waiters)
                self._active += 1
                return (time.monotonic() - started) * 1000
            except BaseException:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
                    heapq.heapify(self._waiters)
                    self._condition.notify_all()
                raise

    async def release(self) -> None:
        async with self._condition:
            if self._active <= 0:
                raise RuntimeError("Upload admission released without an active transfer")
            self._active -= 1
            self._condition.notify_all()


upload_admission = UploadAdmission()
