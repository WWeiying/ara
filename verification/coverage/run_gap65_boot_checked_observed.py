#!/usr/bin/env python3
"""Gap65 with corrected VCS boot-SP fixture; original observer/checks unchanged."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import run_gap65_late_fault_observed as observed

observed.HOST = observed.ROOT / 'verification/out/gap65-late-fault-preflight-20261004-04'
observed.SCRIPT = Path(__file__).resolve()

if __name__ == '__main__':
    raise SystemExit(observed.main())
