#!/usr/bin/env python3
"""One reviewed feature-bearing SDK attempt on accepted Stage3 BUILD02.

prepare/preflight/service-command do not launch VCS. The parent separately
reviews source-pins.json and launches the printed direct-owner service command.
Firmware is selected by an explicit build receipt SHA, never a latest alias.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
ORIGINAL = ROOT/'verification/performance/next_mechanism/stage4/resident_features/full_call'
SHARED = ROOT/'verification/performance/resident_rvv/qk_shared'
SOC = OUT/'stage3_soc_20261110_02'
SOC_SHA = 'a947cd4ed4dd16c07bfe0335f28c3c13d88178593d4b1b49090bff8d30fd849b'
BUILDER_SHA = 'ad6cfb879e5ee61344a92591f2d78dd290e4a649b543e09b7f179ce88c3337b2'
IMAGE_CHECK = ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
IMAGE_CHECK_SHA = '6b715db42be1baaf8fb6d7bb2714246786b99f3610ce2c74993950fcdef6bc08'
OWN = ('vcs_run.py', 'test_vcs_run.py')
SIM_SECONDS, CHECK_SECONDS, PROTOCOL_SECONDS, SERVICE_SECONDS = 5400, 300, 900, 7200
STEPS = (('image_contract', 'image-contract', 180), ('simulation', 'console', SIM_SECONDS),
         ('sdk', 'sdk', CHECK_SECONDS), ('protocol', 'protocol', PROTOCOL_SECONDS))
PREP_FILES = ('selection.json', 'launch-receipt.json', 'runner-inventory.json',
              'host-tests.log', 'host-tests.command.json', 'image-contract.log',
              'image-contract.command.json', 'runtime-link.log', 'runtime-link.command.json')
ENTRY = 'akv_experimental_attention_execute_features_v2_native'
ENTRY_NAMES = ('akv_decode_execute', ENTRY, 'akv_experimental_qk_f16_pair_panel4',
               '__wrap_akv_experimental_pv_f16_pair', 'akv_experimental_resident_qk',
               'akv_experimental_resident_pv', 'akv_experimental_resident_pv_prepare', 'rotation_body')
REQUIRED_PLUSARGS = ('+AKV_PERF', '+AKV_SUMMARY', '+RESIDENT_QK_PERF',
                     '+RESIDENT_PV_PERF', '+RESIDENT_PV_WATCHDOG')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = HERE/'build_soc.py' if (HERE/'build_soc.py').exists() else SHARED/'build_soc.py'
if hashlib.sha256(builder.read_bytes()).hexdigest() != BUILDER_SHA:
    raise ValueError('Unreviewed Stage3 SoC contract')
b = load(builder, 'stage4_features_run_soc_contract')


def digest(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def merge(pins, extra):
    for path, expected in extra.items():
        path = str(path)
        b.require(path not in pins or pins[path] == expected, 'Conflicting pin: '+path)
        pins[path] = expected


def positive(value):
    return type(value) is int and value > 0


def perf_entries(resident):
    return dict(zip(ENTRY_NAMES, (2, 1, 0 if resident else 3, 0 if resident else 3,
                                 3 if resident else 0, 3 if resident else 0,
                                 3 if resident else 0, 0 if resident else 3)))


def software_path(path):
    return b.output_path(Path(path), 'stage4_features_full_call_build_')


def checked_work(sw):
    b.require(sw.get('schema') == 'stage4-features-full-call-v1' and
              sw.get('state') == 'BUILT_NOT_EXECUTED' and sw.get('kind') in ('perf', 'functional') and
              isinstance(sw.get('scope'), str) and bool(sw['scope']) and
              sw.get('post_pins_match') is True, 'Wrong/unsealed firmware receipt')
    work = sw['expected_work']
    b.require(all(positive(work.get(k)) for k in
                  ('calls', 'output_values', 'legacy_commands', 'resident_commands')),
              'Missing numerical/work counts')
    per_call = work.get('legacy_per_call')
    b.require(isinstance(per_call, list) and len(per_call) == work['calls'] and
              all(positive(n) for n in per_call) and sum(per_call) == work['legacy_commands'],
              'Inconsistent per-call legacy work')
    entries = work.get('actual_entries')
    b.require(isinstance(entries, dict) and set(entries) == set(ENTRY_NAMES) and positive(entries.get(ENTRY)) and
              positive(entries.get('akv_decode_execute')) and
              all(isinstance(k, str) and type(v) is int and v >= 0 for k, v in entries.items()),
              'Missing actual SDK entry contract')
    if sw['kind'] == 'perf':
        b.require(work['calls'] == 4 and work['output_values'] == 1024 and
                  per_call == [237, 4, 4, 237] and work['legacy_commands'] == 482 and
                  work['resident_commands'] == 12 and
                  entries == {k: 2*perf_entries(False)[k]+2*perf_entries(True)[k] for k in ENTRY_NAMES},
                  'Performance requires equal-work H2/D128/T137 ABBA')
    return work


def checker_files(sw, root):
    dependencies = sw.get('checker_dependencies')
    b.require(isinstance(dependencies, dict) and {'check.py', 'fixture.py'} <= dependencies.keys(),
              'Missing frozen checker closure')
    pins = {}
    for name, expected in dependencies.items():
        b.require(isinstance(name, str) and name and Path(name).as_posix() == name and
                  not Path(name).is_absolute() and '..' not in Path(name).parts and digest(expected),
                  'Malformed checker dependency')
        path = root/name
        b.require(path.resolve() == path.absolute() and path.is_file(), 'Linked/missing checker input')
        pins[str(path)] = expected
    b.verify(pins)
    return pins


def software_receipt(software, build_sha):
    software = software_path(software)
    b.require(digest(build_sha), 'Explicit reviewed build SHA required')
    b.verify({software/'build.json': build_sha})
    sw = b.read(software/'build.json')
    checked_work(sw)
    b.require(sw.get('elf') == str(software/'attention_features.elf') and
              digest(sw.get('elf_sha256')) and digest(sw.get('source_pins_sha256')),
              'Wrong firmware/pin identity')
    b.verify({software/'source-pins.json': sw['source_pins_sha256'],
              software/'attention_features.elf': sw['elf_sha256']})
    pins = b.read(software/'source-pins.json')
    b.verify(pins)
    merge(pins, sw['artifacts'])
    merge(pins, {software/'build.json': build_sha,
                 software/'source-pins.json': sw['source_pins_sha256'], sw['elf']: sw['elf_sha256']})
    closure = checker_files(sw, software/'inputs')
    b.require(all(pins.get(p) == h for p, h in closure.items()), 'Unpinned checker dependency')
    b.verify(pins)
    return sw, pins


def checker(software, build_sha, local=None):
    sw, pins = software_receipt(software, build_sha)
    root = Path(software)/'inputs' if local is None else Path(local)
    checker_files(sw, root)
    module = load(root/'check.py', 'stage4_features_run_frozen_check')
    b.require(Path(module.f.__file__).resolve() == (root/'fixture.py').resolve(), 'Wrong checker fixture import')
    b.require(module.build_receipt(Path(software)) == sw, 'Checker/build receipt disagreement')
    b.verify(pins)
    return module


def protocol_inventory():
    root = ROOT/'verification/ara_verify'
    paths = sorted(root.rglob('*.py'))
    b.require(root/'uvm_dut.py' in paths and all(not p.is_symlink() for p in paths),
              'Incomplete/linked independent protocol checker')
    return {str(p): b.sha(p) for p in paths}


def source_layout(socdir, software, sw):
    layout = {name: ORIGINAL/name for name in OWN}
    layout.update({name: socdir/'inputs'/name for name in ('build_soc.py', *b.HELPERS)})
    layout.update({'checker/'+name: software/'inputs'/name for name in sw['checker_dependencies']})
    layout['image-check.sh'] = IMAGE_CHECK
    layout.update({'verification/'+str(Path(p).relative_to(ROOT/'verification')): Path(p)
                   for p in protocol_inventory()})
    return layout


def collect(socdir, software, build_sha):
    socdir, software = b.output_path(Path(socdir)), software_path(software)
    b.require(socdir == SOC, 'Only accepted Stage3 BUILD02; no replacement/rebuild')
    b.verify({socdir/'build.json': SOC_SHA, socdir/'inputs/build_soc.py': BUILDER_SHA,
              IMAGE_CHECK: IMAGE_CHECK_SHA})
    soc, pins = b.checked_build(socdir)
    sw, fw_pins = software_receipt(software, build_sha)
    checker(software, build_sha)
    merge(pins, fw_pins)
    merge(pins, {str(p): b.sha(p) for p in source_layout(socdir, software, sw).values()})
    tools = (sys.executable, '/usr/bin/bash', '/usr/bin/readelf', '/usr/bin/ldd',
             '/usr/bin/systemctl', '/usr/bin/systemd-run', '/usr/bin/awk', '/usr/bin/sed',
             '/usr/bin/grep', '/usr/bin/tail', '/usr/bin/head')
    merge(pins, {str(Path(p).resolve()): b.sha(Path(p).resolve()) for p in tools})
    b.verify(pins)
    return soc, sw, pins


def environment(socdir, out):
    source = b.read(socdir/'plan.json')['environment']
    needed = ('VCS_HOME', 'VCS_ARCH_OVERRIDE', 'SNPSLMD_LICENSE_FILE', 'HOME')
    b.require(all(source.get(k) for k in needed), 'Missing accepted VCS environment')
    env = {k: source[k] for k in (*needed, 'LM_LICENSE_FILE') if source.get(k)}
    paths = [str(Path(env['VCS_HOME'])/'linux64/lib'), *source.get('LD_LIBRARY_PATH', '').split(':')]
    env['LD_LIBRARY_PATH'] = ':'.join(dict.fromkeys(p for p in paths if p))
    env.update(PATH='/usr/bin:/bin', LC_ALL='C', TMPDIR='/tmp',
               PYTHONPATH=str(out/'inputs/verification'), PYTHONDONTWRITEBYTECODE='1',
               READELF='/usr/bin/readelf')
    b.require(all(isinstance(v, str) and '\n' not in v and '\0' not in v for v in env.values()),
              'Malformed execution environment')
    return env


def recipes(out, soc, sw, software, python):
    work, simv, elf = out/'work', soc['simv'], sw['elf']
    return dict(
        image_contract=['/usr/bin/bash', str(out/'inputs/image-check.sh'), str(Path(simv).parent), elf, 'akv_v2'],
        simulation=[simv, '-no_save', '-l', str(work/'run.vcs.log'), '+PRELOAD='+elf,
            '+TESTCASE=stage4_features_full_call', '+NO_FSDB', '+NO_INSTR_TRACE',
            '+COMMIT_TRACE='+str(work/'commit.csv'), '+VECTOR_TRACE='+str(work/'vector_trace.csv'),
            *REQUIRED_PLUSARGS, '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
        sdk=[python, '-B', str(out/'inputs/checker/check.py'), '--build', str(software),
             '--log', str(work/'run.vcs.log'), '--vector', str(work/'vector_trace.csv'),
             '--commit', str(work/'commit.csv')],
        protocol=[python, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
            '--require-axi', '--require-axi-write', '--vector-trace', str(work/'vector_trace.csv'),
            '--log', str(work/'run.vcs.log'), '--simv', simv, '--elf', elf,
            '--output', str(work/'uvm_result.json')])


def selection(out, socdir, software, build_sha, soc, sw):
    python = str(Path(sys.executable).resolve())
    return dict(schema='stage4-features-full-call-vcs-v1', kind=sw['kind'], soc_build=str(socdir),
        software_build=str(software), soc_receipt_sha256=SOC_SHA, software_receipt_sha256=build_sha,
        firmware_pins_sha256=sw['source_pins_sha256'], elf_sha256=sw['elf_sha256'],
        configuration=soc['configuration'], image_contract=soc['image_contract'],
        cpu_overlay=soc['cpu_overlay'], image_pins=soc['image_pins'],
        checker_dependencies=sw['checker_dependencies'], expected_work=sw['expected_work'],
        protocol_inventory=protocol_inventory(), scope=sw['scope'],
        python=python, environment=environment(socdir, out),
        commands=recipes(out, soc, sw, software, python), sim_seconds=SIM_SECONDS,
        checker_seconds=CHECK_SECONDS, protocol_seconds=PROTOCOL_SECONDS, service_seconds=SERVICE_SECONDS,
        automatic_retry=False, fsdb=False, full_ggml=False, performance_acceptance=False)


def output_path(path):
    return b.output_path(Path(path), 'stage4_resident_features_vcs_')


def service_unit(out):
    return 'stage4-features-full-call-'+out.name+'.service'


def service_argv(out, s, review):
    return ['/usr/bin/systemd-run', '--user', '--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'work'), '--property=RuntimeMaxSec='+str(SERVICE_SECONDS),
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        *['--setenv='+k+'='+v for k, v in sorted(s['environment'].items())],
        s['python'], '-B', '-u', str(out/'inputs/vcs_run.py'), 'run', '--output', str(out),
        '--parent-reviewed', '--review-sha256', review]


def host_command(out, name, argv, env, seconds):
    b.save(out/(name+'.command.json'), dict(argv=argv, cwd=str(out), timeout_seconds=seconds))
    with (out/(name+'.log')).open('x') as stream:
        proc = subprocess.run(argv, cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=seconds)
    b.require(proc.returncode == 0, 'Preparation failed: '+name)
    return (out/(name+'.log')).read_text()


def runtime_libraries(text):
    b.require('not found' not in text, 'Unresolved simulator library')
    libraries = re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)', text, re.M)
    b.require(libraries, 'Missing runtime loader evidence')
    return {str(Path(p).resolve()): b.sha(Path(p).resolve()) for p in libraries}


def prepare(out, socdir, software, build_sha):
    b.require(HERE == ORIGINAL, 'Prepare with the original reviewed runner')
    out, socdir, software = output_path(out), b.output_path(Path(socdir)), software_path(software)
    b.require(not out.exists(), 'Preserve every prior output/attempt')
    out.mkdir(); (out/'inputs').mkdir(); (out/'work').mkdir()
    report = dict(state='FAIL', execution='NOT_RUN', simulation_started=False, automatic_retry=False)
    try:
        soc, sw, pins = collect(socdir, software, build_sha)
        for name, src in source_layout(socdir, software, sw).items():
            dest = out/'inputs'/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        checker(software, build_sha, out/'inputs/checker')
        inventory = b.files(out/'inputs'); b.save(out/'runner-inventory.json', inventory)
        s = selection(out, socdir, software, build_sha, soc, sw); b.save(out/'selection.json', s)
        b.save(out/'launch-receipt.json', dict(environment=s['environment'], execution='NOT_RUN',
            service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')))
        host_command(out, 'host-tests', [s['python'], '-B', str(out/'inputs/test_vcs_run.py'), '-v'],
                     s['environment'], 180)
        checked_image_log(host_command(out, 'image-contract', s['commands']['image_contract'], s['environment'], 180))
        linked = host_command(out, 'runtime-link', ['/usr/bin/ldd', soc['simv']], s['environment'], 30)
        merge(pins, runtime_libraries(linked))
        merge(pins, inventory); merge(pins, {str(out/n): b.sha(out/n) for n in PREP_FILES})
        b.verify(pins); b.save(out/'source-pins.json', pins)
        report.update(state='PREPARED_NOT_EXECUTED', host_tests_passed=True,
                      source_pins_sha256=b.sha(out/'source-pins.json'))
        b.save(out/'prepared.json', report); verify_prepared(out)
    except BaseException as exc:
        report.update(state='FAIL', error=repr(exc))
    b.save(out/'prepare-report.json', report)
    b.require(report['state'] == 'PREPARED_NOT_EXECUTED', 'Preparation failed; retained '+str(out))
    return report


def verify_prepared(out):
    out = output_path(out)
    s, pins, prepared = (b.read(out/n) for n in ('selection.json', 'source-pins.json', 'prepared.json'))
    b.require(prepared == dict(state='PREPARED_NOT_EXECUTED', execution='NOT_RUN', simulation_started=False,
        automatic_retry=False, host_tests_passed=True, source_pins_sha256=b.sha(out/'source-pins.json')),
        'Prepared receipt drift')
    b.verify(pins); b.exact_files(out/'inputs', b.read(out/'runner-inventory.json'))
    socdir, software = Path(s['soc_build']), software_path(s['software_build'])
    build_sha = s['software_receipt_sha256']
    soc, sw, required = collect(socdir, software, build_sha)
    checker(software, build_sha, out/'inputs/checker')
    expected = {str(out/'inputs'/name): b.sha(src) for name, src in source_layout(socdir, software, sw).items()}
    b.require(b.read(out/'runner-inventory.json') == expected, 'Frozen runner/checker inventory drift')
    merge(required, expected); merge(required, {str(out/n): b.sha(out/n) for n in PREP_FILES})
    merge(required, runtime_libraries((out/'runtime-link.log').read_text()))
    b.require(all(pins.get(p) == h for p, h in required.items()), 'Missing mandatory pin')
    b.require(s == selection(out, socdir, software, build_sha, soc, sw), 'Selection/configuration/recipe drift')
    b.require(b.read(out/'launch-receipt.json') == dict(environment=s['environment'], execution='NOT_RUN',
        service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')), 'Launch recipe drift')
    return s, pins, soc, sw


def service_command(out, review):
    s, *_ = verify_prepared(out)
    b.require(review == b.sha(out/'source-pins.json') and
              not any((out/n).exists() for n in ('attempt.json', 'owner.json', 'result.json')) and
              not any((out/'work').iterdir()), 'Review mismatch or already attempted')
    return service_argv(out, s, review)


def checked_image_log(text):
    rows = text.splitlines()
    b.require(all(rows.count(line) == 1 for line in
                  ('sim_akv_enabled=1', 'sim_akv_v2_enabled=1', 'sim_l2_bytes=16777216')),
              'AKV-v2/image capacity contract evidence missing')


def successful_log(text):
    b.require(text.count('Core Test *** SUCCESS ***') == 1 and
              not re.search(r'Fatal:|Error:|Error-|\bFAILED\b', text), 'Firmware/assertion/EOC failure')


def checked_sdk(proof, sw):
    work = checked_work(sw)
    b.require(proof.get('state') == 'SDK_FEATURES_CHECKED' and proof.get('scope') == sw['scope'] and
              all(proof.get(k) is False for k in
                  ('protocol_checked', 'post_image_checked', 'performance_acceptance', 'whole_model')),
              'Incomplete/wrong-scope SDK result')
    numerical = proof.get('numerical', {})
    b.require(numerical.get('calls') == work['calls'] and numerical.get('output_values') == work['output_values'] and
              numerical.get('bitexact') is True and numerical.get('fflags_checked') is True and
              numerical.get('vcsr_vstart_checked') is True and
              numerical.get('non_rne_pair_checked') is (sw['kind'] == 'functional') and
              isinstance(numerical.get('fcsr'), list) and len(numerical['fcsr']) == work['calls'] and
              all(type(v) is int and 0 <= v <= 255 for v in numerical['fcsr']),
              'Missing bit-exact numerical/CSR checks')
    legacy = proof.get('legacy_work', {})
    b.require(legacy.get('commands') == work['legacy_commands'] and
              legacy.get('per_call') == work['legacy_per_call'] and
              isinstance(proof.get('resident_work'), list) and
              len(proof['resident_work']) == work['resident_commands'] and
              proof.get('vector_work', {}).get('resident_commands') == work['resident_commands'],
              'SDK work contract mismatch')
    entries = proof.get('actual_entries', {})
    rows = entries.get('per_call')
    b.require(entries.get('calls') == work['calls'] and entries.get('rotation_branch_body_checked') is True and
              isinstance(rows, list) and len(rows) == work['calls'], 'Missing per-call retirement proof')
    totals = Counter()
    for row in rows:
        b.require(isinstance(row, dict) and set(row) == set(work['actual_entries']) and
                  all(type(v) is int and v >= 0 for v in row.values()), 'Invalid actual entry counts')
        totals.update(row)
    b.require(dict(totals) == work['actual_entries'], 'SDK entry totals differ from build contract')
    timing = numerical.get('timing', {})
    for name in ('full_call_cycles', 'issue_cycles', 'final_drain_cycles'):
        b.require(isinstance(timing.get(name), list) and len(timing[name]) == work['calls'] and
                  all(positive(v) for v in timing[name]), 'Missing complete-call/drain timing')
    full, issue, drain = (timing[k] for k in ('full_call_cycles', 'issue_cycles', 'final_drain_cycles'))
    b.require(all(a == i+d for a, i, d in zip(full, issue, drain)), 'Incorrect complete-call denominator')
    if sw['kind'] == 'perf':
        baseline, resident = (full[0]+full[3])/2, (full[1]+full[2])/2
        b.require(rows == [perf_entries(on) for on in (False, True, True, False)] and
                  timing.get('strong_baseline_mean') == baseline and timing.get('resident_mean') == resident and
                  timing.get('full_call_speedup') == baseline/resident, 'Wrong ABBA route/timing denominator')


def checked_protocol(proof, soc, sw, log, vector):
    image = {p: h for p, h in soc['image_pins'].items() if p == soc['simv'] or p.endswith('.so')}
    b.require(any(p.endswith('.so') for p in image), 'No compiled design library')
    b.require(proof.get('status') == 'PASS' and proof.get('issues') == [] and
        proof.get('elf_sha256') == sw['elf_sha256'] and proof.get('simv_sha256') == b.sha(soc['simv']) and
        proof.get('sim_image_sha256') == image and proof.get('log_sha256') == b.sha(log) and
        proof.get('vector_trace_sha256') == b.sha(vector), 'Independent protocol identity/evidence mismatch')
    counts = proof.get('contract_counts') or {}
    b.require(all(type(counts.get(k)) is int and counts[k] == 0 for k in
                  ('exceptions', 'protocol_errors', 'outstanding')), 'Zero exceptions/errors/outstanding required')


def execution_receipts(out, s):
    for command, name, seconds in STEPS:
        b.require(b.read(out/'work'/(name+'.command.json')) == dict(argv=s['commands'][command],
            cwd=str(out/'work'), timeout_seconds=seconds), 'Executed recipe differs: '+command)
    owner = b.read(out/'owner.json')
    b.require(owner['unit'] == service_unit(out) and b.read(out/'attempt.json') ==
        dict(review_sha256=b.sha(out/'source-pins.json'), **owner), 'Attempt/ownership identity mismatch')
    b.direct_owner(owner['cgroup'], owner['unit'], owner['main_pid'], owner['owner_pid'])


def run(out, review, parent_reviewed):
    out = output_path(out)
    b.require(parent_reviewed and Path(__file__).resolve() == out/'inputs/vcs_run.py',
              'Parent-reviewed frozen worker required')
    owner = b.claim_attempt(out, review, service_unit(out), terminal='result.json')
    report = dict(state='FAIL', numerical_checked=False, independent_protocol_checked=False,
        actual_entries_checked=False, work_checked=False, automatic_retry=False, full_ggml=False,
        whole_model=False, performance_measured=False, performance_acceptance=False, deployment_approved=False)
    status = dict(state='PREFLIGHT', child_pid=None, **owner)
    try:
        base, _ = b.helpers(out/'inputs')
        b.require(not any((out/'work').iterdir()), 'Stale work; never retry')
        s, pins, soc, sw = verify_prepared(out)
        os.environ.clear(); os.environ.update(s['environment'])
        start = time.monotonic(); simulation_wall = None
        log, vector, commit = (out/'work'/n for n in ('run.vcs.log', 'vector_trace.csv', 'commit.csv'))
        for command, name, seconds in STEPS:
            tick = time.monotonic()
            base.execute(s['commands'][command], out/'work', out/'work'/(name+'.log'),
                         seconds, status, out/'status.json', command.upper())
            if command == 'image_contract': checked_image_log((out/'work/image-contract.log').read_text())
            if command == 'simulation':
                simulation_wall = time.monotonic()-tick; successful_log(log.read_text())
                io_pins = {str(p): b.sha(p) for p in (Path(sw['elf']), log, vector, commit, out/'work/console.log')}
            if command in ('sdk', 'protocol'): b.verify(io_pins)
        proof = b.read(out/'work/sdk.log'); checked_sdk(proof, sw)
        checked_protocol(b.read(out/'work/uvm_result.json'), soc, sw, log, vector)
        execution_receipts(out, s); verify_prepared(out)
        b.require(b.sha(out/'source-pins.json') == review, 'Reviewed pins changed')
        report.update(state='PASS', numerical_checked=True, independent_protocol_checked=True,
            actual_entries_checked=True, work_checked=True, post_pins_match=True, post_image_match=True,
            performance_measured=sw['kind'] == 'perf', kind=sw['kind'], scope=sw['scope'], source_pins_sha256=review,
            soc_build=s['soc_build'], software_build=s['software_build'], soc_receipt_sha256=SOC_SHA,
            software_receipt_sha256=s['software_receipt_sha256'], elf_sha256=sw['elf_sha256'],
            image_pins=soc['image_pins'], configuration=soc['configuration'], checked=proof,
            simulation_wall_seconds=simulation_wall, execution_wall_seconds=time.monotonic()-start,
            checker_io_sha256=io_pins | {str(out/'work'/n): b.sha(out/'work'/n) for n in
                                         ('sdk.log', 'protocol.log', 'uvm_result.json')})
    except BaseException as exc:
        report.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
    try:
        report['artifacts'] = b.files(out, exclude=('status.json', 'service.stdout.log', 'service.stderr.log'))
    except BaseException as exc:
        report.update(state='FAIL', artifact_error=repr(exc))
    b.save(out/'result.json', report)
    status.update(state=report['state'], child_pid=None)
    (out/'status.json').write_text(json.dumps(status, indent=2)+'\n')
    print(json.dumps(dict(state=report['state'], output=str(out))), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('prepare', 'preflight', 'service-command', 'run'):
        p = sub.add_parser(name, allow_abbrev=False); p.add_argument('--output', type=Path, required=True)
        if name == 'prepare':
            p.add_argument('--soc-build', type=Path, required=True)
            p.add_argument('--software-build', type=Path, required=True)
            p.add_argument('--build-sha256', required=True)
        if name in ('service-command', 'run'): p.add_argument('--review-sha256', required=True)
        if name == 'run': p.add_argument('--parent-reviewed', action='store_true')
    args = parser.parse_args(); out = output_path(args.output)
    if args.action == 'prepare': print(json.dumps(prepare(out, args.soc_build, args.software_build, args.build_sha256), indent=2))
    elif args.action == 'preflight': verify_prepared(out); print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif args.action == 'service-command': print(shlex.join(service_command(out, args.review_sha256)))
    else: return run(out, args.review_sha256, args.parent_reviewed)
    return 0


if __name__ == '__main__':
    def interrupted(sig, _frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    raise SystemExit(main())
