"""Qt (PySide6) interface for the KERNEL OS Simulator."""

from __future__ import annotations

import csv
import io
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Callable

from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QFontDatabase, QKeySequence, QLinearGradient, QPainter, QPen,
                           QPixmap, QShortcut, QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QFrame, QGraphicsOpacityEffect,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
                               QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from . import banker, disk_scheduling, fragmentation, multiprogramming, page_replacement, paging, scheduling, segmentation
from .models import Process

FG = "#f2f3f5"
MUTED = "#8b919b"
ACCENT = "#0a84ff"
GREEN = "#32d74b"
RED = "#ff6961"
BLUE = "#64a8ff"
BG = "#0b0c0f"
SIDEBAR = "#111317"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    default: str
    multiline: bool = False
    height: int = 6
    hint: str = ""   # dropdown choices, separated by "·"
    help: str = ""   # plain-language explanation shown under the label


@dataclass(frozen=True)
class ModuleSpec:
    title: str
    subtitle: str
    fields: tuple[FieldSpec, ...]
    run: Callable[[dict[str, str]], str]


def _int(value: str, label: str) -> int:
    try:
        return int(value.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a whole number.") from exc


_TIME_VALUE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(hr/s|hrs?/s|hours?|hrs?|min/s|mins?/s|minutes?|mins?)?\s*$",
    re.IGNORECASE,
)


def _time_value(value: str, label: str) -> tuple[int, bool]:
    """Parse a time as minutes when it has an hr/min suffix; bare values stay unitless."""
    match = _TIME_VALUE.fullmatch(value)
    if not match:
        raise ValueError(f"{label} must be a number, optionally followed by hr/s or min/s (for example, 2 hr/s or 30 min/s).")
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    explicit = bool(unit)
    if unit.startswith("hr") or unit.startswith("hour"):
        number *= 60
    if not number.is_integer():
        raise ValueError(f"{label} must resolve to a whole number of minutes.")
    return int(number), explicit


def _time_label(has_units: bool) -> str:
    return "minutes (unitless values treated as minutes)" if has_units else "time units"


def _scheduling_inputs(data: dict[str, str]) -> tuple[list[Process], int, bool]:
    rows = _rows(data["processes"], "Processes", 4)
    parsed_rows = []
    has_units = False
    for row in rows:
        arrival, arrival_unit = _time_value(row[1], f"Arrival time for {row[0]}")
        burst, burst_unit = _time_value(row[2], f"Burst time for {row[0]}")
        has_units |= arrival_unit or burst_unit
        parsed_rows.append((row[0], arrival, burst, _int(row[3], f"Priority for {row[0]}")))
    quantum, quantum_unit = _time_value(data["quantum"], "Time quantum")
    has_units |= quantum_unit
    processes = [Process(pid, arrival, burst, priority) for pid, arrival, burst, priority in parsed_rows]
    return processes, quantum, has_units


def _rows(value: str, label: str, columns: int | None = None) -> list[list[str]]:
    parsed: list[list[str]] = []
    try:
        for row in csv.reader(io.StringIO(value)):
            if not row or not any(cell.strip() for cell in row):
                continue
            cleaned = [cell.strip() for cell in row]
            if columns is not None and len(cleaned) != columns:
                raise ValueError(f"{label}: each row needs exactly {columns} comma-separated values.")
            parsed.append(cleaned)
    except csv.Error as exc:
        raise ValueError(f"{label} contains invalid CSV formatting.") from exc
    return parsed


def _number_rows(value: str, label: str, columns: int | None = None) -> list[list[int]]:
    return [[_int(v, label) for v in row] for row in _rows(value, label, columns)]


def _format_table(headers: list[str], rows: list[list[object]]) -> str:
    values = [[str(value) for value in headers], *[[str(value) for value in row] for row in rows]]
    if not values:
        return ""
    widths = [max(len(row[i]) for row in values) for i in range(len(headers))]
    divider = "-+-".join("-" * width for width in widths)
    lines = [" | ".join(value.ljust(widths[i]) for i, value in enumerate(values[0])), divider]
    lines.extend(" | ".join(value.ljust(widths[i]) for i, value in enumerate(row)) for row in values[1:])
    return "\n".join(lines)


def _vector(values: tuple[int, ...] | list[int]) -> str:
    return "[" + ", ".join(map(str, values)) + "]"


def _run_scheduling(data: dict[str, str]) -> str:
    processes, quantum, has_units = _scheduling_inputs(data)
    result = scheduling.run(data["algorithm"], processes, quantum)
    lines = [result.algorithm, f"Time unit: {_time_label(has_units)}.",
             "Priority convention: lower number means higher priority.", "",
             _format_table(["Process", "AT", "BT", "Priority", "CT", "TAT", "WT", "RT"],
                           [[r.pid, r.arrival, r.burst, r.priority, r.completion, r.turnaround, r.waiting, r.response] for r in result.rows]), "",
             "GANTT CHART · see time-scaled blocks below"]
    lines.extend(["", f"Average waiting time:    {result.average_waiting:.2f}",
                  f"Average turnaround time: {result.average_turnaround:.2f}",
                  f"Average response time:   {result.average_response:.2f}",
                  f"CPU utilization:         {result.cpu_utilization:.2f}%",
                  f"Total elapsed time:      {result.makespan}"])
    return "\n".join(lines)


