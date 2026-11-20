"""Known-answer, boundary, error and large-dataset tests.

Run with a readable report (input, expected answer, actual answer, CORRECT / WRONG):
    python tests/test_algorithms.py
Plain pass/fail run:
    python -m unittest discover tests
"""
import io
import os
import random
import sys
import textwrap
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kernel_sim import (banker, disk_scheduling as disk, fragmentation as frag,
                        multiprogramming as mp, page_replacement as pr, paging,
                        scheduling as sch, segmentation as seg)
from kernel_sim.models import Process

random.seed(1)
PROCS = [Process("P1", 0, 5, 2), Process("P2", 1, 3, 1), Process("P3", 2, 8, 3), Process("P4", 3, 6, 2)]
PROCS_TXT = "P1(arr 0, burst 5, pri 2) P2(1,3,1) P3(2,8,3) P4(3,6,2); higher priority number = higher priority"

REPORT = []  # one record per check: (class, test, label, given, expected, actual, ok)


class Case(unittest.TestCase):
    """unittest base class whose checks are also recorded for the printed report."""

    def _record(self, label, given, expected, actual, ok):
        *_, cls, name = self.id().split(".")
        REPORT.append((cls, name, label, given, expected, actual, ok))

    def check(self, label, given, expected, actual):
        self._record(label, given, expected, actual, actual == expected)
        self.assertEqual(actual, expected, f"{label} | input: {given}")

    def rejects(self, label, given, fn, *args):
        """The input is invalid, so fn must raise ValueError (an error message, not a crash)."""
        try:
            fn(*args)
        except ValueError as exc:
            self._record(label, given, "ValueError (input refused)", f"ValueError: {exc}", True)
            return
        self._record(label, given, "ValueError (input refused)", "accepted the input", False)
        self.fail(f"{label} | input was accepted: {given}")


class Scheduling(Case):
    def test_known_averages(self):
        expected = {"FCFS": (5.75, 11.25), "SJF (non-preemptive)": (5.25, 10.75),
                    "SRTF (preemptive)": (5.0, 10.5), "Priority (non-preemptive)": (7.75, 13.25),
                    "Priority (preemptive)": (9.0, 14.5), "Round Robin": (9.75, 15.25)}
        for name, want in expected.items():
            r = sch.run(name, PROCS, 2)
            self.check(f"{name}: average (waiting, turnaround)", f"{PROCS_TXT}; quantum 2", want,
                       (r.average_waiting, r.average_turnaround))

    def test_idle_gap(self):
        r = sch.fcfs([Process("A", 5, 2)])
        self.check("CPU idles until the process arrives: completion time", "A(arrival 5, burst 2)", 7,
                   r.rows[0].completion)

    def test_decimal_times(self):
        dec = [Process("A", Fraction(0), Fraction(3), 1), Process("B", Fraction("0.5"), Fraction(1), 5),
               Process("C", Fraction("1.2"), Fraction("0.7"), 3)]
        given = "A(arr 0, burst 3, pri 1) B(0.5, 1, 5) C(1.2, 0.7, 3); quantum 0.5"
        for name, done in (("SRTF (preemptive)", [4.7, 1.5, 2.2]), ("Priority (preemptive)", [4.7, 1.5, 2.2]),
                           ("Round Robin", [4.7, 2, 3.2]), ("FCFS", [3, 4, 4.7])):
            r = sch.run(name, dec, Fraction("0.5"))
            self.check(f"{name}: completion times with decimal arrivals and bursts", given, done,
                       [row.completion for row in r.rows])
        r = sch.run("SRTF (preemptive)", dec)
        self.check("SRTF: B arriving at 0.5 preempts A (timeline start, end, process)", given,
                   [(0, 0.5, "A"), (0.5, 1.5, "B"), (1.5, 2.2, "C"), (2.2, 4.7, "A")],
                   [(g.start, g.end, g.pid) for g in r.timeline])
        self.check("SRTF: average waiting time", given, 0.6667, round(r.average_waiting, 4))

    def test_decimal_has_no_float_drift(self):
        # 0.1 + 0.2 is 0.30000000000000004 in float arithmetic, which would leave a fake idle gap before C.
        ps = [Process("A", Fraction(0), Fraction("0.1")), Process("B", Fraction(0), Fraction("0.2")),
              Process("C", Fraction("0.3"), Fraction("0.1"))]
        r = sch.fcfs(ps)
        self.check("FCFS: (C completion, CPU utilization)", "A(0, 0.1) B(0, 0.2) C(0.3, 0.1)", (0.4, 100.0),
                   (r.rows[2].completion, r.cpu_utilization))

    def test_errors(self):
        self.rejects("empty process list", "no processes", sch.fcfs, [])
        self.rejects("negative arrival time", "A(arrival -1, burst 2)", sch.fcfs, [Process("A", -1, 2)])
        self.rejects("zero burst time", "A(arrival 0, burst 0)", sch.fcfs, [Process("A", 0, 0)])
        self.rejects("duplicate process IDs", "A, A", sch.fcfs, [Process("A", 0, 1), Process("A", 0, 1)])
        self.rejects("zero time quantum", f"{PROCS_TXT}; quantum 0", sch.round_robin, PROCS, 0)

    def test_large(self):
        big = [Process(str(i), random.randint(0, 3000), random.randint(1, 10), random.randint(0, 9))
               for i in range(1000)]
        for name in ("FCFS", "SJF (non-preemptive)", "SRTF (preemptive)", "Priority (preemptive)", "Round Robin"):
            r = sch.run(name, big, 3)
            self.check(f"{name}: large run", "1000 random processes, quantum 3",
                       "1000 rows, no negative waiting time",
                       f"{len(r.rows)} rows, {'no negative waiting time' if all(x.waiting >= 0 for x in r.rows) else 'NEGATIVE waiting time'}")


