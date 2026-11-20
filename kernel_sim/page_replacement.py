"""FIFO, LRU, Optimal, Second Chance, Clock, NRU, NFU, Random and Working Set page replacement with a frame-by-frame trace."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from .validation import require_non_negative, require_positive

ALGORITHMS = ("FIFO", "LRU", "Optimal", "Second Chance", "Clock", "NRU", "NFU", "Random", "Working Set")


@dataclass(frozen=True)
class ReferenceStep:
    index: int
    page: int
    frames: tuple[int | None, ...]
    result: str
    replaced: int | None
    write: bool = False
    bits: tuple[str | None, ...] = ()  # per frame: "R1" (Second Chance, Clock), "R1M0" (NRU), "R1 C2" (NFU: R bit, counter)
    detail: str = ""  # why this page was chosen, e.g. "1: R=1 -> second chance; 2: R=0 -> replaced"
    hand: int | None = None  # Clock: frame index the hand points at after this step


@dataclass(frozen=True)
class ReplacementResult:
    algorithm: str
    steps: tuple[ReferenceStep, ...]
    hits: int
    faults: int
    fault_rate: float


def simulate(references: list[int], frame_count: int, algorithm: str, writes: list[bool] | None = None,
             tick: int = 0, seed: int = 0) -> ReplacementResult:
    """`writes[i]` marks reference i as a write (sets the modified bit; only NRU looks at it).
    `tick` is a number of references: NRU and NFU clear every reference bit before reference `tick`, `2 * tick`, ...
    (NFU first adds each R bit to its page's counter); Working Set uses it as the window size. 0 = never for NRU/NFU.
    Random and NRU (which picks randomly inside the lowest class) use a fixed `seed`, so the same input always gives the same result."""
    require_positive(frame_count, "Frame count")
    if not references:
        raise ValueError("Enter at least one page reference.")
    for page in references:
        require_non_negative(page, "Page reference")
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Choose one of: {', '.join(ALGORITHMS)}.")
    require_non_negative(tick, "Clock tick / window size")
    if algorithm == "Working Set":
        require_positive(tick, "Working Set window size")
    writes = writes or [False] * len(references)
    if len(writes) != len(references):
        raise ValueError("Every page reference needs a read/write flag.")

    frames: list[int | None] = [None] * frame_count
    loaded_at: dict[int, int] = {}
    last_used: dict[int, int] = {}
    queue: deque[int] = deque()  # Second Chance: resident pages, oldest first
    hand = 0  # Clock: next frame to examine
    referenced: dict[int, bool] = {}  # R bit. Second Chance and Clock load a page with 0; NRU and NFU with 1 (the load is a use)
    modified: dict[int, bool] = {}  # NRU modified (dirty) bit, set by writes
    counter: dict[int, int] = {}  # NFU: number of ticks in which the page was used
    rng = random.Random(seed)
    hits = faults = 0
    steps: list[ReferenceStep] = []
    for i, page in enumerate(references):
        replaced: int | None = None
        detail = ""
        if algorithm in ("NRU", "NFU") and tick and i and i % tick == 0:  # clock tick
            if algorithm == "NFU":
                for resident in frames:
                    if resident is not None:
                        counter[resident] += referenced[resident]
            referenced = dict.fromkeys(referenced, False)
        if page in frames:
            hits += 1
            result = "Hit"
            referenced[page] = True
            modified[page] = modified.get(page, False) or writes[i]
            if algorithm in ("Second Chance", "Clock"):
                detail = f"{page}: hit, R set to 1"
        else:
            faults += 1
            result = "Fault"
            if None in frames:
                slot = frames.index(None)
            elif algorithm == "FIFO":
                slot = min(range(frame_count), key=lambda k: loaded_at[frames[k]])  # type: ignore[index]
            elif algorithm == "LRU":
                slot = min(range(frame_count), key=lambda k: last_used[frames[k]])  # type: ignore[index]
            elif algorithm == "Second Chance":
                notes = []
                while referenced[queue[0]]:  # used since it loaded: clear its bit, send it to the back
                    notes.append(f"{queue[0]}: R=1 -> second chance (R cleared, moved to back)")
                    referenced[queue[0]] = False
                    queue.rotate(-1)
                notes.append(f"{queue[0]}: R=0 -> replaced")
                slot = frames.index(queue.popleft())
                detail = "; ".join(notes)
            elif algorithm == "Clock":
                notes = []
                while referenced[frames[hand]]:  # type: ignore[index]
                    notes.append(f"frame {hand + 1} ({frames[hand]}): R=1 -> second chance (R cleared, hand moves on)")
                    referenced[frames[hand]] = False  # type: ignore[index]
                    hand = (hand + 1) % frame_count
                notes.append(f"frame {hand + 1} ({frames[hand]}): R=0 -> replaced")
                slot = hand
                detail = "; ".join(notes)
            elif algorithm == "NRU":  # class 0 = R0 M0, 1 = R0 M1, 2 = R1 M0, 3 = R1 M1; a random page of the lowest class goes
                classes = [2 * referenced[f] + modified[f] for f in frames]  # type: ignore[index]
                candidates = [k for k, c in enumerate(classes) if c == min(classes)]
                slot = rng.choice(candidates)
                detail = (f"lowest class {classes[slot]}: pages {[frames[k] for k in candidates]}; "
                          f"random pick {frames[slot]} -> replaced")
            elif algorithm == "NFU":  # lowest counter; ties go to the oldest page
                slot = min(range(frame_count), key=lambda k: (counter[frames[k]], loaded_at[frames[k]]))  # type: ignore[index]
                detail = f"{frames[slot]}: lowest counter ({counter[frames[slot]]}) -> replaced"  # type: ignore[index]
            elif algorithm == "Random":
                slot = rng.randrange(frame_count)
                detail = f"random pick: frame {slot + 1} ({frames[slot]}) -> replaced"
            elif algorithm == "Working Set":
                outside = [k for k in range(frame_count) if i - last_used[frames[k]] > tick]  # type: ignore[index]
                if outside:  # first page in frame order that has not been used within the window
                    slot = outside[0]
                    detail = f"{frames[slot]}: last used {i - last_used[frames[slot]]} references ago (> window {tick}), outside the working set -> replaced"  # type: ignore[index]
                else:
                    slot = min(range(frame_count), key=lambda k: (last_used[frames[k]], k))  # type: ignore[index]
                    detail = f"all pages are in the working set (window {tick}) -> oldest page {frames[slot]} replaced"
            else:  # Optimal
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
            if algorithm == "Second Chance":
                queue.append(page)
            if algorithm == "Clock":
                hand = (slot + 1) % frame_count
            referenced[page] = algorithm in ("NRU", "NFU")
            modified[page] = writes[i]
            counter[page] = 0
        last_used[page] = i
        bits: tuple[str | None, ...] = ()
        if algorithm in ("Second Chance", "Clock"):
            bits = tuple(None if f is None else f"R{int(referenced[f])}" for f in frames)
        elif algorithm == "NRU":
            bits = tuple(None if f is None else f"R{int(referenced[f])}M{int(modified[f])}" for f in frames)
        elif algorithm == "NFU":
            bits = tuple(None if f is None else f"R{int(referenced[f])} C{counter[f]}" for f in frames)
        steps.append(ReferenceStep(i + 1, page, tuple(frames), result, replaced, writes[i], bits, detail,
                                   hand if algorithm == "Clock" else None))
    return ReplacementResult(algorithm, tuple(steps), hits, faults, faults / len(references))
