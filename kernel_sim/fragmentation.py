"""Fixed and variable partition allocation on an address-based memory map, with fragmentation summaries."""

from __future__ import annotations

from dataclasses import dataclass

from .validation import require_positive


@dataclass(frozen=True)
class Allocation:
    process_id: str
    process_size: int
    block_index: int
    block_size: int
    internal_waste: int


@dataclass(frozen=True)
class FragmentationResult:
    mode: str
    strategy: str
    allocations: tuple[Allocation, ...]
    unallocated: tuple[str, ...]
    free_blocks: tuple[int, ...]
    total_free: int
    largest_hole: int
    external_fragmentation: int
    internal_fragmentation: int
    memory_map: tuple[tuple[int, int, str], ...] = ()  # (base, size, "Free" or process id), by address


class _Block:
    __slots__ = ("base", "size", "label", "source")

    def __init__(self, base: int, size: int, label: str, source: int) -> None:
        self.base, self.size, self.label, self.source = base, size, label, source

    @property
    def free(self) -> bool:
        return self.label == "Free"


def _next_fit(blocks: list[_Block], address: int, size: int) -> int | None:
    """First fitting hole at or after `address`, then wrap around to the holes before it."""
    for wrapped in (False, True):
        for i, b in enumerate(blocks):
            if b.free and b.size >= size and (b.base < address) == wrapped:
                return i
    return None


def allocate(
    blocks: list[int], processes: list[tuple[str, int]], mode: str = "Fixed partitions", strategy: str = "First fit"
) -> FragmentationResult:
    if not blocks:
        raise ValueError("Enter at least one memory block.")
    if not processes:
        raise ValueError("Enter at least one process.")
    if mode not in {"Fixed partitions", "Variable partitions"}:
        raise ValueError("Choose fixed or variable partitions.")
    if strategy not in {"First fit", "Best fit", "Worst fit", "Next fit"}:
        raise ValueError("Choose First fit, Best fit, Worst fit, or Next fit.")
    for size in blocks:
        require_positive(size, "Memory block size")
    ids = [pid for pid, _ in processes]
    if len(set(ids)) != len(ids) or any(not pid.strip() for pid in ids):
        raise ValueError("Process IDs must be unique and non-empty.")
    for pid, size in processes:
        require_positive(size, f"Memory required by {pid}")

    memory: list[_Block] = []
    base = 0
    for i, size in enumerate(blocks):  # blocks sit back to back from address 0
        memory.append(_Block(base, size, "Free", i + 1))
        base += size
    allocations: list[Allocation] = []
    unallocated: list[str] = []
    internal = 0
    next_address = 0
    for pid, requested in processes:
        fits = [i for i, b in enumerate(memory) if b.free and b.size >= requested]
        if not fits:
            unallocated.append(pid)
            continue
        if strategy == "First fit":
            index = fits[0]
        elif strategy == "Best fit":
            index = min(fits, key=lambda i: (memory[i].size, i))
        elif strategy == "Worst fit":
            index = max(fits, key=lambda i: (memory[i].size, -i))
        else:
            index = _next_fit(memory, next_address, requested)
        hole = memory[index]
        waste = hole.size - requested if mode == "Fixed partitions" else 0
        internal += waste
        allocations.append(Allocation(pid, requested, hole.source, hole.size, waste))
        if mode == "Variable partitions" and hole.size > requested:  # split: allocated part + free remainder
            memory.insert(index + 1, _Block(hole.base + requested, hole.size - requested, "Free", hole.source))
            hole.size = requested
        hole.label = pid
        next_address = hole.base + requested
    holes = tuple(b.size for b in memory if b.free)
    total_free = sum(holes)
    largest = max(holes, default=0)
    return FragmentationResult(
        mode, strategy, tuple(allocations), tuple(unallocated), holes,
        total_free, largest, total_free - largest if mode == "Variable partitions" else 0, internal,
        tuple((b.base, b.size, b.label) for b in memory),
    )
