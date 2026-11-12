#!/usr/bin/env python3
"""Single direct-owner SoC continuation: wait by filesystem events, stop on failure."""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import struct
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
BUILDER_SHA = 'f5f8c6380a7a5c9e5f7c55e5a525e1eae956ae9be230a55404d0488880885610'
PROTOCOL = OUT/'stage3_attention_sdk_vcs_20261110_01'
PROTOCOL_SHA = '70ccad29ade83850f3c6a94276b8f60d7258513c4091939267641f550bbd3fb1'
PROTOCOL_PINS = 'd532da52c58a5742c294cab8a7148397a08e4e2ec13cb1a568e3f7c0582da3c2'
TAGPACK = OUT/'shared_fma_tagpack_acceptance_20261105_02/soc'
ISA = {
    'rv64uv-ara-vmul': '14b27da997dfa263b8ba1e874e0e0657df540a34e2f7bd07a07f9d158e368649',
    'rv64uv-ara-vfmacc': '1dda285079a5c96cb109ca450e00cb06f5f8ea9d7b2a1d4f13c2e44df87c5d98',
    'rv64uv-ara-vfwmacc': '947275822c51a3bdc1e5a79eb3e596ac4bec7431e7e897584b2da4810ebd6b5e',
}
SOFTWARE = {
    'qbs_m4': ('stage2_qwen3_attn_m4_build_20261109_04', 'c769005b73c70f2df22f5e9c1e04482a37f4c271be7985885895a52339a9339f'),
    'qbs_m8': ('stage2_qwen3_attn_m8_build_20261109_04', '3aa43cea622e4c2c9c371f79a98e3f9b09e33413de1c8a8a6d78cf83cdb405b6'),
    'resident_sdk': ('stage3_attention_sdk_build_20261110_02', 'ac91488d3ea3836121973fa2ecf54c5ef34a7798b1b510dbb2941d8bdedabd81'),
}
HELPERS = {
    'check_projection.py': ('verification/performance/next_mechanism/stage2/check_projection.py',
        'bf539a97ac63ba54239ecb5ce07ec6d52b1273f2f7e070225dc8bd7091c9d869'),
    'run_projection.py': ('verification/performance/next_mechanism/stage2/run_projection.py',
        '0769722dff1d1efb33ff7d3c66a21e9cdc89a6d0bf500f83c9d054c75dccadb7'),
}
OWN = ('soc_campaign.py', 'soc_campaign_test.py')
RUNS = tuple(('candidate', name) for name in (*ISA, *SOFTWARE)) + (('baseline', 'resident_sdk'),)
FMA_ROW = re.compile(r'^FMA_SOC_SUMMARY (\S+) shared=(\d+) cycles=(\d+) issued=(\d+) retired=(\d+) '
    r'blocked=(\d+) latency_wait=(\d+) fma=(\d+),(\d+),(\d+),(\d+)$', re.M)


def require(ok, message):
    if not ok: raise ValueError(message)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def builder():
    path = HERE/'soc_build.py'
    import hashlib
    require(hashlib.sha256(path.read_bytes()).hexdigest() == BUILDER_SHA, 'Builder source drift')
    return load(path, 'soc_campaign_build')


def same_sources(b, candidate, baseline):
    def relative(directory):
        return {str(Path(p).relative_to(directory/'source')): h
                for p, h in b.read(directory/'inventory.json')['source'].items()}
    require(relative(candidate) == relative(baseline), 'FMA pair must have identical RTL/dependency bytes')
    a, z = (b.read(p/'plan.json') for p in (candidate, baseline))
    require(a['configuration']['shared_fma'] == 1 and z['configuration']['shared_fma'] == 0 and
            {k:v for k,v in a['configuration'].items() if k != 'shared_fma'} ==
            {k:v for k,v in z['configuration'].items() if k != 'shared_fma'}, 'Not a single FMA selection pair')
    normalized = []
    commands = []
    for p in (candidate, baseline):
        text = (p/'sources.f').read_text().replace(str(p), '{BUILD}')
        normalized.append(text.replace('+define+ARA_SHARED_FMA=1\n', ''))
        commands.append([t.replace(str(p), '{BUILD}') for t in b.read(p/'plan.json')['command']])
    require(normalized[0] == normalized[1] and commands[0] == commands[1], 'Pair compile inputs differ beyond FMA macro')


