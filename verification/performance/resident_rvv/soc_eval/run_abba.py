#!/usr/bin/env python3
"""Explicitly admitted ABBA successor; never starts from an unaccepted smoke."""
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
EVAL = Path('/home/wangwy/openproject/ara_dsa/verification/performance/resident_rvv/soc_eval')
sys.path.insert(0, str(EVAL))
import experiment as e

require, sha = e.require, e.sha
SMOKE_RUNNER_SHA = '5cad3e1cf352e3b0c465bc6844de3c190203983c8cc02f48180f8c21bf58173c'
require(sha(EVAL/'run_smoke.py') == SMOKE_RUNNER_SHA, 'Sealed smoke runner drift')
s = e.load(EVAL/'run_smoke.py', 'abba_sealed_smoke')
OUT = s.OUT
SOC_BUILD = OUT/'resident_pv_soc_build_20261109_03'
ABBA_BUILD = OUT/'resident_pv_soc_eval_abba_20261109_01'
ABBA_ELF_SHA = '4057d833a46f8b5f402303de68df2a3f67311b990dd3cf466128bbeec7c1baa5'
OWN = ('run_abba.py', 'test_run_abba.py', 'ABBA.md')
ORDER = (0, 1, 1, 0)
COUNTS = (237, 100, 100, 237)


def recheck_protocol(log, vector):
    sys.path.insert(0, str(s.ROOT/'verification'))
    from ara_verify.uvm_dut import check_real_uvm_log
    return check_real_uvm_log(log, require_events=True, require_backend=True,
        require_axi=True, require_axi_write=True, vector_trace=vector)


def checked_smoke(directory, socdir, soc):
    directory = s.output_path(directory)
    require(Path(socdir).resolve() == SOC_BUILD.resolve(), 'ABBA requires the reviewed SoC03')
    resultfile = directory/'result.json'
    m = json.loads(resultfile.read_text())
    require(m.get('state') == 'PASS' and m.get('kind') == 'smoke' and all(m.get(k) is True
        for k in ('numerical_checked', 'independent_protocol_checked', 'post_pins_match', 'post_image_match')),
        'Completed independently accepted smoke required')
    selected, pins, smoke_soc, software = s.verify_prepared(directory)
    require(selected['soc_build'] == m['soc_build'] == str(socdir) and
        smoke_soc == soc and m['build'] == selected['build'] and software['kind'] == 'smoke' and
        m['configuration'] == soc['configuration'] and m['software_sha256'] == software['elf_sha256'] and
        m['image_sha256'] == sha(soc['simv']) and
        m['source_pins_sha256'] == sha(directory/'source-pins.json'), 'Smoke hardware/software identity mismatch')
    actual = {str(p): sha(p) for p in directory.rglob('*') if p.is_file() and
        p != resultfile and p.name not in ('status.json', 'service.stdout.log', 'service.stderr.log')}
    require(m['artifacts'] == actual, 'Smoke evidence inventory drift')
    e.contract.verify(m['artifacts'])
    for name, command, seconds in (('console', 'simulation', s.SIM_SECONDS), ('checker', 'protocol', s.PROTOCOL_SECONDS)):
        require(json.loads((directory/'work'/(name+'.command.json')).read_text()) ==
            dict(argv=selected['commands'][command], cwd=str(directory/'work'), timeout_seconds=seconds),
            'Smoke executed-command identity mismatch')
    log, vector = directory/'work/run.vcs.log', directory/'work/vector_trace.csv'
    text = log.read_text()
    s.successful_log(text)
    require(m['numerical'] == s.check_numerical(text, software) and
        m['akv_work'] == s.check_akv(text) and m['vector_work'] == s.check_vectors(vector) and
        m['resident_work'] == e.check_resident_work(vector, text, 'smoke'), 'Smoke work/numerical evidence mismatch')
    proof = json.loads((directory/'work/uvm_result.json').read_text())
    s.check_protocol(proof, soc, software, log, vector)
    independently_checked = recheck_protocol(log, vector)
    require(independently_checked.get('status') == 'PASS' and independently_checked.get('issues') == [] and
        all(proof.get(k) == v for k, v in independently_checked.items()), 'Smoke protocol replay mismatch')
    e.merge(pins, actual)
    e.merge(pins, {str(resultfile): sha(resultfile)})
    e.contract.verify(pins)
    return dict(result=str(resultfile), result_sha256=sha(resultfile),
        source_pins_sha256=m['source_pins_sha256'], log_sha256=sha(log), vector_sha256=sha(vector),
        protocol_sha256=sha(directory/'work/uvm_result.json'), independent_recheck=True), pins