def _run_banker(data: dict[str, str]) -> str:
    ids = [cell.strip() for cell in data["process_ids"].split(",") if cell.strip()]
    total = [_int(cell, "Total resource count") for cell in data["total"].split(",") if cell.strip()]
    allocation = _number_rows(data["allocation"], "Allocation matrix", len(total))
    maximum = _number_rows(data["maximum"], "Maximum matrix", len(total))
    request_pid = data["request_pid"].strip()
    request_values = data["request"].strip()
    if bool(request_pid) != bool(request_values):
        raise ValueError("Enter both a request process ID and its resource vector, or leave both blank.")
    request_status = ""
    trace = ()
    if request_pid:
        request = [_int(cell, "Requested resource count") for cell in request_values.split(",") if cell.strip()]
        evaluated = banker.request_resources(ids, allocation, maximum, total, request_pid, request)
        result = evaluated.safety
        request_status = evaluated.message
        trace = evaluated.trace
    else:
        result = banker.check_safety(ids, allocation, maximum, total)
        trace = result.trace
    resources = [f"R{i + 1}" for i in range(len(total))]
    rows = [[pid, *result.need[i]] for i, pid in enumerate(ids)]
    status = "SAFE STATE" if result.safe else "UNSAFE STATE"
    sequence = " → ".join(result.safe_sequence) if result.safe else "No complete safe sequence exists."
    blocked = f"\nProcesses that could not finish: {', '.join(result.blocked)}" if result.blocked else ""
    heading = f"BANKER'S ALGORITHM — {status}"
    if request_pid:
        heading = f"{request_status}\n\n{heading} ({'state after request' if request_status.startswith('REQUEST GRANTED') else 'unchanged current state'})"
    return (heading + f"\n\nTotal resources:     {_vector(total)}"
            f"\nAvailable resources: {_vector(result.available)}\n\nNEED MATRIX\n"
            + _format_table(["Process", *resources], rows)
            + f"\n\nSafe sequence: {sequence}{blocked}"
            + "\n\n" + ("REQUEST + SAFETY TRACE" if request_pid else "SAFETY TRACE")
            + "\n" + "\n".join(trace))


def _run_paging(data: dict[str, str]) -> str:
    page_size = _int(data["page_size"], "Page size")
    table = [tuple(row) for row in _number_rows(data["page_table"], "Page table", 2)]
    result = paging.translate(page_size, table, _int(data["logical_address"], "Logical address"))
    mapping = _format_table(["Page", "Frame"], [[p, f] for p, f in table])
    return (f"PAGE TABLE\n{mapping}\n\nLogical address {result['logical_address']}"
            f" = page {result['page']} × page size {result['page_size']} + offset {result['offset']}\n"
            f"Page {result['page']} maps to frame {result['frame']}.\n"
            f"Physical address = frame × page size + offset\n"
            f"                 = {result['frame']} × {result['page_size']} + {result['offset']}\n"
            f"                 = {result['physical_address']}")


def _run_page_replacement(data: dict[str, str]) -> str:
    refs = [_int(x, "Page reference") for x in data["references"].replace("\n", ",").split(",") if x.strip()]
    result = page_replacement.simulate(refs, _int(data["frames"], "Frame count"), data["algorithm"])
    headers = ["Step", "Reference", *[f"Frame {i + 1}" for i in range(_int(data["frames"], "Frame count"))], "Result", "Replaced"]
    rows = [[s.index, s.page, *["—" if f is None else f for f in s.frames], s.result,
             "—" if s.replaced is None else s.replaced] for s in result.steps]
    return (f"{result.algorithm} · {len(result.steps)} references\n\n"
            + _format_table(headers, rows)
            + f"\n\nHits: {result.hits}    Page faults: {result.faults}    Fault rate: {result.fault_rate:.1%}")


def _run_segmentation(data: dict[str, str]) -> str:
    segments = [tuple(row) for row in _number_rows(data["segments"], "Segment table", 3)]
    result = segmentation.translate(segments, _int(data["segment"], "Segment number"), _int(data["offset"], "Offset"))
    table = _format_table(["Segment", "Base", "Limit"], [[n, base, limit] for n, base, limit in segments])
    return (f"SEGMENT TABLE\n{table}\n\nLogical address = (segment {result['segment']}, offset {result['offset']})\n"
            f"Bounds check: {result['offset']} < {result['limit']} ✓\n"
            f"Physical address = base + offset = {result['base']} + {result['offset']} = {result['physical_address']}")


def _run_fragmentation(data: dict[str, str]) -> str:
    blocks = [_int(x, "Block size") for x in data["blocks"].replace("\n", ",").split(",") if x.strip()]
    processes = [(row[0], _int(row[1], "Process size")) for row in _rows(data["processes"], "Processes", 2)]
    result = fragmentation.allocate(blocks, processes, data["mode"], data["strategy"])
    rows = [[a.process_id, a.process_size, a.block_index, a.block_size,
             a.internal_waste if result.mode == "Fixed partitions" else 0] for a in result.allocations]
    lines = [f"{result.mode} · {result.strategy}", "",
             _format_table(["Process", "Requested", "Block", "Block size", "Internal waste"], rows)]
    lines.append("\nUnallocated: " + (", ".join(result.unallocated) if result.unallocated else "none"))
    if result.mode == "Fixed partitions":
        lines.append(f"Total internal fragmentation: {result.internal_fragmentation}")
    else:
        lines.extend([f"Remaining free holes: {_vector(result.free_blocks)}",
                      f"Total free memory: {result.total_free}", f"Largest contiguous hole: {result.largest_hole}",
                      f"External fragmentation (free space outside largest hole): {result.external_fragmentation}"])
    return "\n".join(lines)


