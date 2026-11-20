"""CPU scheduling algorithms and common completion metrics."""

from __future__ import annotations

from collections import deque
from fractions import Fraction
from typing import Callable

from .models import Process, ScheduleResult, ScheduleRow, Segment
from .validation import require_non_negative, require_positive, require_unique


def _validate(processes: list[Process]) -> None:
    if not processes:
        raise ValueError("Add at least one process before running the scheduler.")
    require_unique((p.pid for p in processes), "Process ID")
    for p in processes:
        if not p.pid.strip():
            raise ValueError("Process IDs cannot be blank.")
        require_non_negative(p.arrival, f"Arrival time for {p.pid}")
        require_positive(p.burst, f"Burst time for {p.pid}")


def _merge(segments: list[Segment]) -> tuple[Segment, ...]:
    merged: list[Segment] = []
    for item in segments:
        if item.end <= item.start:
            continue
        if merged and merged[-1].pid == item.pid and merged[-1].end == item.start:
            previous = merged[-1]
            merged[-1] = Segment(previous.start, item.end, item.pid)
        else:
            merged.append(item)
    return tuple(merged)


def _n(x) -> int | float:
    """Exact time -> int when whole, else a float rounded to 6 places (for display)."""
    x = Fraction(x)
    return int(x) if x.denominator == 1 else round(float(x), 6)


def _result(processes: list[Process], algorithm: str, timeline: list[Segment]) -> ScheduleResult:
    # Times may be ints or Fractions (decimal input), so sums stay exact until the final conversion.
    completion: dict[str, object] = {}
    first_start: dict[str, object] = {}
    for segment in timeline:
        if segment.pid is not None:
            completion[segment.pid] = segment.end
            first_start.setdefault(segment.pid, segment.start)
    stats = [(p, completion[p.pid], completion[p.pid] - p.arrival, completion[p.pid] - p.arrival - p.burst,
              first_start[p.pid] - p.arrival) for p in processes]  # (process, CT, TAT, WT, RT)
    rows = tuple(ScheduleRow(p.pid, _n(p.arrival), _n(p.burst), p.priority, _n(c), _n(t), _n(w), _n(r))
                 for p, c, t, w, r in stats)

    def average(column: int) -> float:
        return float(Fraction(sum(row[column] for row in stats)) / len(stats))

    makespan = max((s.end for s in timeline), default=0)
    busy = sum(s.end - s.start for s in timeline if s.pid is not None)
    return ScheduleResult(
        algorithm,
        rows,
        tuple(Segment(_n(s.start), _n(s.end), s.pid) for s in _merge(timeline)),
        average(3), average(2), average(4),
        _n(makespan),
        float(100 * Fraction(busy) / Fraction(makespan)) if makespan else 0.0,
    )


def _non_preemptive(processes: list[Process], chooser: Callable[[Process], tuple]) -> list[Segment]:
    pending = sorted(enumerate(processes), key=lambda pair: (pair[1].arrival, pair[0]))
    ready: list[tuple[int, Process]] = []
    timeline: list[Segment] = []
    time = 0
    index = 0
    while index < len(pending) or ready:
        while index < len(pending) and pending[index][1].arrival <= time:
            order, process = pending[index]
            ready.append((order, process))
            index += 1
        if not ready:
            next_time = pending[index][1].arrival
            if next_time > time:
                timeline.append(Segment(time, next_time, None))
                time = next_time
            continue
        order, process = min(ready, key=lambda item: (*chooser(item[1]), item[0]))
        ready.remove((order, process))
        timeline.append(Segment(time, time + process.burst, process.pid))
        time += process.burst
    return timeline


def fcfs(processes: list[Process]) -> ScheduleResult:
    _validate(processes)
    return _result(processes, "First Come, First Served (FCFS)", _non_preemptive(processes, lambda p: (p.arrival,)))


