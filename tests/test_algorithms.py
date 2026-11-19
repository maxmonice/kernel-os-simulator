"""Known-answer, boundary, error and large-dataset tests.

Run from the project folder:  python -m unittest discover tests
"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kernel_sim import (banker, disk_scheduling as disk, fragmentation as frag,
                        multiprogramming as mp, page_replacement as pr, paging,
                        scheduling as sch, segmentation as seg)
from kernel_sim.models import Process

random.seed(1)
PROCS = [Process("P1", 0, 5, 2), Process("P2", 1, 3, 1), Process("P3", 2, 8, 3), Process("P4", 3, 6, 2)]


class Scheduling(unittest.TestCase):
    def test_known_averages(self):
        expected = {"FCFS": (5.75, 11.25), "SJF (non-preemptive)": (5.25, 10.75),
                    "SRTF (preemptive)": (5.0, 10.5), "Priority (non-preemptive)": (5.25, 10.75),
                    "Priority (preemptive)": (5.0, 10.5), "Round Robin": (9.75, 15.25)}
        for name, (w, t) in expected.items():
            r = sch.run(name, PROCS, 2)
            self.assertEqual((r.average_waiting, r.average_turnaround), (w, t), name)

    def test_idle_gap(self):
        r = sch.fcfs([Process("A", 5, 2)])
        self.assertEqual(r.rows[0].completion, 7)

    def test_errors(self):
        with self.assertRaises(ValueError): sch.fcfs([])
        with self.assertRaises(ValueError): sch.fcfs([Process("A", -1, 2)])
        with self.assertRaises(ValueError): sch.fcfs([Process("A", 0, 0)])
        with self.assertRaises(ValueError): sch.fcfs([Process("A", 0, 1), Process("A", 0, 1)])
        with self.assertRaises(ValueError): sch.round_robin(PROCS, 0)

    def test_large(self):
        big = [Process(str(i), random.randint(0, 3000), random.randint(1, 10), random.randint(0, 9))
               for i in range(1000)]
        for name in ("FCFS", "SJF (non-preemptive)", "SRTF (preemptive)", "Priority (preemptive)", "Round Robin"):
            r = sch.run(name, big, 3)
            self.assertEqual(len(r.rows), 1000)
            self.assertTrue(all(x.waiting >= 0 for x in r.rows))


class Banker(unittest.TestCase):
    A = [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]]
    M = [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]]
    ids = list("01234")

    def test_safe(self):
        r = banker.check_safety(self.ids, self.A, self.M, [10, 5, 7])
        self.assertTrue(r.safe)
        self.assertEqual(r.available, (3, 3, 2))
        self.assertEqual(r.need[0], (7, 4, 3))
        self.assertEqual(r.safe_sequence, ("1", "3", "4", "0", "2"))

    def test_unsafe(self):
        r = banker.check_safety(["A", "B"], [[1], [1]], [[3], [3]], [2])
        self.assertFalse(r.safe)
        self.assertEqual(r.safe_sequence, ())

    def test_request(self):
        ok = banker.request_resources(self.ids, self.A, self.M, [10, 5, 7], "1", [1, 0, 2])
        self.assertTrue(ok.granted)
        bad = banker.request_resources(self.ids, self.A, self.M, [10, 5, 7], "4", [3, 3, 0])
        self.assertFalse(bad.granted)

    def test_errors(self):
        with self.assertRaises(ValueError): banker.check_safety([], [], [], [1])
        with self.assertRaises(ValueError): banker.check_safety(["A"], [[2]], [[1]], [5])  # max < alloc
        with self.assertRaises(ValueError): banker.check_safety(["A"], [[9]], [[9]], [5])  # over total

    def test_large(self):
        n, m = 300, 8
        alloc = [[0] * m for _ in range(n)]
        r = banker.check_safety([str(i) for i in range(n)], alloc, [[1] * m for _ in range(n)], [1] * m)
        self.assertTrue(r.safe)
        self.assertEqual(len(r.safe_sequence), n)


class Paging(unittest.TestCase):
    def test_translate(self):
        r = paging.translate(1024, [(0, 5), (1, 2)], 1030)
        self.assertEqual((r["page"], r["offset"], r["frame"], r["physical_address"]), (1, 6, 2, 2054))

    def test_boundary_and_errors(self):
        self.assertEqual(paging.translate(10, [(0, 3)], 0)["physical_address"], 30)
        with self.assertRaises(ValueError): paging.translate(10, [(0, 3)], 10)  # unmapped page
        with self.assertRaises(ValueError): paging.translate(0, [(0, 3)], 1)
        with self.assertRaises(ValueError): paging.translate(10, [(0, 3)], -1)
        with self.assertRaises(ValueError): paging.translate(10, [(0, 3), (0, 4)], 1)


class PageReplacement(unittest.TestCase):
    REF = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]

    def test_known_faults(self):
        for algo, faults in (("FIFO", 15), ("LRU", 12), ("Optimal", 9)):
            r = pr.simulate(self.REF, 3, algo)
            self.assertEqual((r.faults, r.hits), (faults, 20 - faults), algo)

    def test_belady(self):
        ref = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
        self.assertEqual(pr.simulate(ref, 3, "FIFO").faults, 9)
        self.assertEqual(pr.simulate(ref, 4, "FIFO").faults, 10)

    def test_edges(self):
        self.assertEqual(pr.simulate([1, 1, 1], 1, "LRU").faults, 1)
        with self.assertRaises(ValueError): pr.simulate([], 3, "FIFO")
        with self.assertRaises(ValueError): pr.simulate([1], 0, "FIFO")
        with self.assertRaises(ValueError): pr.simulate([-1], 2, "FIFO")
        with self.assertRaises(ValueError): pr.simulate([1], 2, "MRU")

    def test_large(self):
        ref = [random.randint(0, 100) for _ in range(20000)]
        res = {a: pr.simulate(ref, 10, a).faults for a in ("FIFO", "LRU", "Optimal")}
        self.assertLessEqual(res["Optimal"], min(res["FIFO"], res["LRU"]))


class Segmentation(unittest.TestCase):
    T = [(0, 1000, 400), (1, 6000, 100)]

    def test_valid(self):
        self.assertEqual(seg.translate(self.T, 1, 99)["physical_address"], 6099)

    def test_out_of_range(self):
        with self.assertRaises(ValueError): seg.translate(self.T, 1, 100)
        with self.assertRaises(ValueError): seg.translate(self.T, 7, 0)
        with self.assertRaises(ValueError): seg.translate(self.T, 0, -1)
        with self.assertRaises(ValueError): seg.translate([], 0, 0)
        with self.assertRaises(ValueError): seg.translate([(0, 0, 0)], 0, 0)

    def test_large(self):
        t = [(i, i * 100, 100) for i in range(5000)]
        self.assertEqual(seg.translate(t, 4999, 99)["physical_address"], 499999)


class Fragmentation(unittest.TestCase):
    BLOCKS = [100, 500, 200, 300, 600]
    PROCS = [("P1", 212), ("P2", 417), ("P3", 112), ("P4", 426)]

    def where(self, strategy, mode="Variable partitions"):
        r = frag.allocate(self.BLOCKS, self.PROCS, mode, strategy)
        return {a.process_id: a.block_index for a in r.allocations}, r

    def test_textbook(self):
        self.assertEqual(self.where("First fit")[0], {"P1": 2, "P2": 5, "P3": 2})
        self.assertEqual(self.where("Best fit")[0], {"P1": 4, "P2": 2, "P3": 3, "P4": 5})
        w, r = self.where("Worst fit")
        self.assertEqual(w, {"P1": 5, "P2": 2, "P3": 5})
        self.assertEqual(r.unallocated, ("P4",))

    def test_fixed_internal(self):
        r = frag.allocate([100, 500], [("A", 60), ("B", 450)], "Fixed partitions", "First fit")
        self.assertEqual(r.internal_fragmentation, 40 + 50)

    def test_external(self):
        r = frag.allocate([100, 100], [("A", 60), ("B", 60), ("C", 90)], "Variable partitions", "First fit")
        self.assertEqual(r.unallocated, ("C",))
        self.assertEqual((r.total_free, r.largest_hole, r.external_fragmentation), (80, 40, 40))

    def test_errors(self):
        with self.assertRaises(ValueError): frag.allocate([], [("A", 1)])
        with self.assertRaises(ValueError): frag.allocate([10], [("A", 0)])
        with self.assertRaises(ValueError): frag.allocate([10], [("A", 1), ("A", 1)])

    def test_large(self):
        r = frag.allocate([random.randint(50, 500) for _ in range(2000)],
                          [(str(i), random.randint(1, 100)) for i in range(2000)],
                          "Variable partitions", "Best fit")
        self.assertEqual(len(r.allocations) + len(r.unallocated), 2000)


class Disk(unittest.TestCase):
    REQ = [98, 183, 37, 122, 14, 124, 65, 67]

    def test_known_movement(self):
        for algo, total in (("FCFS", 640), ("SSTF", 236), ("SCAN", 331), ("C-SCAN", 382),
                            ("LOOK", 299), ("C-LOOK", 322)):
            self.assertEqual(disk.schedule(self.REQ, 53, algo, 0, 199).total_movement, total, algo)

    def test_elevator_is_scan(self):
        a = disk.schedule(self.REQ, 53, "SCAN (Elevator)")
        b = disk.schedule(self.REQ, 53, "SCAN")
        self.assertEqual((a.service_order, a.total_movement), (b.service_order, b.total_movement))
        self.assertEqual(a.algorithm, "SCAN (Elevator)")

    def test_lecture_slide_example(self):  # DISK-SCHEDULING slide 21: head 100, moving up
        req = [55, 58, 39, 18, 90, 160, 150, 38, 184]
        for algo, total in (("FCFS", 498), ("SSTF", 248), ("LOOK", 250), ("C-LOOK", 322)):
            self.assertEqual(disk.schedule(req, 100, algo).total_movement, total, algo)

    def test_sstf_order(self):
        self.assertEqual(disk.schedule(self.REQ, 53, "SSTF").service_order, (65, 67, 37, 14, 98, 122, 124, 183))

    def test_errors(self):
        with self.assertRaises(ValueError): disk.schedule([], 0, "FCFS")
        with self.assertRaises(ValueError): disk.schedule([300], 0, "FCFS")
        with self.assertRaises(ValueError): disk.schedule([5], 250, "FCFS")
        with self.assertRaises(ValueError): disk.schedule([5], 0, "XYZ")
        with self.assertRaises(ValueError): disk.schedule([5], 0, "SCAN", 10, 10)

    def test_large(self):
        req = [random.randint(0, 199) for _ in range(3000)]
        for algo in ("FCFS", "SSTF", "SCAN", "C-SCAN", "LOOK", "C-LOOK"):
            r = disk.schedule(req, 50, algo)
            self.assertEqual(sorted(r.service_order), sorted(req), algo)


class Multiprogramming(unittest.TestCase):
    def test_small(self):
        ev = mp.simulate([mp.Job("A", 0, 4), mp.Job("B", 0, 2)])
        self.assertEqual([(e.time, e.event) for e in ev],
                         [(0, "A arrives"), (0, "B arrives"), (4, "B completes"), (6, "A completes")])
        self.assertEqual(ev[2].active, (("A", 2.0),))
        self.assertEqual(ev[1].active, (("A", 4.0), ("B", 2.0)))

    def test_idle_gap(self):
        ev = mp.simulate([mp.Job("A", 0, 1), mp.Job("B", 5, 2)])
        self.assertEqual([(e.time, e.event) for e in ev],
                         [(0, "A arrives"), (1, "A completes"), (5, "B arrives"), (7, "B completes")])

    def test_errors(self):
        with self.assertRaises(ValueError): mp.simulate([])
        with self.assertRaises(ValueError): mp.simulate([mp.Job("A", 0, 0)])
        with self.assertRaises(ValueError): mp.simulate([mp.Job("A", 0, 1), mp.Job("A", 1, 1)])

    def test_large(self):
        jobs = [mp.Job(str(i), random.randint(0, 500), random.randint(1, 10)) for i in range(1000)]
        ev = mp.simulate(jobs)
        self.assertEqual(sum(e.event.endswith("completes") for e in ev), 1000)


if __name__ == "__main__":
    unittest.main()
