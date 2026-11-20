# Unit Test Documentation

Test file: [`tests/test_algorithms.py`](../tests/test_algorithms.py) · Framework: Python `unittest` (standard library, nothing to install) · **49 tests / 166 checks**, all passing (about 1.5 s). Latest report (input, expected, actual, result for every check): [`test-results.txt`](test-results.txt).

## How to run

From the project folder:

```powershell
python tests/test_algorithms.py                 # readable report: input, expected, actual, CORRECT / WRONG
python tests/test_algorithms.py > docs/test-results.txt   # save that report
python -m unittest discover tests               # plain pass/fail run
python -m unittest tests.test_algorithms.Disk   # one module only (plain run)
```

The report prints every check in this form, grouped by module and test:

```
P1 requests [1,0,2]: granted?
  Input    : 5 processes, total [10,5,7], Allocation [[0,1,0],...], Max [[7,5,3],...]
  Expected : True
  Actual   : True
  Result   : CORRECT
```

A wrong answer prints `*** WRONG ***` with the expected and actual values, and the command exits with an error code. The last line summarises the run, e.g. `166 of 166 checks CORRECT | 49 of 49 tests passed`. In the plain run, a dot (`.`) is a passing test, `F` a failed assertion and `E` a crash.

## What the tests prove

The tests call the simulation code directly (the `kernel_sim/*.py` modules, not the GUI) and compare the result with an answer known in advance. Every module is tested in four ways:

| Kind | Purpose | Example |
|---|---|---|
| **Known answer** | Output equals a textbook or lecture-slide result worked out by hand | FIFO on the classic reference string gives 15 faults |
| **Boundary / edge** | Behaviour at limits (first address, last offset, idle CPU gap) | Segment offset equal to the limit is rejected |
| **Error handling** | Bad input raises `ValueError` with a message instead of crashing | Negative arrival time, blank list, duplicate IDs |
| **Large dataset** | A substantially larger input still runs correctly | 20,000 page references, 5,000 segments |

Random large inputs use a fixed seed (`random.seed(1)`), so every run is repeatable.

## Test cases by module

### 1. CPU Scheduling (6 tests)
Shared data: P1 (arrival 0, burst 5, priority 2), P2 (1, 3, 1), P3 (2, 8, 3), P4 (3, 6, 2). Priority rule: **a higher number means higher priority**.

| Test | What it checks | Expected |
|---|---|---|
| `test_known_averages` | Average waiting / turnaround time for every algorithm (Round Robin quantum 2) | FCFS 5.75 / 11.25 · SJF 5.25 / 10.75 · SRTF 5.00 / 10.50 · Priority non-preemptive 7.75 / 13.25 · Priority preemptive 9.00 / 14.50 · Round Robin 9.75 / 15.25 |
| `test_idle_gap` | CPU sits idle until a late-arriving process | Process arriving at 5 with burst 2 completes at 7 |
| `test_decimal_times` | Decimal arrivals and bursts (A 0/3, B 0.5/1, C 1.2/0.7, quantum 0.5) | SRTF and preemptive Priority finish at `4.7, 1.5, 2.2`; Round Robin `4.7, 2, 3.2`; FCFS `3, 4, 4.7`; B preempts A at 0.5; SRTF average waiting 0.6667 |
| `test_decimal_has_no_float_drift` | 0.1 + 0.2 must equal 0.3 exactly, so no fake idle gap appears | C completes at 0.4, CPU utilization 100.0 |
| `test_errors` | Rejects empty list, negative arrival, zero burst, duplicate IDs, zero quantum | `ValueError` each time |
| `test_large` | 1,000 random processes through five algorithms | 1,000 result rows, no negative waiting time |

### 2. Banker's Algorithm (5 tests)
Shared data: the classic 5-process / 3-resource example, total `10,5,7`.

| Test | What it checks | Expected |
|---|---|---|
| `test_safe` | Available, Need matrix and safe sequence | Available `3,3,2` · Need of P0 `7,4,3` · sequence `1 → 3 → 4 → 0 → 2` |
| `test_unsafe` | A state where nobody can finish | Reported unsafe, empty sequence |
| `test_request` | Resource-request algorithm | P1 asking `1,0,2` is granted; P4 asking `3,3,0` is refused |
| `test_errors` | Empty input, maximum below allocation, allocation above total | `ValueError` each time |
| `test_large` | 300 processes × 8 resource types | Safe, sequence of 300 |

### 3. Paging (2 tests)

| Test | What it checks | Expected |
|---|---|---|
| `test_translate` | Page size 1024, table `0→5, 1→2`, logical address 1030 | Page 1, offset 6, frame 2, physical **2054** |
| `test_boundary_and_errors` | Address 0 maps to frame 3 × 10 = 30; unmapped page gives a page fault (no physical address); optional logical / physical memory sizes give page and frame counts and a bounds check; rejects frame outside physical memory, address outside logical memory, page larger than physical memory, zero page size, negative address, duplicate page numbers | As described, `ValueError` for each invalid case |