def wait_builds(paths, timeout):
    """Watch close/rename events; never restart services or poll their progress."""
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC)
    if fd < 0: raise OSError(ctypes.get_errno(), 'inotify_init1')
    try:
        for path in paths:
            if libc.inotify_add_watch(fd, os.fsencode(path), 0x8 | 0x80) < 0:
                raise OSError(ctypes.get_errno(), 'inotify_add_watch')
        deadline = time.monotonic() + timeout
        while not all((path/'build.json').is_file() for path in paths):
            remaining = deadline-time.monotonic()
            require(remaining > 0 and select.select([fd], [], [], max(0, remaining))[0], 'Build completion event deadline')
            os.read(fd, 65536)
    finally:
        os.close(fd)


def checked_build(s, directory):
    b = s.tools(); plan, pins = s.preflight(directory)
    report = b.read(directory/'build.json')
    require(report['state'] == 'ENABLEMENT_SOC_BUILT_NOT_EXECUTED' and
            report['configuration'] == plan['configuration'] and report['cpu_overlay'] == b.CPU_OVERLAY and
            report['source_pins_sha256'] == b.sha(directory/'source-pins.json') and
            report['post_pins_match'] is True and report['post_image_match'] is True,
            'Unaccepted terminal build')
    image = b.image_inventory(directory/'sim')
    require(image == report['image_pins'] == b.read(directory/'image-pins.json'), 'Image membership/content drift')
    return report, pins | image | {str(directory/'build.json'): b.sha(directory/'build.json')}


def software(b, name):
    directory_name, digest = SOFTWARE[name]; directory = OUT/directory_name
    b.verify({directory/'build.json': digest})
    report = b.read(directory/'build.json')
    require(report['state'] == 'BUILT_NOT_EXECUTED' and report['post_pins_match'] is True and
            report['source_pins_sha256'] == b.sha(directory/'source-pins.json'), 'Unsealed firmware')
    pins = b.read(directory/'source-pins.json') | report.get('artifacts', {})
    pins.update({str(directory/'source-pins.json'): b.sha(directory/'source-pins.json'), str(directory/'build.json'): digest})
    require(pins.get(report['elf']) == report['elf_sha256'], 'Firmware absent from closure')
    if name.startswith('qbs_'):
        require((report['m'], report['n'], report['k'], report['trials'], report['flag_seeds']) ==
                (8, 64, 2048, [4, 4] if name == 'qbs_m4' else [8, 8], [0, 8]), 'Projection shape drift')
    b.verify(pins)
    return dict(directory=str(directory), elf=report['elf'], elf_sha256=report['elf_sha256'], receipt_sha256=digest), pins


