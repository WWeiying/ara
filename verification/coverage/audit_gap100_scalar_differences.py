"""All-instruction GAP100 scalar difference inventory; no normalization/admission."""
import argparse
import json
from pathlib import Path

import check_gap100_runtime as runtime

require = runtime.require


def differences(spike, dut):
    require(len(spike) == len(dut), "Instruction populations differ; no stuttering applied")
    rows = []
    for index, (a, b) in enumerate(zip(spike, dut)):
        require((a.pc, a.instruction) == (b.pc, b.instruction), "Window/outside-window PC or instruction mismatch")
        require(not a.vector_writes and not a.fpr_writes, "Unexpected vector/FP instruction result")
        if a.gpr_writes == b.gpr_writes and a.memory_accesses == b.memory_accesses:
            continue
        fields = dict(index=index, pc=hex(a.pc), insn=hex(a.instruction),
                      spike_gpr=a.gpr_writes, dut_gpr=b.gpr_writes,
                      spike_memory=a.memory_accesses, dut_memory=b.memory_accesses)
        changed_values = []
        same_shape = a.gpr_writes.keys() == b.gpr_writes.keys() and len(a.memory_accesses) == len(b.memory_accesses)
        if same_shape:
            changed_values += [(a.gpr_writes[k], b.gpr_writes[k]) for k in a.gpr_writes
                               if a.gpr_writes[k] != b.gpr_writes[k]]
            for (address_a, value_a), (address_b, value_b) in zip(a.memory_accesses, b.memory_accesses):
                same_shape &= address_a == address_b and (value_a is None) == (value_b is None)
                if value_a != value_b:
                    changed_values.append((value_a, value_b))
        fields['bit7_only_value_difference'] = bool(same_shape and changed_values and
            all(x is not None and y is not None and x ^ y == 0x80 for x, y in changed_values))
        rows.append(fields)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == runtime.OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    pre = runtime.runner.life.read_bound(runtime.runner.PRE / 'preflight-manifest.json', runtime.runner.PRE_SEAL)
    manifest = runtime.runner.life.read_bound(runtime.RUN / 'manifest.json', runtime.RUN_SEAL)
    pins = runtime.runner.life.merge_pins(manifest['pins'], {
        str(runtime.RUN / 'manifest.json'): runtime.RUN_SEAL,
        str(runtime.runner.PRE / 'preflight-manifest.json'): runtime.runner.PRE_SEAL})
    for path in (runtime.RUN / 'commit_trace.csv', runtime.RUN / 'simulation-status.json',
                 Path(__file__).resolve(), Path(__file__).with_name('test_audit_gap100_scalar_differences.py'),
                 Path(runtime.__file__).resolve()):
        pins = runtime.runner.life.merge_pins(pins, {str(path): runtime.runner.life.digest(path)})
    runtime.runner.life.check(pins)
    status = json.loads((runtime.RUN / 'simulation-status.json').read_bytes())
    require(status.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and status.get('returncode') == 0,
            'Run not terminal-successful')
    spike = runtime.software.shared.parse_spike_commits(Path(pre['input_spike_trace']))
    start = next(i for i, c in enumerate(spike) if c.pc == 0x80000000)
    spike = spike[start:]
    terminals = [i for i, c in enumerate(spike) if (pre['symbols']['tohost'], 1) in c.memory_accesses]
    require(len(terminals) == 1, 'Ambiguous Spike terminal')
    spike = spike[:terminals[0] + 1]
    dut = runtime.retired_commits(runtime.commit_rows(runtime.RUN / 'commit_trace.csv'))
    require(dut[-1].memory_accesses == ((pre['symbols']['tohost'], 1),), 'Incomplete DUT terminal')
    result = differences(spike, dut)
    runtime.runner.life.check(pins)
    artifact = dict(status='GAP100_ALL_SCALAR_DIFFERENCES_DIAGNOSTIC_NOT_QUALIFIED',
        instructions=len(dut), all_pc_instructions_equal=True, difference_count=len(result),
        bit7_only_value_differences=sum(r['bit7_only_value_difference'] for r in result),
        differences=result, input_pins=pins, normalization_performed=False,
        scalar_comparison_qualified=False, coverage_admitted=False,
        limitations=['Bit7 classification does not prove def-use provenance or authorize dropping differences.',
                     'DUT trace does not directly expose all CSR write effects; separate trap/state audit required.'])
    runtime.save(out, artifact)
    print(json.dumps(dict(output=str(out), seal=runtime.runner.life.digest(out),
                         instructions=len(dut), differences=len(result), coverage_admitted=False)))


if __name__ == '__main__':
    main()