class Banker(Case):
    A = [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]]
    M = [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]]
    ids = list("01234")
    TXT = "5 processes, total [10,5,7], Allocation [[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]], Max [[7,5,3],[3,2,2],[9,0,2],[2,2,2],[4,3,3]]"

    def test_safe(self):
        r = banker.check_safety(self.ids, self.A, self.M, [10, 5, 7])
        self.check("safe state", self.TXT, True, r.safe)
        self.check("Available = Total - sum(Allocation)", self.TXT, (3, 3, 2), r.available)
        self.check("Need of P0 = Max - Allocation", self.TXT, (7, 4, 3), r.need[0])
        self.check("safe sequence", self.TXT, ("1", "3", "4", "0", "2"), r.safe_sequence)

    def test_unsafe(self):
        r = banker.check_safety(["A", "B"], [[1], [1]], [[3], [3]], [2])
        given = "2 processes, total [2], Allocation [[1],[1]], Max [[3],[3]] (each needs 2 more, none available)"
        self.check("safe state?", given, False, r.safe)
        self.check("safe sequence", given, (), r.safe_sequence)

    def test_request(self):
        ok = banker.request_resources(self.ids, self.A, self.M, [10, 5, 7], "1", [1, 0, 2])
        self.check("P1 requests [1,0,2]: granted?", self.TXT, True, ok.granted)
        bad = banker.request_resources(self.ids, self.A, self.M, [10, 5, 7], "4", [3, 3, 0])
        self.check("P4 requests [3,3,0] (more than Available): granted?", self.TXT, False, bad.granted)

    def test_errors(self):
        self.rejects("no processes", "empty lists", banker.check_safety, [], [], [], [1])
        self.rejects("maximum below allocation", "Allocation [[2]], Max [[1]], total [5]",
                     banker.check_safety, ["A"], [[2]], [[1]], [5])
        self.rejects("allocation above total", "Allocation [[9]], Max [[9]], total [5]",
                     banker.check_safety, ["A"], [[9]], [[9]], [5])

    def test_large(self):
        n, m = 300, 8
        alloc = [[0] * m for _ in range(n)]
        r = banker.check_safety([str(i) for i in range(n)], alloc, [[1] * m for _ in range(n)], [1] * m)
        self.check("large run", "300 processes, 8 resource types, each needs 1 of each, total 1 of each",
                   "safe, 300 in sequence", f"{'safe' if r.safe else 'unsafe'}, {len(r.safe_sequence)} in sequence")


