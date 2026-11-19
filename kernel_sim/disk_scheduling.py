"""Disk-head request ordering and total head-movement calculations."""

from __future__ import annotations

from dataclasses import dataclass

from .validation import require_non_negative


@dataclass(frozen=True)
class DiskResult:
    algorithm: str
    service_order: tuple[int, ...]
    path: tuple[int, ...]
    total_movement: int


def schedule(
    requests: list[int], head: int, algorithm: str, low: int = 0, high: int = 199, direction: str = "Right"
) -> DiskResult:
    if not requests:
        raise ValueError("Enter at least one disk request.")
    for label, value in (("Head position", head), ("Lower cylinder", low), ("Upper cylinder", high)):
        require_non_negative(value, label)
    if low >= high:
        raise ValueError("The upper cylinder must be greater than the lower cylinder.")
    if not low <= head <= high:
        raise ValueError("The starting head position must be within the cylinder range.")
    for request in requests:
        if not low <= request <= high:
            raise ValueError(f"Request {request} is outside the configured cylinder range {low}–{high}.")
    if direction not in {"Left", "Right"}:
        raise ValueError("Choose a direction: Left or Right.")
    label = algorithm
    if algorithm == "SCAN (Elevator)":  # "elevator" is the textbook name for SCAN
        algorithm = "SCAN"
    allowed = {"FCFS", "SSTF", "SCAN", "C-SCAN", "LOOK", "C-LOOK"}
    if algorithm not in allowed:
        raise ValueError(f"Choose one of: {', '.join(sorted(allowed))}.")

    if algorithm == "FCFS":
        order = requests.copy()
        path = [head, *order]
    elif algorithm == "SSTF":
        pending = list(enumerate(requests))
        order = []
        position = head
        while pending:
            i, request = min(pending, key=lambda item: (abs(item[1] - position), item[0]))
            order.append(request)
            position = request
            pending.remove((i, request))
        path = [head, *order]
    else:
        left = sorted((r for r in requests if r < head), reverse=True)
        right = sorted(r for r in requests if r >= head)
        if direction == "Left":
            first, second = left, right
        else:
            first, second = right, left
        if algorithm == "SCAN":
            path = [head, *first]
            boundary = low if direction == "Left" else high
            if path[-1] != boundary:
                path.append(boundary)
            path.extend(second)
            order = first + second
        elif algorithm == "C-SCAN":
            path = [head, *first]
            boundary = low if direction == "Left" else high
            opposite = high if direction == "Left" else low
            if path[-1] != boundary:
                path.append(boundary)
            path.append(opposite)
            wrapped = sorted(second, reverse=(direction == "Left"))
            path.extend(wrapped)
            order = first + wrapped
        elif algorithm == "LOOK":
            path = [head, *first, *second]
            order = first + second
        else:  # C-LOOK wraps to the farthest outstanding request, then keeps moving.
            wrapped = sorted(second, reverse=(direction == "Left"))
            path = [head, *first, *wrapped]
            order = first + wrapped
    movement = sum(abs(path[i] - path[i - 1]) for i in range(1, len(path)))
    return DiskResult(label, tuple(order), tuple(path), movement)
