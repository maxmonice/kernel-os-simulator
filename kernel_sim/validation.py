"""Input validation helpers shared by the pure simulation modules."""

from __future__ import annotations

import re
from collections.abc import Iterable


def require_non_negative(value: int, label: str) -> int:
    if value < 0:
        raise ValueError(f"{label} must be zero or greater.")
    return value


def require_positive(value: int, label: str) -> int:
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return value


_SIZE = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)?\s*", re.IGNORECASE)


def parse_size(text: str, label: str) -> int:
    """Bytes from '4096', '4KB', '16 GB' (1 KB = 1024 B); bare numbers are bytes."""
    match = _SIZE.fullmatch(text or "")
    if not match:
        raise ValueError(f"{label} must be a size like 4096, 4KB or 16GB.")
    unit = (match.group(2) or "B").upper()
    size = int(float(match.group(1)) * 1024 ** ["B", "KB", "MB", "GB", "TB"].index(unit))
    return require_positive(size, label)


def require_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{label} '{value}' is repeated. Each entry must be unique.")
        seen.add(value)
