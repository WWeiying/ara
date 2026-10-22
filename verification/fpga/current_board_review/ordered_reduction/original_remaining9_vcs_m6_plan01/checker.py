#!/usr/bin/env python3
"""Nine authentic shapes, shared strict architectural CSV checker; no wave claims."""
from collections import Counter
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'original_remaining9_prepare01'
SHAPES = ['e16_mf2', 'e16_m1', 'e16_m2', 'e16_m4', 'e16_m8', 'e32_mf2', 'e32_m2', 'e32_m4', 'e32_m8']
READY_SHA = 'ad59b118f7b223b7deea74a04e43a63ff616705571748e01f0d18e1ce98d937c'
sys.path.insert(0, str(HERE.parents[1] / 'gather_repair05'))
import regression as common

require, read, sha = common.require, common.read, common.sha
OBJDUMP = HERE.parents[4] / 'install/riscv-gcc/bin/riscv64-unknown-elf-objdump'
def marker(spec):
    return f"RVV_FP_REDSPECIAL_PASS sew={spec['config']['sew']} cases=1 flags_seen=16 errors=0"
VETO = re.compile(common.BAD.pattern + r'|\bRVV_FP_REDSPECIAL_DETAIL\b|\b(?:FAIL|FAILED|ABORT|ABORTED|TRAP|MISMATCH|DETAIL)\b', re.I)


def is_rvv(insn):
    return insn & 127 == 0x57 or (insn & 127 in (0x07, 0x27) and (insn >> 12) & 7 in (0, 5, 6, 7))


def is_csr(insn):
    return insn & 127 == 0x73 and (insn >> 12) & 7 != 0


