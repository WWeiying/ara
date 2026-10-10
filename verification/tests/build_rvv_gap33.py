#!/usr/bin/env python3
"""Build mask/slide and CSR cases with the isolated non-ZCC workflow."""
import build_rvv_memory_gaps as builder

NAMES = [f'vcoverage_gap33_e{s}_m{m}' for s in (8, 16, 32, 64) for m in (1, 2, 4, 8)]
NAMES += ['linux_csr_gap33']

if __name__ == '__main__':
    builder.cases = lambda: [(name,) for name in NAMES]
    builder.main()