class Paging(Case):
    def test_translate(self):
        r = paging.translate(1024, [(0, 5), (1, 2)], 1030)
        given = "page size 1024, page table {0:5, 1:2}, logical address 1030"
        self.check("(page, offset, frame, physical address)", given, (1, 6, 2, 2054),
                   (r["page"], r["offset"], r["frame"], r["physical_address"]))

    def test_boundary_and_errors(self):
        self.check("address 0 -> frame 3 x 10", "page size 10, {0:3}, address 0", 30,
                   paging.translate(10, [(0, 3)], 0)["physical_address"])
        self.check("unmapped page = page fault (no physical address)", "page size 10, {0:3}, address 10", None,
                   paging.translate(10, [(0, 3)], 10)["physical_address"])
        r = paging.translate(10, [(0, 3)], 5, 100, 50)
        self.check("(pages, frames, physical) with memory sizes", "page size 10, {0:3}, address 5, logical 100, physical 50",
                   (10, 5, 35), (r["pages"], r["frames"], r["physical_address"]))
        self.rejects("frame outside physical memory", "page size 10, {0:9}, address 5, logical 100, physical 50",
                     paging.translate, 10, [(0, 9)], 5, 100, 50)
        self.rejects("address outside logical memory", "page size 10, {0:1}, address 100, logical 100",
                     paging.translate, 10, [(0, 1)], 100, 100, 50)
        self.rejects("page size larger than physical memory", "page size 60, physical 50",
                     paging.translate, 60, [(0, 1)], 5, 100, 50)
        self.rejects("zero page size", "page size 0", paging.translate, 0, [(0, 3)], 1)
        self.rejects("negative address", "address -1", paging.translate, 10, [(0, 3)], -1)
        self.rejects("duplicate page numbers", "{0:3, 0:4}", paging.translate, 10, [(0, 3), (0, 4)], 1)