def specification(shape):
    require(shape in SHAPES and sha(REF / 'READY.json') == READY_SHA, 'Exact accepted reference membership')
    ref = REF / shape
    require(sha(ref / 'READY.json') == read(REF / 'READY.json')['case_ready_pins'][str(ref / 'READY.json')], 'Case READY drift')
    ready = read(ref / 'READY.json')
    elf = ref / 'soc/program.elf'
    require(sha(elf) == ready['soc_sha256'], 'Original SoC ELF drift')
    text = subprocess.check_output([str(OBJDUMP), '-d', str(elf)], text=True)
    instructions = {m[1]: {'pc': int(m[1], 16), 'insn': m[2], 'text': m[3]} for m in
        re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)', text, re.M)}
    symbols = read(ref / 'soc/symbols.json')
    proof = read(ref / 'sourceproof.json')
    c = proof['config']
    require(c['shape'] == shape, 'Source shape identity')
    routine = [dict(pc=p, insn=i, text=t) for p, i, t in proof['helper_windows']['soc']['op_0']['new']]
    require(len(routine) == 21 and [r['insn'] for r in routine] ==
            [r[1] for r in proof['helper_windows']['soc']['op_0']['original']], 'Original21 proof mismatch')
    require(all(instructions[f'{r["pc"]:x}']['insn'] == r['insn'] for r in routine), 'Actual helper differs')
    unused_ranges = []
    for name in ('op_1', 'op_2'):
        rows = proof['helper_windows']['soc'][name]['new']
        require(len(rows) == 21 and rows[0][0] == symbols[name] and
                all(instructions[f'{pc:x}']['insn'] == insn for pc, insn, _ in rows), 'Unused helper ELF drift')
        unused_ranges.append([rows[0][0], rows[-1][0] + len(rows[-1][1]) // 2])
    capacity_routine = [r for r in instructions.values() if symbols['capacity'] <= r['pc'] < symbols['op_0']]
    require(len(capacity_routine) == 3 and capacity_routine[0]['insn'] == '52fd' and
            capacity_routine[-1]['insn'] == '8082' and
            (int(capacity_routine[1]['insn'],16) >> 20) == ((8 if c['sew']==16 else 16) |
            {'mf2':7,'m1':0,'m2':1,'m4':2,'m8':3}[c['lmul']]), 'Original capacity3/type')
    csr_prelude = [r for r in instructions.values() if is_csr(int(r['insn'], 16)) and
                   (r['pc'] < symbols['trap_entry'] or symbols['main'] <= r['pc'] < symbols['text'] or
                    symbols[c['identity'] + '_main'] <= r['pc'] < symbols['capacity'])]
    require(len(csr_prelude)==7 and [r['insn'] for r in csr_prelude[:5]] == ['30401073', '30529073', '3002a073',
            '00305073', '00805073'] and all(int(r['insn'],16)&~0xf80 == 0xc2202073 for r in csr_prelude[5:]), 'Original startup/C CSR sequence')
    # SoC globals permit GP relaxation absent in Spike; never translate main PCs by a fixed offset.
    selected = {'input_store': '00ff9023' if c['sew']==16 else '00f2a023',
        'seed_store': 'fefb1f23' if c['sew']==16 else 'fefb2e23',
        'mask_store': '00e60023', 'output_init': '00c68023',
        'fixture_bits': '6398', 'fixture_flags': '479c', 'output_read': '00064803' if c['sew']==16 else '00064503'}
    sites = {}
    for name, encoding in selected.items():
        found = [r for r in instructions.values() if r['insn'] == encoding and
                 symbols[c['identity'] + '_main'] <= r['pc'] < symbols['capacity']]
        require(len(found) == 1, 'Original C instruction not uniquely identified: ' + name)
        sites[name] = found[0]['pc']
    exit_rows = [r for r in instructions.values() if symbols['replay_exit'] <= r['pc'] < symbols['memcpy']]
    store, = [r for r in exit_rows if r['text'].startswith('sd\t')]
    park, = [r for r in exit_rows if r['pc'] > store['pc']]
    require(park['insn'] == 'a001', 'Original CTRL park')
    fixtures = [[int(a, 16), int(b)] for a, b in re.findall(
        r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}', (ref / 'prepared/fixtures.h').read_text())]
    require(len(fixtures) == 6720 and fixtures[4905] == [c['nan'],16], 'Correct fixture bank')
    bits = [int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)', (ref/'prepared/input_bits.h').read_text())]
    require(len(bits)==16 and bits[12]==c['inf'], 'Original input constants')
    return dict(config=c, input_bits=bits, elf_sha256=ready['soc_sha256'], instructions=instructions, symbols=symbols, routine=routine, sites=sites,
                unused_ranges=unused_ranges, capacity_routine=capacity_routine, csr_prelude=csr_prelude,
                fixtures=fixtures, exit_store=store, park=park, exit_address=0xd0000000)



def input_value(bits, scenario, i, sew):
    if scenario == 0: return bits[i%2]
    if scenario == 1: return bits[14]
    if scenario == 2: return bits[2 if i%2 else 15]
    if scenario == 3: return bits[13 if i%2 else 12]
    if scenario == 4: return bits[[2,7,3,7,11,11][i%6]] ^ ((1<<(sew-1)) if i%6 in (3,5) else 0)
    if scenario == 5: return bits[[8,9,10,8,9,10][i%6]] ^ ((1<<(sew-1)) if i%6>=3 else 0)
    if scenario == 6: return bits[15 if i%2 else 2]
    return bits[7 if i%2 else 2]

def console_gate(text, spec):
    name = spec['config']['identity']
    require(not VETO.search(text), 'Raw failure/DETAIL veto')
    lines = text.splitlines()
    for prefix, exact in [('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN ' + name),
                          ('RVV_FP_REDSPECIAL_PASS', marker(spec)),
                          ('BOARD_CASE_PASS', 'BOARD_CASE_PASS ' + name),
                          ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS'),
                          ('Core Test *** SUCCESS ***', common.SUCCESS)]:
        require([line for line in lines if line.startswith(prefix)] == [exact], 'Missing/ambiguous oracle: ' + prefix)
    require('$finish' in text, 'Missing simulator finish')


def retirement(rows, spec):
    symbols, sites, routine = spec['symbols'], spec['sites'], spec['routine']
    c = spec['config']; width_bytes, cap = c['word_bytes'], c['cap']
    lookup = {r['pc']: i for i, r in enumerate(routine)}
    cap_routine = spec['capacity_routine']
    cap_lookup = {r['pc']: i for i, r in enumerate(cap_routine)}
    prelude = spec['csr_prelude']
    cap_steps = csr_steps = 0
    rvv_counts = Counter()
    regs, memory, counts = {0: 0}, {}, Counter()
    fixtures, output = [], []
    helper = []
    total = retired = parked = capacity = 0
    last_cycle = -1
    step = 0
    began = exited = False
    selected_fixture = []
    target = None
    areas = [(symbols[n], symbols[n] + size) for n, size in
             [('input', 512*width_bytes), ('seed', 64*width_bytes), ('mask', 64), ('output', 144)]]

    for line, row in enumerate(rows, 2):
        total += 1
        cycle = int(row['cycle'])
        require(cycle >= last_cycle and row['event'] != 'cvx_exception', 'Cycle reversal/exception')
        last_cycle = cycle
        if row['event'] != 'retire':
            continue
        require(int(row['order']) == retired and int(row['trap']) == 0, 'Retirement order/trap')
        retired += 1
        pc, insn = int(row['pc'], 16), int(row['insn'], 16)
        rd, value = int(row['rd']), int(row['rd_wdata'], 16)
        address, rmask, wmask, wdata = (int(row[n], 16) for n in
                                       ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        code = spec['instructions'].get(f'{pc:x}')
        require(code is not None and int(code['insn'], 16) == insn, 'Actual ELF instruction encoding/PC')
        if exited:
            require(pc == spec['park']['pc'] and insn == 0xa001 and rd == rmask == wmask == 0,
                    'Post-exit non-original park')
            parked += 1
            continue
        require(not any(lo <= pc < hi for lo, hi in spec['unused_ranges']), 'Unused helper PC range')
        require(pc != symbols['trap_entry'], 'Unexpected helper/trap')
        # Architectural retirements, not CVX requests, advance these one-shot windows.
        if 0 < cap_steps < 3:
            require(pc == cap_routine[cap_steps]['pc'], 'Capacity must retire all3 consecutively')
        if pc in cap_lookup:
            i = cap_lookup[pc]
            require(i == cap_steps and csr_steps == len(prelude) and not began, 'Capacity source phase/once')
            if i == 0:
                require((rd, value) == (5, (1 << 64) - 1), 'Capacity original AVL')
                capacity += 1
            elif i == 1:
                require((rd, value) == (10, cap) and regs.get(5) == (1 << 64) - 1, 'Capacity VLMAX result')
            cap_steps += 1
        if is_csr(insn) and pc not in lookup:
            require(cap_steps == 0 and not began and csr_steps < len(prelude) and
                    pc == prelude[csr_steps]['pc'], 'CSR outside original source phase')
            if (insn >> 20) == 0xc22:
                require(rd == (insn >> 7) & 31 and value == 128, 'Original C vlenb')
            csr_steps += 1
        if is_rvv(insn):
            require(pc in lookup or pc == cap_routine[1]['pc'], 'RVV outside capacity/op0 allowlist')
            require(rvv_counts[pc] == 0, 'Duplicate RVV retirement')
            rvv_counts[pc] += 1
        if wmask:
            if insn & 127 == 0x23:
                width = 1 << ((insn >> 12) & 7)
            elif insn & 3 in (0, 2) and insn >> 13 in (6, 7):
                width = 4 if insn >> 13 == 6 else 8
            else:
                require(not any(lo <= address < hi for lo, hi in areas), 'Unclassified scalar setup store')
                width = 0
            if width:
                require(width <= 8 and wmask == ((1 << width) - 1) << (address % 8), 'Scalar write byte enables')
                if any(lo <= address < hi for lo, hi in areas):
                    for b in range(width):
                        memory[address + b] = (wdata >> (8 * b)) & 255
        for name in ('input_store', 'seed_store', 'mask_store', 'output_init'):
            if pc == sites[name]:
                require(wmask != 0, 'Missing initialization memory effect')
                n = counts[name]
                if name == 'input_store':
                    scenario,index = divmod(n,cap)
                    require(scenario<8 and address==symbols['input']+index*width_bytes and
                            wdata==input_value(spec['input_bits'],scenario,index,c['sew']), 'Original all-scenario input initialization')
                elif name == 'seed_store':
                    scenario,index = divmod(n,64)
                    require(scenario<8 and address==symbols['seed']+index*width_bytes and
                            wdata==spec['input_bits'][[1,14,2,12,2,8,1,12][scenario]], 'Original seed64 initialization')
                elif name == 'mask_store':
                    fill,index = divmod(n,64)
                    require(fill<3360 and address==symbols['mask']+index and wdata==[255,0,85,36][(fill//15)%4], 'Original all-mode mask fill')
                else:
                    require(not began and n<144 and address==symbols['output']+n and wdata==91, 'Original output initialization')
                counts[name] += 1
        if pc in (sites['fixture_bits'], sites['fixture_flags']):
            field = 0 if pc == sites['fixture_bits'] else 8
            index = len(fixtures) // 2
            require(index < 3360 and len(fixtures) % 2 == field // 8, 'Fixture order')
            require(address == symbols['fixtures'] + (3360 + index) * 16 + field and
                    rmask == (255 if field == 0 else 15) and rd == (14 if field == 0 else 15) and
                    value == spec['fixtures'][3360 + index][field // 8], 'Fixture bank/order/value/load')
            fixtures.append(index)
            if index == 1545:
                selected_fixture.append(dict(address=hex(address), value=value, pc=hex(pc)))
        if step:
            require(pc == routine[step]['pc'], 'Helper must retire all21 consecutively')
        if pc in lookup:
            i = lookup[pc]
            require(cap_steps == 3 and csr_steps == len(prelude), 'op0 before complete source prelude')
            require((i == 0 and not began) or (i > 0 and began and step > 0), 'op0 interior outside one-shot window')
            require(i == step, 'Original21 order')
            if i == 0:
                require(not began, 'Duplicate original target')
                began = True
                require([regs.get(r) for r in range(10, 18)] == [symbols['input'], symbols['seed'],
                        symbols['output'] + 8, c['vl'], cap, symbols['mask'], 0, 0], 'Original arguments')
                for name, expected in [('input', b''.join(input_value(spec['input_bits'],3,j,c['sew']).to_bytes(width_bytes,'little') for j in range(cap))),
                                       ('seed', c['inf'].to_bytes(width_bytes,'little') * 64),
                                       ('mask', b'\x24' * 64), ('output', b'\x5b' * 144)]:
                    require([memory.get(symbols[name] + j) for j in range(len(expected))] == list(expected),
                            'Full original setup: ' + name)
                require(len(fixtures) == 3092, 'Selected call must follow fixture row1545')
            returns = {0: (5, 128//width_bytes), 3: (5, cap), 6: (5, c['vl']), 7: (29, 0), 8: (30, 0),
                       12: (10, 0), 13: (6, 16), 14: (6, 16 << 32), 15: (10, 16 << 32), 18: (5, 128//width_bytes)}
            if i in returns:
                require((rd, value) == returns[i], 'Helper vset/flags/vstart/saved CSR result')
            if i in (9, 10, 16, 17):
                src = (insn >> 15) & 31
                require(rd == 0 and regs.get(src) == 0, 'CSR request/restore saved operand')
            if i == 11:
                target = dict(pc=hex(pc), insn=f'{insn:08x}', cycle=cycle, retired=retired, csv_line=line)
            if i == 19:
                require(regs.get(12) == symbols['output'] + 8, 'Full-register destination store pointer')
            helper.append(dict(index=i, pc=hex(pc), insn=f'{insn:08x}', rd=rd, value=value, cycle=cycle))
            step = (step + 1) % 21
        if pc == sites['output_read']:
            index = len(output)
            require(began and step == 0 and len(helper) == 21 and index < 144, 'Oracle timing/count')
            expected = (b'\x5b'*8 + c['nan'].to_bytes(width_bytes,'little') + b'\x5b'*(136-width_bytes))[index]
            require(address == symbols['output'] + index and rmask == 1 << (address % 8) and
                    rd == (int(spec['instructions'][f"{pc:x}"]['insn'],16)>>7)&31 and value == expected, 'Original144 LBU result/guards/tail')
            output.append(value)
        elif rmask and began and symbols['output'] <= address < symbols['output'] + 144:
            require(pc in lookup, 'Unexpected output oracle PC/type')
        if address == spec['exit_address'] and wmask:
            require(pc == spec['exit_store']['pc'] and wdata == 0 and wmask == 255, 'Original CTRL exit0')
            require(len(output) == 144 and len(helper) == 21 and step == 0, 'Incomplete oracle/helper at exit')
            exited = True
        if rd:
            regs[rd] = value
    expected_rvv = {r['pc']: 1 for r in [*cap_routine, *routine] if is_rvv(int(r['insn'], 16))}
    require(dict(rvv_counts) == expected_rvv and cap_steps == 3 and csr_steps == len(prelude),
            'Missing exact RVV/capacity/CSR source sequence')
    require(exited and capacity == 1 and len(helper) == 21 and len(fixtures) == 6720 and
            dict(counts) == dict(input_store=8*cap, seed_store=512, mask_store=215040, output_init=144),
            'Incomplete original loops/fixture/exit')
    return dict(status='PASS_RAW_ORIGINAL_SINGLE144', target=target, helper=helper, target_calls=1,
                unused_helper_retirements=0, rvv_retirements=sum(rvv_counts.values()),
                capacity_instructions=cap_steps, outside_helper_csr_instructions=csr_steps,
                fixture_bank=1, fixture_row=1545, selected_fixture=selected_fixture,
                fixture_field_reads=len(fixtures), initialization_counts=dict(counts), output_bytes=144,
                shape=c['shape'], flags=16, vstart=0, result=hex(c['nan']), csr_restoration='original writes retired with saved zero operands',
                vector_payload_scope='CSV scalar full-byte oracle, not direct vector-port/wave observation',
                csv_rows=total, retired_rows=retired, csv_last_cycle=last_cycle, post_exit_park=parked)


def artifacts(result, case, ledger, spec, validator):
    require(result.status == 'PASS' and result.name == case['id'] and not result.reason, 'Not exact single PASS')
    common.check_artifacts(result, case, ledger)
    for path in (result.artifact_dir / 'console.log', result.artifact_dir / 'work/run.vcs.log'):
        console_gate(path.read_text(), spec)
    path = result.artifact_dir / 'commit_trace.csv'
    generic = validator(path)
    require(generic['cvx_exception_count'] == 0 and generic['rows'] > 0, 'Generic trace/exception')
    with path.open(newline='') as stream:
        strict = retirement(csv.DictReader(stream), spec)
    require((strict['csv_rows'], strict['csv_last_cycle'], strict['retired_rows']) ==
            (generic['rows'], generic['last_cycle'], generic['retire_count']), 'Trace count disagreement')
    return dict(generic=generic, strict=strict, csv_sha256=sha(path))

