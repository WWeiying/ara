#!/usr/bin/env python3
"""Successor: testbench clock process permits a declaration-time counter init."""
import importlib.util
from pathlib import Path

source = Path(__file__).resolve().with_name('run_with_fifo.py')
spec = importlib.util.spec_from_file_location('resident_gate_fifo_runner', source)
fifo_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fifo_runner)
runner = fifo_runner.runner
old = str((runner.HERE / 'akv_gate_tb.sv').relative_to(runner.ROOT))
runner.SOURCES[runner.SOURCES.index(old)] = str((runner.HERE / 'akv_gate_clockfix_tb.sv').relative_to(runner.ROOT))
runner.EXTRA.append(str(Path(__file__).resolve().relative_to(runner.ROOT)))

if __name__ == '__main__':
    raise SystemExit(runner.main())