def _run_disk(data: dict[str, str]) -> str:
    requests = [_int(x, "Disk request") for x in data["requests"].replace("\n", ",").split(",") if x.strip()]
    result = disk_scheduling.schedule(requests, _int(data["head"], "Head position"), data["algorithm"],
                                     _int(data["low"], "Lower cylinder"), _int(data["high"], "Upper cylinder"), data["direction"])
    legs = " → ".join(map(str, result.path))
    movements = " + ".join(str(abs(result.path[i] - result.path[i - 1])) for i in range(1, len(result.path)))
    return (f"{result.algorithm} · direction {data['direction']}\n\nService order: "
            + " → ".join(map(str, result.service_order))
            + f"\nHead path: {legs}\n\nMovement: {movements} = {result.total_movement} cylinders")


def _run_multiprogramming(data: dict[str, str]) -> str:
    rows = _rows(data["programs"], "Programs", 4)
    parsed_rows = []
    has_units = False
    for row in rows:
        arrival, arrival_unit = _time_value(row[1], f"Arrival time for {row[0]}")
        burst, burst_unit = _time_value(row[2], f"CPU burst for {row[0]}")
        has_units |= arrival_unit or burst_unit
        parsed_rows.append((row[0], arrival, burst, _int(row[3], "Memory requirement")))
    quantum, quantum_unit = _time_value(data["quantum"], "Time quantum")
    has_units |= quantum_unit
    programs = [multiprogramming.Program(*row) for row in parsed_rows]
    result = multiprogramming.simulate(programs, _int(data["memory"], "Memory capacity"), quantum)
    rows = [[p.pid, p.arrival, p.cpu_burst, p.memory_mb] for p in programs]
    states = [[p.pid, p.state, p.memory_mb, p.completion if p.completion is not None else "—",
               p.waiting if p.waiting is not None else "—"] for p in result.summaries]
    timeline = "  ".join(f"{start}–{end}: {pid}" for start, end, pid in result.timeline)
    return ("ROUND-ROBIN MULTIPROGRAMMING SIMULATION\n"
            + f"Time unit: {_time_label(has_units)}.\n\nINPUT PROGRAMS\n"
            + _format_table(["Program", "Arrival", "CPU burst", "Memory MB"], rows)
            + "\n\nFINAL STATUS\n"
            + _format_table(["Program", "State", "Memory MB", "Completion", "Waiting"], states)
            + f"\n\nCPU timeline: {timeline}"
            + f"\nPeak memory use: {result.memory_utilization_peak:.1f}% of {data['memory']} MB"
            + f"\nCPU utilization: {result.cpu_utilization:.1f}%"
            + f"\nThroughput: {result.throughput:.3f} completed programs per time unit"
            + f"\nContext switches: {result.context_switches}"
            + f"\nElapsed time: {result.elapsed}")


