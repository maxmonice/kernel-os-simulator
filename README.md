# KERNEL — Operating System Simulator

A small Python desktop app for exploring operating-system concepts. The interface uses PySide6 (Qt); the simulation modules use only the Python standard library.

## Run on Windows

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). During setup, enable **Add python.exe to PATH**. Then run `pip install PySide6` once (the interface uses Qt).
2. Download this project from GitHub using **Code → Download ZIP**, then extract the ZIP. (If you already use Git, clone the repository instead.)
3. Open the extracted `kernel-os-simulator` folder.
4. Double-click `run.bat` to start the simulator.

To work on the code, install [Visual Studio Code](https://code.visualstudio.com/), open the project folder, and optionally install Microsoft's Python extension. You can also run `kernel_app.py` from VS Code.

## Modules

- CPU Scheduling: FCFS, non-preemptive SJF, preemptive SRTF, priority, and Round Robin, with response-time metrics
- Banker's Algorithm: need and available resources, safe-state check, safe sequence, and optional tentative resource requests
- Paging and Page Replacement: page mapping, address translation, FIFO, LRU, and Optimal
- Segmentation: segment-table checks and logical-address translation
- Fragmentation: First Fit, Best Fit, Next Fit, and Worst Fit
- Disk Scheduling: FCFS, SSTF, SCAN, C-SCAN, LOOK, and C-LOOK
- Multiprogramming: time-sliced CPU sharing and memory admission

The CPU scheduling page shows a time-scaled Gantt chart with individual process blocks and boundary times in the simulation output. CPU Scheduling and Multiprogramming accept times such as `2 hr/s` or `30 min/s`; when a suffix is used, bare time values are interpreted as minutes.

## Project team

- Amiel Amido — Group leader
- Kevin James Riparip — Project team
- Rafael Carlos III — Project team

## Project files

`kernel_app.py` starts the application. The `kernel_sim` folder contains the interface and the individual simulation modules. `run.bat` is a Windows launcher, and `.vscode/launch.json` provides a VS Code debug configuration.

## Notes

This is an educational simulator. It demonstrates simplified models and does not control the computer's actual CPU, memory, or disks.
