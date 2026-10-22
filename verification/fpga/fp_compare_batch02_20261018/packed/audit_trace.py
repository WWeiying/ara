#!/usr/bin/env python3
"""Read-only execution audit; writes only a new audit receipt, never runs Spike."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import prepare


def audit(directory):
    result = json.loads((directory / 'result.json').read_text())
    assert result['bound'] == 319 and result['reference']['status'] == 'SPIKE_PASS_NOT_DUT'
    for p, digest in result['files'].items():
        assert prepare.sha(p) == digest, p
    original = prepare.PARENT / prepare.CASES['319'][0] / 'original'
    rows, _, _ = prepare.model(original, 128, 1, 0, 319)
    helpers, current = {}, None
    for line in (directory / 'spike.dis').read_text().splitlines():
        m = re.match(r'^[0-9a-f]+ <op_(\d+)>:', line)
        if m: current = int(m[1]); helpers[current] = []
        elif re.match(r'^[0-9a-f]+ <', line): current = None
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+', line)
        if m and current is not None: helpers[current].append((int(m[1], 16), int(m[2], 16)))
    starts = {insns[0][0]: op for op, insns in helpers.items()}
    registers, active, completed, calls = [0] * 32, None, 0, []
    retired = 0
    with (directory / 'commits.log').open() as stream:
        for line in stream:
            m = re.match(r'^core\s+0:\s+[0-3]\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)', line)
            if not m: continue
            retired += 1
            pc, word = map(lambda v: int(v, 16), m.groups())
            if pc in starts:
                assert active is None and completed < len(rows)
                row = rows[completed]; op = starts[pc]
                assert op == row['op']
                assert [registers[i] for i in (13, 14, 16, 17)] == [row['vl'], 128, 0, row['sticky']]
                active = dict(ordinal=completed + 1, op=op, vl=row['vl'], sticky=row['sticky'],
                              args=registers[10:18], instruction_index=0, entry_retired=retired)
            if active is not None:
                expected = helpers[active['op']]
                assert (pc, word) == expected[active['instruction_index']]
                active['instruction_index'] += 1
                if active['instruction_index'] == len(expected):
                    status = registers[10]
                    assert status & 0xffffffff == 0 and status >> 32 == rows[completed]['flags']
                    active.update(returned_vstart=status & 0xffffffff, returned_flags=status >> 32,
                                  return_retired=retired)
                    calls.append(active); completed += 1; active = None
            for reg, value in re.findall(r'\bx\s*(\d+)\s+(0x[0-9a-f]+)', line):
                if int(reg): registers[int(reg)] = int(value, 16)
    assert completed == 319 and active is None
    assert retired == result['reference']['retired_to_htif_exit']
    receipt = dict(status='SPIKE_ACTUAL_319_HELPERS_ORDER_ARGUMENTS_FLAGS_VSTART_PASS_NOT_DUT',
                   retired_to_exit=retired, actual_calls=completed, calls=calls,
                   limitation='Inputs independently checked by host flow; no claim of raw-trace VRF numerical audit.')
    path = directory / 'trace_audit.json'
    assert not path.exists()
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['status'], retired)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    assert directory.is_relative_to(prepare.HERE)
    audit(directory)
