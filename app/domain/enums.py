"""Enumerations that mirror the Postgres enum types, plus the queue's lifecycle verbs."""

from __future__ import annotations

from enum import StrEnum


class MemoryKind(StrEnum):
    """Mirrors the current memory_kind declared by migrations/006_remove_place_memory_kind.sql."""

    LINK = "link"
    IMAGE = "image"
    TEXT = "text"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"

    @classmethod
    def parse(cls, value: object) -> MemoryKind | None:
        """Return the member for a client-supplied value, or None if it is not a kind."""
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                return None
        return None


class MemoryStatus(StrEnum):
    """mirrors CREATE TYPE memory_status (migrations/001_initial.sql:8)."""

    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AssetStatus(StrEnum):
    """mirrors CREATE TYPE asset_status (migrations/001_initial.sql:11)."""

    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    ATTACHED = "attached"
    FAILED = "failed"


class ResurfacingCadence(StrEnum):
    """mirrors the user_preferences.resurfacing_cadence CHECK (migrations/001_initial.sql:164)."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    OFF = "off"


class JobStatus(StrEnum):
    """memory_processing_jobs.status — a text CHECK, not an enum, and it uses different
    words for the same lifecycle than memory_status does (completed vs ready)."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResolution(StrEnum):
    """What happened to a job, as distinct from what its row says it is. The claim loop needs the
    difference: 'requeued' and 'lease_lost' both mean nothing was processed, while 'completed' and
    'failed' mean the job left the queue. The status column cannot express lease_lost at all."""

    REQUEUED = "requeued"
    COMPLETED = "completed"
    FAILED = "failed"
    LEASE_LOST = "lease_lost"


def memory_status_for_job(status: JobStatus) -> MemoryStatus:
    """Project the job lifecycle onto the memory lifecycle. Single owner of that mapping."""
    return {
        JobStatus.QUEUED: MemoryStatus.QUEUED,
        JobStatus.PROCESSING: MemoryStatus.PROCESSING,
        JobStatus.COMPLETED: MemoryStatus.READY,
        JobStatus.FAILED: MemoryStatus.FAILED,
    }[status]


def is_terminal_job_status(status: JobStatus) -> bool:
    return status in (JobStatus.COMPLETED, JobStatus.FAILED)
