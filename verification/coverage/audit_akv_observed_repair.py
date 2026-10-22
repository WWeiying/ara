"""Full ORIGINAL AKV software oracle plus independently checked observed state.

No new simulation, interpreter, full32VRF claim, or coverage admission. Image and
normal exit are separately pinned by the parent runner. This does not alter the
historical HOLD records: it implements the explicitly approved observed scope.
"""
import argparse
import json
from pathlib import Path

import audit_extra_acceptance_20261008 as extra
import review_akv_budget_native_evidence as native

original = extra.original
require = extra.require
CASES = {original.DESCRIPTOR: 'descriptor', original.SKEW: 'skew'}


def source(name):
    require(name in CASES, 'Unknown original AKV case')
    return extra.descriptor.RUNS[name]


def audit(directory, name):
    directory = Path(directory).resolve()
    require(name in CASES, 'Unknown original AKV case')
    expected_sha = extra.HASHES[CASES[name]]
    elf = directory/'input.elf'
    require(extra.sha(elf) == extra.sha(source(name)/'input.elf') == expected_sha,
            'Original ELF only; no modified stimulus')
    paths = [elf, directory/'commit_trace.csv', directory/'run.vcs.log',
             directory/'console.log', directory/'trace_hart_0.log']
    pins = {str(p): extra.sha(p) for p in paths}
    core = original.verify(name, directory, elf.read_bytes(), 2097152)
    symbols = core['elf_layout']['symbols']
    if name == original.DESCRIPTOR:
        rows = list(extra.rows(directory/'commit_trace.csv'))
        readback = extra.descriptor.descriptor_readback(rows, symbols)
        architectural = native.descriptor_architecture(rows, core['elf_layout'],
                                                        (directory/'trace_hart_0.log').read_text())
        require(architectural['precise_trap_CSR_reads'] == 69, 'All23 trap CSR triplets required')
        unobserved = ['command-boundary vl/vtype/vstart/fflags', 'full32VRF/native vector write ports']
    else:
        readback = extra.skew_readback(extra.rows(directory/'commit_trace.csv'), symbols)
        require(len(core['protocol']['snapshots']) == 24, 'All12 fflags/vstart pairs required')
        architectural = dict(protocol=core['protocol'], precise_boundary_CSR_reads=24,
                             trap_count=core['protocol']['exceptions'])
        unobserved = ['command-boundary vl/vtype', 'full32VRF/native vector write ports']
    require(all(extra.sha(p) == h for p, h in pins.items()), 'Evidence drift during audit')
    return dict(status='PASS', qualification='ORIGINAL_COMPLETE_OBSERVED_ARCHITECTURE',
                case=name, ELF_sha256=expected_sha, original_checks=core['checks'],
                independent_readback=readback, observed_architecture=architectural,
                original_protocol=core['protocol'], original_uart_and_perf=core['uart'],
                privilege=core['privilege'], input_pins=pins, checker_sha256=extra.sha(__file__),
                unobserved_not_claimed=unobserved, full_scalar_ISA_comparison_claimed=False,
                coverage_admitted=False, current_RTL_acceptance_inferred=False,
                original_checks_removed=False, new_simulation_started=False,
                runner_obligations='Verify normal exit and image/config pins; replay original ELF to claim current RTL, and qualify same-image VDB separately.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=CASES, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(not args.output.exists(), 'Fresh report required')
    result = audit(args.run, args.case)
    with args.output.open('x') as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write('\n')
    print(json.dumps(dict(case=args.case, status=result['status'], output=str(args.output),
                         qualification=result['qualification'], coverage_admitted=False)))
