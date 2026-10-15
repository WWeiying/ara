#!/usr/bin/env python3
"""Source-derived e8/m8/op2 prefix model and read-only Spike trace audit."""
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

NAME = 'gather_prefix_e8_m8_ops2'
CAP, BOUND, MAX_RETIRED = 1024, 112, 5_000_000


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def prefix(source, bound):
    require(bound == BOUND, 'e8m8 natural boundary must be112')
    anchor = '            ++cases;\n'
    require(source.count(anchor) == 1, 'Ambiguous original statistics boundary')
    source = source.replace(anchor, anchor + f'            if(cases=={bound})goto prefix_done;\n')
    marker = '    text(errors ? "RVV_PERMUTE_FAIL sew=":"RVV_PERMUTE_PASS sew=");'
    require(source.count(marker) == 1, 'Original final statistics changed')
    return source.replace(marker,
        f'prefix_done:\n    if(cases!={bound})++errors;\n'
        '    text(errors ? "RVV_GATHER_PREFIX_FAIL sew=":"RVV_GATHER_PREFIX_PASS sew=");')


def model():
    mask64 = (1 << 64) - 1
    rng, data, indices, indices16 = 0xe736815b449aec21, [], [], []
    for i in range(CAP):
        rng = (rng ^ (rng << 13)) & mask64
        rng ^= rng >> 7
        rng = (rng ^ (rng << 17)) & mask64
        data.append(rng & 255)
        index = (0, 1, CAP-1, CAP, CAP+1, rng % (CAP+32))[i % 6]
        indices.append(index & 255)
        indices16.append(index)
    rows = []
    for seed, op, scalar, length, mode, trial in itertools.product(
            range(3), range(21), range(8), range(7), range(4), range(4)):
        if op != 2:
            continue
        require(seed == scalar == 0, 'Prefix unexpectedly leaves first seed/scalar')
        vl = (0, 1, 2, 3, CAP//2, CAP-1, CAP)[length]
        start = (1, vl // 2, vl if vl <= 1023 else CAP-1, CAP-1)[trial]
        predicate, output = [0] * 128, [91] * CAP
        for i in range(CAP):
            pick = mode == 0 or (mode == 1 and i % 2 == 1) or (mode == 2 and i % 7 == 2)
            if pick:
                predicate[i // 8] |= 1 << (i % 8)
            if pick and start <= i < vl:
                output[i] = data[0]
        rows.append(dict(ordinal=len(rows)+1, tuple=[seed, op, scalar, length, mode, trial],
                         vl=vl, vstart=start, scalar=0, predicate=predicate, output=output))
        if len(rows) == BOUND:
            break
    require(rows[-1]['tuple'] == [0,2,0,6,3,3] and data[0] == 185, 'Source model endpoint')
    require([r['tuple'] for r in rows] ==
            [[0,2,0,l,m,t] for l in range(7) for m in range(4) for t in range(4)],
            'Complete seed0/scalar0 block membership/order')
    require(all([r['vstart'] for r in rows[96+m*4:100+m*4]] == [1,512,1023,1023]
                for m in range(4)), 'VL1024 original restart boundaries')
    digest = lambda a: hashlib.sha256(b''.join(x.to_bytes(1,'little') for x in a)).hexdigest()
    return dict(sew=8, lmul='m8', capacity=CAP, input=data, indices=indices, indices16=indices16,
                input_bytes_sha256=digest(data), index_bytes_sha256=digest(indices),
                rows=rows, excluded_ops0_through1_empty_iterations=1792, original_calls=2688,
                original_stopped_tuple=None, fullcap_checks=114688, guards=224)


class ReferenceBoundExceeded(ValueError):
    def __init__(self, evidence):
        super().__init__('NOT_COMPLETED_WITHIN_BOUND')
        self.evidence = evidence


def audit_trace(trace, elf, expected):
    routine = instructions(elf, NAME+'_op_2')
    require(len(routine) == 13 and routine[8]['insn'] == '30803c57', 'Original routine drift')
    lookup = {r['pc']:i for i,r in enumerate(routine)}
    addresses = {n:symbol(elf,n,OBJDUMP)[0] for n in
                 ('input','indices','indices16','predicate','output','replay_log','tohost')}
    exit_insns = instructions(elf,'replay_exit')
    exit_store, = [r for r in exit_insns if r['text'].startswith('sd\t')]
    regs, memory, counts, calls = {0:0}, {}, [0]*13, []
    vectors, csr = {}, {}
    current, step, retired, loads, exited = None, 0, 0, 0, False
    console = bytearray(8192)
    total_commits, last_pc = 0, None

    def group(first):
        require(all(n in vectors for n in range(first,first+8)), 'Missing actual vector source')
        return list(b''.join(vectors[n].to_bytes(128,'little') for n in range(first,first+8)))

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
    vector_pattern = re.compile(r'\bv(\d+)\s+0x([0-9a-f]+)')
    csr_pattern = re.compile(r'\bc\d+_(vstart|vl|vtype)\s+0x([0-9a-f]+)')
    accesses_pattern = re.compile(r'\bmem\s+0x([0-9a-f]+)(?:\s+0x([0-9a-f]+))?')
    with trace.open() as stream:
        for lineno, line in enumerate(stream, 1):
            require('trap_' not in line, 'Unexpected Spike trap')
            match = line_pattern.match(line)
            if not match:
                continue
            pc, code, rest = int(match[1],16), int(match[2],16), match[3]
            total_commits += 1
            last_pc = pc
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
            i = lookup.get(pc)
            if i is not None:
                i = lookup[pc]
                require(i == step and code == int(routine[i]['insn'],16), '13asm order/encoding')
                if i == 0:
                    finish()
                    j = len(calls)
                    require(j < BOUND, 'Extra original call')
                    gold = expected['rows'][j]
                    args = [addresses['input'], addresses['indices'], addresses['output']+1,
                            gold['vl'], CAP, addresses['predicate'], 0, gold['vstart']]
                    require([regs.get(n) for n in range(10,18)] == args, 'Actual call arguments differ')
                    for name, values, width in (
                        ('input',expected['input'],1), ('indices',expected['indices'],1),
                        ('indices16',expected['indices16'],2),
                        ('predicate',gold['predicate'],1), ('output',[91]*(CAP+2),1)):
                        for k, want in enumerate(values):
                            require(memory_value(addresses[name]+width*k,width) == want,
                                    f'Setup mismatch call{j+1} {name}[{k}]')
                    current = dict(ordinal=j+1, original_tuple=gold['tuple'], args=[hex(x) for x in args],
                                   setup_values_checked=4226, reads=set())
                    calls.append(current)
                require(rd is not None or i not in (0,5,9,10), 'Missing CSR/vset return')
                if i in (0,5,10):
                    require(int(rd[1])==5 and int(rd[2],16)==(gold['vl'] if i==5 else CAP), 'Actual VL return')
                if i == 8:
                    require((code >> 15) & 31 == 0, 'Unsigned immediate0 encoding')
                    require(csr.get('vl') == gold['vl'] and csr.get('vstart') == gold['vstart']
                            and csr.get('vtype') == 3, 'Actual target CSR')
                    require(group(8) == expected['input'] and group(16) == expected['indices']
                            and group(24) == [91]*CAP, 'Actual target vector inputs')
                    require(0 in vectors and vectors[0] & ((1 << CAP)-1) ==
                            int.from_bytes(bytes(gold['predicate'][:128]),'little'), 'Actual target predicate')
                    current['actual_source0'] = group(8)[0]
                    current['immediate_unsigned'] = 0
                    require(regs.get(28)==0 and regs.get(17)==gold['vstart'], 'Target scalar/start drift')
                    current['target'] = dict(pc=hex(pc), opcode=routine[i]['insn'], retired=retired,
                                             trace_line=lineno, vl=gold['vl'], vstart=gold['vstart'], scalar=0)
                if i == 9:
                    require(int(rd[1])==10 and int(rd[2],16)==0, 'vstart did not reset')
                    current['returned_vstart'] = 0
                if i == 11:
                    require(csr.get('vl') == CAP and group(24) == gold['output'], 'Actual store vector')
                    accesses = [(int(a,16),int(b,16) if b else None)
                                for a,b in accesses_pattern.findall(rest)]
                    require(accesses == [(addresses['output']+1+k,v)
                                         for k,v in enumerate(gold['output'])], 'Actual full vector store')
                counts[i] += 1
                step = (step+1) % 13
            for n, value in vector_pattern.findall(rest):
                vectors[int(n)] = int(value,16)
            for name, value in csr_pattern.findall(rest):
                csr[name] = int(value,16)
            if i in (0,5,10):
                require(csr.get('vl') == (gold['vl'] if i == 5 else CAP)
                        and csr.get('vtype') == 3, 'Actual vset state')
            if i == 8:
                require(group(24) == gold['output'] and csr.get('vstart') == 0,
                        'Actual target full result/reset')
            if current is not None and read and rd:
                address = int(read[1],16)
                if addresses['output'] <= address < addresses['output']+(CAP+2):
                    require(step==0 and code & 127 == 3 and ((code>>12)&7)==4,
                            'Oracle must be actual scalar LBU after complete routine')
                    index = address-addresses['output']
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
    if not exited and total_commits >= MAX_RETIRED:
        complete = sum('reads' not in c or c['reads'] == set(range(CAP+2)) for c in calls)
        raise ReferenceBoundExceeded(dict(reason='instruction_limit_without_htif_exit',
            total_commit_records=total_commits, firmware_retired=retired, last_pc=hex(last_pc),
            calls_entered=len(calls), calls_with_complete_oracle=complete, routine_counts=counts,
            scalar_output_reads=loads, last_call_tuple=current['original_tuple'] if current else None,
            last_call_oracle_reads=len(current['reads']) if current and 'reads' in current else None,
            last_call_asm_step=step, reconstructed_console=console.split(b'\0',1)[0].decode('ascii')))
    require(exited and len(calls)==BOUND and counts==[BOUND]*13 and loads==114912,
            'Incomplete calls/asm/oracle/exit')
    text = console.split(b'\0',1)[0].decode('ascii')
    require('RVV_GATHER_PREFIX_PASS sew=8 cases=112 errors=0' in text and
            f'BOARD_CASE_PASS {NAME}' in text and 'BOARD_REPLAY_PASS' in text and
            not re.search(r'FAIL|TRAP|MISMATCH|DETAIL|RVV_PERMUTE_PASS',text), 'Raw console veto')
    return dict(status='PASS_SPIKE_RAW112_SETUP_ASM_FULLORACLE_NOT_DUT',
                actual_full_vector_inputs_checks=112, actual_full_vector_result_checks=112,
                actual_full_vector_store_checks=112, actual_source0=expected['input'][0],
                target_hits=112, routine_retire_counts=counts, returned_vstart_zero=112,
                fullcap_scalar_checks=114688, both_guard_checks=224, output_scalar_loads=loads,
                total_commit_records_to_htif=total_commits,
                firmware_retired_to_htif_store=retired, htif_store_value=1,
                addresses={k:hex(v) for k,v in addresses.items()}, calls=calls,
                reconstructed_console=text, original_stopped_tuple=None)
