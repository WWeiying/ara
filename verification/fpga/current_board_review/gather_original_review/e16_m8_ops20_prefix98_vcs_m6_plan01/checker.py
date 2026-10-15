#!/usr/bin/env python3
"""Strict e16/m8 ei16 prefix CSV gate, derived from the accepted prefix98 contract."""
import csv
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'e16_m8_ops20_prefix98_prepare01'
sys.path.insert(0, str(REF))
import reference_check as source
from reference_check import require, NAME, CAP, BOUND
sys.path.insert(0, str(HERE.parents[1] / 'gather_repair05'))
import regression as common

read, sha = common.read, common.sha
VETO = re.compile(common.BAD.pattern + r'|\bRVV_PERMUTE_DETAIL\b|\b(?:FAIL|FAILED|ABORT|ABORTED|TRAP|MISMATCH|DETAIL)\b'
                  r'|RVV_PERMUTE_PASS|RVV_GATHER_PREFIX_FAIL', re.I)


def specification(elf):
    routine = source.instructions(elf, NAME + '_op_20')
    proof = read(REF / 'source_elf_proof.json')
    require(routine == proof['soc_routine'] and len(routine) == 13 and
        [r['insn'] for r in routine] == [r['insn'] for r in proof['original_routine']], 'Original13 ELF drift')
    require(all('e16,m8,tu,mu' in routine[i]['text'] for i in (0, 5, 10)) and
            routine[8]['insn'] == '38880c57', 'Unexpected actual SEW/LMUL/operation')
    addresses = {n: source.symbol(elf, n, source.OBJDUMP)[0]
                 for n in ('input', 'indices', 'indices16', 'predicate', 'output')}
    exit_code = source.instructions(elf, 'replay_exit')
    store, = [r for r in exit_code if r['text'].startswith('sd\t')]
    park, = [r for r in exit_code if r['pc'] > store['pc']]
    require(park['insn'] == 'a001' and park['text'].startswith('j\t'), 'Not original CTRL park')
    return dict(sew=16, lmul=8, element_bytes=2, routine=routine, addresses=addresses,
                exit_store=store, exit_address=0xd0000000, park=park)


def console_gate(text):
    require(not VETO.search(text), 'Raw failure/abort/parent-marker veto')
    lines = text.splitlines()
    for prefix, exact in (('RVV_GATHER_PREFIX_PASS', 'RVV_GATHER_PREFIX_PASS sew=16 cases=98 errors=0'),
            ('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN ' + NAME), ('BOARD_CASE_PASS', 'BOARD_CASE_PASS ' + NAME),
            ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS'),
            ('Core Test *** SUCCESS ***', 'Core Test *** SUCCESS *** (tohost = 0)')):
        require([s for s in lines if s.startswith(prefix)] == [exact], 'Missing/ambiguous oracle: ' + prefix)


