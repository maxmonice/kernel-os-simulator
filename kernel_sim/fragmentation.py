"""Memory blocks that each hold one process: First, Best, Next and Worst fit with fragmentation summaries."""

from __future__ import annotations

from dataclasses import dataclass

from .validation import require_positive


@dataclass(frozen=True)
class Allocation:
    process_id: str
    process_size: int
    block_index: int  # 1-based, in the order the blocks were entered
    block_size: int
    internal_waste: int  # block_size - process_size: space inside the block the process does not use


@dataclass(frozen=True)
class FragmentationResult:
    strategy: str
    allocations: tuple[Allocation, ...]
    unallocated: tuple[str, ...]
    free_blocks: tuple[int, ...]  # sizes of the blocks left empty
    total_free: int
    largest_hole: int  # largest empty block
    external_fragmentation: int  # empty memory that goes unused because a process could not be placed
    internal_fragmentation: int
    memory_map: tuple[tuple[int, int, str | None], ...]  # (base, size, process id, or None for an empty block), by address


def allocate(blocks: list[int], processes: list[tuple[str, int]], strategy: str = "First fit") -> FragmentationResult:
    """Place each process in one empty block. A block never holds a second process, even if it has room left."""
    if not blocks:
        raise ValueError("Enter at least one memory block.")
    if not processes:
        raise ValueError("Enter at least one process.")
    if strategy not in {"First fit", "Best fit", "Worst fit", "Next fit"}:
        raise ValueError("Choose First fit, Best fit, Worst fit, or Next fit.")
    for size in blocks:
        require_positive(size, "Memory block size")
    ids = [pid for pid, _ in processes]
    if len(set(ids)) != len(ids) or any(not pid.strip() for pid in ids):
        raise ValueError("Process IDs must be unique and non-empty.")
    for pid, size in processes:
        require_positive(size, f"Memory required by {pid}")

    owner: list[str | None] = [None] * len(blocks)
    allocations: list[Allocation] = []
    unallocated: list[str] = []
    next_start = 0  # Next fit resumes searching here, just after the last placement
    for pid, requested in processes:
        fits = [i for i, size in enumerate(blocks) if owner[i] is None and size >= requested]
        if not fits:
            unallocated.append(pid)
            continue
        if strategy == "First fit":
            index = fits[0]
        elif strategy == "Best fit":
            index = min(fits, key=lambda i: (blocks[i], i))
        elif strategy == "Worst fit":
            index = max(fits, key=lambda i: (blocks[i], -i))
        else:
            index = min(fits, key=lambda i: (i < next_start, i))  # first fit at or after next_start, then wrap around
        owner[index] = pid
        allocations.append(Allocation(pid, requested, index + 1, blocks[index], blocks[index] - requested))
        next_start = index + 1
    memory_map, base = [], 0
    for size, pid in zip(blocks, owner):
        memory_map.append((base, size, pid))
        base += size
    empty = tuple(size for size, pid in zip(blocks, owner) if pid is None)
    return FragmentationResult(
        strategy, tuple(allocations), tuple(unallocated), empty, sum(empty), max(empty, default=0),
        sum(empty) if unallocated else 0, sum(a.internal_waste for a in allocations), tuple(memory_map),
    )
