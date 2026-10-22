#!/usr/bin/env python3
"""Synthetic protocol-boundary probes with real helper opcodes, not full fixture evidence."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
AUTHOR = HERE.parent / 'segment_full144_vcs_m8_plan01'
FROZEN = Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/frozen/sources')
sys.path.insert(0, str(FROZEN / 'verification'))
from ara_verify.trace import validate_trace

spec = importlib.util.spec_from_file_location('independent_segment_backend', AUTHOR / 'checker.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
actual = c.specification()
codes = {int(p): i for p, i in actual['code'].items()}
target = actual['symbols']['target_0']
staging = next(p for p in actual['helpers']['op_0']['pcs']
               if codes[p] & 127 == 7 and (codes[p] >> 12) & 7 in (0, 5, 6, 7)
               and p != target)


def probe(label, case, second_target=False, drop=None, fault=False):
    observer = c.Checker(actual)
    observer.current = case
    rows = []

    def emit(event, owner, pc, trap=0):
        row = dict.fromkeys(c.FIELDS, '0')
        row.update(cycle=str(len(rows)), event=event, order=str(owner), port='0',
                   trans_id=str(owner), pc=f'{pc:016x}', insn=f'{codes[pc]:08x}', trap=str(trap))
        observer.event(row, codes[pc])
        rows.append(row)

    for owner, pc in enumerate((staging, target if second_target else staging)):
        emit('arch_start', owner, pc)
        emit('cvx_req', owner, pc)
        if owner != drop:
            emit('uop_alloc', owner, pc)
            emit('uop_done', owner, pc)
        emit('cvx_resp', owner, pc, int(fault and owner == 1))
        if not (fault and owner == 1):
            emit('retire', owner, pc)
    with tempfile.TemporaryDirectory(prefix='segment-backend-boundary-') as tmp:
        path = Path(tmp) / 'trace.csv'
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=c.FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        generic = validate_trace(path)
    assert generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] > 0
    try:
        coverage = observer.backend_coverage()
    except ValueError as error:
        return dict(label=label, generic_accepted=True, strict_accepted=False, reason=str(error))
    return dict(label=label, generic_accepted=True, strict_accepted=True, coverage=coverage)


tests = [probe('two_real_staging_owners', 0),
         probe('whole_staging_pair_removed', 0, drop=0),
         probe('alloff_VL1_target_pair_removed', 3, second_target=True, drop=1),
         probe('alloff_VL1_target_pair_present', 3, second_target=True),
         probe('VL0_target_legally_no_uop', 0, second_target=True, drop=1),
         probe('actual_eligible_early_fault_no_target_uop', 8, second_target=True, drop=1, fault=True)]
assert [t['strict_accepted'] for t in tests] == [True, False, False, True, True, True]
print(json.dumps(dict(status='FOCUSED_BACKEND_BOUNDARY_PASS', tests=tests,
                     checker_sha256=hashlib.sha256((AUTHOR / 'checker.py').read_bytes()).hexdigest(),
                     trace_validator_sha256=hashlib.sha256((FROZEN / 'verification/ara_verify/trace.py').read_bytes()).hexdigest(),
                     scope='Synthetic event ledger only; real ELF opcodes; no full Checker.row or fixture-state validation',
                     actual_raw_parses=0, DUT_runs=0, source_oracle_runs=0), indent=2))
