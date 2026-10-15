#!/usr/bin/env python3
"""Strict raw CSV gate for two authentic 98-call child prefixes, not parent closure."""
import csv
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import check_stall_prefix2 as source
from prepare_batch import sha
from replay_candidate03 import read, require, pins_check, FAIL

DATA = source.DATA
NAMES = source.NAMES
VETO = re.compile(FAIL.pattern + r'|RVV_GATHER_PREFIX_FAIL|RVV_PERMUTE_PASS|\bABORT(?:ED)?\b|\bTRAP\b|\bMISMATCH\b', re.I | re.M)


def console_gate(text, name):
    require(not VETO.search(text), 'Failure/abort/parent marker veto')
    lines = text.splitlines()
    for prefix, marker in (
        ('RVV_GATHER_PREFIX_PASS', 'RVV_GATHER_PREFIX_PASS sew=8 cases=98 errors=0'),
        ('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN '+name),
        ('BOARD_CASE_PASS', 'BOARD_CASE_PASS '+name),
        ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS')):
        require([s for s in lines if s.startswith(prefix)] == [marker], 'Missing/ambiguous '+prefix)
    successes = [s for s in lines if s.startswith('Core Test *** SUCCESS ***')]
    require(len(successes) == 1 and successes[0] in (
        'Core Test *** SUCCESS ***', 'Core Test *** SUCCESS *** (tohost = 0)'), 'Missing/ambiguous simulator exit0 marker')


def identity(record, plan, out, worker):
    require(record['status'] == 'ADVANCING_TWO_SIMV' and len(record['samples']) == 2, 'Actual startup confirmation missing')
    before, after = record['samples']
    require(len(before) == len(after) == 2 and len({a['pid'] for a in before}) == 2, 'Not two actual PIDs')
    simv = read(Path(plan['image'])/'image.json')['simv']
    require(record['worker_cgroup'] == worker['cgroup'] and
            plan['unit'] in {s for line in worker['cgroup'].splitlines() for s in line.split('/')}, 'Wrong worker cgroup')
    names = []
    for a, b in zip(before, after):
        require(a['pid'] == b['pid'] and a['start_ticks'] == b['start_ticks'], 'PID generation changed')
        require(a['argv'] == b['argv'] and a['executable'] == b['executable'] == str(Path(simv).resolve()) and
                a['cgroup'] == b['cgroup'] == worker['cgroup'], 'Actual simv identity mismatch')
        argv = b['argv']
        names_arg = [s.split('=', 1)[1] for s in argv if s.startswith('+TESTCASE=')]
        require(argv[0] == simv and len(names_arg) == 1 and names_arg[0] in NAMES, 'Wrong actual case')
        name = names_arg[0]
        names.append(name)
        folder = out/'replay/tests'/name
        require(a['cwd'] == b['cwd'] == str(folder/'work'), 'Wrong actual cwd')
        for prefix, value in (('+PRELOAD=', str(folder/'input.elf')), ('+COMMIT_TRACE=', str(folder/'commit_trace.csv'))):
            require([s for s in argv if s.startswith(prefix)] == [prefix+value], 'Wrong actual private inputs')
    require(set(names) == set(NAMES), 'Duplicate/missing actual case')


def progress(record, plan, out, worker):
    identity(record, plan, out, worker)
    for a, b in zip(*record['samples']):
        require(b['cpu_ticks'] > a['cpu_ticks'] and b['trace_bytes'] > a['trace_bytes'] > 0 and
                b['last_cycle'] > a['last_cycle'] > 0, 'Actual CPU/CSV/cycle growth missing')


def retirement(rows, spec, model):
    routine = spec['soc_routine']
    lookup = {r['pc']:i for i, r in enumerate(routine)}
    regs, events, reads, counts = {}, [], {}, [0]*13
    step, call, loads, retired, total_rows, last_cycle, exited = 0, 0, 0, 0, 0, 0, False
    def finish_call():
        if call:
            require(step == 0 and len(reads) == 514 and loads == 514, 'Incomplete per-call fullcap/guards/asm')
    for row in rows:
        total_rows += 1
        last_cycle = int(row['cycle'])
        if row['event'] != 'retire':
            continue
        require(not exited and int(row['trap']) == 0, 'Retirement after exit or architectural trap')
        retired += 1
        require(retired <= 5_000_000, 'Retired bound exceeded, not a DUT cycle bound')
        pc, insn = int(row['pc'],16), int(row['insn'],16)
        rd, value, address = int(row['rd']), int(row['rd_wdata'],16), int(row['mem_addr'],16)
        if pc in lookup:
            i = lookup[pc]
            require(i == step and insn == int(routine[i]['insn'],16), 'Original 13-instruction call order/encoding differs')
            if i == 0:
                finish_call()
                require(call < 98, 'Extra original call')
                expected = model['rows'][call]
                require(all(regs.get(reg) == want for reg, want in (
                    (10,spec['input_address']), (11,spec['index_address']), (12,spec['output_address']+1),
                    (13,expected['vl']), (14,512), (15,spec['predicate_address']),
                    (16,expected['scalar']), (17,expected['vstart']))), 'Original call setup/pointers/cap/VL/vstart differs')
                call += 1
                reads, loads = {}, 0
            if i == 8:
                require(regs.get(13) == expected['vl'] and regs.get(17) == expected['vstart'] and
                        regs.get(28) == expected['scalar'], 'Target actual scalar/VL/vstart differs')
                events.append(dict(ordinal=call, original_tuple=expected['tuple'], pc=hex(pc),
                    insn=routine[i]['insn'], cycle=last_cycle, retired=retired,
                    vl=expected['vl'], vstart=expected['vstart'], scalar=expected['scalar']))
            if i == 9:
                require(rd == 10 and value == 0, 'Returned vstart is not zero')
            counts[i] += 1
            step = (step+1)%13
        if call and int(row['mem_rmask'],16) and spec['output_address'] <= address < spec['output_address']+514:
            require(step == 0 and insn & 127 == 3, 'Oracle read before original asm returned')
            index = address-spec['output_address']
            want = 91 if index in (0,513) else model['rows'][call-1]['output'][index-1]
            require(value & 255 == want and index not in reads, 'Fullcap/guard mismatch or duplicate read')
            reads[index] = value & 255
            loads += 1
        if address == spec['exit_store_address'] and int(row['mem_wmask'],16):
            require(pc == spec['exit_store_pc'] and int(row['mem_wdata'],16) == 0,
                    'SoC CTRL exit must store raw returncode0, not Spike HTIF1')
            finish_call()
            exited = True
        if rd:
            regs[rd] = value
    finish_call()
    require(exited and call == len(events) == 98 and counts == [98]*13, 'Missing call/asm/target/exit')
    return dict(target_hits=98, returned_vstart_zero=98, routine_retire_counts=counts, events=events,
        fullcap_scalar_checks=50176, both_guard_checks=196, actual_output_scalar_loads=50372,
        csv_rows=total_rows, csv_last_cycle=last_cycle, retired_rows=retired, soc_ctrl_exit_store_value=0)


def check_case(result, folder, entry, image, spec, model, trace_validator):
    name = result['name']
    require(name in NAMES and result['status'] == 'PASS' and result['returncode'] == 0 and not result['reason'] and
            result['artifact_dir'] == str(folder), 'Not exact case PASS/exit0')
    private = folder/'input.elf'
    inputs = read(folder/'inputs.json')
    require(sha(private) == entry['sha256'] and inputs['binary'] ==
            dict(source=entry['path'], path=str(private), sha256=entry['sha256']), 'Private ELF drift')
    require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), 'Private M4 drift')
    command = read(folder/'command.json')
    argv = command['command']
    require(argv[0] == image['simv'] and command['cwd'] == str(folder/'work'), 'Wrong image/cwd')
    for prefix, value in (('+TESTCASE=',name), ('+PRELOAD=',str(private)), ('+COMMIT_TRACE=',str(folder/'commit_trace.csv'))):
        require([s for s in argv if s.startswith(prefix)] == [prefix+value], 'Command identity differs')
    require('+NO_FSDB' in argv and not any(s in ('-cm','-ucli') for s in argv), 'Unexpected instrumentation')
    for path in (folder/'console.log', folder/'work/run.vcs.log'):
        console_gate(path.read_text(), name)
    path = folder/'commit_trace.csv'
    trace = trace_validator(path)
    require(trace['cvx_exception_count'] == 0 and trace['rows'] > 0, 'Invalid/exception trace')
    with path.open(newline='') as stream:
        measured = retirement(csv.DictReader(stream), spec, model)
    require(measured['csv_rows'] == trace['rows'] and measured['csv_last_cycle'] == trace['last_cycle'] and
            measured['retired_rows'] == trace['retire_count'], 'Independent CSV counts differ')
    return dict(name=name, status='PASS', returncode=0, elf_sha256=sha(private),
        trace_sha256=sha(path), console_sha256=sha(folder/'console.log'), trace=trace, **measured)