def sjf_non_preemptive(processes: list[Process]) -> ScheduleResult:
    _validate(processes)
    return _result(processes, "Shortest Job First (non-preemptive)", _non_preemptive(processes, lambda p: (p.burst, p.arrival)))


def _preemptive(processes: list[Process], key: Callable[[Process, dict], tuple]) -> list[Segment]:
    """Run the best-ranked ready process until it finishes or the next arrival, then choose again."""
    remaining = {p.pid: p.burst for p in processes}
    order = {p.pid: i for i, p in enumerate(processes)}
    timeline: list[Segment] = []
    time = 0
    while any(value > 0 for value in remaining.values()):
        ready = [p for p in processes if p.arrival <= time and remaining[p.pid] > 0]
        if not ready:
            next_time = min(p.arrival for p in processes if remaining[p.pid] > 0)
            timeline.append(Segment(time, next_time, None))
            time = next_time
            continue
        current = min(ready, key=lambda p: (*key(p, remaining), order[p.pid]))
        later = [p.arrival for p in processes if p.arrival > time]
        step = min(remaining[current.pid], min(later) - time) if later else remaining[current.pid]
        timeline.append(Segment(time, time + step, current.pid))
        remaining[current.pid] -= step
        time += step
    return timeline


def shortest_remaining_time_first(processes: list[Process]) -> ScheduleResult:
    """Preemptive SJF: run the ready process with the least remaining CPU time."""
    _validate(processes)
    return _result(processes, "Shortest Remaining Time First (SRTF; preemptive)",
                   _preemptive(processes, lambda p, remaining: (remaining[p.pid], p.arrival)))


def priority_non_preemptive(processes: list[Process]) -> ScheduleResult:
    _validate(processes)
    return _result(processes, "Priority (non-preemptive; higher value is higher)", _non_preemptive(processes, lambda p: (-p.priority, p.arrival)))


def priority_preemptive(processes: list[Process]) -> ScheduleResult:
    _validate(processes)
    return _result(processes, "Priority (preemptive; higher value is higher)",
                   _preemptive(processes, lambda p, remaining: (-p.priority, p.arrival)))


def round_robin(processes: list[Process], quantum: int) -> ScheduleResult:
    _validate(processes)
    require_positive(quantum, "Time quantum")
    arrivals = sorted(enumerate(processes), key=lambda pair: (pair[1].arrival, pair[0]))
    remaining = {p.pid: p.burst for p in processes}
    ready: deque[Process] = deque()
    timeline: list[Segment] = []
    time = 0
    index = 0
    while index < len(arrivals) or ready:
        while index < len(arrivals) and arrivals[index][1].arrival <= time:
            ready.append(arrivals[index][1])
            index += 1
        if not ready:
            next_time = arrivals[index][1].arrival
            timeline.append(Segment(time, next_time, None))
            time = next_time
            continue
        process = ready.popleft()
        run_for = min(quantum, remaining[process.pid])
        end = time + run_for
        timeline.append(Segment(time, end, process.pid))
        while index < len(arrivals) and arrivals[index][1].arrival <= end:
            ready.append(arrivals[index][1])
            index += 1
        remaining[process.pid] -= run_for
        time = end
        if remaining[process.pid] > 0:
            ready.append(process)
    return _result(processes, f"Round Robin (quantum = {_n(quantum)})", timeline)


def run(algorithm: str, processes: list[Process], quantum: int = 2) -> ScheduleResult:
    choices = {
        "FCFS": fcfs,
        "SJF (non-preemptive)": sjf_non_preemptive,
        "SRTF (preemptive)": shortest_remaining_time_first,
        "Priority (non-preemptive)": priority_non_preemptive,
        "Priority (preemptive)": priority_preemptive,
        "Round Robin": lambda items: round_robin(items, quantum),
    }
    try:
        return choices[algorithm](processes)
    except KeyError as exc:
        raise ValueError(f"Unknown scheduling algorithm: {algorithm}") from exc