MODULES: dict[str, ModuleSpec] = {
    "CPU Scheduling": ModuleSpec(
        "CPU Scheduling",
        "Use plain numbers or suffix times with hr/s or min/s. Bare values mean minutes when any suffix is used.",
        (
            FieldSpec("algorithm", "Algorithm", "FCFS",
                      hint="FCFS · SJF (non-preemptive) · SRTF (preemptive) · Priority (non-preemptive) · Priority (preemptive) · Round Robin"),
            FieldSpec("quantum", "Time quantum (Round Robin)", "2"),
            FieldSpec("processes", "Processes", "P1,0,4,2\nP2,1,2,1\nP3,2,3,3\nP4,3,5,2\nP5,4,6,1\nP6,5,1,2",
                      True, 8,
                      help="One per line: ID, arrival, burst, priority. Example times: 1 hr/s, 30 min/s."),
        ),
        _run_scheduling,
    ),
    "Banker's Algorithm": ModuleSpec(
        "Banker's Algorithm",
        "Check whether the current allocation has a safe completion sequence.",
        (
            FieldSpec("process_ids", "Process IDs (comma-separated)", "P0,P1,P2,P3,P4"),
            FieldSpec("total", "Total resources (one per type)", "10,5,7"),
            FieldSpec("allocation", "Allocation matrix", "0,1,0\n2,0,0\n3,0,2\n2,1,1\n0,0,2", True, 6,
                      help="One row per process; one value per resource."),
            FieldSpec("maximum", "Maximum demand matrix", "7,5,3\n3,2,2\n9,0,2\n2,2,2\n4,3,3", True, 6,
                      help="Use the same process and resource order as Allocation."),
            FieldSpec("request_pid", "Optional request process ID", "", help="Leave blank to run only the safety check."),
            FieldSpec("request", "Optional resource request", "", help="Comma-separated amount per resource, e.g. 1,0,2."),
        ),
        _run_banker,
    ),
    "Paging": ModuleSpec(
        "Paging",
        "Map logical pages to physical frames and translate a logical address.",
        (
            FieldSpec("page_size", "Page size", "4"),
            FieldSpec("logical_address", "Logical address", "3"),
            FieldSpec("page_table", "Page table", "0,5\n1,6\n2,3\n3,2", True, 7,
                      help="One mapping per line: page, frame."),
        ),
        _run_paging,
    ),
    "Page Replacement": ModuleSpec(
        "Page Replacement",
        "Follow each page reference through memory frames and compare hits with faults.",
        (
            FieldSpec("algorithm", "Algorithm", "FIFO", hint="FIFO · LRU · Optimal"),
            FieldSpec("frames", "Number of frames", "3"),
            FieldSpec("references", "Page reference string", "7,0,1,2,0,3,0,4,2,3,0,3,2", True, 7,
                      help="Comma-separated or one page per line."),
        ),
        _run_page_replacement,
    ),
    "Segmentation": ModuleSpec(
        "Segmentation",
        "Validate a segment and offset against its base and limit.",
        (
            FieldSpec("segment", "Segment number", "1"),
            FieldSpec("offset", "Offset within segment", "399"),
            FieldSpec("segments", "Segment table", "0,1400,1000\n1,6300,400\n2,4300,400\n3,3200,1100\n4,4700,1000", True, 7,
                      help="One per line: segment, base, limit."),
        ),
        _run_segmentation,
    ),
    "Fragmentation": ModuleSpec(
        "Fragmentation",
        "Allocate processes into memory and inspect the space that remains unused.",
        (
            FieldSpec("mode", "Partition mode", "Variable partitions", hint="Fixed partitions · Variable partitions"),
            FieldSpec("strategy", "Allocation strategy", "First fit", hint="First fit · Best fit · Next fit · Worst fit"),
            FieldSpec("blocks", "Memory blocks (comma-separated)", "100,500,200,300,600"),
            FieldSpec("processes", "Processes", "P1,212\nP2,417\nP3,112\nP4,426", True, 7,
                      help="One per line: ID, size."),
        ),
        _run_fragmentation,
    ),
    "Disk Scheduling": ModuleSpec(
        "Disk Scheduling",
        "Compare head movement for common disk request ordering algorithms.",
        (
            FieldSpec("algorithm", "Algorithm", "SCAN", hint="FCFS · SSTF · SCAN · C-SCAN · LOOK · C-LOOK"),
            FieldSpec("direction", "Initial direction", "Right", hint="Left · Right"),
            FieldSpec("head", "Starting head position", "53"),
            FieldSpec("low", "Lowest cylinder", "0"),
            FieldSpec("high", "Highest cylinder", "199"),
            FieldSpec("requests", "Requests", "98,183,37,122,14,124,65,67", True, 7,
                      help="Comma-separated or one cylinder per line."),
        ),
        _run_disk,
    ),
    "Multiprogramming": ModuleSpec(
        "Multiprogramming",
        "Share CPU time and memory. Suffix times with hr/s or min/s; bare values mean minutes when units are used.",
        (
            FieldSpec("memory", "Available memory (MB)", "1024"),
            FieldSpec("quantum", "CPU time slice", "2"),
            FieldSpec("programs", "Programs", "A,0,5,400\nB,1,3,300\nC,2,4,500\nD,3,2,256", True, 8,
                      help="One per line: ID, arrival, CPU burst, memory (MB). Example times: 1 hr/s, 30 min/s."),
        ),
        _run_multiprogramming,
    ),
}



PROCESS_COLORS = ("#0a84ff", "#30b0a0", "#bf5af2", "#ff9f0a", "#32d74b", "#ff6482", "#64d2ff")

# Real backdrop blur needs Windows 11 22H2+ (DWM system backdrop). Elsewhere the UI stays opaque.
GLASS = sys.platform == "win32" and sys.getwindowsversion().build >= 22621
UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"

_QSS = Template("""
* { font-family: "$ui"; font-size: 13px; color: $fg; }
#root { background: transparent; }
#sidebar { background: $sidebar_bg; border-right: 1px solid rgba(255,255,255,0.07); }
#content { background: $content_bg; }
QLabel { background: transparent; }
QLabel#title { font-size: 28px; font-weight: 600; }
QLabel#brand { font-size: 14px; font-weight: 600; }
QLabel#subtitle { color: $muted; }
QLabel#section { font-size: 14px; font-weight: 600; }
QLabel#cardtitle { font-size: 14px; font-weight: 600; }
QLabel#field { font-size: 12px; font-weight: 600; }
QLabel#hint, QLabel#side { color: $muted; font-size: 11px; }
QLineEdit, QPlainTextEdit, QComboBox {
    background: rgba(0,0,0,0.30); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 7px; padding: 6px 9px; selection-background-color: $sel; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QComboBox:on { border: 1px solid $accent; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url($chevron); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: #1d2026; border: 1px solid rgba(255,255,255,0.10);
    selection-background-color: $accent; selection-color: white; outline: 0; padding: 4px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle { background: rgba(255,255,255,0.16); border-radius: 3px; min-height: 30px; min-width: 30px; }
QScrollBar::handle:hover { background: rgba(255,255,255,0.30); }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QSplitter::handle { background: transparent; }
""")


def _color(value: str | QColor, alpha: float = 1.0) -> QColor:
    c = QColor(value)
    c.setAlphaF(alpha)
    return c


