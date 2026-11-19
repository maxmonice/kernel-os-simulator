"""FIFO, LRU, and Optimal page replacement with a frame-by-frame trace."""

from __future__ import annotations

from dataclasses import dataclass

from .validation import require_non_negative, require_positive


@dataclass(frozen=True)
class ReferenceStep:
    index: int
    page: int
    frames: tuple[int | None, ...]
    result: str
    replaced: int | None


@dataclass(frozen=True)
class ReplacementResult:
    algorithm: str
    steps: tuple[ReferenceStep, ...]
    hits: int
    faults: int
    fault_rate: float


def simulate(references: list[int], frame_count: int, algorithm: str) -> ReplacementResult:
    require_positive(frame_count, "Frame count")
    if not references:
        raise ValueError("Enter at least one page reference.")
    for page in references:
        require_non_negative(page, "Page reference")
    if algorithm not in {"FIFO", "LRU", "Optimal"}:
        raise ValueError("Choose FIFO, LRU, or Optimal page replacement.")

    frames: list[int | None] = [None] * frame_count
    loaded_at: dict[int, int] = {}
    last_used: dict[int, int] = {}
    hits = faults = 0
    steps: list[ReferenceStep] = []
    for i, page in enumerate(references):
        replaced: int | None = None
        if page in frames:
            hits += 1
            result = "Hit"
        else:
            faults += 1
            result = "Fault"
            if None in frames:
                slot = frames.index(None)
            elif algorithm == "FIFO":
                slot = min(range(frame_count), key=lambda k: loaded_at[frames[k]])  # type: ignore[index]
            elif algorithm == "LRU":
                slot = min(range(frame_count), key=lambda k: last_used[frames[k]])  # type: ignore[index]
            else:
                slot, farthest = 0, -1
                for slot_index, resident in enumerate(frames):
                    try:
                        when = references.index(resident, i + 1)  # type: ignore[arg-type]
                    except ValueError:  # never used again: take the first such frame
                        slot = slot_index
                        break
                    if when > farthest:
                        slot, farthest = slot_index, when
            replaced = frames[slot]
            frames[slot] = page
            loaded_at[page] = i
        last_used[page] = i
        steps.append(ReferenceStep(i + 1, page, tuple(frames), result, replaced))
    return ReplacementResult(algorithm, tuple(steps), hits, faults, faults / len(references))
