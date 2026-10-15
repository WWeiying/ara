#!/usr/bin/env python3
"""Finish the interrupted audit from hash-bound completed raw scans; never run DUT."""
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import replay as original

base = original.base
read, sha, require = base.read, base.sha, base.require
OUT = HERE / 'vcs_candidate04_01'
PREP = HERE / 'prepared01'
SUCCESSOR = HERE.parent / 'whole_register_history_edges/successor02'
UNIT = 'ara-whole1134-candidate04-01.service'
PLAN_SHA = '4026384e0a1bb8f3163c8f4604bfa08a95350b3d12e49f2bbafdbe5696a84269'
# Digests printed by the completed pre-pause raw CSV + per-call oracle scan.
CSV_SHA = dict(enumerate([
    '57d361d765b94faa6b3d9fc7bd155b503321d5abb8983b6aeecccc088727093d',
    '18c1467b8a361939de8adea3cf05fbce3c6fd056aba2d33668e85d9eea35ae83',
    '33704d7c9788b2bcf2315255434153ac5893f742f8f84e4bec2563840cd39891',
    'daa1577c3f3b95952c01594f422f64b62384998ce614473e3fab870492464dbd',
    'd6ce9b94a5fd2b7c1b81f2c529964fb0762492bfbc6fd17c16cf7bc5850ebf63',
    'a474b980f64245599e56df00337c79a97eacd3d090d48bb2edcb152f87fca247',
    '40202bf1d28a70dd802e83f5ee181275110de1e0448e8ae8942564b0a2e8d6a8',
    '3f5b35694d51e2c9a869a7c02a4ebee9059a1bf1639cf06cdfa26382b192cbaf',
    '3a350c80e2cc1a508f378cd1700a00c0c612156e0594ec481594e80b4394ae4d',
    '078fb18584124a7340891ef73d5e24f1ae63a848798df01b29e5b8fd572661b0',
    'ef25aa64667b4be0ee907ec3a10059f9f591a65af62720fae9492ddbb4243d74',
    '5eab2570078ffcb81c37019fabe4c2c99bfa96131d8d8f8c3b0e60a509278580',
    'b0aed8ba1e6ac7a22226410696c486039e3de49e4e973c221582b8d4bc2c6d66',
    '3c6d643b49be90fa35587f3951c96a336b89d78cb4863796788fe8b00765c23d',
    '27a0e696fd1e20c760465704d486364a290494bea65561f4847f7fbd2f18c61d',
    '0b0e566141c411599150d65b300fb40be3239594d3c0042ffb5e35e76db13add',
    'd74729406b5881741c63c44dea310a5da384af117081df235b7835f9deca7007',
    '4795314e9de7d9305d8e86b311ae9d27ac582c24e98a6077696c469a988615d7',
    'd20879eb1863fc59ea68b56712ae6ef42263f9f3901e8e36f67b3969a34da23a',
    '1b3002b3f944706e0b611068ef504f3bef5049b6df8299cb47df7f0feeef0c3f',
]))


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    targets = [HERE / n for n in ('terminal_audit01.json', 'strict_acceptance01.json',
                                 'strict_acceptance01_validation.json')]
    require(not any(p.exists() for p in targets), 'Fresh audit outputs required')
    pause_path = HERE / 'PAUSED_PROGRESS.json'
    pause_sha, pause = sha(pause_path), read(pause_path)
    require(pause['raw_audit_process_finished'] and pause['raw_audit_exit_code'] == 0,
            'Pre-pause raw scan was not complete')
    plan, terminal = read(OUT / 'plan.json'), read(OUT / 'complete.json')
    require(sha(OUT / 'plan.json') == terminal['plan_sha256'] == PLAN_SHA, 'Original plan drift')
    for path, field in ((OUT / 'complete.json', 'old_terminal_sha256'),
                        (OUT / 'replay/run.json', 'old_run_sha256'),
                        (OUT / 'replay/summary.json', 'old_summary_sha256')):
        require(sha(path) == pause[field], 'Original terminal evidence drift: ' + str(path))
    require(terminal['status'] == 'PASS_1134_IN_20_PARTITIONS' and terminal['pins_unchanged']
            and terminal.get('firstfailure') is None and not list(OUT.rglob('firstfailure.json')),
            'Original campaign failed/incomplete')
    base.verify_pins(plan['pins'])
    programs = original.validate_reference()
    ledger, _, _ = original.checked.original.identity()
    require(terminal['image_sha256'] == plan['image_sha256'] == original.checked.original.IMAGE_SHA,
            'Wrong M4 image')
    geometry = load(HERE / 'prepare.py', 'whole_audit_geometry')
    tuples, skipped = geometry.geometry(0, 20)
    saved = read(PREP / 'tuples.json')
    require(tuples == saved['cases'] and skipped == saved['skipped'] and
            len(tuples) == 1134 and len(skipped) == 366, 'Original tuple/exclusion drift')
    source = (PREP / 'original/whole_oracle.c').read_text()
    oracle = source[source.index('        unsigned n='):source.index('    text(errors ? "RVV_WHOLE_FAIL')]
    require(oracle in (PREP / 'case.c').read_text(), 'Original oracle body drift')
    run, summary = read(OUT / 'replay/run.json'), read(OUT / 'replay/summary.json')
    names = [f'whole_op{op:02d}' for op in list(range(16, 20)) + list(range(16))]
    require([c['id'] for c in plan['cases']] == [r['name'] for r in terminal['results']] ==
            [r['name'] for r in summary] == run['tests'] == names, 'Membership/order drift')
    require(run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS': 20} and
            run['jobs'] == 6 and run['simv'] == ledger['simv'] and run['commit_trace'],
            'Runner interrupted/incomplete/wrong image')
    evidence, rows = {}, []
    for c, result, reported in zip(plan['cases'], summary, terminal['results']):
        name = c['id']
        op = int(name[-2:])
        folder = OUT / 'replay/tests' / name
        count = sum(t['op'] == op for t in tuples)
        excluded = sum(t['op'] == op for t in skipped)
        require(c['original_cases'] == count and c['original_skips'] == excluded, 'Partition counts drift')
        require(result['status'] == reported['status'] == 'PASS' and
                result['returncode'] == reported['returncode'] == 0 and
                result['reason'] == reported['reason'] == '' and result['artifact_dir'] == str(folder) and
                0 < result['elapsed_s'] == reported['elapsed_s'] < c['timeout_s'] == 5400,
                'Partition result incomplete/timeout')
        require(sha(folder / 'input.elf') == sha(Path(c['elf'])) == c['sha256'] == programs[name]['sha256'],
                'Private/source ELF drift')
        inputs, command = read(folder / 'inputs.json'), read(folder / 'command.json')
        require(inputs['binary'] == dict(source=c['elf'], path=str(folder / 'input.elf'), sha256=c['sha256'])
                and inputs['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files']), 'Input identity drift')
        argv = command['command']
        require(argv[0] == ledger['simv'] and command['cwd'] == str(folder / 'work'), 'Command image/cwd drift')
        for prefix, value in (('+PRELOAD=', str(folder / 'input.elf')), ('+TESTCASE=', name),
                              ('+COMMIT_TRACE=', str(folder / 'commit_trace.csv'))):
            require([x for x in argv if x.startswith(prefix)] == [prefix + value], 'Command argument drift')
        for log in (folder / 'console.log', folder / 'work/run.vcs.log'):
            text = log.read_text()
            require(original.checked.reviewed.strict_console(text) and
                    not re.search(r'RVV_WHOLE_(?:FAIL|DETAIL|BYTE)|\b(?:ABORTED|CANCELLED|TIMEOUT)\b', text) and
                    all(text.splitlines().count(m) == 1 for m in c['pass_markers']), 'Raw oracle/exit veto')
        require(sha(folder / 'commit_trace.csv') == CSV_SHA[op], 'Previously audited full CSV changed: ' + name)
        trace = read(folder / 'trace_summary.json')
        require(trace['status'] == 'VALID' and trace['cvx_exception_count'] == 0, 'Trace summary invalid')
        for filename in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                         'commit_trace.csv', 'trace_summary.json'):
            path = folder / filename
            evidence[str(path)] = sha(path)
        rows.append(dict(name=name, status='PASS', cases=count, skips=excluded,
                         elapsed_s=result['elapsed_s'], retired=trace['retire_count'],
                         fulloracle_byte_reads=count * 1088, csv_sha256=CSV_SHA[op],
                         private_elf_sha256=c['sha256'], trace=trace))
        print('HASH_BOUND_RAW_SCAN_CONFIRMED', name, flush=True)
    require(sum(r['retired'] for r in rows) == 27209016 and
            sum(r['fulloracle_byte_reads'] for r in rows) == 1233792, 'Scan totals changed')
    elapsed = terminal['finished'] - read(OUT / 'launch.json')['time']
    require(0 < elapsed < plan['outer_timeout_s'] == 30000, 'Campaign elapsed bound')
    sys.path.insert(0, str(HERE.parent / 'fp_comparison_original'))
    import restart_dependency_gate as dependency
    state = dependency.query_unit(UNIT)
    absence = dependency.absence([UNIT])
    service = dict(unit=UNIT, Result='success', ExecMainStatus=0, MainPID=0)
    attribution = dict(source='Parent explicit observation reported in this conversation before pause',
                       parent_report='inactive/MainPID0/Resultsuccess/Exec0',
                       independent_numeric_service_exit_recovered=False,
                       current_read_only_query=state, current_process_cgroup_absence=absence)
    base.verify_pins(plan['pins'])
    require(sha(pause_path) == pause_sha, 'Pause record changed')
    scope = 'Exactly20 operation partitions,1134 tuples,366 original exclusions; not continuous whole_all, Linux ELF execution or Whole59.'
    audit = dict(status='INDEPENDENT_RAW_TERMINAL_20_PARTITIONS_PASS', scope=scope,
                 method='Completed pre-pause full CSV/tuple/1088-byte-per-call oracle scan; current20 CSV hashes match recorded scan digests; current raw logs, identities and pins rechecked.',
                 plan_sha256=PLAN_SHA, image_sha256=plan['image_sha256'], original_pin_count=len(plan['pins']),
                 original_pins_unchanged=True, cases=1134, skips=366, retired=27209016,
                 fulloracle_byte_reads=1233792, launch_to_terminal_s=elapsed, results=rows,
                 no_abort_evidence=dict(runner_status='COMPLETE', pass_count=20, no_cancelled_results=True,
                    no_firstfailure=True, legacy_aborted_field_absent='aborted' not in terminal,
                    limitation='No synthetic legacy aborted=false field; successful service exit is parent-observed.'),
                 service_attribution=attribution, paused_progress_sha256=pause_sha,
                 paused_progress_preserved=True, simulation_started=False, finished=time.time())
    save_new(targets[0], audit)
    for path in (OUT / 'plan.json', OUT / 'complete.json', OUT / 'replay/run.json', OUT / 'replay/summary.json',
                 OUT / 'launch.json', PREP / 'tuples.json', PREP / 'source_pins.json', pause_path,
                 HERE / 'terminal_audit01.md', targets[0], Path(__file__), HERE / 'startup_review01.json',
                 original.checked.original.IMAGE / 'image.json', SUCCESSOR / 'driver.py', SUCCESSOR / 'README.md'):
        evidence[str(path)] = sha(path)
    acceptance = dict(status='WHOLE1134_STRICT_TERMINAL_PASS', output=str(OUT),
                      image_sha256=plan['image_sha256'], plan_sha256=PLAN_SHA, groups=20,
                      cases=1134, skips=366, firstfailure=None, pins_unchanged=True,
                      service=service, service_attribution=attribution, evidence_pins=evidence,
                      independent_audit=str(targets[0]), scope=scope, whole_all_dut_pass=False,
                      whole59_dut_pass=False, launch_authorization=False)
    # Exercise only the successor's read-only terminal gate, never its worker/launch.
    sys.path.insert(0, str(SUCCESSOR))
    successor = load(SUCCESSOR / 'driver.py', 'whole59_terminal_gate_only')
    os.environ.update(dependency.bus_environment())
    candidate = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=HERE, prefix='audit_candidate_', suffix='.json', delete=False) as f:
            candidate = Path(f.name)
            json.dump(acceptance, f, indent=2)
            f.write('\n')
        successor.terminal_gate(dict(whole1134_acceptance=dict(path=str(candidate), sha256=sha(candidate))),
                                dict(image_sha256=plan['image_sha256']))
        base.verify_pins(evidence)
        require(sha(pause_path) == pause_sha, 'Pause record changed before finalization')
        save_new(targets[1], acceptance)
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)
    save_new(targets[2], dict(status='EXISTING_SUCCESSOR02_TERMINAL_GATE_PASS',
        acceptance_path=str(targets[1]), acceptance_sha256=sha(targets[1]),
        audit_sha256=sha(targets[0]), evidence_pin_count=len(evidence),
        old_pin_count=len(plan['pins']), pause_record_unchanged=True,
        gate_sha256=sha(SUCCESSOR / 'driver.py'), simulation_started=False, finished=time.time()))
    print(json.dumps(read(targets[2]), indent=2), flush=True)


if __name__ == '__main__':
    require(sys.flags.optimize == 0, 'Python -O prohibited')
    main()