def _mix(a: str | QColor, b: str | QColor, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(*(round(x + (y - x) * t) for x, y in
                    ((ca.red(), cb.red()), (ca.green(), cb.green()), (ca.blue(), cb.blue()))))


def _animate(anim: QPropertyAnimation, target: float, ms: int = 150) -> None:
    """Retarget from the current value, so rapid hover in/out never snaps (interruptible)."""
    anim.stop()
    anim.setDuration(ms)
    anim.setEasingCurve(QEasingCurve.Type.OutQuart)
    anim.setEndValue(target)
    anim.start()


class GlassButton(QAbstractButton):
    """accent | quiet | nav. Colour eases on hover, presses to 0.97 scale, shows a ring on Tab focus."""

    def __init__(self, text: str, kind: str = "quiet", parent: QWidget | None = None):
        super().__init__(parent)
        self.kind, self._hover, self._sel = kind, 0.0, 0.0
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._hover_anim = QPropertyAnimation(self, b"hover", self)
        self._sel_anim = QPropertyAnimation(self, b"sel", self)
        if kind == "nav":
            self.setCheckable(True)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.toggled.connect(lambda on: _animate(self._sel_anim, 1.0 if on else 0.0, 200))

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    def _get_sel(self) -> float:
        return self._sel

    def _set_sel(self, v: float) -> None:
        self._sel = v
        self.update()

    hover = Property(float, _get_hover, _set_hover)
    sel = Property(float, _get_sel, _set_sel)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        width = fm.horizontalAdvance(self.text()) + (24 if self.kind == "nav" else 32)
        return QSize(width, 34 if self.kind == "nav" else 34)

    def enterEvent(self, event) -> None:  # noqa: N802
        _animate(self._hover_anim, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        _animate(self._hover_anim, 0.0, 220)
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isDown() and self.kind != "nav":
            c = rect.center()
            p.translate(c)
            p.scale(0.97, 0.97)
            p.translate(-c)
        h, s = self._hover, self._sel
        radius = 8.0
        font = QFont(self.font())
        text_color: QColor
        if self.kind == "accent":
            fill = _mix(ACCENT, "#4aa3ff", h)
            text_color = QColor("white")
            font.setWeight(QFont.Weight.DemiBold)
            p.setBrush(fill)
            p.setPen(Qt.PenStyle.NoPen)
        elif self.kind == "quiet":
            p.setBrush(_color("white", 0.07 + 0.05 * h))
            p.setPen(QPen(_color("white", 0.09), 1))
            text_color = QColor(FG)
        else:
            p.setBrush(_color("white", 0.10 * s + 0.05 * h * (1 - s)))
            p.setPen(Qt.PenStyle.NoPen)
            text_color = _mix(MUTED, FG, max(s, 0.6 * h))
            if s > 0.5:
                font.setWeight(QFont.Weight.DemiBold)
        p.drawRoundedRect(rect, radius, radius)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_color(ACCENT, 0.9), 2))
            p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), radius + 1, radius + 1)
        p.setFont(font)
        p.setPen(text_color)
        align = Qt.AlignmentFlag.AlignVCenter | (
            Qt.AlignmentFlag.AlignLeft if self.kind == "nav" else Qt.AlignmentFlag.AlignHCenter)
        p.drawText(rect.adjusted(12, 0, -12, 0), align, self.text())