def retirement(rows, spec, model):
    routine, addresses = spec['routine'], spec['addresses']
    lookup = {r['pc']: i for i, r in enumerate(routine)}
    regs, memory, counts, calls = {0: 0}, {}, [0]*13, []
    current, step, retired, total, last_cycle, parked, exited = None, 0, 0, 0, -1, 0, False

    def finish():
        if current is not None:
            require(step == 0 and current['reads'] == set(range(CAP+2)), 'Missing full oracle/guards/asm')
            require(current.get('returned_vstart') == 0, 'Missing returned CSR')
            del current['reads']

    for line, row in enumerate(rows, 2):
        total += 1
        cycle = int(row['cycle'])
        require(cycle >= last_cycle and row['event'] != 'cvx_exception', 'Cycle reversal/exception')
        last_cycle = cycle
        if row['event'] != 'retire':
            continue
        require(int(row['order']) == retired and int(row['trap']) == 0, 'Retirement order/trap')
        retired += 1
        require(retired <= source.MAX_RETIRED, 'Retired sanity bound exceeded')
        pc, insn = int(row['pc'], 16), int(row['insn'], 16)
        rd, value = int(row['rd']), int(row['rd_wdata'], 16)
        address = int(row['mem_addr'], 16)
        rmask, wmask = int(row['mem_rmask'], 16), int(row['mem_wmask'], 16)
        if exited:
            require(pc == spec['park']['pc'] and insn == int(spec['park']['insn'], 16) and
                    rd == rmask == wmask == 0, 'Post-exit non-original park/side effect')
            parked += 1
            continue
        if wmask and insn & 127 == 0x23:
            width = 1 << ((insn >> 12) & 7)
            require(width <= 8, 'Invalid scalar store')
            raw = int(row['mem_wdata'], 16)
            for b in range(width):
                memory[address+b] = (raw >> (b*8)) & 255
        if insn == int(routine[8]['insn'], 16):
            require(pc == routine[8]['pc'], 'Extra target outside original routine')
        if pc in lookup:
            i = lookup[pc]
            require(i == step and insn == int(routine[i]['insn'], 16), 'Original13 order/encoding')
            if i == 0:
                finish()
                j = len(calls)
                require(j < BOUND, 'Extra call')
                gold = model['rows'][j]
                args = [addresses['input'], addresses['indices16'], addresses['output']+2,
                        gold['vl'], CAP, addresses['predicate'], gold['scalar'], gold['vstart']]
                require([regs.get(r) for r in range(10, 18)] == args, 'Actual call arguments differ')
                for name, values, width in (
                    ('input', model['input'], 2), ('indices', model['indices'], 2),
                    ('indices16', model['indices16'], 2), ('predicate', gold['predicate'], 1),
                    ('output', [91]*(CAP+2), 2)):
                    for k, want in enumerate(values):
                        got = [memory.get(addresses[name]+width*k+b) for b in range(width)]
                        require(None not in got, 'Missing initialized source bytes')
                        require(sum(v << (8*b) for b, v in enumerate(got)) == want,
                                f'Setup/RNG mismatch call{j+1} {name}[{k}]')
                current = dict(ordinal=j+1, original_tuple=gold['tuple'], reads=set(), setup_values_checked=2178)
                calls.append(current)
            if i in (0, 5, 10):
                require(rd == 5 and value == (gold['vl'] if i == 5 else CAP), 'Actual vsetvli return')
            if i == 8:
                require(regs.get(28) == gold['scalar'] and regs.get(17) == gold['vstart'] and
                        regs.get(13) == gold['vl'], 'Actual target scalar/start/VL')
                current['target'] = dict(pc=hex(pc), insn=routine[i]['insn'], cycle=cycle,
                    retired=retired, csv_line=line, vl=gold['vl'], vstart=gold['vstart'], scalar=gold['scalar'])
            if i == 9:
                require(rd == 10 and value == 0, 'Returned vstart nonzero')
                current['returned_vstart'] = 0
            counts[i] += 1
            step = (step+1) % 13
        if current is not None and rmask and addresses['output'] <= address < addresses['output']+2*(CAP+2):
            require(step == 0 and insn & 127 == 3 and (insn >> 12) & 7 == 5 and rd != 0,
                    'Oracle must be LHU after complete original asm')
            require((address-addresses['output']) % 2 == 0, 'Misaligned oracle')
            k = (address-addresses['output']) // 2
            require(k not in current['reads'], 'Duplicate oracle read')
            want = 91 if k in (0, CAP+1) else gold['output'][k-1]
            require(value == want, f'Full oracle mismatch call{len(calls)} index{k}')
            current['reads'].add(k)
        if address == spec['exit_address'] and wmask:
            require(pc == spec['exit_store']['pc'] and insn == int(spec['exit_store']['insn'], 16) and
                    int(row['mem_wdata'], 16) == 0, 'CTRL exit not original returncode0')
            finish()
            current, exited = None, True
        if rd:
            regs[rd] = value
    require(exited and len(calls) == BOUND and counts == [BOUND]*13, 'Missing calls/asm/exit')
    return dict(status='PASS_RAW98_FULL_SETUP_ORACLE', target_hits=98, calls=calls,
        routine_retire_counts=counts, returned_vstart_zero=98, fullcap_checks=50176, guards=196,
        actual_output_scalar_loads=50372, csv_rows=total, csv_last_cycle=last_cycle, retired_rows=retired,
        post_exit_park_retired=parked, soc_ctrl_exit=0, exact_historical_stopped_tuple=None)


def artifacts(result, case, ledger, spec, validator):
    require(result.status == 'PASS' and result.name == NAME and not result.reason, 'Not exact case PASS')
    common.check_artifacts(result, case, ledger)
    for path in (result.artifact_dir/'console.log', result.artifact_dir/'work/run.vcs.log'):
        console_gate(path.read_text())
    path = result.artifact_dir/'commit_trace.csv'
    generic = validator(path)
    require(generic['cvx_exception_count'] == 0 and generic['rows'] > 0, 'Generic trace/exception')
    with path.open(newline='') as stream:
        raw = retirement(csv.DictReader(stream), spec, source.model())
    require((raw['csv_rows'], raw['csv_last_cycle'], raw['retired_rows']) ==
            (generic['rows'], generic['last_cycle'], generic['retire_count']), 'Independent trace counts differ')
    return dict(generic=generic, strict=raw, csv_sha256=sha(path))