### 4. Page Replacement (12 tests)

| Test | What it checks | Expected |
|---|---|---|
| `test_known_faults` | Reference string `7,0,1,2,0,3,0,4,2,3,0,3,2,1,2,0,1,7,0,1`, 3 frames | FIFO **15**, LRU **12**, Optimal **9** faults (hits = 20 − faults) |
| `test_second_chance` | Second Chance = FIFO, but a page used again since it was loaded is skipped once. Same reference string, 3 frames | **11** faults, 9 hits; frames after 8 references `(7,-,-) (7,0,-) (7,0,1) (2,0,1) (2,0,1) (2,0,3) (2,0,3) (4,0,3)`; `1,2,3,1,4` replaces page 2 (FIFO would replace 1); `1,2,3,1,2,3,4` replaces page 1 |
| `test_nru` | NRU: class = 2 × R + M (R = referenced since the last clock tick, M = modified); a **random** page from the lowest non-empty class is replaced (fixed seed, so runs repeat); R bits are cleared every N references. 3 frames | `1W,2,3,2,4` with a tick every 3: page 3 is the only class-0 page (not referenced, not modified) and is replaced · `1W,2,3,4`: only pages 2 or 3 are ever chosen (the written page 1 is class 3) and over many seeds both are chosen · `1,2,3,4`: any of 1, 2, 3 can be chosen · same seed gives the same result · the Decision column lists the lowest-class pages and the pick · mismatched read/write flags and a negative tick are refused |
| `test_second_chance_decision_column` | R bit of every frame and the Decision text. `1,2,3,1,4`, 3 frames | After the hit on page 1 the bits are `R1 R0 R0`; at the fault: `1: R=1 -> second chance (R cleared, moved to back); 2: R=0 -> replaced` |
| `test_clock` | Clock = Second Chance with a circle of frames and a hand. `1,2,3,1,4`, 3 frames | Frame 1 (R=1) gets another chance, frame 2 (R=0) is replaced, final frames `(1,4,3)`, hand at frame index 2; classic string gives 11 faults, 9 hits, the same as Second Chance |
| `test_nfu` | At each clock tick a page's counter grows by its R bit and R is cleared; lowest counter is replaced. `1,2,1,3,4`, 3 frames | Tick 2: counters 1→2, 2→1, 3→1; tie goes to the older page, so page 2 is replaced, bits `R0 C2, R1 C0, R0 C1`. Tick 0: all counters 0, so page 1 is replaced |
| `test_random` | Fixed seed makes Random repeatable | Two runs are identical; hits + faults = 20; the referenced page is always in a frame; never fewer faults than Optimal |
| `test_working_set` | Window N: the first page (in frame order) unused for more than N references is replaced, else the oldest page. `1,2,3,1,3,3,3,4`, 3 frames | Window 2 replaces page 1 (LRU would replace 2); window 10 on `1,2,3,4` replaces page 1; window 0 is refused |
| `test_optimal_takes_first_unused_frame` | Optimal tie-break when several pages are never used again | `[1,2,3,4]` with 3 frames ends as `(4, 2, 3)` |
| `test_belady` | Belady's anomaly: more frames, more faults under FIFO | 3 frames → 9 faults, 4 frames → 10 faults |
| `test_edges` | Repeated page with one frame; empty string, zero frames, negative page, unknown algorithm | 1 fault; `ValueError` for bad input |
| `test_large` | 20,000 random references, 10 frames | Optimal never has more faults than FIFO or LRU |

### 5. Segmentation (4 tests)
Shared table: segment 0 (base 1000, limit 400), segment 1 (base 6000, limit 100).

| Test | What it checks | Expected |
|---|---|---|
| `test_valid` | Segment 1, offset 99 | Physical 6099 |
| `test_out_of_range` | Offset equal to limit, missing segment, negative offset, empty table, zero limit | `ValueError` each time |
| `test_ram_and_overlap` | Memory map with RAM size 8000; segment that does not fit in RAM; overlapping segments | Map `free / Segment 0 / free / Segment 1 / free`; `ValueError` for the other two |
| `test_large` | 5,000 segments | Segment 4999, offset 99 → 499999 |

### 6. Fragmentation (7 tests)
Every memory block holds **one process**. A process never goes into an occupied block, and leftover space inside a filled block is internal fragmentation, not a new free block.
Shared data: blocks `100,500,200,300,600`; processes P1 212, P2 417, P3 112, P4 426.

