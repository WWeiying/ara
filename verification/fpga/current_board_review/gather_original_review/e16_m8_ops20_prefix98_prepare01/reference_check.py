#!/usr/bin/env python3
"""Source-derived e16/m8/op20 prefix model and read-only Spike trace audit."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from audit_accepted8 import instructions, OBJDUMP
from prepare_successor import symbol

NAME = 'gather_prefix_e16_m8_ops20'
CAP, BOUND, MAX_RETIRED = 512, 98, 5_000_000


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def model():
    mask64 = (1 << 64) - 1
    rng, data, indices = 0xe736815b449aec21, [], []
    for i in range(CAP):
        rng = (rng ^ (rng << 13)) & mask64
        rng ^= rng >> 7
        rng = (rng ^ (rng << 17)) & mask64
        data.append(rng & 65535)
        indices.append((0, 1, 511, 512, 513, rng % 544)[i % 6])
    rows = []
    for seed, op, scalar, length, mode, trial in itertools.product(
            range(3), range(21), range(8), range(7), range(4), range(4)):
        if op != 20:
            continue
        require(seed == scalar == 0, 'Prefix unexpectedly leaves first seed/scalar')
        vl = (0, 1, 2, 3, 256, 511, 512)[length]
        start = (1, vl // 2, vl if vl <= 1023 else 511, 511)[trial]
        predicate, output = [0] * 128, [91] * CAP
        for i in range(CAP):
            pick = mode == 0 or (mode == 1 and i % 2 == 1) or (mode == 2 and i % 7 == 2)
            if pick:
                predicate[i // 8] |= 1 << (i % 8)
            if pick and start <= i < vl:
                output[i] = data[indices[i]] if indices[i] < CAP else 0
        rows.append(dict(ordinal=len(rows)+1, tuple=[seed, op, scalar, length, mode, trial],
                         vl=vl, vstart=start, scalar=0, predicate=predicate, output=output))
        if len(rows) == BOUND:
            break
    require(rows[-1]['tuple'] == [0,20,0,6,0,1] and data[0] == 61881, 'Source model endpoint')
    digest = lambda a: hashlib.sha256(b''.join(x.to_bytes(2,'little') for x in a)).hexdigest()
    return dict(sew=16, lmul='m8', capacity=CAP, input=data, indices=indices, indices16=indices,
                input_bytes_sha256=digest(data), index_bytes_sha256=digest(indices),
                rows=rows, excluded_ops0_through19_empty_iterations=17920, original_calls=2688,
                original_stopped_tuple=None, fullcap_checks=50176, guards=196)


def audit_trace(trace, elf, expected):
    routine = instructions(elf, NAME+'_op_20')
    require(len(routine) == 13 and routine[8]['insn'] == '38880c57', 'Original routine drift')
    lookup = {r['pc']:i for i,r in enumerate(routine)}
    addresses = {n:symbol(elf,n,OBJDUMP)[0] for n in
                 ('input','indices','indices16','predicate','output','replay_log','tohost')}
    exit_insns = instructions(elf,'replay_exit')
    exit_store, = [r for r in exit_insns if r['text'].startswith('sd\t')]
    regs, memory, counts, calls = {0:0}, {}, [0]*13, []
    current, step, retired, loads, exited = None, 0, 0, 0, False
    console = bytearray(8192)

    def finish():
        if current is not None:
            require(step == 0 and current['reads'] == set(range(CAP+2)), 'Missing oracle/guards or asm')
            require(current.get('returned_vstart') == 0, 'Missing returned vstart')
            current.pop('reads')

    def memory_value(address, width):
        require(all(address+i in memory for i in range(width)), 'Missing initialized source bytes')
        return sum(memory[address+i] << (8*i) for i in range(width))

    line_pattern = re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    rd_pattern = re.compile(r'\bx(\d+)\s+(0x[0-9a-f]+)')
    write_pattern = re.compile(r'\bmem\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*$')
    read_pattern = re.compile(r'\bmem\s+(0x[0-9a-f]+)\s*$')
    with trace.open() as stream:
        for lineno, line in enumerate(stream, 1):
            require('trap_' not in line, 'Unexpected Spike trap')
            match = line_pattern.match(line)
            if not match:
                continue
            pc, code, rest = int(match[1],16), int(match[2],16), match[3]
            if pc < 0x80000000:
                continue
            retired += 1
            require(retired <= MAX_RETIRED, 'Retired budget exceeded')
            rd, write, read = rd_pattern.search(rest), write_pattern.search(rest), read_pattern.search(rest)
            if write and code & 127 == 35:
                address, value = int(write[1],16), int(write[2],16)
                width = 1 << ((code >> 12) & 7)
                require(width <= 8, 'Invalid scalar store width')
                for byte in range(width):
                    memory[address+byte] = (value >> (8*byte)) & 255
                if width == 1 and addresses['replay_log'] <= address < addresses['replay_log']+8192:
                    console[address-addresses['replay_log']] = value & 255
            if pc in lookup:
                i = lookup[pc]
                require(i == step and code == int(routine[i]['insn'],16), '13asm order/encoding')
                if i == 0:
                    finish()
                    j = len(calls)
                    require(j < BOUND, 'Extra original call')
                    gold = expected['rows'][j]
                    args = [addresses['input'], addresses['indices16'], addresses['output']+2,
                            gold['vl'], CAP, addresses['predicate'], 0, gold['vstart']]
                    require([regs.get(n) for n in range(10,18)] == args, 'Actual call arguments differ')
                    for name, values, width in (
                        ('input',expected['input'],2), ('indices',expected['indices'],2),
                        ('indices16',expected['indices16'],2),
                        ('predicate',gold['predicate'],1), ('output',[91]*(CAP+2),2)):
                        for k, want in enumerate(values):
                            require(memory_value(addresses[name]+width*k,width) == want,
                                    f'Setup mismatch call{j+1} {name}[{k}]')
                    current = dict(ordinal=j+1, original_tuple=gold['tuple'], args=[hex(x) for x in args],
                                   setup_values_checked=2178, reads=set())
                    calls.append(current)
                require(rd is not None or i not in (0,5,9,10), 'Missing CSR/vset return')
                if i in (0,5,10):
                    require(int(rd[1])==5 and int(rd[2],16)==(gold['vl'] if i==5 else CAP), 'Actual VL return')
                if i == 8:
                    require(regs.get(28)==0 and regs.get(17)==gold['vstart'], 'Target scalar/start drift')
                    current['target'] = dict(pc=hex(pc), opcode=routine[i]['insn'], retired=retired,
                                             trace_line=lineno, vl=gold['vl'], vstart=gold['vstart'], scalar=0)
                if i == 9:
                    require(int(rd[1])==10 and int(rd[2],16)==0, 'vstart did not reset')
                    current['returned_vstart'] = 0
                counts[i] += 1
                step = (step+1) % 13
            if current is not None and read and rd:
                address = int(read[1],16)
                if addresses['output'] <= address < addresses['output']+2*(CAP+2):
                    require(step==0 and code & 127 == 3 and ((code>>12)&7)==5,
                            'Oracle must be actual scalar LHU after complete routine')
                    require((address-addresses['output'])%2==0, 'Misaligned oracle element')
                    index = (address-addresses['output'])//2
                    require(index not in current['reads'], 'Duplicate scalar output read')
                    want = 91 if index in (0,CAP+1) else gold['output'][index-1]
                    require(int(rd[2],16)==want, f'Output mismatch call{len(calls)} index{index}')
                    current['reads'].add(index)
                    loads += 1
            if pc == exit_store['pc']:
                require(write and int(write[1],16)==addresses['tohost'] and int(write[2],16)==1,
                        'HTIF exit not zero')
                finish()
                exited = True
                break
            if rd:
                regs[int(rd[1])] = int(rd[2],16)
    require(exited and len(calls)==BOUND and counts==[BOUND]*13 and loads==50372,
            'Incomplete calls/asm/oracle/exit')
    text = console.split(b'\0',1)[0].decode('ascii')
    require('RVV_GATHER_PREFIX_PASS sew=16 cases=98 errors=0' in text and
            f'BOARD_CASE_PASS {NAME}' in text and 'BOARD_REPLAY_PASS' in text and
            not re.search(r'FAIL|TRAP|MISMATCH|DETAIL|RVV_PERMUTE_PASS',text), 'Raw console veto')
    return dict(status='PASS_SPIKE_RAW98_SETUP_ASM_FULLORACLE_NOT_DUT',
                target_hits=98, routine_retire_counts=counts, returned_vstart_zero=98,
                fullcap_scalar_checks=50176, both_guard_checks=196, output_scalar_loads=loads,
                firmware_retired_to_htif_store=retired, htif_store_value=1,
                addresses={k:hex(v) for k,v in addresses.items()}, calls=calls,
                reconstructed_console=text, original_stopped_tuple=None)

