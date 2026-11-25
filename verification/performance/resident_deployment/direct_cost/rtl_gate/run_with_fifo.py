#!/usr/bin/env python3
"""Successor manifest: add the production FIFO required by the output buffer."""
import importlib.util
from pathlib import Path

source = Path(__file__).resolve().with_name('run.py')
spec = importlib.util.spec_from_file_location('resident_gate_original_runner', source)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.SOURCES.insert(runner.SOURCES.index('hardware/src/common_cells_compat/fall_through_register_v1.sv'),
                      runner.COMMON + 'src/fifo_v3.sv')
runner.EXTRA.append(str(Path(__file__).resolve().relative_to(runner.ROOT)))

if __name__ == '__main__':
    raise SystemExit(runner.main())
