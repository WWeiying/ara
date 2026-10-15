#!/usr/bin/env python3
"""Read-only audit of prepared original-prefix inputs; no simulator invocation."""
import collections
import json
import re
from pathlib import Path
from recover import HERE, ARCH, NAME, EXPECTED, sha, save


def main():
    out = HERE / 'prepared01'
    pins = json.loads((out / 'pins.json').read_text())
    assert all(sha(path) == digest for path, digest in pins.items())
    assert (HERE / 'recovery01' / NAME).read_bytes() == (ARCH / 'overlay/opt/ara-tests' / NAME).read_bytes()
    assert sha(HERE / 'recovery01' / NAME) == EXPECTED
    assert (out / 'prepared/original/scenario.S').read_bytes() == (ARCH / (NAME + '.S')).read_bytes()
    assert (out / 'prepared/original/operations.h').read_bytes() == (ARCH / 'operations.h').read_bytes()
    calls = json.loads((out / 'host/expected_calls.json').read_text())
    assert len(calls) == 777 and [r['trial'] for r in calls] == list(range(777))
    soc = json.loads((out / 'soc/programs.json').read_text())['programs']['fixed_e8_m4_prefix777']
    spike = json.loads((out / 'reference/status.json').read_text())
    assert sha(soc['path']) == soc['sha256']
    # The whole vector helper body is position-independent and must retain its
    # instruction bytes, not merely contain the same target opcode somewhere.
    old = (HERE / 'recovery01/original.dis').read_text()
    new = (out / 'soc/fixed_e8_m4_prefix777.dis').read_text()
    instructions = lambda text: [(int(m[1], 16), m[2]) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s', text, re.M)]
    old_body = [bits for pc, bits in instructions(old) if 0x10918 <= pc <= 0x10970]
    symbols = json.loads((out / 'soc/symbols.json').read_text())
    new_body = [bits for pc, bits in instructions(new) if symbols['op_0'] <= pc < symbols['op_1']]
    assert old_body == new_body and len(old_body) > 10
    result = dict(status='READY_PREFIX777_REFERENCE_ONLY', original_elf_sha256=EXPECTED,
        original_c_bytes_recovered=False, full_linux_elf_byte_rebuilt=True,
        pins_checked=len(pins), pins_unchanged=True, op0_instruction_bytes_identical=True,
        op0_instructions=len(old_body), original_target_pc='0x1094e', soc_target_pc=hex(soc['target_pc']),
        soc_elf_sha256=soc['sha256'], calls=777, seeds=sorted({r['seed'] for r in calls}),
        operators=sorted({r['op'] for r in calls}),
        vxrm_counts=dict(collections.Counter(r['vxrm'] for r in calls)),
        initial_vxsat_counts=dict(collections.Counter(r['initial_vxsat'] for r in calls)),
        no_active_window_calls=sum(r['vstart'] >= r['vl'] for r in calls), last_tuple=calls[-1],
        reference=spike, original_complete_calls=10752, original_linux_replayed=False, DUT_started=False)
    path = HERE / 'audit01.json'
    assert not path.exists()
    save(path, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
