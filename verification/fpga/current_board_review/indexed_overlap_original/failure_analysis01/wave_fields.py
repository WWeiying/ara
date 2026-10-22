#!/usr/bin/env python3
"""Extract already-recorded AddrGen fields at the first bad address; no DUT."""
import json
from analyze import HERE, sha, save

path = HERE / 'compact.vcd'
base = 'ara_tb.dut.i_ara_soc.i_system.i_ara.'
addrgen = base + 'i_vlsu.i_addrgen.'
points = {3676605000, 3676645000, 3676785000}
scopes, declarations, wanted, state, samples = [], {}, {}, {}, []

def sample(t):
    if t in points:
        values = {}
        for code, name in wanted.items():
            value = state.get(code, 'x')
            values[name] = int(value, 2) if set(value) <= {'0', '1'} else value
        samples.append(dict(ticks=t, time_ns=t / 10000, values=values))

with path.open() as stream:
    for line in stream:
        s = line.split()
        if not s:
            continue
        if s[0] == '$scope':
            scopes.append(s[2])
        elif s[0] == '$upscope':
            scopes.pop()
        elif s[0] == '$var':
            name = '.'.join(scopes + [s[4]])
            if name.startswith(addrgen + 'pe_req_q.') or name in (
                    addrgen + 'mmu_vaddr_o', addrgen + 'idx_final_vaddr_q'):
                wanted[s[3]] = name
                declarations[name] = dict(code=s[3], width=int(s[2]), suffix=s[5:-1])
            elif name == base + 'i_dispatcher.eew_q' and s[5] in ('[4][2:0]', '[5][2:0]'):
                name += s[5].split(']')[0] + ']'
                wanted[s[3]] = name
                declarations[name] = dict(code=s[3], width=int(s[2]))
        elif s[0] == '$enddefinitions':
            break
    t = None
    for line in stream:
        s = line.strip()
        if not s:
            continue
        if s[0] == '#':
            sample(t)
            t = int(s[1:])
            if t > max(points):
                break
        elif s[0] in 'bB':
            value, code = s[1:].split()
            if code in wanted:
                state[code] = value
        elif s[0] in '01xXzZ' and s[1:] in wanted:
            state[s[1:]] = s[0]

assert len(samples) == 3
for item in samples:
    v = item['values']
    assert v[addrgen + 'pe_req_q.vstart'] == 15
    assert v[addrgen + 'pe_req_q.old_eew_vs2'] == 2
    assert v[addrgen + 'pe_req_q.eew_vs2'] == 3
    assert v[base + 'i_dispatcher.eew_q[4]'] == 2
    assert v[base + 'i_dispatcher.eew_q[5]'] == 3
assert samples[1]['values'][addrgen + 'mmu_vaddr_o'] == 0x4000a000
assert samples[2]['values'][addrgen + 'mmu_vaddr_o'] == 0x400040017000
assert samples[2]['values'][addrgen + 'idx_final_vaddr_q'] == 0x400040017000
frozen = __import__('pathlib').Path('/home/wangwy/fpga_runs/current_board_memory_candidate05/frozen/sources/hardware/src/vlsu/addrgen.sv')
save(HERE / 'wave_fields.json', dict(
    status='BAD_ADDRESS_OBSERVED_BEFORE_MMU_TRANSLATION',
    units='100fs', declarations=declarations, samples=samples,
    distinction='Request vstart remains 15; fault response CSR vstart is 16.',
    caveat='No operand payload or per-register physical layout transition is asserted by this decoder.',
    evidence_pins={str(p): sha(p) for p in (path, HERE / 'wave_fields.py',
                   HERE / 'first_error.json', HERE / 'wave_metadata.json', frozen)},
))
print(json.dumps(dict(status='BAD_ADDRESS_OBSERVED_BEFORE_MMU_TRANSLATION', samples=len(samples))))