class PageReplacement(Case):
    REF = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
    REF_TXT = "reference string 7,0,1,2,0,3,0,4,2,3,0,3,2,1,2,0,1,7,0,1 with 3 frames"

    def test_known_faults(self):
        for algo, faults in (("FIFO", 15), ("LRU", 12), ("Optimal", 9)):
            r = pr.simulate(self.REF, 3, algo)
            self.check(f"{algo}: (page faults, hits)", self.REF_TXT, (faults, 20 - faults), (r.faults, r.hits))

    def test_second_chance(self):
        # Second Chance = FIFO, but a page used since it was loaded is skipped once (its reference bit is cleared).
        sc = pr.simulate(self.REF, 3, "Second Chance")
        self.check("Second Chance: (page faults, hits)", self.REF_TXT, (11, 9), (sc.faults, sc.hits))
        self.check("Second Chance: frames after the first 8 references", self.REF_TXT,
                   [(7, None, None), (7, 0, None), (7, 0, 1), (2, 0, 1), (2, 0, 1), (2, 0, 3), (2, 0, 3), (4, 0, 3)],
                   [s.frames for s in sc.steps[:8]])
        used = pr.simulate([1, 2, 3, 1, 4], 3, "Second Chance")
        self.check("page 1 was used again, so it is skipped and page 2 is replaced (FIFO would replace page 1)",
                   "reference string 1,2,3,1,4 with 3 frames", (2, (1, 4, 3)), (used.steps[-1].replaced, used.steps[-1].frames))
        every = pr.simulate([1, 2, 3, 1, 2, 3, 4], 3, "Second Chance")
        self.check("every page used: all get a second chance, then the oldest is replaced",
                   "reference string 1,2,3,1,2,3,4 with 3 frames", (1, (4, 2, 3)), (every.steps[-1].replaced, every.steps[-1].frames))

    def test_nru(self):
        # NRU replaces a RANDOM page from the lowest non-empty class: 0 = R0 M0 (not used, not written),
        # 1 = R0 M1, 2 = R1 M0, 3 = R1 M1. R bits are cleared every `tick` references. The seed is fixed, so a run repeats.
        def last(refs, writes, tick, seed=0):
            s = pr.simulate(refs, 3, "NRU", writes, tick, seed).steps[-1]
            return s.replaced, s.frames, s.bits

        self.check("clock tick before reference 4: page 3 is the only class-0 page (not used, not written), so it is replaced",
                   "reference string 1W,2,3,2,4 with 3 frames, tick every 3",
                   (3, (1, 2, 4), ("R0M1", "R1M0", "R1M0")), last([1, 2, 3, 2, 4], [True, False, False, False, False], 3))
        self.check("a written page is never chosen while lower classes exist: 1W is class 3, 2 and 3 are class 2",
                   "reference string 1W,2,3,4 with 3 frames, no tick", True,
                   all(last([1, 2, 3, 4], [True, False, False, False], 0, seed)[0] in (2, 3) for seed in range(20)))
        picked = {last([1, 2, 3, 4], [True, False, False, False], 0, seed)[0] for seed in range(30)}
        self.check("the pick is random inside the lowest class: over many seeds both class-2 pages are chosen",
                   "reference string 1W,2,3,4 with 3 frames, seeds 0-29", {2, 3}, picked)
        self.check("all pages in the same class: any of the three can be chosen",
                   "reference string 1,2,3,4 with 3 frames, seeds 0-59", {1, 2, 3},
                   {last([1, 2, 3, 4], [False] * 4, 0, seed)[0] for seed in range(60)})
        self.check("same input and seed give the same result", "reference string 1,2,3,4 with 3 frames, seed 7",
                   last([1, 2, 3, 4], [False] * 4, 0, 7), last([1, 2, 3, 4], [False] * 4, 0, 7))
        s = pr.simulate([1, 2, 3, 2, 4], 3, "NRU", None, 3).steps[-1]
        self.check("Decision column names the lowest class and its pages, and the replaced page is one of them",
                   "reference string 1,2,3,2,4 with 3 frames, tick every 3", (True, True),
                   (s.detail.startswith("lowest class 0: pages [1, 3]; random pick "), s.replaced in (1, 3)))
        self.rejects("read/write flags must match the references", "2 references, 1 flag", pr.simulate, [1, 2], 3, "NRU", [True])
        self.rejects("negative clock tick", "tick -1", pr.simulate, [1], 3, "NRU", None, -1)

    def test_second_chance_decision_column(self):
        s = pr.simulate([1, 2, 3, 1, 4], 3, "Second Chance").steps
        given = "reference string 1,2,3,1,4 with 3 frames"
        self.check("R bit of every frame after the hit on page 1 (R=1) and after the fault on 4", given,
                   (("R1", "R0", "R0"), ("R0", "R0", "R0")), (s[3].bits, s[4].bits))
        self.check("decision at the fault: R=1 gets another chance, R=0 is replaced", given,
                   "1: R=1 -> second chance (R cleared, moved to back); 2: R=0 -> replaced", s[4].detail)

    def test_clock(self):
        # Clock makes the same decisions as Second Chance; it just walks a circle of frames with a hand.
        s = pr.simulate([1, 2, 3, 1, 4], 3, "Clock").steps
        given = "reference string 1,2,3,1,4 with 3 frames"
        self.check("decision at the fault (hand starts at frame 1)", given,
                   "frame 1 (1): R=1 -> second chance (R cleared, hand moves on); frame 2 (2): R=0 -> replaced", s[4].detail)
        self.check("final frames, replaced page and hand position (0-based frame index)", given,
                   ((1, 4, 3), 2, 2), (s[4].frames, s[4].replaced, s[4].hand))
        self.check("Clock and Second Chance: (faults, hits) on the classic string", self.REF_TXT, ((11, 9), (11, 9)),
                   tuple((r.faults, r.hits) for r in (pr.simulate(self.REF, 3, "Clock"), pr.simulate(self.REF, 3, "Second Chance"))))

    def test_nfu(self):
        # NFU: at every clock tick each page's counter grows by its R bit and R is cleared; lowest counter is replaced.
        s = pr.simulate([1, 2, 1, 3, 4], 3, "NFU", None, 2).steps[-1]
        self.check("tick every 2: counters 1->2, 2->1, 3->1; tie between 2 and 3 goes to the older page 2",
                   "reference string 1,2,1,3,4 with 3 frames, tick 2", (2, (1, 4, 3), ("R0 C2", "R1 C0", "R0 C1")),
                   (s.replaced, s.frames, s.bits))
        s = pr.simulate([1, 2, 1, 3, 4], 3, "NFU", None, 0).steps[-1]
        self.check("no tick: all counters stay 0, so the oldest page (1) is replaced",
                   "reference string 1,2,1,3,4 with 3 frames, tick 0", (1, (4, 2, 3)), (s.replaced, s.frames))

    def test_random(self):
        a, b = pr.simulate(self.REF, 3, "Random"), pr.simulate(self.REF, 3, "Random")
        self.check("same input and seed give the same result", self.REF_TXT, True, a == b)
        self.check("every reference is a hit or a fault, and the referenced page is in a frame after every step",
                   self.REF_TXT, True, a.hits + a.faults == 20 and all(s.page in s.frames for s in a.steps))
        self.check("Random never beats Optimal", self.REF_TXT, True, a.faults >= pr.simulate(self.REF, 3, "Optimal").faults)

    def test_working_set(self):
        # Working Set replaces the FIRST page (in frame order) that has not been used within the window,
        # so it can differ from LRU, which replaces the page unused for longest.
        refs, given = [1, 2, 3, 1, 3, 3, 3, 4], "reference string 1,2,3,1,3,3,3,4 with 3 frames"
        s = pr.simulate(refs, 3, "Working Set", None, 2).steps[-1]
        self.check("window 2: pages 1 and 2 are outside the working set; frame order picks 1", given + ", window 2",
                   (1, (4, 2, 3)), (s.replaced, s.frames))
        lru = pr.simulate(refs, 3, "LRU").steps[-1]
        self.check("LRU on the same references replaces 2 instead", given, (2, (1, 4, 3)), (lru.replaced, lru.frames))
        s = pr.simulate([1, 2, 3, 4], 3, "Working Set", None, 10).steps[-1]
        self.check("window 10: every page is in the working set, so the oldest (1) is replaced",
                   "reference string 1,2,3,4 with 3 frames, window 10", (1, (4, 2, 3)), (s.replaced, s.frames))
        self.rejects("Working Set needs a window", "window 0", pr.simulate, [1], 3, "Working Set", None, 0)

    def test_optimal_takes_first_unused_frame(self):
        r = pr.simulate([1, 2, 3, 4], 3, "Optimal")  # 1, 2, 3 never used again: frame 1 is replaced
        self.check("Optimal tie-break: final frames", "reference string 1,2,3,4 with 3 frames (1,2,3 never used again)",
                   (4, 2, 3), r.steps[-1].frames)

    def test_belady(self):
        ref = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
        self.check("FIFO with 3 frames: faults", "reference string 1,2,3,4,1,2,5,1,2,3,4,5", 9,
                   pr.simulate(ref, 3, "FIFO").faults)
        self.check("FIFO with 4 frames: faults (Belady's anomaly, more frames = more faults)",
                   "reference string 1,2,3,4,1,2,5,1,2,3,4,5", 10, pr.simulate(ref, 4, "FIFO").faults)

    def test_edges(self):
        self.check("same page repeated, one frame: faults", "reference string 1,1,1 with 1 frame, LRU", 1,
                   pr.simulate([1, 1, 1], 1, "LRU").faults)
        self.rejects("empty reference string", "no references", pr.simulate, [], 3, "FIFO")
        self.rejects("zero frames", "reference 1, 0 frames", pr.simulate, [1], 0, "FIFO")
        self.rejects("negative page number", "reference -1", pr.simulate, [-1], 2, "FIFO")
        self.rejects("unknown algorithm", "algorithm MRU", pr.simulate, [1], 2, "MRU")

    def test_large(self):
        ref = [random.randint(0, 100) for _ in range(20000)]
        res = {a: pr.simulate(ref, 10, a).faults for a in ("FIFO", "LRU", "Optimal")}
        sc = pr.simulate(ref, 10, "Second Chance")
        self.check("Second Chance: every reference is a hit or a fault", "20000 random references (pages 0-100), 10 frames",
                   20000, sc.hits + sc.faults)
        self.check("Optimal never has more faults than FIFO or LRU",
                   f"20000 random references (pages 0-100), 10 frames; FIFO {res['FIFO']}, LRU {res['LRU']}, Optimal {res['Optimal']} faults",
                   True, res["Optimal"] <= min(res["FIFO"], res["LRU"]))