def prepare(out, candidate, baseline):
    s = builder(); b = s.tools()
    require(not out.exists(), 'Preserve prior campaign')
    pins = {}
    for directory in (candidate, baseline):
        _, inherited = s.preflight(directory); b.verify(inherited)
        pins.update(inherited)
        pins[str(directory/'source-pins.json')] = b.sha(directory/'source-pins.json')
        pins[str(directory/'prepared.json')] = b.sha(directory/'prepared.json')
    same_sources(b, candidate, baseline)
    b.verify({PROTOCOL/'result.json': PROTOCOL_SHA, PROTOCOL/'source-pins.json': PROTOCOL_PINS})
    require(b.read(PROTOCOL/'result.json')['state'] == 'PASS', 'Independent protocol predecessor not accepted')
    protocol_pins = b.read(PROTOCOL/'source-pins.json')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    for name in (*OWN, 'soc_build.py'):
        src = HERE/name; shutil.copyfile(src, inputs/name)
        pins[str(src)] = pins[str(inputs/name)] = b.sha(src)
    for name in ('build_soc.py', 'base_build.py', 'closure_build.py'):
        src = candidate/'inputs'/name; shutil.copyfile(src, inputs/name)
        pins[str(inputs/name)] = b.sha(src)
    for name, (rel, digest) in HELPERS.items():
        b.verify({ROOT/rel: digest}); shutil.copyfile(ROOT/rel, inputs/name)
        pins[str(ROOT/rel)] = pins[str(inputs/name)] = digest
    protocol_root = PROTOCOL/'inputs/verification/ara_verify'
    for src in sorted(protocol_root.rglob('*.py')):
        require(protocol_pins.get(str(src)) == b.sha(src), 'Unpinned frozen protocol helper')
        dest = inputs/'verification/ara_verify'/src.relative_to(protocol_root)
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dest)
        pins[str(src)] = pins[str(dest)] = b.sha(src)
    pins[str(PROTOCOL/'result.json')] = PROTOCOL_SHA
    pins[str(PROTOCOL/'source-pins.json')] = PROTOCOL_PINS
    programs = {}
    for name, digest in ISA.items():
        src = TAGPACK/'inputs'/name; b.verify({src: digest})
        dest = inputs/name; shutil.copyfile(src, dest)
        pins[str(src)] = pins[str(dest)] = digest
        programs[name] = dict(elf=str(dest), elf_sha256=digest)
    for name in SOFTWARE:
        programs[name], extra = software(b, name); b.verify(extra); pins.update(extra)
    fw = OUT/SOFTWARE['resident_sdk'][0]
    checker = inputs/'checker'; checker.mkdir()
    for name in ('check.py', 'fixture.py'):
        src = fw/'inputs/fixture'/name
        require(pins.get(str(src)) == b.sha(src), 'Unpinned SDK checker/oracle')
        shutil.copyfile(src, checker/name); pins[str(checker/name)] = b.sha(src)
    environment = b.read(candidate/'plan.json')['environment'].copy()
    environment['LD_LIBRARY_PATH'] = str(Path(environment['VCS_HOME'])/'linux64/lib') + ':' + environment.get('LD_LIBRARY_PATH', '')
    environment.update(PYTHONPATH=str(inputs/'verification'), PYTHONDONTWRITEBYTECODE='1', READELF='/usr/bin/readelf')
    plan = dict(schema='enablement-soc-campaign-v1', candidate=str(candidate), baseline=str(baseline),
        programs=programs, runs=[list(r) for r in RUNS], environment=environment,
        python=str(Path(sys.executable).resolve()), automatic_retry=False,
        build_wait_seconds=7900, simulation_seconds=5400, protocol_seconds=1200, service_seconds=60000)
    b.save(out/'plan.json', plan)
    pins[str(out/'plan.json')] = b.sha(out/'plan.json')
    b.verify(pins); b.save(out/'source-pins.json', pins)
    b.save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=b.sha(out/'source-pins.json')))
    return dict(state='PREPARED_NOT_EXECUTED', review_sha256=b.sha(out/'source-pins.json'))


def successful(text):
    require(text.count('Core Test *** SUCCESS ***') == 1 and not re.search(
        r'(?im)(^\s*(?:Fatal:|Fatal-|Error:|Error-)|\$fatal|Assertion failed|\bFAILED\b|\bTIMEOUT\b)', text), 'EOC/assertion failure')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b', line):
            require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*', line), 'UVM failure')


def fma_summary(text, shared, floating=False):
    rows = FMA_ROW.findall(text)
    require(len(rows) == 4 and len({r[0] for r in rows}) == 4 and
            all(int(r[1]) == shared and r[3] == r[4] for r in rows), 'FMA selection/drain evidence')
    require(not floating or sum(int(r[3]) for r in rows) > 0, 'Missing native FP activity')
    return rows


