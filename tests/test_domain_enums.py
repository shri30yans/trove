"""The domain enums are only the single owner of each vocabulary if the mirrors stay in step.

Postgres and the Expo client each declare these lists independently, so this file is the only
automated check that all three agree. A rename on either side fails here rather than at runtime.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.domain.enums import (
    AssetStatus,
    JobResolution,
    JobStatus,
    MemoryKind,
    MemoryStatus,
    ResurfacingCadence,
    is_terminal_job_status,
    memory_status_for_job,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENUM_DECLARATION = re.compile(r"CREATE TYPE (?:\w+\.)?(\w+) AS ENUM \(([^)]*)\)", re.I)
CHECK_DECLARATION = re.compile(r"CHECK \((\w+) IN \(([^)]*)\)\)", re.I)


def _schema_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted((REPO_ROOT / "migrations").glob("*.sql")))


def _labels(raw: str) -> tuple[str, ...]:
    return tuple(match for match in re.findall(r"'([^']*)'", raw))


def test_postgres_declares_the_enums_this_package_mirrors() -> None:
    declared = {name.lower(): _labels(labels) for name, labels in ENUM_DECLARATION.findall(_schema_text())}
    assert declared["memory_kind"] == tuple(kind.value for kind in MemoryKind)
    assert declared["memory_status"] == tuple(status.value for status in MemoryStatus)
    assert declared["asset_status"] == tuple(status.value for status in AssetStatus)


def test_the_check_constrained_columns_match_their_enums() -> None:
    checks = {name.lower(): _labels(labels) for name, labels in CHECK_DECLARATION.findall(_schema_text())}
    assert checks["status"] == tuple(status.value for status in JobStatus)
    assert checks["resurfacing_cadence"] == tuple(cadence.value for cadence in ResurfacingCadence)


def test_the_client_schema_offers_the_same_memory_kinds(mobile_schema) -> None:
    result = mobile_schema("src/domain/pending-capture.ts", "memoryKindSchema", "text")
    assert result["valid"]
    assert tuple(result["labels"]) == tuple(kind.value for kind in MemoryKind)


def test_the_kind_vocabulary_is_not_redeclared_anywhere_in_python() -> None:
    """Only app/domain/enums.py may spell out the list of kinds."""
    needle = '"link", "image"'
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "app").rglob("*.py")
        if path.name != "enums.py" and needle in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"duplicate MemoryKind lists at {offenders}"


def test_every_memory_kind_parses_and_anything_else_does_not() -> None:
    for kind in MemoryKind:
        assert MemoryKind.parse(kind.value) is kind
    for value in ("", "LINK", "photo", None, 3, ["link"], True):
        assert MemoryKind.parse(value) is None


def test_a_completed_job_is_a_ready_memory_and_the_other_states_line_up() -> None:
    assert memory_status_for_job(JobStatus.QUEUED) is MemoryStatus.QUEUED
    assert memory_status_for_job(JobStatus.PROCESSING) is MemoryStatus.PROCESSING
    assert memory_status_for_job(JobStatus.COMPLETED) is MemoryStatus.READY
    assert memory_status_for_job(JobStatus.FAILED) is MemoryStatus.FAILED


def test_the_job_to_memory_projection_covers_both_lifecycles_completely() -> None:
    projected = {memory_status_for_job(status) for status in JobStatus}
    assert projected == set(MemoryStatus)


def test_terminal_job_states_are_the_two_the_worker_stops_on() -> None:
    assert is_terminal_job_status(JobStatus.COMPLETED)
    assert is_terminal_job_status(JobStatus.FAILED)
    assert not is_terminal_job_status(JobStatus.QUEUED)
    assert not is_terminal_job_status(JobStatus.PROCESSING)


@pytest.mark.parametrize("resolution", list(JobResolution))
def test_the_queue_resolutions_are_distinct_strings(resolution: JobResolution) -> None:
    assert resolution.value == str(resolution)
    assert JobResolution.REQUEUED is not JobResolution.LEASE_LOST