| Test | What it checks | Expected |
|---|---|---|
| `test_textbook` | Block chosen by each strategy | First fit: P1→2, P2→5, P3→3, P4 unplaced · Best fit: P1→4, P2→2, P3→3, P4→5 · Worst fit: P1→5, P2→2, P3→4, P4 unplaced |
| `test_one_process_per_block` | A block with room left is not shared | Blocks `500,200`, A=100, B=100: A→1, B→2. With only block `500`, B is unplaced |
| `test_next_fit_resumes_after_last_placement` | Next fit continues after the previous placement (P1=212, P2=100) | First fit puts P2 in block 1, Next fit puts it in block 3 |
| `test_internal_fragmentation` | Unused space inside filled blocks | Blocks `100,500`, A=60, B=450: (100−60) + (500−450) = **90**; no external fragmentation |
| `test_external_fragmentation` | Empty memory while a process cannot be placed | Blocks `100,100`, A=60, C=150: C unplaced; empty 100, largest empty block 100, external fragmentation 100 |
| `test_errors` | No blocks, zero-size process, duplicate IDs, unknown strategy | `ValueError` each time |
| `test_large` | 2,000 random blocks and 2,000 random processes, Best fit | Every process allocated or listed unallocated; no block used twice |

### 7. Disk Scheduling (6 tests)
Shared data: requests `98,183,37,122,14,124,65,67`, head at 53, cylinders 0–199.

| Test | What it checks | Expected total head movement |
|---|---|---|
| `test_known_movement` | All six algorithms, direction right | FCFS **640** · SSTF **236** · SCAN **331** · C-SCAN **382** · LOOK **299** · C-LOOK **322** |
| `test_elevator_is_scan` | "SCAN (Elevator)" is the same algorithm as SCAN | Same service order and total; result keeps the Elevator label |
| `test_lecture_slide_example` | Lecture slide 21 (head 100, moving up, requests `55,58,39,18,90,160,150,38,184`) | FCFS 498 · SSTF 248 · LOOK 250 · C-LOOK 322 (average seek 55.3 / 27.6 / 27.8 / 35.8) |
| `test_sstf_order` | Nearest-first order | `65, 67, 37, 14, 98, 122, 124, 183` |
| `test_errors` | Empty list, request or head outside the cylinder range, unknown algorithm, equal lower and upper limits | `ValueError` each time |
| `test_large` | 3,000 random requests through every algorithm | Every request is served exactly once |

### 8. Multiprogramming (4 tests)
Equal-share CPU model: every active job gets 1/n of the processor.

| Test | What it checks | Expected |
|---|---|---|
| `test_small` | Jobs A (burst 4) and B (burst 2), both arriving at 0 | Events `A arrives, B arrives, B completes @4, A completes @6`; remaining work A 4 / B 2 at start, A 2 when B finishes |
| `test_idle_gap` | A finishes before B arrives | Events at times 0, 1, 5, 7 |
| `test_errors` | No jobs, zero burst, duplicate IDs | `ValueError` each time |
| `test_large` | 1,000 random jobs | 1,000 completion events |

## Adding a test

1. Open `tests/test_algorithms.py` and find the class for the module (`Scheduling`, `Banker`, …).
2. Add a method whose name starts with `test_`, call the module function and use `self.assertEqual(...)`; for invalid input use `with self.assertRaises(ValueError): ...`.
3. Use `self.check(label, input_text, expected, actual)` for a normal answer and `self.rejects(label, input_text, function, *args)` for input that must be refused, so the check appears in the report. Then refresh the saved report:

```powershell
python tests/test_algorithms.py > docs/test-results.txt
```

### 9. Time input parsing (2 tests)
Checks the text-to-number step used by CPU Scheduling and Multiprogramming (skipped if PySide6 is not installed).

| Test | What it checks | Expected |
|---|---|---|
| `test_decimal_and_units` | `5`, `0.5`, `.5`, `1.5 hr/s`, `2 min/s`, `0.25 hr/s` | 5, 1/2, 1/2, 90, 2, 15 (hr/s become minutes; exact fractions, no rounding error) |
| `test_errors` | Empty text, `abc`, `-1`, `1,5`, `1..5`, `5 days` | `ValueError` each time |

### 10. Fragmentation chart data (1 test)
Checks the numbers behind the memory-map chart with the class worksheet (six blocks, seven processes; skipped if PySide6 is not installed).

| Test | What it checks | Expected |
|---|---|---|
| `test_worksheet` | Blocks `350,200,400,150,300,250`, processes `180,120,290,140,220,100,275` | Four columns (First, Best, Next, Worst fit). First fit: P1–P6 in blocks 1–6. Best fit: P1→2, P2→4, P3→5, P4→6, P5→1, P6→3. Worst fit: P1→3, P2→1, P3→5, P4→6, P6→2. P7 never fits; Worst fit also cannot place P5. First fit map: P1–P6 fill blocks 1–6 in order |

## Scope and limits

- The tests cover the algorithm code only. The GUI is checked by hand with the screenshots in this folder.
- Expected values come from textbook examples, the lecture slides (Disk Scheduling slide 21) and hand calculation. The Multiprogramming, Priority and Segmentation memory-map expectations were worked out by hand rather than taken from a book.
