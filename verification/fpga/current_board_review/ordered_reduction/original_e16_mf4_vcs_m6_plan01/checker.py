#!/usr/bin/env python3
"""Original e16/mf4 single: complete architectural CSV, no waveform claims."""
from collections import Counter
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'original_e16_mf4_prepare01'
sys.path.insert(0, str(HERE.parents[1] / 'gather_repair05'))
import regression as common

require, read, sha = common.require, common.read, common.sha
NAME = 'original_e16_mf4'
ELF_SHA = 'eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162'
OBJDUMP = HERE.parents[4] / 'install/riscv-gcc/bin/riscv64-unknown-elf-objdump'
MARKER = 'RVV_FP_REDSPECIAL_PASS sew=16 cases=1 flags_seen=16 errors=0'
VETO = re.compile(common.BAD.pattern + r'|\bRVV_FP_REDSPECIAL_DETAIL\b|\b(?:FAIL|FAILED|ABORT|ABORTED|TRAP|MISMATCH|DETAIL)\b', re.I)


def specification():
    elf = REF / 'soc/program.elf'
    require(sha(elf) == ELF_SHA, 'Original SoC ELF drift')
    text = subprocess.check_output([str(OBJDUMP), '-d', str(elf)], text=True)
    instructions = {m[1]: {'pc': int(m[1], 16), 'insn': m[2], 'text': m[3]} for m in
        re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)', text, re.M)}
    symbols = read(REF / 'soc/symbols.json')
    proof = read(REF / 'sourceproof.json')
    routine = [dict(pc=p, insn=i, text=t) for p, i, t in proof['helper_windows']['soc']['op_0']['new']]
    require(len(routine) == 21 and [r['insn'] for r in routine] ==
            [r[1] for r in proof['helper_windows']['soc']['op_0']['original']], 'Original21 proof mismatch')
    require(all(instructions[f'{r["pc"]:x}']['insn'] == r['insn'] for r in routine), 'Actual helper differs')
    # SoC globals permit GP relaxation absent in Spike; never translate main PCs by a fixed offset.
    selected = {'input_store': '00ff9023', 'seed_store': 'fefb1f23',
        'mask_store': '00e60023', 'output_init': '00c68023',
        'fixture_bits': '6398', 'fixture_flags': '479c', 'output_read': '00064803'}
    sites = {}
    for name, encoding in selected.items():
        found = [r for r in instructions.values() if r['insn'] == encoding and
                 symbols['original_e16_mf4_main'] <= r['pc'] < symbols['capacity']]
        require(len(found) == 1, 'Original C instruction not uniquely identified: ' + name)
        sites[name] = found[0]['pc']
    exit_rows = [r for r in instructions.values() if symbols['replay_exit'] <= r['pc'] < symbols['memcpy']]
    store, = [r for r in exit_rows if r['text'].startswith('sd\t')]
    park, = [r for r in exit_rows if r['pc'] > store['pc']]
    require(park['insn'] == 'a001', 'Original CTRL park')
    fixtures = [[int(a, 16), int(b)] for a, b in re.findall(
        r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}', (REF / 'prepared/fixtures.h').read_text())]
    require(len(fixtures) == 6720 and fixtures[4905] == [0x7e00, 16] and
            fixtures[1545] == [0x7c00, 0], 'Correct fixture bank')
    return dict(instructions=instructions, symbols=symbols, routine=routine, sites=sites,
                fixtures=fixtures, exit_store=store, park=park, exit_address=0xd0000000)


def console_gate(text):
    require(not VETO.search(text), 'Raw failure/DETAIL veto')
    lines = text.splitlines()
    for prefix, exact in [('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN ' + NAME),
                          ('RVV_FP_REDSPECIAL_PASS', MARKER),
                          ('BOARD_CASE_PASS', 'BOARD_CASE_PASS ' + NAME),
                          ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS'),
                          ('Core Test *** SUCCESS ***', common.SUCCESS)]:
        require([line for line in lines if line.startswith(prefix)] == [exact], 'Missing/ambiguous oracle: ' + prefix)
    require('$finish' in text, 'Missing simulator finish')


def retirement(rows, spec):
    symbols, sites, routine = spec['symbols'], spec['sites'], spec['routine']
    lookup = {r['pc']: i for i, r in enumerate(routine)}
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
             [('input', 1024), ('seed', 128), ('mask', 64), ('output', 144)]]

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
        require(pc not in (symbols['op_1'], symbols['op_2'], symbols['trap_entry']), 'Unexpected helper/trap')
        if pc == symbols['capacity']:
            capacity += 1
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
            require(i == step, 'Original21 order')
            if i == 0:
                require(not began, 'Duplicate original target')
                began = True
                require([regs.get(r) for r in range(10, 18)] == [symbols['input'], symbols['seed'],
                        symbols['output'] + 8, 8, 16, symbols['mask'], 0, 0], 'Original arguments')
                for name, expected in [('input', bytes.fromhex('007c00fc') * 8),
                                       ('seed', bytes.fromhex('007c') * 64),
                                       ('mask', b'\x24' * 64), ('output', b'\x5b' * 144)]:
                    require([memory.get(symbols[name] + j) for j in range(len(expected))] == list(expected),
                            'Full original setup: ' + name)
                require(len(fixtures) == 3092, 'Selected call must follow fixture row1545')
            returns = {0: (5, 64), 3: (5, 16), 6: (5, 8), 7: (29, 0), 8: (30, 0),
                       12: (10, 0), 13: (6, 16), 14: (6, 16 << 32), 15: (10, 16 << 32), 18: (5, 64)}
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
            expected = 0 if index == 8 else 0x7e if index == 9 else 0x5b
            require(address == symbols['output'] + index and rmask == 1 << (address % 8) and
                    rd == 16 and value == expected, 'Original144 LBU result/guards/tail')
            output.append(value)
        elif rmask and began and symbols['output'] <= address < symbols['output'] + 144:
            require(pc in lookup, 'Unexpected output oracle PC/type')
        if address == spec['exit_address'] and wmask:
            require(pc == spec['exit_store']['pc'] and wdata == 0 and wmask == 255, 'Original CTRL exit0')
            require(len(output) == 144 and len(helper) == 21 and step == 0, 'Incomplete oracle/helper at exit')
            exited = True
        if rd:
            regs[rd] = value
    require(exited and capacity == 1 and len(helper) == 21 and len(fixtures) == 6720 and
            dict(counts) == dict(input_store=128, seed_store=512, mask_store=215040, output_init=144),
            'Incomplete original loops/fixture/exit')
    return dict(status='PASS_RAW_ORIGINAL_SINGLE144', target=target, helper=helper, target_calls=1,
                fixture_bank=1, fixture_row=1545, selected_fixture=selected_fixture,
                fixture_field_reads=len(fixtures), initialization_counts=dict(counts), output_bytes=144,
                flags=16, vstart=0, result='0x7e00', csr_restoration='original writes retired with saved zero operands',
                vector_payload_scope='CSV scalar full-byte oracle, not direct vector-port/wave observation',
                csv_rows=total, retired_rows=retired, csv_last_cycle=last_cycle, post_exit_park=parked)


def artifacts(result, case, ledger, spec, validator):
    require(result.status == 'PASS' and result.name == NAME and not result.reason, 'Not exact single PASS')
    common.check_artifacts(result, case, ledger)
    for path in (result.artifact_dir / 'console.log', result.artifact_dir / 'work/run.vcs.log'):
        console_gate(path.read_text())
    path = result.artifact_dir / 'commit_trace.csv'
    generic = validator(path)
    require(generic['cvx_exception_count'] == 0 and generic['rows'] > 0, 'Generic trace/exception')
    with path.open(newline='') as stream:
        strict = retirement(csv.DictReader(stream), spec)
    require((strict['csv_rows'], strict['csv_last_cycle'], strict['retired_rows']) ==
            (generic['rows'], generic['last_cycle'], generic['retire_count']), 'Trace count disagreement')
    return dict(generic=generic, strict=strict, csv_sha256=sha(path))
