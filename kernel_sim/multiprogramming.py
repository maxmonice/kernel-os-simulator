"""Equal-share (processor-sharing) CPU simulation: every active job gets 1/n of one CPU."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .validation import require_non_negative, require_positive, require_unique


@dataclass(frozen=True)
class Job:
    pid: str
    arrival: float
    burst: float


@dataclass(frozen=True)
class Event:
    time: float
    event: str                              # "<pid> arrives" or "<pid> completes"
    active: tuple[tuple[str, float], ...]   # (pid, remaining) of the jobs sharing the CPU after the event


def _nearly_equal(a: float, b: float) -> bool:
    if math.isinf(a) or math.isinf(b):
        return False
    return abs(a - b) <= 4 * max(math.ulp(a), math.ulp(b))


def simulate(jobs: list[Job]) -> tuple[Event, ...]:
    if not jobs:
        raise ValueError("Enter at least one job.")
    require_unique((j.pid for j in jobs), "Job ID")
    for j in jobs:
        if not j.pid.strip():
            raise ValueError("Job IDs cannot be blank.")
        require_non_negative(j.arrival, f"Arrival time for {j.pid}")
        require_positive(j.burst, f"Burst time for {j.pid}")

    waiting = sorted(enumerate(jobs), key=lambda item: (item[1].arrival, item[0]))
    waiting = [j for _, j in waiting]
    remaining = {j.pid: j.burst for j in jobs}
    active: list[Job] = []
    events: list[Event] = []
    nxt = 0
    time = waiting[0].arrival

    def log(text: str) -> None:
        events.append(Event(time, text, tuple((j.pid, remaining[j.pid]) for j in active)))

    while nxt < len(waiting) or active:
        least = min((remaining[j.pid] for j in active), default=math.inf)
        next_completion = time + least * len(active) if active else math.inf
        next_arrival = waiting[nxt].arrival if nxt < len(waiting) else math.inf
        simultaneous = _nearly_equal(next_arrival, next_completion)
        completion_due = next_completion < next_arrival or simultaneous
        event_time = next_arrival if simultaneous else min(next_arrival, next_completion)

        if active:
            share = (event_time - time) / len(active)
            for j in active:
                remaining[j.pid] = 0.0 if completion_due and remaining[j.pid] == least else max(0.0, remaining[j.pid] - share)
        time = event_time

        done = [j for j in active if remaining[j.pid] <= 0]
        active = [j for j in active if remaining[j.pid] > 0]
        for j in done:
            log(f"{j.pid} completes")
        while nxt < len(waiting) and waiting[nxt].arrival == time:
            active.append(waiting[nxt])
            nxt += 1
            log(f"{active[-1].pid} arrives")
    return tuple(events)
