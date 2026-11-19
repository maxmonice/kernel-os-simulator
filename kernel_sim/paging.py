"""Page-table mapping and logical-to-physical address translation."""

from __future__ import annotations

from .validation import require_non_negative, require_positive, require_unique


def translate(page_size: int, page_table: list[tuple[int, int]], logical_address: int,
              logical_size: int | None = None, physical_size: int | None = None) -> dict:
    """page = address // page_size, offset = address % page_size, physical = frame * page_size + offset.

    With memory sizes given, the address must lie inside logical memory and the frame inside physical
    memory. A page missing from the table is a page fault (physical_address is None), not an error.
    """
    require_positive(page_size, "Page size")
    require_non_negative(logical_address, "Logical address")
    require_unique((str(page) for page, _ in page_table), "Page number")
    for page, frame in page_table:
        require_non_negative(page, "Page number")
        require_non_negative(frame, "Frame number")
    pages = frames = None
    if logical_size is not None and physical_size is not None:
        if page_size > logical_size or page_size > physical_size:
            raise ValueError("Page size must be smaller than both memory sizes.")
        if logical_address >= logical_size:
            raise ValueError(f"Logical address must be a whole number between 0 and {logical_size - 1}.")
        pages, frames = logical_size // page_size, physical_size // page_size
    page_number, offset = divmod(logical_address, page_size)
    result = {"logical_address": logical_address, "page_size": page_size, "page": page_number, "offset": offset,
              "pages": pages, "frames": frames, "frame": None, "physical_address": None}
    frame = dict(page_table).get(page_number)
    if frame is None:
        return result  # page fault
    if frames is not None and frame >= frames:
        raise ValueError(f"Frame number must be between 0 and {frames - 1}.")
    result["frame"] = frame
    result["physical_address"] = frame * page_size + offset
    return result
