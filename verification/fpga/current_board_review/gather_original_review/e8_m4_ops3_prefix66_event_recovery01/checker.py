#!/usr/bin/env python3
"""Full original m4 setup and scalar RVFI oracle; no Golden-result acceptance."""
import csv
import importlib.util
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from newscope import *

HERE = Path("/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/gather_original_review/e8_m4_ops3_prefix66_vcs_m6_plan01")
REF = HERE.parent / 'e8_m4_ops3_prefix66_prepare01'
sys.path.insert(0, str(REF))
module_spec = importlib.util.spec_from_file_location('owned_m4_source_reference', REF / 'reference_check.py')
source = importlib.util.module_from_spec(module_spec)
sys.modules[module_spec.name] = source
module_spec.loader.exec_module(source)
sys.path.insert(0, str(HERE.parents[1] / 'gather_repair05'))
import regression as common

require, read, sha = source.require, common.read, common.sha
VETO = re.compile(common.BAD.pattern + r'|\bRVV_PERMUTE_DETAIL\b|\b(?:FAIL|FAILED|ABORT|ABORTED|TRAP|MISMATCH|DETAIL)\b'
                  r'|RVV_PERMUTE_PASS|RVV_GATHER_PREFIX_FAIL', re.I)


def model():
    result = source.model()
    require(result['capacity'] == CAP and result['lmul'] == LMUL and len(result['rows']) == BOUND,
            'Source model physical scope drift')
    require(result['rows'][-1]['tuple'] == ENDPOINT and result['input'][31] == 177,
            'Source model endpoint/immediate drift')
    require(all(len(r['output']) == CAP and len(r['predicate']) == PREDICATE_BYTES and
                r['predicate'][LOGICAL_MASK_BYTES:] == [0]*LOGICAL_MASK_BYTES for r in result['rows']),
            'Physical predicate/model drift')
    return result


def specification(elf):
    require(sha(elf) == SOC_ELF_SHA, 'Frozen source ELF drift')
    proof = read(REF / 'source_elf_proof.json')
    routine = source.instructions(elf, RUNTIME_ID + '_op_3')
    require(routine == proof['soc_routine'] and len(routine) == 13 and
            [r['insn'] for r in routine] == [r['insn'] for r in proof['original_routine']],
            'Original13 ELF drift')
    require(all('e8,m4,tu,mu' in routine[i]['text'] for i in (0, 5, 10)) and
            routine[8]['insn'] == '308fbc57', 'Unexpected m4/immediate encoding')
    addresses = {name: source.symbol(elf, name, source.OBJDUMP)[0]
                 for name in ('input', 'indices', 'indices16', 'predicate', 'output')}
    predicate_size = source.symbol(elf, 'predicate', source.OBJDUMP)[1]
    require(predicate_size == PREDICATE_BYTES, 'Physical predicate storage must be128')
    capacity = source.instructions(elf, RUNTIME_ID + '_capacity')[1]
    require(capacity['insn'] == '0022f557', 'Actual capacity m4 encoding')
    exit_code = source.instructions(elf, 'replay_exit')
    store, = [r for r in exit_code if r['text'].startswith('sd\t')]
    park, = [r for r in exit_code if r['pc'] > store['pc']]
    require(park['insn'] == 'a001' and park['text'].startswith('j\t'), 'Original CTRL park required')
    disassembly = subprocess.check_output([str(source.OBJDUMP), '-d', str(elf)], text=True, timeout=30)
    code = {}
    for line in disassembly.splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)', line)
        if match:
            code[str(int(match[1], 16))] = int(match[2], 16)
    require(code, 'Empty ELF instruction map')
    return dict(sew=SEW, lmul=LMUL_REGS, capacity=CAP, physical_predicate_bytes=PREDICATE_BYTES,
                routine=routine, capacity_vset=capacity, addresses=addresses, code=code,
                exit_store=store, exit_address=0xd0000000, park=park)


def console_gate(text):
    require(not VETO.search(text), 'Raw PASS+FAIL/abort/detail veto')
    for prefix, exact in (
            ('RVV_GATHER_PREFIX_PASS', 'RVV_GATHER_PREFIX_PASS sew=8 cases=66 errors=0'),
            ('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN '+RUNTIME_ID),
            ('BOARD_CASE_PASS', 'BOARD_CASE_PASS '+RUNTIME_ID),
            ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS'),
            ('Core Test *** SUCCESS ***', 'Core Test *** SUCCESS *** (tohost = 0)')):
        require([line for line in text.splitlines() if line.startswith(prefix)] == [exact],
                'Missing/ambiguous runtime oracle: '+prefix)
    require('$finish' in text, 'Missing raw simulator completion')


