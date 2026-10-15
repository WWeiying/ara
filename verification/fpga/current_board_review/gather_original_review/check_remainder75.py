#!/usr/bin/env python3
"""Independent raw oracle/identity/retirement gates for the fixed 12+63 plan."""
import argparse
import csv
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
from prepare_batch import HERE, sha, save
from replay_candidate03 import read, require, pins_check
from check_terminal import console_check

DATA = HERE / 'remainder75_01'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
IMAGE_SHA = 'e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673'
UNIT = 'ara-gather75-candidate04-01.service'


def validate_plan(plan):
    require(plan['image'] == str(IMAGE) and plan['image_sha256'] == IMAGE_SHA and
            plan['unit'] == UNIT and plan['programs'] == str(DATA / 'soc75'), 'Wrong fixed image/unit/programs identity')
    inventory = read(HERE / 'inventory83.json')['records']
    accepted = read(HERE / 'acceptance_audit01/audit.json')
    require(accepted['status'] == 'PASS_8_SOURCE_FULLORACLE_IDENTITY_AUDIT', 'Accepted8 anchor missing')
    original = {r['case']['name']:r['case'] for r in inventory}
    accepted_names = [r['original_case']['name'] for r in accepted['results']]
    first_cases = read(HERE / 'remainder12_01/prepared01/provenance.json')['cases']
    first_names = [r['original_case']['name'] for r in first_cases]
    all_remaining = first_names + [r['case']['name'] for r in inventory if r['case']['name'] not in set(accepted_names+first_names)]
    names = ['gather_'+n.removeprefix('rvv_small_gather_restart_') for n in all_remaining]
    require(plan['accepted_source_names'] == accepted_names and plan['remaining_source_names'] == all_remaining and
            plan['names'] == names and len(names) == len(set(names)) == 75 and
            len(set(accepted_names) | set(all_remaining)) == 83 and
            not set(accepted_names) & set(all_remaining), 'Exact accepted8+remaining75 membership differs')
    source_keys = [[original[n]['sew'], original[n]['lmul'], original[n]['selected_trial']['op']] for n in all_remaining]
    all_keys = source_keys + [[original[n]['sew'], original[n]['lmul'], original[n]['selected_trial']['op']] for n in accepted_names]
    require(plan['remaining_source_keys'] == source_keys and len({tuple(k) for k in all_keys}) == 83,
            'Sourcekey/parent duplicate counted as single')
    require(plan['jobs'] == 4 and plan['timeout_per_case_s'] == 300 and plan['retries'] == 0 and
            plan['service_runtime_max_s'] == 6300 and plan['requires_parent_review'] is True and
            plan['stop_first_failure'] is True and plan['skip_accepted_execution'] is True and
            plan['parent_closure'] is False and plan['original_linux_elf_replay'] is False,
            'Wrong jobs/budget/retry/scope policy')
    require(plan['stages'] == [dict(name='first12', cases=names[:12], jobs=4),
                              dict(name='remaining63', cases=names[12:], jobs=4)], 'Wrong stage gate/order')
    return names


def verify_identity(out, plan, stage, record, worker):
    require(record['status'] == 'ADVANCING_4_SIMV' and record['raw_samples_retained'] and
            len(record['samples']) == 2, 'Four actual simv startup samples missing')
    before, after = record['samples']
    require(len(before) == len(after) == 4 and len({s['pid'] for s in before}) == 4,
            'Wrong actual simv PID count')
    simv = read(Path(plan['image']) / 'image.json')['simv']
    require(record['worker_cgroup'] == worker['cgroup'] and plan['unit'] in worker['cgroup'], 'Wrong worker cgroup')
    names = []
    for a,b in zip(before, after):
        require(a['pid'] == b['pid'] and a['start_ticks'] == b['start_ticks'], 'Actual PID/generation identity differs')
        require(a['executable'] == b['executable'] == str(Path(simv).resolve()) and
                a['cgroup'] == b['cgroup'] == worker['cgroup'] and
                a['argv'] == b['argv'] and a['cwd'] == b['cwd'], 'Actual simv identity differs')
        argv = b['argv']
        case_names = [x.split('=',1)[1] for x in argv if x.startswith('+TESTCASE=')]
        require(argv[0] == simv and len(case_names) == 1 and case_names[0] in stage['cases'], 'Wrong actual stage case')
        name = case_names[0]
        names.append(name)
        folder = out / stage['name'] / 'replay/tests' / name
        require(b['cwd'] == str(folder / 'work'), 'Wrong actual private work directory')
        for prefix,value in (('+PRELOAD=',str(folder / 'input.elf')), ('+COMMIT_TRACE=',str(folder / 'commit_trace.csv'))):
            require([x for x in argv if x.startswith(prefix)] == [prefix+value], 'Wrong actual private preload/trace')
    require(len(set(names)) == 4, 'Duplicate actual startup cases')
    return before,after