def terminal(out, plan, digest, trace_validator):
    require(sha(out/'plan.json') == digest, 'Plan drift')
    pins_check(plan['pins'])
    worker = read(out/'worker_exit.json')
    require(worker['runner_returncode'] == 0 and worker['error'] is None and worker['plan_sha256'] == digest and
            worker['retries'] == 0 and not worker['aborted'], 'Worker nonexit0/error/abort')
    run, summary = read(out/'replay/run.json'), read(out/'replay/summary.json')
    image = read(Path(plan['image'])/'image.json')
    require(run['status'] == 'COMPLETE' and run.get('completed_at') and run['tests'] == NAMES and
            run['jobs'] == 2 and run['timeout_s'] == 9000 and run['simv'] == image['simv'] and
            run['status_counts'] == {'PASS':2} and run['commit_trace'] and not run['code_coverage'], 'Run not exact COMPLETE/PASS2')
    require([r['name'] for r in summary] == NAMES, 'Summary membership differs')
    progress(read(out/'actual_simv_confirmation.json'), plan, out, read(out/'worker.json'))
    programs = read(Path(plan['programs'])/'programs.json')['programs']
    results = [check_case(r, out/'replay/tests'/r['name'], programs[r['name']], image, spec,
               source.prep.model(spec['operation']), trace_validator) for r, spec in zip(summary, plan['cases'])]
    pins_check(plan['pins'])
    return results