class Panel(QFrame):
    """Glass surface: faint white fill, hairline border, and a top edge that catches light."""

    def __init__(self, hoverable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._hover, self._hoverable = 0.0, hoverable
        self._anim = QPropertyAnimation(self, b"hover", self)

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    hover = Property(float, _get_hover, _set_hover)

    def enterEvent(self, event) -> None:  # noqa: N802
        if self._hoverable:
            _animate(self._anim, 1.0, 180)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hoverable:
            _animate(self._anim, 0.0, 240)
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(_color("white", 0.040 + 0.020 * self._hover))
        p.setPen(QPen(_color("white", 0.085 + 0.06 * self._hover), 1))
        p.drawRoundedRect(rect, 10, 10)
        edge = QLinearGradient(rect.left(), 0, rect.right(), 0)
        edge.setColorAt(0.0, _color("white", 0.0))
        edge.setColorAt(0.5, _color("white", 0.16))
        edge.setColorAt(1.0, _color("white", 0.0))
        p.setPen(QPen(edge, 1))
        p.drawLine(QPointF(rect.left() + 10, rect.top()), QPointF(rect.right() - 10, rect.top()))


def _label(text: str, name: str, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _fade_in(widget: QWidget, ms: int = 200, start: float = 0.0) -> None:
    """Brief opacity ramp; the effect is removed afterwards so text stays crisp and scrolling stays cheap."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ms)
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutQuart)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class GanttView(QWidget):
    """Time-scaled CPU timeline. Blocks wipe in left to right when a run finishes."""

    LEFT, RIGHT, TOP, BOTTOM, UNIT = 6, 20, 26, 66, 48

    def __init__(self) -> None:
        super().__init__()
        self._data: tuple | None = None
        self._reveal = 1.0
        self._anim = QPropertyAnimation(self, b"reveal", self)
        self.setFixedHeight(96)

    def _get_reveal(self) -> float:
        return self._reveal

    def _set_reveal(self, v: float) -> None:
        self._reveal = v
        self.update()

    reveal = Property(float, _get_reveal, _set_reveal)

    def clear(self) -> None:
        self._data = None
        self.setMinimumWidth(0)
        self.update()

    def set_data(self, timeline, colors: dict[str, str], makespan: int, axis_unit: str) -> None:
        self._data = (timeline, colors, makespan, axis_unit)
        self.setMinimumWidth(self.LEFT + max(1, makespan) * self.UNIT + self.RIGHT)
        self._reveal = 0.0
        self._anim.stop()
        self._anim.setDuration(520)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuart)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._data is None:
            return
        timeline, colors, makespan, axis_unit = self._data
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(_color(MUTED))
        small = QFont(self.font())
        small.setPixelSize(11)
        p.setFont(small)
        p.drawText(QPointF(self.LEFT, 14), f"CPU time ({axis_unit})")
        if not timeline:
            p.drawText(QPointF(self.LEFT, 48), "No scheduled intervals")
            return
        total = self.LEFT + max(1, makespan) * self.UNIT
        p.setClipRect(QRectF(0, 0, self.LEFT + (total - self.LEFT) * self._reveal + 1, self.height()))
        bold = QFont(small)
        bold.setWeight(QFont.Weight.DemiBold)
        bold.setPixelSize(12)
        for iv in timeline:
            x1, x2 = self.LEFT + iv.start * self.UNIT, self.LEFT + iv.end * self.UNIT
            box = QRectF(x1 + 1, self.TOP, x2 - x1 - 2, self.BOTTOM - self.TOP - 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_color(colors[iv.pid], 0.92) if iv.pid else _color("white", 0.07))
            p.drawRoundedRect(box, 6, 6)
            if x2 - x1 >= 32:
                p.setFont(bold)
                p.setPen(QColor("white") if iv.pid else _color(MUTED))
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, iv.pid or "IDLE")
        marks = {0, makespan, *(i.start for i in timeline), *(i.end for i in timeline)}
        mono = QFont(MONO_FONT)
        mono.setPixelSize(10)
        p.setFont(mono)
        for tick in sorted(marks):
            x = self.LEFT + tick * self.UNIT
            p.setPen(_color("white", 0.25))
            p.drawLine(QPointF(x, self.BOTTOM - 17), QPointF(x, self.BOTTOM - 12))
            p.setPen(_color(FG, 0.85))
            p.drawText(QRectF(x - 20, self.BOTTOM - 11, 40, 14), Qt.AlignmentFlag.AlignCenter, str(tick))


class OverviewPage(QScrollArea):
    """Project landing page with the team and a quick module index."""

    def __init__(self, open_module: Callable[[str], None]):
        super().__init__()
        self.setWidgetResizable(True)
        host = QWidget()
        self.setWidget(host)
        col = QVBoxLayout(host)
        col.setContentsMargins(32, 28, 32, 28)
        col.setSpacing(0)
        col.addWidget(_label("Project team", "title"))
        col.addSpacing(14)
        team = QGridLayout()
        team.setSpacing(12)
        members = (("Amiel Amido", "Group leader"), ("Kevin James Riparip", "Project team"),
                   ("Rafael Carlos III", "Project team"))
        for i, (name, role) in enumerate(members):
            card = Panel()
            lay = QVBoxLayout(card)
            lay.setContentsMargins(18, 14, 18, 14)
            lay.setSpacing(3)
            lay.addWidget(_label(name, "cardtitle"))
            lay.addWidget(_label(role, "subtitle"))
            team.addWidget(card, 0, i)
        col.addLayout(team)
        col.addSpacing(26)
        col.addWidget(_label("Modules", "title"))
        col.addSpacing(14)
        grid = QGridLayout()
        grid.setSpacing(12)
        for index, title in enumerate(MODULES):
            card = Panel(hoverable=True)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(18, 14, 18, 16)
            lay.setSpacing(4)
            lay.addWidget(_label(title, "cardtitle"))
            lay.addWidget(_label(MODULES[title].subtitle, "subtitle", True))
            lay.addSpacing(8)
            button = GlassButton("Open module")
            button.clicked.connect(lambda _=False, name=title: open_module(name))
            lay.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(card, *divmod(index, 2))
        col.addLayout(grid)
        col.addStretch(1)
        for c in (0, 1, 2):
            team.setColumnStretch(c, 1)
        for c in (0, 1):
            grid.setColumnStretch(c, 1)


class ModulePage(QWidget):
    def __init__(self, spec: ModuleSpec):
        super().__init__()
        self.spec = spec
        self.widgets: dict[str, QWidget] = {}
        self.gantt: GanttView | None = None
        self._build()

    def _build(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(32, 24, 32, 28)
        col.setSpacing(0)
        col.addWidget(_label(self.spec.title, "title"))
        col.addSpacing(4)
        col.addWidget(_label(self.spec.subtitle, "subtitle", True))
        col.addSpacing(18)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(12)
        split.setChildrenCollapsible(False)
        col.addWidget(split, 1)

        # ---- inputs
        inputs = Panel()
        left = QVBoxLayout(inputs)
        left.setContentsMargins(20, 18, 8, 18)
        left.setSpacing(0)
        left.addWidget(_label("Inputs", "section"))
        left.addSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_host = QWidget()
        form = QVBoxLayout(form_host)
        form.setContentsMargins(0, 0, 12, 0)
        form.setSpacing(14)
        mono_css = f'font-family: "{MONO_FONT}"; font-size: 13px;'  # global QSS would override setFont
        for field in self.spec.fields:
            group = QVBoxLayout()
            group.setSpacing(4)
            group.addWidget(_label(field.label, "field"))
            if field.multiline and field.help:
                group.addWidget(_label(field.help, "hint", True))
            if field.multiline:
                widget: QWidget = QPlainTextEdit(field.default)
                widget.setStyleSheet(mono_css)
                widget.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
                widget.setTabChangesFocus(True)  # Tab moves between fields instead of typing a tab
                widget.setFixedHeight(round(QFontMetrics(QFont(MONO_FONT, 10)).lineSpacing() * field.height) + 24)
            elif field.hint:
                widget = QComboBox()
                widget.addItems([item.strip() for item in field.hint.split("·")])
                widget.setCurrentText(field.default)
            else:
                widget = QLineEdit(field.default)
            group.addWidget(widget)
            self.widgets[field.key] = widget
            form.addLayout(group)
        form.addStretch(1)
        scroll.setWidget(form_host)
        left.addWidget(scroll, 1)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet("background: rgba(255,255,255,0.08);")
        left.addSpacing(10)
        left.addWidget(rule)
        left.addSpacing(12)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 12, 0)
        run = GlassButton("Run simulation", "accent")
        run.clicked.connect(self.run_simulation)
        example = GlassButton("Load example")
        example.clicked.connect(self.reset_sample)
        actions.addWidget(run)
        actions.addWidget(example)
        actions.addStretch(1)
        left.addLayout(actions)
        left.addSpacing(10)
        self.status = _label("Ready · input is checked when you run", "hint", True)
        left.addWidget(self.status)

        # ---- output
        outputs = Panel()
        right = QVBoxLayout(outputs)
        right.setContentsMargins(20, 18, 20, 18)
        right.setSpacing(0)
        right.addWidget(_label("Output", "section"))
        right.addSpacing(10)
        if self.spec.title == "CPU Scheduling":
            right.addWidget(_label("Gantt chart", "hint"))
            right.addSpacing(4)
            self.gantt = GanttView()
            strip = QScrollArea()
            strip.setWidget(self.gantt)
            strip.setWidgetResizable(True)
            strip.setFixedHeight(self.gantt.height() + 14)
            strip.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            right.addWidget(strip)
            right.addSpacing(12)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(mono_css)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        right.addWidget(self.output, 1)
        self._write_output("Choose or edit the inputs, then run the simulation.\n\n"
                           "Add as many input rows as you need.")

        split.addWidget(inputs)
        split.addWidget(outputs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([470, 760])

    # ----- actions ----------------------------------------------------------
    def read_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for field in self.spec.fields:
            w = self.widgets[field.key]
            if isinstance(w, QPlainTextEdit):
                values[field.key] = w.toPlainText().strip()
            elif isinstance(w, QComboBox):
                values[field.key] = w.currentText().strip()
            else:
                values[field.key] = w.text().strip()  # type: ignore[attr-defined]
        return values

    def _set_status(self, text: str, color: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};")

    def run_simulation(self) -> None:
        try:
            result = self.spec.run(self.read_values())
        except ValueError as exc:
            message = str(exc)
        except (KeyError, IndexError):
            message = "A row is missing a value or has an extra one. Check that every line follows the format shown above its box."
        except Exception as exc:  # keep the window alive whatever the input is
            message = f"Something unexpected happened while running: {exc}"
        else:
            self._write_output(result)
            if self.gantt is not None:
                try:
                    self._draw_gantt(self.read_values())
                except (ValueError, KeyError, IndexError):
                    self.gantt.clear()
            self._set_status("Simulation complete", GREEN)
            return
        if self.gantt is not None:
            self.gantt.clear()
        self._write_output(f"INPUT NEEDS ATTENTION\n\n{message}\n\nCorrect the inputs and try again.", "error")
        self._set_status("Could not run · check the input", RED)

    def reset_sample(self) -> None:
        for field in self.spec.fields:
            w = self.widgets[field.key]
            if isinstance(w, QPlainTextEdit):
                w.setPlainText(field.default)
            elif isinstance(w, QComboBox):
                w.setCurrentText(field.default)
            else:
                w.setText(field.default)  # type: ignore[attr-defined]
        self._set_status("Example inputs restored", MUTED)
        if self.gantt is not None:
            self.gantt.clear()
        self._write_output("Example inputs restored. Press Run simulation to view the results.")

    def _draw_gantt(self, data: dict[str, str]) -> None:
        assert self.gantt is not None
        processes, quantum, has_units = _scheduling_inputs(data)
        result = scheduling.run(data["algorithm"], processes, quantum)
        colors = {pr.pid: PROCESS_COLORS[i % len(PROCESS_COLORS)] for i, pr in enumerate(processes)}
        self.gantt.set_data(result.timeline, colors, result.makespan, "minutes" if has_units else "time units")

    def _write_output(self, content: str, tag: str | None = None) -> None:
        self.output.clear()
        cursor = self.output.textCursor()
        for number, line in enumerate(content.split("\n")):
            fmt = QTextCharFormat()
            text = line.strip()
            kind = tag
            if kind is None and text:
                if "UNSAFE STATE" in text:
                    kind = "bad"
                elif "SAFE STATE" in text:
                    kind = "good"
                elif text.isupper() and not any(ch.isdigit() or ch == "|" for ch in text):
                    kind = "heading"
            if kind:
                fmt.setForeground(QColor({"error": RED, "bad": RED, "good": GREEN, "heading": BLUE}[kind]))
                if kind != "error":
                    fmt.setFontWeight(QFont.Weight.Bold)
            if number:
                cursor.insertBlock()
            cursor.insertText(line, fmt)
        self.output.moveCursor(QTextCursor.MoveOperation.Start)
        _fade_in(self.output, 220, 0.3)


class KernelApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KERNEL · Operating System Simulator")
        screen = QApplication.primaryScreen().availableGeometry()
        width, height = min(1440, screen.width() - 40), min(920, screen.height() - 40)
        self.resize(width, height)
        self.move(screen.x() + (screen.width() - width) // 2, screen.y() + (screen.height() - height) // 2)
        self.setMinimumSize(min(1100, width), min(640, height))
        if GLASS:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.order = ["Overview", *MODULES]
        self.current = "Overview"
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, GlassButton] = {}
        self._build_shell()
        for keys in ("Ctrl+Return", "Ctrl+Enter", "F5"):
            QShortcut(QKeySequence(keys), self, self._run_current_simulation)
        self.show_module("Overview", animate=False)

    def _build_shell(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 18, 12, 18)
        side.setSpacing(2)
        side.addWidget(_label("Project", "side"))
        side.addSpacing(4)
        for title in self.order:
            button = GlassButton(title, "nav")
            button.setFixedHeight(34)
            button.clicked.connect(lambda _=False, name=title: self.show_module(name))
            side.addWidget(button)
            self.nav_buttons[title] = button
            if title == "Overview":
                side.addSpacing(16)
                side.addWidget(_label("Modules", "side"))
                side.addSpacing(4)
        side.addStretch(1)
        side.addWidget(_label("Add rows as needed. Inputs are checked before each run.", "side", True))
        row.addWidget(sidebar)

        content = QFrame()
        content.setObjectName("content")
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(48)
        bar = QHBoxLayout(header)
        bar.setContentsMargins(32, 0, 32, 0)
        bar.addWidget(_label("Kernel", "brand"))
        bar.addSpacing(8)
        bar.addWidget(_label("Operating System Simulator", "subtitle"))
        bar.addStretch(1)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {GREEN}; font-size: 9px;")
        bar.addWidget(dot)
        bar.addWidget(_label("Ready", "subtitle"))
        col.addWidget(header)
        hairline = QFrame()
        hairline.setFixedHeight(1)
        hairline.setStyleSheet("background: rgba(255,255,255,0.07);")
        col.addWidget(hairline)
        self.stack = QStackedWidget()
        col.addWidget(self.stack, 1)
        row.addWidget(content, 1)

        self.pages["Overview"] = OverviewPage(self.show_module)
        for title, spec in MODULES.items():
            self.pages[title] = ModulePage(spec)
        for page in self.pages.values():
            self.stack.addWidget(page)

    def _run_current_simulation(self) -> None:
        page = self.pages.get(self.current)
        if isinstance(page, ModulePage):
            page.run_simulation()

    def show_module(self, title: str, animate: bool = True) -> None:
        if animate and title == self.current:
            return
        self.current = title
        self.stack.setCurrentWidget(self.pages[title])
        for name, button in self.nav_buttons.items():
            button.setChecked(name == title)
        if animate:
            _fade_in(self.pages[title], 180, 0.0)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if sys.platform != "win32":
            return
        try:  # dark title bar + acrylic backdrop; the glass layers above are translucent over it
            import ctypes
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            for attr, value in ((20, 1), (38, 3)):
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(value)), 4)
            margins = (ctypes.c_int * 4)(-1, -1, -1, -1)
            dwm.DwmExtendFrameIntoClientArea(hwnd, margins)
        except Exception:
            pass


def _chevron_path() -> str:
    """Small chevron image for combo boxes (QSS can't draw one)."""
    path = Path(tempfile.gettempdir()) / "kernel_sim_chevron.png"
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(MUTED), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline([QPointF(5, 8), QPointF(10, 13), QPointF(15, 8)])
    p.end()
    pix.save(str(path))
    return path.as_posix()


def build_app() -> QApplication:
    global UI_FONT, MONO_FONT
    app = QApplication.instance() or QApplication(sys.argv)
    families = set(QFontDatabase.families())
    UI_FONT = next((f for f in ("SF Pro Text", "SF Pro Display", "Segoe UI Variable Text", "Segoe UI")
                    if f in families), app.font().family())
    MONO_FONT = next((f for f in ("SF Mono", "Cascadia Mono", "Consolas") if f in families), "Courier New")
    app.setStyle("Fusion")
    app.setStyleSheet(_QSS.substitute(
        ui=UI_FONT, fg=FG, muted=MUTED, accent=ACCENT, sel="#1c3a5e", chevron=_chevron_path(),
        sidebar_bg="rgba(16,18,22,0.52)" if GLASS else SIDEBAR,
        content_bg="rgba(10,11,14,0.82)" if GLASS else BG))
    return app


def launch() -> None:
    app = build_app()
    window = KernelApp()
    window.show()
    sys.exit(app.exec())