def check_case(out, work, name, program, shared):
    text = (work/'run.vcs.log').read_text(); successful(text)
    fma_summary(text, shared, name in ('rv64uv-ara-vfmacc', 'rv64uv-ara-vfwmacc'))
    if name in ISA:
        stem = name.removeprefix('rv64uv-ara-')
        require(len(re.findall(r'^PASSED: .*[/\\]'+re.escape(stem)+r'\.c!$', text, re.M)) == 1, 'ISA numerical oracle verdict')
        return dict(state='ISA_CHECKED', case=name, self_checking_accepted_elf=True)
    if name.startswith('qbs_'):
        checker = load(out/'inputs/check_projection.py', 'enablement_projection_check')
        runner = load(out/'inputs/run_projection.py', 'enablement_projection_loans')
        result = checker.check_run(work/'run.vcs.log', Path(program['directory']), 1)
        build = json.loads((Path(program['directory'])/'build.json').read_text())
        result['actual_loans'] = runner.check_loans(text, build['n'], 1, checker.fields, build['trials'])
        return result
    require(name == 'resident_sdk', 'Unknown case')
    sys.modules.pop('fixture', None)
    sys.path.insert(0, str(out/'inputs/checker'))
    checker = load(out/'inputs/checker/check.py', 'enablement_sdk_check')
    result = checker.check(Path(program['directory']), work/'run.vcs.log', work/'vector.csv', work/'commit.csv')
    require(result['numerical']['calls'] == 3 and result['numerical']['output_values'] == 1088 and
            result['numerical']['bitexact'] is True and len(result['resident_work']) == 22 and
            result['legacy_work']['commands'] == 247, 'Incomplete original SDK proof')
    return result


def compare_cycles(baseline, candidate):
    require(len(baseline) == len(candidate) == 3 and all(type(v) is int and v > 0 for v in [*baseline, *candidate]),
            'Missing/incomplete full-call cycle data')
    return [dict(trial=i, fma0_cycles=z, fma1_cycles=a, cycle_delta=a-z,
                 fma0_over_fma1=z/a, regression=a>z) for i, (z, a) in enumerate(zip(baseline, candidate))]


def unit(out): return 'enablement-soc-campaign-'+out.name+'.service'


def verify_prepared(out, review):
    s = builder(); b = s.tools()
    require(review == b.sha(out/'source-pins.json') and b.read(out/'prepared.json') ==
            dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=review), 'Campaign review drift')
    plan, pins = b.read(out/'plan.json'), b.read(out/'source-pins.json')
    require(plan['runs'] == [list(r) for r in RUNS] and plan['automatic_retry'] is False, 'Finite queue drift')
    b.verify(pins)
    return s, b, plan, pins


