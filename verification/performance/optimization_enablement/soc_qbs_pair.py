#!/usr/bin/env python3
"""Two FMA=0 QBS calls after the sealed seven-run worker exits successfully."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
MAIN = OUT/'enablement_soc_campaign_20261111_01'
MAIN_REVIEW = 'fe7849a1147d4e31ca5e67a4b20b316bfd74dcef55123301a6e7e74310e7977c'
CAMPAIGN_SHA = '4f2f2bc06af8919c6c7d8421ebc8617b6f2931c6833f876528120e26fddfaf41'
CASES = ('qbs_m4', 'qbs_m8')
OWN = ('soc_qbs_pair.py', 'soc_qbs_pair_test.py')


def require(ok, message):
    if not ok: raise ValueError(message)


def campaign():
    path = HERE/'soc_campaign.py' if (HERE/'soc_campaign.py').exists() else MAIN/'inputs/soc_campaign.py'
    import hashlib
    require(hashlib.sha256(path.read_bytes()).hexdigest() == CAMPAIGN_SHA, 'Frozen campaign helper drift')
    spec = importlib.util.spec_from_file_location('qbs_pair_campaign', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def output(path):
    path = Path(path).absolute()
    require(path == path.resolve() and path.parent == OUT and path.name.startswith('enablement_soc_qbs_pair_'),
            'Fresh direct enablement_soc_qbs_pair_* output required')
    return path


def wait_main_exit(owner, timeout):
    # A pidfd refers to this process incarnation, not a reusable numeric PID.
    try:
        fd = os.pidfd_open(owner['main_pid'])
    except ProcessLookupError:
        return
    try:
        try:
            cgroup = Path('/proc')/str(owner['main_pid'])/'cgroup'
            require('/'+owner['unit'] in cgroup.read_text(), 'Main PID belongs to another service')
        except FileNotFoundError:
            require(select.select([fd], [], [], 0)[0], 'Main process vanished without exit event')
        require(select.select([fd], [], [], timeout)[0], 'Main worker exit deadline')
    finally:
        os.close(fd)


def main_verdict(report, runs):
    require(report.get('state') == 'SOC_COMBINATION_CHECKED' and report.get('post_pins_match') is True and
            report.get('source_pins_sha256') == MAIN_REVIEW, 'Main seven-run terminal is not PASS; dispatch prohibited')
    expected = [(arm, name, 'PASS') for arm, name in runs]
    actual = [(r.get('arm'), r.get('case'), r.get('state')) for r in report.get('completed', [])]
    require(actual == expected, 'Main seven-run completion inventory differs')


def compare_trials(case, baseline, candidate):
    require(case in CASES, 'Unknown QBS comparison case')
    mode = 4 if case == 'qbs_m4' else 8
    require(baseline.get('state') == candidate.get('state') == 'PASS' and
            baseline['outputs_bit_exact'] == candidate['outputs_bit_exact'] == 1024 and
            baseline['command_count'] == candidate['command_count'] == 8,
            'Incomplete projection numerical/work evidence')
    a, z = candidate['trials'], baseline['trials']
    require(len(a) == len(z) == 2, 'Missing/extra projection trial')
    rows = []
    identity = ('id', 'mode', 'status', 'commands', 'context', 'flags', 'expected_flags',
                'q8_bad', 'output_bad', 'guards_bad')
    for i, (zero, one) in enumerate(zip(z, a)):
        require(zero['id'] == one['id'] == i and zero['mode'] == one['mode'] == mode and
                all(zero[k] == one[k] for k in identity), 'Cross-mode/trial/flags/work comparison')
        require(type(zero['total']) is int and type(one['total']) is int and zero['total'] > 0 and one['total'] > 0,
                'Invalid complete-call cycles')
        rows.append(dict(case=case, trial=i, mode=mode, flags=zero['flags'], commands=zero['commands'],
            fma0_total=zero['total'], fma1_total=one['total'], delta=one['total']-zero['total'],
            ratio=zero['total']/one['total'], regression=one['total']>zero['total']))
    return rows


def prepare(out):
    c = campaign(); s, b, plan, inherited = c.verify_prepared(MAIN, MAIN_REVIEW)
    require(not out.exists(), 'Preserve every previous pair attempt')
    out.mkdir(); inputs = out/'inputs'
    shutil.copytree(MAIN/'inputs', inputs, symlinks=False)
    pins = dict(inherited)
    for path in inputs.rglob('*'):
        if path.is_file():
            original = MAIN/'inputs'/path.relative_to(inputs)
            require(inherited.get(str(original)) == b.sha(path), 'Copy not in sealed main execution closure')
            pins[str(path)] = b.sha(path)
    for name in OWN:
        shutil.copyfile(HERE/name, inputs/name)
        pins[str(HERE/name)] = pins[str(inputs/name)] = b.sha(HERE/name)
    for name in ('source-pins.json', 'prepared.json', 'plan.json', 'owner.json', 'attempt.json'):
        pins[str(MAIN/name)] = b.sha(MAIN/name)
    owner = b.read(MAIN/'owner.json')
    require(owner['unit'] == c.unit(MAIN) and owner['main_pid'] == owner['owner_pid'] and
            b.read(MAIN/'attempt.json') == dict(review_sha256=MAIN_REVIEW, **owner), 'Wrong main direct-owner binding')
    environment = plan['environment'].copy()
    environment['PYTHONPATH'] = str(inputs/'verification')
    new = dict(schema='enablement-soc-qbs-pair-v1', main=str(MAIN), main_review=MAIN_REVIEW,
        main_owner=owner, baseline=plan['baseline'], candidate=plan['candidate'],
        programs={k: plan['programs'][k] for k in CASES}, cases=list(CASES),
        python=plan['python'], environment=environment, automatic_retry=False,
        main_wait_seconds=60000, simulation_seconds=5400, protocol_seconds=1200, service_seconds=80000)
    b.save(out/'plan.json', new)
    pins[str(out/'plan.json')] = b.sha(out/'plan.json')
    b.verify(pins); b.save(out/'source-pins.json', pins)
    b.save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=b.sha(out/'source-pins.json')))
    return dict(state='PREPARED_NOT_EXECUTED', review_sha256=b.sha(out/'source-pins.json'))


def verified(out, review):
    c = campaign(); s = c.builder(); b = s.tools()
    require(review == b.sha(out/'source-pins.json') and b.read(out/'prepared.json') ==
            dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=review), 'Pair review drift')
    plan, pins = b.read(out/'plan.json'), b.read(out/'source-pins.json')
    require(plan['main'] == str(MAIN) and plan['main_review'] == MAIN_REVIEW and plan['cases'] == list(CASES)
            and plan['automatic_retry'] is False, 'Finite pair plan drift')
    b.verify(pins)
    return c, s, b, plan, pins


def unit(out): return 'enablement-soc-qbs-pair-'+out.name+'.service'


def service(out, review):
    _, _, _, plan, _ = verified(out, review)
    require(not (out/'attempt.json').exists(), 'One pair attempt only')
    return ['/usr/bin/systemd-run', '--user', '--unit='+unit(out), '--property=Type=exec',
        '--property=RuntimeMaxSec=80000', '--property=MemoryMax=8G', '--property=CPUQuota=100%',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        plan['python'], '-B', '-u', str(out/'inputs/soc_qbs_pair.py'), 'execute',
        '--output', str(out), '--review-sha256', review]


def protocol(base, b, plan, out, work, program, image, evidence, status):
    dest = work/'protocol.json'
    command = [plan['python'], '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
        '--require-axi', '--require-axi-write', '--vector-trace', evidence/'vector.csv',
        '--log', evidence/'run.vcs.log', '--simv', image['simv'], '--elf', program['elf'], '--output', dest]
    command = list(map(str, command))
    base.execute(command, work, work/'protocol.log', plan['protocol_seconds'], status, out/'status.json', 'PROTOCOL')
    proof = b.read(dest)
    wanted_image = {p: h for p, h in image['image_pins'].items() if p == image['simv'] or p.endswith('.so')}
    require(proof['status'] == 'PASS' and proof['issues'] == [] and
            proof['elf_sha256'] == program['elf_sha256'] and proof['simv_sha256'] == b.sha(image['simv']) and
            proof['sim_image_sha256'] == wanted_image and proof['log_sha256'] == b.sha(evidence/'run.vcs.log') and
            proof['vector_trace_sha256'] == b.sha(evidence/'vector.csv') and
            all(proof['contract_counts'][k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding')),
            'Independent protocol/work/image identity failure')


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/soc_qbs_pair.py', 'Frozen pair worker required')
    c, s, b, plan, pins = verified(out, review)
    owner = b.claim_attempt(out, review, unit(out), terminal='result.json')
    base, _ = b.helpers(out/'inputs')
    status = dict(state='WAIT_MAIN_PIDFD_EXIT', child_pid=None, main_wait_pid=plan['main_owner']['main_pid'], **owner)
    base.save(out/'status.json', status)
    report = dict(schema=plan['schema'], state='FAIL', completed=[], comparisons=[],
        source_pins_sha256=review, automatic_retry=False, performance_acceptance=False, whole_model=False)
    try:
        wait_main_exit(plan['main_owner'], plan['main_wait_seconds'])
        terminal = b.read(MAIN/'result.json')
        main_verdict(terminal, c.RUNS)
        b.verify({MAIN/'source-pins.json': MAIN_REVIEW})
        pins[str(MAIN/'result.json')] = b.sha(MAIN/'result.json')
        require(terminal['build_binding_sha256'] == b.sha(MAIN/'build-binding.json'), 'Main build binding drift')
        pins[str(MAIN/'build-binding.json')] = terminal['build_binding_sha256']
        c.same_sources(b, Path(plan['candidate']), Path(plan['baseline']))
        images = {}
        for arm in ('candidate', 'baseline'):
            images[arm], extra = c.checked_build(s, Path(plan[arm])); pins.update(extra)
        os.environ.clear(); os.environ.update(plan['environment'])
        artifacts = {}
        for name in CASES:
            program = plan['programs'][name]
            require(program == b.read(MAIN/'plan.json')['programs'][name], 'Not the exact main firmware/data contract')
            oldwork = MAIN/('candidate_'+name)
            original_hashes = b.files(oldwork)
            completed = next(r for r in terminal['completed'] if r['arm'] == 'candidate' and r['case'] == name)
            require(completed['log_sha256'] == original_hashes[str(oldwork/'run.vcs.log')], 'Candidate original log drift')
            c.successful((oldwork/'run.vcs.log').read_text())
            candidate = c.check_case(out, oldwork, name, program, 1)
            require(candidate == b.read(oldwork/'numerical.json'), 'Candidate original checker proof differs on replay')
            replay = out/('candidate_recheck_'+name); replay.mkdir()
            b.save(replay/'numerical.json', candidate)
            protocol(base, b, plan, out, replay, program, images['candidate'], oldwork, status)
            b.verify(original_hashes)
            artifacts.update(original_hashes); artifacts.update(b.files(replay))
            b.verify(pins)
            work = out/('baseline_'+name); work.mkdir()
            command = [images['baseline']['simv'], '-no_save', '-l', str(work/'run.vcs.log'),
                '+PRELOAD='+program['elf'], '+TESTCASE=enablement_soc_qbs_pair_'+name,
                '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                '+COMMIT_TRACE='+str(work/'commit.csv'), '+VECTOR_TRACE='+str(work/'vector.csv'),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
            base.execute(command, work, work/'console.log', plan['simulation_seconds'], status, out/'status.json', 'SIMULATION_'+name)
            raw = b.files(work)
            baseline = c.check_case(out, work, name, program, 0)
            b.save(work/'numerical.json', baseline)
            protocol(base, b, plan, out, work, program, images['baseline'], work, status)
            b.verify(raw); b.verify(pins)
            rows = compare_trials(name, baseline, candidate)
            b.save(work/'comparison.json', dict(rows=rows, elf_sha256=program['elf_sha256'], only_fma_macro_differs=True))
            artifacts.update(b.files(work))
            b.verify(artifacts)
            report['comparisons'].extend(rows)
            report['completed'].append(dict(arm='baseline', case=name, state='PASS', elf_sha256=program['elf_sha256']))
            base.save(out/'progress.json', report)
        b.verify(pins); b.verify(artifacts)
        b.save(out/'artifact-pins.json', artifacts)
        report.update(state='QBS_FMA_PAIR_CHECKED', post_pins_match=True, post_artifacts_match=True,
            main_result_sha256=pins[str(MAIN/'result.json')], artifact_pins_sha256=b.sha(out/'artifact-pins.json'))
    except BaseException as exc:
        report['error'] = repr(exc)
    b.save(out/'result.json', report)
    status.update(state=report['state'], child_pid=None); base.save(out/'status.json', status)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'QBS_FMA_PAIR_CHECKED')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False); sub = parser.add_subparsers(dest='action', required=True)
    for name in ('prepare', 'service-command', 'execute'):
        p = sub.add_parser(name, allow_abbrev=False); p.add_argument('--output', type=Path, required=True)
        if name != 'prepare': p.add_argument('--review-sha256', required=True)
    a = parser.parse_args(); out = output(a.output)
    if a.action == 'prepare': print(json.dumps(prepare(out)), flush=True)
    elif a.action == 'service-command': print(json.dumps(service(out, a.review_sha256)))
    else: return execute(out, a.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    raise SystemExit(main())
