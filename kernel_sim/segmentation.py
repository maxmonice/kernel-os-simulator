"""Segment-table validation (RAM fit, no overlap), physical memory map and address translation."""

from __future__ import annotations

from .validation import require_non_negative, require_unique


def translate(segments: list[tuple[int, int, int]], segment_number: int, offset: int, ram: int | None = None) -> dict:
    if not segments:
        raise ValueError("Enter at least one segment.")
    require_unique((str(number) for number, _, _ in segments), "Segment number")
    for number, base, limit in segments:
        require_non_negative(number, "Segment number")
        require_non_negative(base, "Segment base")
        if limit <= 0:
            raise ValueError(f"The limit for segment {number} must be greater than zero.")
        if ram is not None and (base > ram or limit > ram - base):
            raise ValueError(f"Segment {number} must fit inside RAM.")
    ordered = sorted(segments, key=lambda s: s[1])
    for (n1, b1, l1), (n2, b2, _) in zip(ordered, ordered[1:]):
        if b2 < b1 + l1:
            raise ValueError(f"Segment {n2} overlaps segment {n1}.")
    require_non_negative(segment_number, "Segment number")
    require_non_negative(offset, "Offset")
    table = {number: (base, limit) for number, base, limit in segments}
    if segment_number not in table:
        raise ValueError(f"Segment {segment_number} does not exist.")
    base, limit = table[segment_number]
    if offset >= limit:
        raise ValueError(f"Address fault: offset {offset} is outside segment {segment_number} (limit {limit}).")
    memory_map: list[tuple[int, int, str]] = []  # (start, end, label), end exclusive; gaps are "Free"
    cursor = 0
    for number, b, l in ordered:
        if b > cursor:
            memory_map.append((cursor, b, "Free"))
        memory_map.append((b, b + l, f"Segment {number}"))
        cursor = b + l
    if ram is not None and cursor < ram:
        memory_map.append((cursor, ram, "Free"))
    return {"segment": segment_number, "base": base, "limit": limit, "offset": offset,
            "physical_address": base + offset, "memory_map": tuple(memory_map)}