def service(out, review):
    _, _, plan, _ = verify_prepared(out, review)
    require(not (out/'attempt.json').exists(), 'One campaign attempt only')
    return ['/usr/bin/systemd-run', '--user', '--unit='+unit(out), '--property=Type=exec',
        '--property=RuntimeMaxSec=60000', '--property=MemoryMax=8G', '--property=CPUQuota=100%',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        plan['python'], '-B', '-u', str(out/'inputs/soc_campaign.py'), 'execute',
        '--output', str(out), '--review-sha256', review]


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/soc_campaign.py', 'Frozen continuation worker required')
    s, b, plan, pins = verify_prepared(out, review)
    owner = b.claim_attempt(out, review, unit(out), terminal='result.json')
    base, _ = b.helpers(out/'inputs')
    status = dict(state='WAIT_BUILD_EVENTS', child_pid=None, **owner)
    base.save(out/'status.json', status)
    report = dict(state='FAIL', completed=[], performance_acceptance=False, whole_model=False, automatic_retry=False)
    try:
        paths = [Path(plan[k]) for k in ('candidate', 'baseline')]
        wait_builds(paths, plan['build_wait_seconds'])
        builds = {}
        for arm, path in zip(('candidate', 'baseline'), paths):
            builds[arm], extra = checked_build(s, path); pins.update(extra)
        same_sources(b, *paths)
        b.save(out/'build-binding.json', {arm: dict(path=plan[arm], sha256=b.sha(Path(plan[arm])/'build.json')) for arm in builds})
        pins[str(out/'build-binding.json')] = b.sha(out/'build-binding.json')
        os.environ.clear(); os.environ.update(plan['environment'])
        proofs = {}
        for arm, name in RUNS:
            b.verify(pins)
            work = out/(arm+'_'+name); work.mkdir()
            hw, program = builds[arm], plan['programs'][name]
            command = [hw['simv'], '-no_save', '-l', str(work/'run.vcs.log'), '+PRELOAD='+program['elf'],
                '+TESTCASE=enablement_soc_'+name, '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                '+AKV_PERF', '+AKV_SUMMARY', '+RESIDENT_QK_PERF', '+RESIDENT_PV_PERF', '+RESIDENT_PV_WATCHDOG',
                '+COMMIT_TRACE='+str(work/'commit.csv'), '+VECTOR_TRACE='+str(work/'vector.csv'),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
            base.execute(command, work, work/'console.log', plan['simulation_seconds'], status, out/'status.json', 'SIMULATION_'+name)
            io = {str(work/n): b.sha(work/n) for n in ('run.vcs.log', 'vector.csv', 'commit.csv')}
            proof = check_case(out, work, name, program, hw['configuration']['shared_fma'])
            b.save(work/'numerical.json', proof)
            protocol = [plan['python'], '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                '--require-axi', '--require-axi-write', '--vector-trace', str(work/'vector.csv'),
                '--log', str(work/'run.vcs.log'), '--simv', hw['simv'], '--elf', program['elf'], '--output', str(work/'protocol.json')]
            base.execute(protocol, work, work/'protocol.log', plan['protocol_seconds'], status, out/'status.json', 'PROTOCOL_'+name)
            p = b.read(work/'protocol.json')
            require(p['status'] == 'PASS' and p['issues'] == [] and p['elf_sha256'] == program['elf_sha256'] and
                    p['simv_sha256'] == b.sha(hw['simv']) and p['log_sha256'] == io[str(work/'run.vcs.log')] and
                    p['vector_trace_sha256'] == io[str(work/'vector.csv')], 'Independent protocol/identity failure')
            counts = p['contract_counts']
            require(all(counts[k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding')), 'Protocol work not drained')
            b.verify(io); b.verify(pins)
            proofs[(arm, name)] = proof
            report['completed'].append(dict(arm=arm, case=name, state='PASS', log_sha256=b.sha(work/'run.vcs.log')))
            base.save(out/'progress.json', report)
        comparison = compare_cycles(proofs[('baseline', 'resident_sdk')]['numerical']['full_call_cycles_diagnostic_only'],
                                    proofs[('candidate', 'resident_sdk')]['numerical']['full_call_cycles_diagnostic_only'])
        b.save(out/'full-call-comparison.json', dict(rows=comparison, same_elf=True, only_fma_macro_differs=True,
            model_speedup_claim=False, all_shapes_no_regression_claim=False))
        b.verify(pins)
        report.update(state='SOC_COMBINATION_CHECKED', post_pins_match=True, full_call_comparison=comparison,
            source_pins_sha256=review, build_binding_sha256=b.sha(out/'build-binding.json'))
    except BaseException as exc:
        report['error'] = repr(exc)
    b.save(out/'result.json', report)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'SOC_COMBINATION_CHECKED')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False); sub = parser.add_subparsers(dest='action', required=True)
    for name in ('prepare', 'service-command', 'execute'):
        p = sub.add_parser(name, allow_abbrev=False); p.add_argument('--output', type=Path, required=True)
        if name == 'prepare':
            p.add_argument('--candidate', type=Path, required=True); p.add_argument('--baseline', type=Path, required=True)
        else: p.add_argument('--review-sha256', required=True)
    a = parser.parse_args(); s = builder(); out = s.output(a.output)
    if a.action == 'prepare': print(json.dumps(prepare(out, s.output(a.candidate), s.output(a.baseline))), flush=True)
    elif a.action == 'service-command': print(json.dumps(service(out, a.review_sha256)))
    else: return execute(out, a.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    raise SystemExit(main())