class Segmentation(Case):
    T = [(0, 1000, 400), (1, 6000, 100)]
    T_TXT = "segments {0: base 1000 limit 400, 1: base 6000 limit 100}"

    def test_valid(self):
        self.check("segment 1, offset 99: physical address", self.T_TXT, 6099,
                   seg.translate(self.T, 1, 99)["physical_address"])

    def test_out_of_range(self):
        self.rejects("offset equal to the limit", f"{self.T_TXT}; segment 1, offset 100", seg.translate, self.T, 1, 100)
        self.rejects("segment does not exist", f"{self.T_TXT}; segment 7", seg.translate, self.T, 7, 0)
        self.rejects("negative offset", f"{self.T_TXT}; segment 0, offset -1", seg.translate, self.T, 0, -1)
        self.rejects("empty segment table", "no segments", seg.translate, [], 0, 0)
        self.rejects("zero limit", "segment 0: base 0 limit 0", seg.translate, [(0, 0, 0)], 0, 0)

    def test_ram_and_overlap(self):
        r = seg.translate(self.T, 1, 99, 8000)
        self.check("memory map for 8000 RAM", self.T_TXT,
                   ((0, 1000, "Free"), (1000, 1400, "Segment 0"), (1400, 6000, "Free"),
                    (6000, 6100, "Segment 1"), (6100, 8000, "Free")), r["memory_map"])
        self.rejects("segment does not fit in RAM", f"{self.T_TXT}; RAM size 6050", seg.translate, self.T, 1, 99, 6050)
        self.rejects("overlapping segments", "segment 0: base 0 limit 100, segment 1: base 50 limit 100",
                     seg.translate, [(0, 0, 100), (1, 50, 100)], 0, 0)

    def test_large(self):
        t = [(i, i * 100, 100) for i in range(5000)]
        self.check("segment 4999, offset 99: physical address", "5000 segments, each limit 100, base = number x 100",
                   499999, seg.translate(t, 4999, 99)["physical_address"])


