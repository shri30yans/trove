"""HTTP byte ranges for private media delivery."""

from __future__ import annotations

import re
from dataclasses import dataclass

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int
    total: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_byte_range(value: str, size: int) -> ByteRange:
    match = _RANGE.fullmatch(value.strip())
    if not match or size <= 0:
        raise ValueError("Unsatisfiable range")
    first, last = match.groups()
    if not first:
        if not last or int(last) <= 0:
            raise ValueError("Unsatisfiable range")
        return ByteRange(max(0, size - int(last)), size - 1, size)
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError("Unsatisfiable range")
    return ByteRange(start, end, size)
