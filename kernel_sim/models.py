"""Shared data models used by the simulator algorithms."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Process:
    pid: str
    arrival: float  # int, float or Fraction (the GUI passes exact Fractions for decimal input)
    burst: float
    priority: int = 0


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    pid: str | None


@dataclass(frozen=True)
class ScheduleRow:
    pid: str
    arrival: int
    burst: int
    priority: int
    completion: int
    turnaround: int
    waiting: int
    response: int


@dataclass(frozen=True)
class ScheduleResult:
    algorithm: str
    rows: tuple[ScheduleRow, ...]
    timeline: tuple[Segment, ...]
    average_waiting: float
    average_turnaround: float
    average_response: float
    makespan: int
    cpu_utilization: float