class Fragmentation(Case):
    """Every block holds one process; a process never goes into a block that is already occupied."""

    BLOCKS = [100, 500, 200, 300, 600]
    PROCS = [("P1", 212), ("P2", 417), ("P3", 112), ("P4", 426)]
    GIVEN = "blocks 100,500,200,300,600; processes P1=212 P2=417 P3=112 P4=426"

    def where(self, strategy):
        r = frag.allocate(self.BLOCKS, self.PROCS, strategy)
        return {a.process_id: a.block_index for a in r.allocations}, r

    def test_textbook(self):
        w, r = self.where("First fit")
        self.check("First fit: process -> block number", self.GIVEN, {"P1": 2, "P2": 5, "P3": 3}, w)
        self.check("First fit: unallocated (P4 needs 426 but only 100, 300 are empty)", self.GIVEN, ("P4",), r.unallocated)
        self.check("Best fit: process -> block number", self.GIVEN, {"P1": 4, "P2": 2, "P3": 3, "P4": 5},
                   self.where("Best fit")[0])
        w, r = self.where("Worst fit")
        self.check("Worst fit: process -> block number", self.GIVEN, {"P1": 5, "P2": 2, "P3": 4}, w)
        self.check("Worst fit: unallocated", self.GIVEN, ("P4",), r.unallocated)

    def test_one_process_per_block(self):
        r = frag.allocate([500, 200], [("A", 100), ("B", 100)], "First fit")
        self.check("a block with room left is not shared: A and B use different blocks", "blocks 500,200; A=100 B=100; First fit",
                   [1, 2], [a.block_index for a in r.allocations])
        self.check("memory map (start, size, process or None for empty)", "blocks 500,200; A=100 B=100; First fit",
                   ((0, 500, "A"), (500, 200, "B")), r.memory_map)
        r = frag.allocate([500], [("A", 100), ("B", 100)], "First fit")
        self.check("second process cannot enter the occupied block", "blocks 500; A=100 B=100", ("B",), r.unallocated)

    def test_next_fit_resumes_after_last_placement(self):
        procs = [("P1", 212), ("P2", 100)]
        given = "blocks 100,500,200,300,600; P1=212 P2=100"
        for strategy, block in (("First fit", 1), ("Next fit", 3)):
            r = frag.allocate(self.BLOCKS, procs, strategy)
            self.check(f"{strategy}: block used by P2 (Next fit continues after block 2)", given, block,
                       r.allocations[1].block_index)

    def test_internal_fragmentation(self):
        r = frag.allocate([100, 500], [("A", 60), ("B", 450)], "First fit")
        self.check("internal fragmentation = (100-60) + (500-450)", "blocks 100,500; A=60 B=450", 90, r.internal_fragmentation)
        self.check("every block is filled, so no external fragmentation", "blocks 100,500; A=60 B=450", 0, r.external_fragmentation)

    def test_external_fragmentation(self):
        r = frag.allocate([100, 100], [("A", 60), ("C", 150)], "First fit")
        given = "blocks 100,100; A=60 C=150"
        self.check("unallocated", given, ("C",), r.unallocated)
        self.check("(empty memory, largest empty block, external fragmentation)", given, (100, 100, 100),
                   (r.total_free, r.largest_hole, r.external_fragmentation))

    def test_errors(self):
        self.rejects("no memory blocks", "blocks: none", frag.allocate, [], [("A", 1)])
        self.rejects("zero-size process", "A=0", frag.allocate, [10], [("A", 0)])
        self.rejects("duplicate process IDs", "A=1, A=1", frag.allocate, [10], [("A", 1), ("A", 1)])
        self.rejects("unknown strategy", "strategy 'Random fit'", frag.allocate, [10], [("A", 1)], "Random fit")

    def test_large(self):
        r = frag.allocate([random.randint(50, 500) for _ in range(2000)],
                          [(str(i), random.randint(1, 100)) for i in range(2000)], "Best fit")
        self.check("every process allocated or listed unallocated", "2000 random blocks, 2000 random processes, Best fit",
                   2000, len(r.allocations) + len(r.unallocated))
        self.check("no block is used twice", "same input", len(r.allocations), len({a.block_index for a in r.allocations}))