def check_numerical(text, software):
    _, original = e.contract.sealed_modules()
    golden = software['golden']
    captured, native = Path(golden['captured']), Path(golden['native_tile64'])
    require(sha(captured) == golden['captured_sha256'] and sha(native) == golden['native_tile64_sha256'],
            'ABBA reference identity drift')
    accepted = original.check_log(text, captured.read_bytes(), native.read_bytes(), software['memory_expected'])
    rows = original.records(text)
    require(len(native.read_bytes()) == 1024, 'Expected 256 native F32 words')
    reference = list(struct.unpack('<256I', native.read_bytes()))
    bits = [row['bits'] for row in rows['OUT']]
    require(bits == reference*4, 'ABBA host-native bitwise mismatch')
    require(all(row['fcsr'] == 3 for row in rows['TRIAL']), 'ABBA FCSR must equal accepted smoke FCSR3')
    issue = accepted['measured_to_return_cycles']
    full = accepted['measured_total_cycles']
    drain = accepted['final_drain_cycles']
    baseline, candidate = (full[0]+full[3])/2, (full[1]+full[2])/2
    return dict(numerical_checked=True, host_native_bitwise_values=1024, four_arms_bitwise_equal=True,
        fcsr=3, guard_fingerprints_checked=4, full_data_hash_checks=1,
        native_golden_sha256=sha(native), captured_golden_sha256=sha(captured),
        baseline_arm='strong rotating RVV', candidate_arm='sealed preparation + resident PV',
        order=list(ORDER), issue_return_cycles=issue, final_drain_cycles=drain, complete_call_cycles=full,
        complete_call_mean_cycles=dict(strong_rotation=baseline, resident_pv=candidate),
        complete_call_strong_rotation_over_resident_pv=baseline/candidate,
        complete_call_reduction_fraction=1-candidate/baseline,
        speedup_scope='Complete call including preparation, execution and final drain; not local PV cycles',
        performance_acceptance=False)


def expected_akv():
    _, original = e.contract.sealed_modules()
    one = original.expected_commands()[1046:1283]
    require(len(one) == 237 and sum(r['command'] == 2 for r in one) == 137, 'Accepted auto template drift')
    return [r for arm in ORDER for r in one if arm == 0 or r['command'] != 2]


def check_akv(text):
    _, original = e.contract.sealed_modules()
    expected, rows, summaries, totals = expected_akv(), [], [], Counter()
    for line in text.splitlines():
        if '[AKV_PERF]' in line:
            require(line.startswith('[AKV_PERF] ') and not summaries, 'Malformed/post-summary AKV PERF')
            row = original.parse_fields(line[len('[AKV_PERF] '):], original.PERF_FIELDS)
            i = len(rows)
            require(i < 674 and row['seq'] == i+1 and all(row[k] == v for k, v in expected[i].items()),
                    'ABBA AKV command sequence/work mismatch')
            require(row['success'] == 1 and row['busy_cycles'] > 0 and all(row[k] == 0 for k in
                ('fault', 'validation_fault', 'validation_error', 'read_fault', 'v2_rejected')), 'ABBA AKV fault')
            require(row['context_ready'] == int(row['command'] != 3) and row['read_payload_bytes'] ==
                row['q_external_bytes']+row['kv_external_bytes']+64*row['v2_full'], 'ABBA AKV lifecycle/payload')
            for k in original.SUMMARY_FIELDS-{'records', 'success_records', 'fault_records', 'validation_fault_records'}:
                totals[k] = max(totals[k], row[k]) if k == 'read_outstanding_max' else totals[k]+row[k]
            rows.append(row)
        elif '[AKV_PERF_SUMMARY]' in line:
            require(line.startswith('[AKV_PERF_SUMMARY] ') and len(rows) == 674, 'Premature/malformed AKV summary')
            summaries.append(original.parse_fields(line[len('[AKV_PERF_SUMMARY] '):], original.SUMMARY_FIELDS))
    summary = dict(totals, records=674, success_records=674, fault_records=0, validation_fault_records=0)
    require(len(rows) == len(expected) == 674 and summaries == [summary], 'ABBA AKV PERF/summary not closed')
    offset, busy = 0, []
    for count in COUNTS:
        busy.append(sum(r['busy_cycles'] for r in rows[offset:offset+count]))
        offset += count
    return dict(commands=674, per_call_commands=list(COUNTS), busy_cycles_per_call=busy, summary=summary)


