#!/usr/bin/env python3
"""Isolated import of the unchanged per-fixture CSV checker."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('kind', choices=['indexed', 'load', 'store', 'resident'])
p.add_argument('csv', type=Path)
p.add_argument('symbols', type=Path)
p.add_argument('out', type=Path)
a = p.parse_args()
if a.kind == 'resident':
    source = HERE.parent / 'indexed_overlap_original/repair06_worker'
    sys.path.insert(0, str(source))
    import checker
    result = checker.analyze(a.csv, a.symbols, {'fault':False, 'overlap':1})
else:
    source = HERE.parent / 'masked_translation' / (
        'indexed_early_illegal_sv39_prepare01' if a.kind == 'indexed' else 'mask_drain_sv39_prepare01')
    sys.path.insert(0, str(source))
    import dut_check
    result = dut_check.analyze(a.csv, json.loads(a.symbols.read_text()), int(a.kind == 'store'))
with a.out.open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
expected = {'indexed':'INDEXED_PREFIX_CSV_PASS','load':'MASK_DRAIN_CSV_PASS',
            'store':'MASK_DRAIN_CSV_PASS','resident':'CSV_FULL_ORACLE_PASS'}[a.kind]
print(result['status'], a.kind, flush=True)
raise SystemExit(int(result['status'] != expected))