def verify_progress(out, plan, stage, record, worker):
    before,after = verify_identity(out,plan,stage,record,worker)
    for a,b in zip(before,after):
        require(b['cpu_ticks'] > a['cpu_ticks'] and b['trace_bytes'] > a['trace_bytes'] > 0 and
                b['last_cycle'] > a['last_cycle'] > 0, 'Raw PID/CPU/trace/cycle growth failed')


def full_retirement(trace_path, case, expected, reference):
    sew = case['original_case']['sew']
    width = sew // 8
    values = {reference['output_address']+width*i:v for i,v in enumerate([91]+expected['full_cap_expected']+[91])}
    observed, regs, targets, returned = {}, {}, [], []
    for item in csv.DictReader(trace_path.open()):
        if item['event'] != 'retire':
            continue
        pc, rd, value = int(item['pc'],16), int(item['rd']), int(item['rd_wdata'],16)
        if pc == reference['soc_target']['pc']:
            require(item['insn'] == reference['soc_target']['insn'] and regs.get(13) == 2 and regs.get(17) == 1,
                    'Target PC/encoding/VL/vstart differs')
            targets.append(dict(pc=hex(pc), cycle=int(item['cycle']), insn=item['insn'], vl=2, vstart=1))
        if pc == reference['returned_vstart_pc']:
            require(rd == 10 and value == 0, 'Returned vstart not zero')
            returned.append(dict(pc=hex(pc), cycle=int(item['cycle']), value=value))
        address = int(item['mem_addr'],16)
        if int(item['mem_rmask'],16) and address in values:
            value_masked = value & ((1 << sew)-1)
            require(value_masked == values[address], 'Full-cap scalar output/guard differs')
            observed[address] = value_masked
        if rd:
            regs[rd] = value
    require(len(targets) == len(returned) == 1 and set(observed) == set(values),
            'Incomplete full-cap/guards/target retirement evidence')
    return dict(target=targets[0], returned_vstart=returned[0], scalar_output_reads=expected['capacity'], guards_read=2)


def check_case(result, folder, entry, image, case, expected, reference, trace_validator):
    name = case['id']
    require(result['status'] == 'PASS' and result['returncode'] == 0 and not result['reason'] and
            result['artifact_dir'] == str(folder), name+': not PASS/exit0')
    inputs = read(folder / 'inputs.json')
    private = folder / 'input.elf'
    require(sha(private) == entry['sha256'] and inputs['binary'] ==
            dict(source=entry['path'], path=str(private), sha256=entry['sha256']), name+': private ELF drift')
    require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), name+': private image drift')
    command = read(folder / 'command.json')
    argv = command['command']
    require(command['cwd'] == str(folder / 'work') and argv[0] == image['simv'], 'Wrong image/cwd')
    for prefix,value in (('+PRELOAD=',str(private)), ('+TESTCASE=',name), ('+COMMIT_TRACE=',str(folder / 'commit_trace.csv'))):
        require([a for a in argv if a.startswith(prefix)] == [prefix+value], 'Wrong command identity')
    require('+NO_FSDB' in argv and not any(a in ('-cm','-ucli') for a in argv), 'Unexpected instrumentation')
    for log in (folder / 'console.log', folder / 'work/run.vcs.log'):
        console_check(log.read_text(), name)
    trace_path = folder / 'commit_trace.csv'
    trace = trace_validator(trace_path)
    require(trace.get('rows',0) > 0 and trace.get('last_cycle',0) > 0 and trace['cvx_exception_count'] == 0,
            'Invalid/empty/trapping trace')
    retirement = full_retirement(trace_path, case, expected, reference)
    return dict(name=name, status='PASS', returncode=0, elapsed_s=result['elapsed_s'],
        elf_sha256=sha(private), console_sha256=sha(folder / 'console.log'), trace_sha256=sha(trace_path),
        trace=trace, **retirement)