def expected_signatures():
    result = []
    for arm in ORDER:
        for tokens in (64, 64, 9):
            result += [0x0205745b]*32
            result += [0x0485705b] if arm else [0x0205355b if i % 2 else 0x0205345b for i in range(tokens)]
    return result


def check_vectors(path):
    actual, config, previous = [], 0, -1
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and {'cycle', 'event', 'insn', 'nr_lanes', 'vlen_bits'} <= set(reader.fieldnames)
            and len(reader.fieldnames) == len(set(reader.fieldnames)), 'Malformed vector columns')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'Malformed vector row')
            cycle = int(row['cycle'])
            require(cycle >= previous and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'), 'Vector epoch/config drift')
            previous = cycle
            if row['event'] == 'config':
                require(config == 0 and cycle == 0 and not actual, 'Unexpected vector epoch')
                config += 1
                continue
            require(config == 1 and row['event'] in ('alloc', 'write', 'done') and
                re.fullmatch('[0-9a-fA-F]{8}', row['insn']), 'Unknown/reset vector event')
            insn = int(row['insn'], 16)
            if row['event'] == 'alloc' and insn & 0x707f in (0x305b, 0x705b):
                actual.append(insn)
    require(config == 1 and actual == expected_signatures(), 'Wrong 664 ABBA vector signatures/rotation')
    return dict(allocations=664, qk_panel4=384, baseline_v_rows=274, rotated_v10=136, resident_pv=6,
        ordered=True, vector_sha256=sha(path), legacy_classification=e.LEGACY_CLASSIFICATION)


def collect(socdir, build, smoke):
    require(Path(socdir).resolve() == SOC_BUILD.resolve() and Path(build).resolve() == ABBA_BUILD.resolve(),
            'Explicit reviewed SoC03 and ABBA software required')
    soc, pins = e.checked_soc(socdir)
    software = e.verify_build(build)
    require(software['kind'] == 'abba' and software['elf_sha256'] == ABBA_ELF_SHA and
        software['baseline_arm'] == 'strong rotating RVV' and software['image_contract'] == soc['image_contract'],
        'Not the sealed strong-rotation ABBA build')
    admission, smoke_pins = checked_smoke(smoke, socdir, soc)
    e.merge(pins, smoke_pins)
    e.merge(pins, json.loads((build/'source-pins.json').read_text()))
    e.merge(pins, software['artifacts'])
    inventory = s.checker_inventory()
    e.merge(pins, inventory)
    e.merge(pins, s.HELPERS)
    e.merge(pins, {str(p): sha(p) for p in (build/'build.json', build/'source-pins.json',
        *(EVAL/n for n in (*s.OWN, *OWN)))})
    e.contract.verify(pins)
    return soc, software, pins, inventory, admission


def output_path(path):
    out = Path(path).resolve()
    require(out.parent == OUT and re.fullmatch(r'(?:resident_pv_)?soc_abba_vcs_[A-Za-z0-9_-]{1,100}', out.name),
            'Fresh direct signoff soc_abba_vcs output required')
    return out


def selection(out, socdir, build, smoke, soc, software, inventory, admission, env, python):
    commands = s.recipes(out, soc, software, python)
    args = commands['simulation']
    args[args.index('+TESTCASE=resident_pv_soc_smoke')] = '+TESTCASE=resident_pv_soc_abba'
    return dict(schema='resident-pv-abba-run-v1', kind='abba', soc_build=str(socdir), build=str(build),
        smoke_run=str(smoke), smoke_admission=admission, soc_receipt_sha256=sha(socdir/'build.json'),
        software_receipt_sha256=sha(build/'build.json'), commands=commands, environment=env,
        python=python, checker_inventory=inventory, sim_seconds=s.SIM_SECONDS,
        protocol_seconds=s.PROTOCOL_SECONDS, service_seconds=s.SERVICE_SECONDS, automatic_launch=False)


def frozen_receipt(out):
    return dict(state='PREPARED_ABBA_NOT_EXECUTED', parent_review_required=True,
                execution='NOT_RUN', source_pins_sha256=sha(out/'source-pins.json'))


def verify_prepared(out):
    out = output_path(out)
    require(json.loads((out/'prepared.json').read_text()) == frozen_receipt(out), 'ABBA prepared receipt drift')
    pins = json.loads((out/'source-pins.json').read_text())
    e.contract.verify(pins)
    selected = json.loads((out/'selection.json').read_text())
    socdir, build, smoke = (Path(selected[k]) for k in ('soc_build', 'build', 'smoke_run'))
    soc, software, mandatory, inventory, admission = collect(socdir, build, smoke)
    require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing ABBA/admission input pin')
    require(selected == selection(out, socdir, build, smoke, soc, software, inventory, admission,
        selected['environment'], str(Path(sys.executable).resolve())), 'ABBA selection/inventory drift')
    require({p.name for p in (out/'inputs').iterdir()} == set(OWN), 'Unexpected frozen ABBA input')
    for name in OWN:
        require(pins.get(str(out/'inputs'/name)) == pins.get(str(EVAL/name)) == sha(out/'inputs'/name),
                'Frozen ABBA runner/document drift')
    for name in ('selection.json', 'host-tests.log', 'host-tests.command.json',
                 'image-contract.log', 'image-contract.command.json'):
        require(pins.get(str(out/name)) == sha(out/name), 'Unpinned ABBA preflight evidence')
    return selected, pins, soc, software


def prepare(socdir, build, smoke, output):
    require(Path(__file__).resolve() == EVAL/'run_abba.py', 'Prepare with the original reviewed ABBA runner')
    out = output_path(output)
    require(not out.exists(), 'Preserve previous attempts; fresh output required')
    socdir, build, smoke = (Path(p).resolve(strict=True) for p in (socdir, build, smoke))
    out.mkdir()
    (out/'work').mkdir()
    status = dict(state='PREFLIGHT', owner_pid=os.getpid(), child_pid=None, execution='NOT_RUN')
    report = dict(state='FAIL', execution='NOT_RUN', performance_measured=False)
    try:
        soc, software, pins, inventory, admission = collect(socdir, build, smoke)
        (out/'inputs').mkdir()
        for name in OWN:
            dest = out/'inputs'/name
            shutil.copyfile(EVAL/name, dest)
            dest.chmod(0o444)
            e.merge(pins, {str(dest): sha(dest)})
        python, env = str(Path(sys.executable).resolve()), s.environment()
        selected = selection(out, socdir, build, smoke, soc, software, inventory, admission, env, python)
        e.save(out/'selection.json', selected)
        e.merge(pins, {str(out/'selection.json'): sha(out/'selection.json')})
        os.environ.clear()
        os.environ.update(env)
        s.execute([python, '-B', str(out/'inputs/test_run_abba.py'), '-v'], out/'inputs',
            out/'host-tests.log', 60, status, out/'status.json', 'HOST_TESTS')
        s.execute(selected['commands']['image_contract'], out/'work', out/'image-contract.log',
            180, status, out/'status.json', 'IMAGE_CONTRACT')
        require(inventory == s.checker_inventory(), 'ara_verify inventory drift')
        e.contract.verify(pins)
        e.merge(pins, {str(out/n): sha(out/n) for n in ('host-tests.log', 'host-tests.command.json',
            'image-contract.log', 'image-contract.command.json')})
        e.save(out/'source-pins.json', pins)
        e.save(out/'prepared.json', frozen_receipt(out))
        verify_prepared(out)
        report.update(state='PREPARED_ABBA_NOT_EXECUTED', source_pins_sha256=sha(out/'source-pins.json'))
    except BaseException as exc:
        report['error'] = repr(exc)
    e.save(out/'prepare-report.json', report)
    status.update(state=report['state'], child_pid=None)
    s.status_save(out/'status.json', status)
    require(report['state'] == 'PREPARED_ABBA_NOT_EXECUTED', 'ABBA preflight failed; retained '+str(out))
    return report


def service_unit(out):
    return 'resident-pv-soc-abba-'+out.name+'.service'


def service_command(out, review):
    verify_prepared(out)
    require(sha(out/'source-pins.json') == review, 'ABBA review hash mismatch')
    return ['/usr/bin/systemd-run', '--user', '--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'work'), '--property=RuntimeMaxSec=4500',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        str(Path(sys.executable).resolve()), '-B', '-u', str(out/'inputs/run_abba.py'),
        'run', '--output', str(out), '--parent-reviewed', '--review-sha256', review]


def run(out, parent_reviewed, review):
    out = output_path(out)
    require(parent_reviewed and sha(out/'source-pins.json') == review, 'Explicit ABBA bundle review required')
    require(Path(__file__).resolve() == out/'inputs/run_abba.py', 'Run the frozen ABBA worker')
    unit = service_unit(out)
    cgroup = Path('/proc/self/cgroup').read_text().strip().splitlines()[-1].split(':', 2)[-1]
    pid = int(subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit,
        '--property=MainPID', '--value'], text=True, timeout=10).strip())
    s.direct_owner(cgroup, unit, pid, os.getpid())
    require(not (out/'result.json').exists() and not any((out/'work').iterdir()), 'Preserve prior ABBA attempt')
    status = dict(state='PREFLIGHT', owner_pid=os.getpid(), child_pid=None)
    result = dict(state='FAIL', kind='abba', numerical_checked=False, independent_protocol_checked=False,
        performance_measured=False, performance_acceptance=False, deployment_approved=False, whole_model=False)
    try:
        selected, pins, soc, software = verify_prepared(out)
        os.environ.clear()
        os.environ.update(selected['environment'])
        s.execute(selected['commands']['image_contract'], out/'work', out/'run-image-contract.log',
            180, status, out/'status.json', 'IMAGE_CONTRACT')
        e.contract.verify(pins)
        started = time.monotonic()
        s.execute(selected['commands']['simulation'], out/'work', out/'work/console.log',
            s.SIM_SECONDS, status, out/'status.json', 'RUNNING')
        wall = time.monotonic()-started
        log, vector = out/'work/run.vcs.log', out/'work/vector_trace.csv'
        text = log.read_text()
        s.successful_log(text)
        numeric, akv, vectors = check_numerical(text, software), check_akv(text), check_vectors(vector)
        resident = e.check_resident_work(vector, text, 'abba')
        require(resident['commands'] == 6 and resident['numerical_checked'] is False and
            resident['protocol_checked'] is False, 'ABBA resident checker scope mismatch')
        s.execute(selected['commands']['protocol'], out/'work', out/'work/checker.log',
            s.PROTOCOL_SECONDS, status, out/'status.json', 'PROTOCOL_CHECK')
        s.check_protocol(json.loads((out/'work/uvm_result.json').read_text()), soc, software, log, vector)
        require(sha(out/'source-pins.json') == review, 'ABBA reviewed inventory drift')
        e.contract.verify(pins)
        post, _, _, _ = verify_prepared(out)
        require(post == selected and sha(out/'source-pins.json') == review, 'ABBA post-run selection drift')
        result.update(state='PASS', numerical_checked=True, independent_protocol_checked=True,
            post_pins_match=True, post_image_match=True, numerical=numeric, akv_work=akv, vector_work=vectors,
            resident_work=resident, performance_measured=True, simulation_wall_seconds=wall,
            source_pins_sha256=sha(out/'source-pins.json'), smoke_admission=selected['smoke_admission'],
            soc_build=selected['soc_build'], build=selected['build'], software_sha256=software['elf_sha256'],
            image_sha256=sha(soc['simv']), configuration=soc['configuration'])
    except BaseException as exc:
        result.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
    result['artifacts'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file() and
        p.name not in ('status.json', 'service.stdout.log', 'service.stderr.log')}
    e.save(out/'result.json', result)
    status.update(state=result['state'], child_pid=None)
    s.status_save(out/'status.json', status)
    print(json.dumps(dict(state=result['state'], output=str(out))), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare', allow_abbrev=False)
    for name in ('soc-build', 'build', 'smoke-run', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    for action in ('preflight', 'service-command', 'run'):
        p = sub.add_parser(action, allow_abbrev=False)
        p.add_argument('--output', type=Path, required=True)
        if action != 'preflight':
            p.add_argument('--review-sha256', required=True)
        if action == 'run':
            p.add_argument('--parent-reviewed', action='store_true')
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        print(json.dumps(prepare(args.soc_build, args.build, args.smoke_run, args.output), indent=2))
    elif args.action == 'preflight':
        verify_prepared(output_path(args.output))
        print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif args.action == 'service-command':
        print(shlex.join(service_command(output_path(args.output), args.review_sha256)))
    else:
        return int(run(args.output, args.parent_reviewed, args.review_sha256)['state'] != 'PASS')
    return 0


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for _signal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(_signal, interrupted)
    sys.exit(main())