def retirement(rows, spec, expected):
    require((spec['sew'], spec['lmul'], spec['capacity'], spec['physical_predicate_bytes']) ==
            (SEW, LMUL_REGS, CAP, PREDICATE_BYTES), 'm4/CAP/predicate scope drift')
    require(expected['capacity'] == CAP and expected['lmul'] == LMUL, 'Model scope drift')
    routine, addresses = spec['routine'], spec['addresses']
    require(len(routine) == 13 and routine[8]['insn'] == '308fbc57' and
            all(int(routine[i]['insn'], 16) >> 20 == VTYPE for i in (0, 5, 10)), 'm4 helper encoding')
    lookup = {r['pc']: i for i, r in enumerate(routine)}
    regs, memory, counts, calls = {0: 0}, {}, [0]*13, []
    current, step, retired, total, last_cycle, exited, parked = None, 0, 0, 0, -1, False, 0
    vlenb_reads, capacity_returns = [], []

    def finish():
        if current is not None:
            require(step == 0 and current['reads'] == set(range(CAP+2)), 'Missing full oracle/guards/asm')
            require(current.get('returned_vstart') == 0, 'Missing returned vstart')
            del current['reads']

    for lineno, row in enumerate(rows, 2):
        total += 1
        cycle = int(row['cycle'])
        require(cycle >= last_cycle and row['event'] in ('retire', 'cvx_req', 'cvx_resp', 'arch_start', 'uop_alloc', 'uop_done'),
                'Cycle reversal/unknown event/exception')
        last_cycle = cycle
        if row['event'] != 'retire':
            continue
        require(int(row['order']) == retired and int(row['trap']) == 0, 'Retirement order/trap')
        retired += 1
        require(retired <= MAX_RETIRED, 'Retired sanity bound exceeded')
        pc, insn, rd = int(row['pc'], 16), int(row['insn'], 16), int(row['rd'])
        value, address = int(row['rd_wdata'], 16), int(row['mem_addr'], 16)
        rmask, wmask = int(row['mem_rmask'], 16), int(row['mem_wmask'], 16)
        require(spec['code'].get(str(pc)) == insn, 'ELF PC/code mismatch')
        if exited:
            require(pc == spec['park']['pc'] and insn == int(spec['park']['insn'], 16) and
                    rd == rmask == wmask == 0, 'Post-exit non-original park/side effect')
            parked += 1
            continue
        if insn & 127 == 115 and insn >> 20 == 0xc22:
            require(rd != 0 and value == VLENB, 'Actual vlenb not128')
            vlenb_reads.append(dict(pc=pc, value=value))
        if pc == spec['capacity_vset']['pc']:
            require(insn == int(spec['capacity_vset']['insn'], 16) and rd == 10 and value == CAP,
                    'Actual capacity not512')
            capacity_returns.append(dict(pc=pc, value=value))
        if wmask and insn & 127 == 0x23:
            width = 1 << ((insn >> 12) & 7)
            require(width <= 8 and wmask == ((1 << width)-1) << (address % 8), 'Scalar store mask/width')
            raw = int(row['mem_wdata'], 16)
            for offset in range(width):
                memory[address+offset] = (raw >> (offset*8)) & 255
        if insn == int(routine[8]['insn'], 16):
            require(pc == routine[8]['pc'], 'Extra target outside original helper')
        if pc in lookup:
            i = lookup[pc]
            require(i == step and insn == int(routine[i]['insn'], 16), 'Original13 order/encoding')
            if i == 0:
                finish()
                ordinal = len(calls)
                require(ordinal < BOUND, 'Extra call')
                gold = expected['rows'][ordinal]
                args = [addresses['input'], addresses['indices'], addresses['output']+1,
                        gold['vl'], CAP, addresses['predicate'], 0, gold['vstart']]
                require([regs.get(n) for n in range(10, 18)] == args, 'Actual call arguments differ')
                values_checked = bytes_checked = 0
                for name, values, width in (
                        ('input', expected['input'], 1), ('indices', expected['indices'], 1),
                        ('indices16', expected['indices16'], 2), ('predicate', gold['predicate'], 1),
                        ('output', [91]*(CAP+2), 1)):
                    for k, want in enumerate(values):
                        got = [memory.get(addresses[name]+width*k+n) for n in range(width)]
                        require(None not in got, 'Missing initialized source bytes')
                        require(sum(v << (8*n) for n, v in enumerate(got)) == want,
                                f'Setup/RNG mismatch call{ordinal+1} {name}[{k}]')
                        values_checked += 1
                        bytes_checked += width
                require((values_checked, bytes_checked) == (SETUP_VALUES, SETUP_BYTES), 'Full setup scope')
                current = dict(ordinal=ordinal+1, original_tuple=gold['tuple'], reads=set(),
                               setup_values_checked=values_checked, setup_bytes_checked=bytes_checked)
                calls.append(current)
            if i in (0, 5, 10):
                require(rd == 5 and value == (gold['vl'] if i == 5 else CAP), 'Actual vsetvli return')
            if i == 8:
                require(regs.get(28) == 0 and regs.get(17) == gold['vstart'] and regs.get(13) == gold['vl'],
                        'Actual target scalar/start/VL')
                require((insn >> 15) & 31 == 31, 'Unsigned immediate31')
                current['target'] = dict(pc=pc, insn=insn, vl=gold['vl'], vstart=gold['vstart'],
                                         scalar=0, immediate=31, source31=expected['input'][31], csv_line=lineno)
            if i == 9:
                require(rd == 10 and value == 0, 'Returned vstart nonzero')
                current['returned_vstart'] = 0
            counts[i] += 1
            step = (step+1) % 13
        if current is not None and rmask and addresses['output'] <= address < addresses['output']+CAP+2:
            require(step == 0 and insn & 127 == 3 and (insn >> 12) & 7 == 4 and rd != 0 and
                    rmask == 1 << (address % 8) and wmask == 0, 'Oracle must be scalar LBU with exact mask')
            k = address-addresses['output']
            require(k not in current['reads'], 'Duplicate oracle read')
            want = 91 if k in (0, CAP+1) else gold['output'][k-1]
            require(value == want, f'Full oracle mismatch call{len(calls)} index{k}')
            current['reads'].add(k)
        if address == spec['exit_address'] and wmask:
            require(pc == spec['exit_store']['pc'] and insn == int(spec['exit_store']['insn'], 16) and
                    int(row['mem_wdata'], 16) == 0 and wmask == 255, 'CTRL exit not original returncode0')
            finish()
            current, exited = None, True
        if rd:
            regs[rd] = value
    require(exited and len(calls) == BOUND and counts == [BOUND]*13, 'Missing calls/asm/exit')
    require(len(vlenb_reads) == 2 and len(capacity_returns) == 1, 'Missing actual vlenb/capacity')
    return dict(status='PASS_RAW66_M4_FULL_SETUP_SCALAR_ORACLE', calls=calls, target_hits=BOUND,
                routine_retire_counts=counts, helper_instruction_retirements=sum(counts),
                fullcap_checks=RESULT_CHECKS, guards=GUARD_CHECKS, actual_output_scalar_loads=ORACLE_LOADS,
                returned_vstart_zero=BOUND, setup_values_per_call=SETUP_VALUES, setup_bytes_per_call=SETUP_BYTES,
                physical_predicate_bytes=PREDICATE_BYTES, actual_vlenb_reads=vlenb_reads,
                actual_capacity_returns=capacity_returns, retired_rows=retired, csv_rows=total,
                csv_last_cycle=last_cycle, post_exit_park_retired=parked, soc_ctrl_exit=0,
                full_child_acceptance=False, exact_historical_stall_reproduction=False)


def artifacts(result, case, ledger, spec, validator):
    require(result.status == 'PASS' and result.name == RUNTIME_ID and not result.reason, 'Not exact runtime PASS')
    require(case['id'] == RUNTIME_ID and case['original_name'] == SOURCE_LABEL, 'Historical/runtime identity drift')
    # The frozen common checker expects original_name to be the actual +TESTCASE.
    common.check_artifacts(result, dict(case, original_name=RUNTIME_ID), ledger)
    for name in ('console.log', 'work/run.vcs.log'):
        console_gate((result.artifact_dir / name).read_text())
    path = result.artifact_dir / 'commit_trace.csv'
    generic = validator(path)
    require(generic['cvx_exception_count'] == 0 and generic['rows'] > 0, 'Generic trace/exception')
    with path.open(newline='') as stream:
        strict = retirement(csv.DictReader(stream), spec, model())
    require((strict['csv_rows'], strict['csv_last_cycle'], strict['retired_rows']) ==
            (generic['rows'], generic['last_cycle'], generic['retire_count']), 'Trace counts differ')
    return dict(generic=generic, strict=strict, csv_sha256=sha(path))