def validate_stage(out, plan_hash, stage_name):
    require(sha(out / 'plan.json') == plan_hash, 'Execution plan drift')
    plan = read(out / 'plan.json')
    names = validate_plan(plan)
    pins_check(plan['pins'])
    stage, = [s for s in plan['stages'] if s['name'] == stage_name]
    if stage_name == 'remaining63':
        first_gate = read(out / 'first12/independent_gate.json')
        require(first_gate['status'] == 'PASS_FIRST12' and first_gate['plan_sha256'] == plan_hash and
                [r['name'] for r in first_gate['results']] == names[:12], 'First12 gate not accepted')
    runner = read(out / stage_name / 'runner_exit.json')
    require(runner['returncode'] == 0 and runner['error'] is None and runner['plan_sha256'] == plan_hash,
            'Stage runner not exit0')
    folder = out / stage_name / 'replay'
    run, summary = read(folder / 'run.json'), read(folder / 'summary.json')
    image = read(Path(plan['image']) / 'image.json')
    require(run['status'] == 'COMPLETE' and run.get('completed_at') and run['tests'] == stage['cases'] and
            run['jobs'] == 4 and run['timeout_s'] == 300 and run['simv'] == image['simv'] and
            run['commit_trace'] and not run['code_coverage'] and run['status_counts'] == {'PASS':len(stage['cases'])},
            'Stage not exact COMPLETE/full PASS')
    require([r['name'] for r in summary] == stage['cases'], 'Summary membership differs')
    verify_progress(out, plan, stage, read(out / stage_name / 'actual_simv_confirmation.json'), read(out / 'worker.json'))
    programs = read(Path(plan['programs']) / 'programs.json')['programs']
    require(list(programs) == names, 'Programs membership drift')
    cases = {c['id']:c for c in read(DATA / 'prepared75/provenance.json')['cases']}
    expected = {c['name']:c for c in read(DATA / 'host_semantics.json')['results']}
    reference = {c['name']:c for c in read(DATA / 'reference75/reference.json')['results']}
    sys.path.insert(0, str(Path(image['snapshot']) / 'sources/verification'))
    from ara_verify.trace import validate_trace
    results = [check_case(r, folder / 'tests' / r['name'], programs[r['name']], image,
                cases[r['name']], expected[r['name']], reference[r['name']], validate_trace) for r in summary]
    pins_check(plan['pins'])
    return results


def validate(out, plan_hash):
    plan = read(out / 'plan.json')
    validate_plan(plan)
    worker = read(out / 'worker_exit.json')
    require(worker['plan_sha256'] == plan_hash and worker['runner_returncode'] == 0 and worker['error'] is None and
            worker['retries'] == 0 and worker['accepted8_rerun'] is False, 'Worker not exit0/no-retry')
    results = []
    for stage in plan['stages']:
        gate = read(out / stage['name'] / 'independent_gate.json')
        current = validate_stage(out, plan_hash, stage['name'])
        require(gate['status'] == 'PASS_'+stage['name'].upper() and gate['plan_sha256'] == plan_hash and
                gate['results'] == current, 'Stored/raw stage acceptance differs')
        results.extend(current)
    require(len(results) == 75, 'Not all remaining75')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--stage', choices=('first12','remaining63'))
    args = parser.parse_args()
    out = args.out.resolve()
    destination = out / args.stage / 'independent_gate.json' if args.stage else out / 'complete.json'
    try:
        results = validate_stage(out,args.plan_sha256,args.stage) if args.stage else validate(out,args.plan_sha256)
        final = dict(status='PASS_'+args.stage.upper() if args.stage else 'PASS_8_ACCEPTED_PLUS_75_SOURCE_SINGLES_CANDIDATE04',
            results=results, plan_sha256=args.plan_sha256, finished=time.time(), retries=0,
            accepted8_rerun=False, parent_closure=False, original_linux_elf_replay=False)
        rc = 0
    except Exception as error:
        final = dict(status='NOT_ACCEPTED', reason=str(error), plan_sha256=args.plan_sha256,
                     finished=time.time(), retries=0, parent_closure=False)
        rc = 1
    save(destination, final)
    print(final['status'], final.get('reason',''), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