class Disk(Case):
    REQ = [98, 183, 37, 122, 14, 124, 65, 67]
    GIVEN = "requests 98,183,37,122,14,124,65,67; head 53; cylinders 0-199; direction right"

    def test_known_movement(self):
        for algo, total in (("FCFS", 640), ("SSTF", 236), ("SCAN", 331), ("C-SCAN", 382),
                            ("LOOK", 299), ("C-LOOK", 322)):
            self.check(f"{algo}: total head movement", self.GIVEN, total,
                       disk.schedule(self.REQ, 53, algo, 0, 199).total_movement)

    def test_elevator_is_scan(self):
        a = disk.schedule(self.REQ, 53, "SCAN (Elevator)")
        b = disk.schedule(self.REQ, 53, "SCAN")
        self.check("SCAN (Elevator) gives the same order and movement as SCAN", self.GIVEN,
                   (b.service_order, b.total_movement), (a.service_order, a.total_movement))
        self.check("result keeps the Elevator label", self.GIVEN, "SCAN (Elevator)", a.algorithm)

    def test_lecture_slide_example(self):  # DISK-SCHEDULING slide 21: head 100, moving up
        req = [55, 58, 39, 18, 90, 160, 150, 38, 184]
        for algo, total in (("FCFS", 498), ("SSTF", 248), ("LOOK", 250), ("C-LOOK", 322)):
            self.check(f"{algo}: total head movement (lecture slide 21)", "requests 55,58,39,18,90,160,150,38,184; head 100; moving up",
                       total, disk.schedule(req, 100, algo).total_movement)

    def test_sstf_order(self):
        self.check("SSTF: service order", self.GIVEN, (65, 67, 37, 14, 98, 122, 124, 183),
                   disk.schedule(self.REQ, 53, "SSTF").service_order)

    def test_errors(self):
        self.rejects("no requests", "empty list", disk.schedule, [], 0, "FCFS")
        self.rejects("request outside cylinder range", "request 300, range 0-199", disk.schedule, [300], 0, "FCFS")
        self.rejects("head outside cylinder range", "head 250, range 0-199", disk.schedule, [5], 250, "FCFS")
        self.rejects("unknown algorithm", "algorithm XYZ", disk.schedule, [5], 0, "XYZ")
        self.rejects("lower limit equals upper limit", "range 10-10", disk.schedule, [5], 0, "SCAN", 10, 10)

    def test_large(self):
        req = [random.randint(0, 199) for _ in range(3000)]
        for algo in ("FCFS", "SSTF", "SCAN", "C-SCAN", "LOOK", "C-LOOK"):
            r = disk.schedule(req, 50, algo)
            self.check(f"{algo}: every request served exactly once", "3000 random requests, head 50",
                       "all 3000 served", "all 3000 served" if sorted(r.service_order) == sorted(req) else "some missing or repeated")


class Multiprogramming(Case):
    def test_small(self):
        ev = mp.simulate([mp.Job("A", 0, 4), mp.Job("B", 0, 2)])
        given = "jobs A(arrival 0, burst 4) and B(arrival 0, burst 2), equal CPU share"
        self.check("events (time, event)", given,
                   [(0, "A arrives"), (0, "B arrives"), (4, "B completes"), (6, "A completes")],
                   [(e.time, e.event) for e in ev])
        self.check("remaining work when B completes", given, (("A", 2.0),), ev[2].active)
        self.check("remaining work after both arrive", given, (("A", 4.0), ("B", 2.0)), ev[1].active)

    def test_idle_gap(self):
        ev = mp.simulate([mp.Job("A", 0, 1), mp.Job("B", 5, 2)])
        self.check("events (time, event)", "A(arrival 0, burst 1) and B(arrival 5, burst 2)",
                   [(0, "A arrives"), (1, "A completes"), (5, "B arrives"), (7, "B completes")],
                   [(e.time, e.event) for e in ev])

    def test_errors(self):
        self.rejects("no jobs", "empty list", mp.simulate, [])
        self.rejects("zero burst", "A(arrival 0, burst 0)", mp.simulate, [mp.Job("A", 0, 0)])
        self.rejects("duplicate job IDs", "A, A", mp.simulate, [mp.Job("A", 0, 1), mp.Job("A", 1, 1)])

    def test_large(self):
        jobs = [mp.Job(str(i), random.randint(0, 500), random.randint(1, 10)) for i in range(1000)]
        ev = mp.simulate(jobs)
        self.check("completion events", "1000 random jobs", 1000, sum(e.event.endswith("completes") for e in ev))


try:
    from kernel_sim.gui import _memory_chart_fragmentation, _time_value
except ImportError:  # the GUI library (PySide6) is not installed: skip only the tests that use the GUI code
    _time_value = _memory_chart_fragmentation = None


@unittest.skipIf(_time_value is None, "PySide6 not installed")
class TimeParsing(Case):
    def test_decimal_and_units(self):
        for text, want in (("5", (5, False)), ("0.5", (Fraction(1, 2), False)), (".5", (Fraction(1, 2), False)),
                           ("1.5 hr/s", (90, True)), ("2 min/s", (2, True)), ("0.25 hr/s", (15, True))):
            self.check(f"time '{text}' -> (minutes or units, has unit suffix)", f"text {text!r}", want,
                       _time_value(text, "Time"))

    def test_errors(self):
        for text in ("", "abc", "-1", "1,5", "1..5", "5 days"):
            self.rejects(f"invalid time {text!r}", f"text {text!r}", _time_value, text, "Time")


@unittest.skipIf(_memory_chart_fragmentation is None, "PySide6 not installed")
class FragmentationChart(Case):
    """The data behind the memory-map chart: worksheet with six blocks (KB) and seven processes, one per block."""

    WORKSHEET = {"strategy": "First fit", "blocks": "350\n200\n400\n150\n300\n250",
                 "processes": "P1,180\nP2,120\nP3,290\nP4,140\nP5,220\nP6,100\nP7,275"}
    GIVEN = "blocks 350,200,400,150,300,250; processes 180,120,290,140,220,100,275"

    def test_worksheet(self):
        runs, colors, chosen = _memory_chart_fragmentation(self.WORKSHEET)
        where = {r.strategy: {a.process_id: a.block_index for a in r.allocations} for r in runs}
        self.check("chart has one column per strategy", self.GIVEN, ["First fit", "Best fit", "Next fit", "Worst fit"],
                   [r.strategy for r in runs])
        self.check("First fit: process -> block", self.GIVEN, {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5, "P6": 6},
                   where["First fit"])
        self.check("Best fit: process -> block", self.GIVEN, {"P1": 2, "P2": 4, "P3": 5, "P4": 6, "P5": 1, "P6": 3},
                   where["Best fit"])
        self.check("Worst fit: process -> block", self.GIVEN, {"P1": 3, "P2": 1, "P3": 5, "P4": 6, "P6": 2},
                   where["Worst fit"])
        self.check("not placed (First, Best, Next, Worst)", self.GIVEN, [("P7",), ("P7",), ("P7",), ("P5", "P7")],
                   [r.unallocated for r in runs])
        self.check("every process has a colour; the chosen strategy is passed through", self.GIVEN,
                   (7, "First fit"), (len(colors), chosen))
        self.check("memory map of First fit (start, size, process or None)", self.GIVEN,
                   ((0, 350, "P1"), (350, 200, "P2"), (550, 400, "P3"), (950, 150, "P4"), (1100, 300, "P5"), (1400, 250, "P6")),
                   runs[0].memory_map)


def _wrap(title, value):
    """'      Input    : value', wrapped so long inputs stay fully visible."""
    return textwrap.fill(str(value), width=100, initial_indent=f"      {title:<9}: ", subsequent_indent=" " * 18)


def print_report() -> int:
    """Run every test and print each check as: input, expected, actual, CORRECT / WRONG."""
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    line = "=" * 78
    current = None
    for cls, name, label, given, expected, actual, ok in REPORT:
        if (cls, name) != current:
            if cls != (current or ("",))[0]:
                print(f"\n{line}\n{cls.upper()}\n{line}")
            print(f"\n  [{name}]")
            current = (cls, name)
        print(f"    {label}")
        print(_wrap("Input", given))
        print(_wrap("Expected", expected))
        print(_wrap("Actual", actual))
        print(_wrap("Result", "CORRECT" if ok else "*** WRONG ***"))
    right = sum(r[-1] for r in REPORT)
    print(f"\n{line}")
    print(f"{right} of {len(REPORT)} checks CORRECT | {result.testsRun - len(result.failures) - len(result.errors)} of "
          f"{result.testsRun} tests passed")
    for case, trace in result.failures + result.errors:
        print(f"\nFAILED: {case}\n{trace}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(print_report())
