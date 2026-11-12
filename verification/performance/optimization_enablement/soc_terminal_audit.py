#!/usr/bin/env python3
"""Independent terminal-only evidence audit; never executes a simulator."""
import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
CAMPAIGN_SHA = '4f2f2bc06af8919c6c7d8421ebc8617b6f2931c6833f876528120e26fddfaf41'
CAMPAIGN_PINS = 'fe7849a1147d4e31ca5e67a4b20b316bfd74dcef55123301a6e7e74310e7977c'
FILES = ('run.vcs.log', 'vector.csv', 'commit.csv', 'numerical.json', 'protocol.json',
         'console.log', 'protocol.log', 'console.command.json', 'protocol.command.json')
RUNS = [('candidate', n) for n in ('rv64uv-ara-vmul', 'rv64uv-ara-vfmacc',
        'rv64uv-ara-vfwmacc', 'qbs_m4', 'qbs_m8', 'resident_sdk')] + [('baseline', 'resident_sdk')]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    def unique(rows):
        value = {}
        for k, v in rows:
            require(k not in value, 'Duplicate JSON key: ' + k)
            value[k] = v
        return value
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def equal(a, b, message):
    require(json.dumps(a, sort_keys=True, allow_nan=False) ==
            json.dumps(b, sort_keys=True, allow_nan=False), message)


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def verify(pins):
    require(bool(pins), 'Empty evidence inventory')
    for path, digest in pins.items():
        require(sha(path) == digest, 'Evidence drift: ' + str(path))


def merge(pins, extra):
    for path, digest in extra.items():
        require(path not in pins or pins[path] == digest, 'Conflicting identity: ' + path)
        pins[path] = digest


def snapshot(directory, names):
    return {str(directory/n): sha(directory/n) for n in names}


def load(path, digest, name):
    require(sha(path) == digest, 'Unreviewed audit dependency: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_worker(directory, unit, seconds):
    """A pidfd exit event is stronger than observing an opened result.json."""
    owner = read(directory/'owner.json')
    require(owner['unit'] == unit and owner['owner_pid'] == owner['main_pid'], 'Original worker ownership mismatch')
    pid = int(subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit,
              '--property=MainPID', '--value'], text=True, timeout=10).strip())
    if pid:
        require(pid == owner['main_pid'], 'Worker identity changed')
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            return
        try:
            poll = select.poll()
            poll.register(fd, select.POLLIN)
            require(poll.poll(int(seconds * 1000)), 'Worker exit event deadline')
        finally:
            os.close(fd)


def terminal(report, review):
    require(report.get('state') == 'SOC_COMBINATION_CHECKED' and 'error' not in report and
            report.get('post_pins_match') is True and report.get('source_pins_sha256') == review,
            'Original worker lacks a complete successful terminal')
    require(report.get('automatic_retry') is False and report.get('whole_model') is False and
            report.get('performance_acceptance') is False, 'Original scope drift')
    rows = report.get('completed', [])
    require([(r.get('arm'), r.get('case')) for r in rows] == RUNS and
            all(r.get('state') == 'PASS' for r in rows), 'Missing/extra/reordered completed cases')
    return rows


def check_commands(work, plan, program, hw, name, qbs_pair=False):
    simulation = [hw['simv'], '-no_save', '-l', str(work/'run.vcs.log'), '+PRELOAD='+program['elf'],
        '+TESTCASE=enablement_soc_'+name, '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
        '+AKV_PERF', '+AKV_SUMMARY', '+RESIDENT_QK_PERF', '+RESIDENT_PV_PERF', '+RESIDENT_PV_WATCHDOG',
        '+COMMIT_TRACE='+str(work/'commit.csv'), '+VECTOR_TRACE='+str(work/'vector.csv'),
        '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
    if qbs_pair:
        simulation = [hw['simv'], '-no_save', '-l', str(work/'run.vcs.log'),
            '+PRELOAD='+program['elf'], '+TESTCASE=enablement_soc_qbs_pair_'+name,
            '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
            '+COMMIT_TRACE='+str(work/'commit.csv'), '+VECTOR_TRACE='+str(work/'vector.csv'),
            '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
    protocol = [plan['python'], '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
        '--require-axi', '--require-axi-write', '--vector-trace', str(work/'vector.csv'),
        '--log', str(work/'run.vcs.log'), '--simv', hw['simv'], '--elf', program['elf'],
        '--output', str(work/'protocol.json')]
    for file, argv, limit in (('console.command.json', simulation, plan['simulation_seconds']),
                              ('protocol.command.json', protocol, plan['protocol_seconds'])):
        equal(read(work/file), dict(argv=argv, cwd=str(work), timeout_seconds=limit), 'Executed command contract differs')


def protocol_check(module, work, program, hw):
    original = read(work/'protocol.json')
    replay = module.check_real_uvm_log(work/'run.vcs.log', require_events=True,
        require_backend=True, require_axi=True, require_axi_write=True, vector_trace=work/'vector.csv')
    replay.update(elf_sha256=sha(program['elf']), simv_sha256=sha(hw['simv']),
                  sim_image_sha256=module.simulation_image(Path(hw['simv'])))
    require(replay.get('status') == 'PASS' and replay.get('issues') == [], 'Independent protocol replay failed')
    require(replay['elf_sha256'] == program['elf_sha256'], 'Program identity drift')
    require(all(replay['contract_counts'][k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding')),
            'Protocol retirement incomplete')
    equal(original, replay, 'Stored protocol differs from independent terminal replay')
    return replay


def case_check(c, protocol, campaign, work, row, plan, hw, qbs_pair=False):
    name = row['case']
    program = plan['programs'][name]
    before = snapshot(work, FILES)
    require(before[str(work/'run.vcs.log')] == row['log_sha256'], 'Original completed log hash differs')
    check_commands(work, plan, program, hw, name, qbs_pair)
    proof = c.check_case(campaign, work, name, program, hw['configuration']['shared_fma'])
    equal(read(work/'numerical.json'), proof, 'Stored numerical/entry proof differs from terminal replay')
    if name == 'resident_sdk':
        equal(proof['actual_entries'], dict(akv_decode_execute=6,
              akv_experimental_attention_execute_v2_native=4), 'Native entry count differs')
    checked = protocol_check(protocol, work, program, hw)
    verify(before)
    return proof, dict(arm=row['arm'], case=name, state='TERMINAL_REPLAY_CHECKED',
        artifacts=before, native_entries=proof.get('actual_entries'),
        protocol_counts=checked['contract_counts'],
        historical_hash_scope='Original completed log plus protocol log/vector/image/ELF hashes; '
                              'other files independently snapshotted and semantically rechecked now')


def pair_terminal(report, review, campaign_result_sha, artifacts_sha):
    require(report.get('schema') == 'enablement-soc-qbs-pair-v1' and
            report.get('state') == 'QBS_FMA_PAIR_CHECKED' and 'error' not in report and
            report.get('source_pins_sha256') == review and
            report.get('post_pins_match') is True and report.get('post_artifacts_match') is True and
            report.get('main_result_sha256') == campaign_result_sha and
            report.get('artifact_pins_sha256') == artifacts_sha,
            'Extra QBS pair lacks a complete bound successful terminal')
    require(report.get('automatic_retry') is False and report.get('performance_acceptance') is False and
            report.get('whole_model') is False, 'Extra QBS pair scope differs')
    require([(r.get('arm'), r.get('case'), r.get('state')) for r in report.get('completed', [])] ==
            [('baseline', 'qbs_m4', 'PASS'), ('baseline', 'qbs_m8', 'PASS')],
            'Missing/extra/reordered QBS baseline cases')


def audit_pair(pair, review, source_sha, campaign, c, protocol, main_plan, builds, proofs, evidence):
    result = read(pair/'result.json')
    pair_terminal(result, review, sha(campaign/'result.json'), sha(pair/'artifact-pins.json'))
    initial = snapshot(pair, ('result.json', 'source-pins.json', 'prepared.json', 'plan.json',
                               'artifact-pins.json', 'owner.json', 'attempt.json'))
    require(sha(pair/'source-pins.json') == review, 'Extra QBS pins review differs')
    pins = read(pair/'source-pins.json'); verify(pins)
    require(pins.get(str(pair/'inputs/soc_qbs_pair.py')) == source_sha, 'Unreviewed QBS pair source')
    p = load(pair/'inputs/soc_qbs_pair.py', source_sha, 'frozen_terminal_qbs_pair')
    _, _, b, plan, inherited = p.verified(pair, review)
    merge(pins, inherited)
    require(plan['main'] == str(campaign) and plan['main_review'] == CAMPAIGN_PINS,
            'Extra QBS pair refers to a different main campaign')
    for arm in ('candidate', 'baseline'):
        require(plan[arm] == main_plan[arm], 'Extra QBS pair uses another build')
    owner = read(pair/'owner.json')
    b.direct_owner(owner['cgroup'], p.unit(pair), owner['main_pid'], owner['owner_pid'])
    equal(read(pair/'attempt.json'), dict(review_sha256=review, **owner), 'Extra pair ownership differs')
    artifacts = read(pair/'artifact-pins.json'); verify(artifacts)
    cases, comparison = [], []
    for name in ('qbs_m4', 'qbs_m8'):
        equal(plan['programs'][name], main_plan['programs'][name], 'Extra pair changed firmware/data')
        work = pair/('baseline_'+name)
        required = snapshot(work, (*FILES, 'comparison.json'))
        require(all(artifacts.get(path) == digest for path, digest in required.items()),
                'Extra QBS output missing from historical artifact pins')
        row = dict(arm='baseline', case=name, state='PASS',
                   log_sha256=artifacts[str(work/'run.vcs.log')])
        baseline, record = case_check(c, protocol, campaign, work, row, plan, builds['baseline'], True)
        candidate = proofs[('candidate', name)]
        original = campaign/('candidate_'+name)
        require(all(artifacts.get(str(original/n)) == sha(original/n) for n in FILES),
                'Pair candidate historical output hashes differ')
        recheck = pair/('candidate_recheck_'+name)
        equal(read(recheck/'numerical.json'), candidate, 'Pair candidate numerical replay differs')
        equal(read(recheck/'protocol.json'), read(original/'protocol.json'), 'Pair candidate protocol replay differs')
        rows = p.compare_trials(name, baseline, candidate)
        equal(read(work/'comparison.json'), dict(rows=rows,
            elf_sha256=plan['programs'][name]['elf_sha256'], only_fma_macro_differs=True),
            'Stored QBS comparison differs from per-mode equal-work recomputation')
        comparison.extend(rows)
        cases.append(record)
    equal(result['comparisons'], comparison, 'QBS pair terminal comparison differs')
    merge(evidence, initial); merge(evidence, pins); merge(evidence, artifacts)
    verify(evidence)
    return cases, comparison


def audit(campaign, review, pair, pair_review, pair_source):
    require(review == CAMPAIGN_PINS and sha(campaign/'source-pins.json') == review, 'Campaign pins review drift')
    result = read(campaign/'result.json')
    rows = terminal(result, review)
    evidence = snapshot(campaign, ('result.json', 'build-binding.json', 'full-call-comparison.json',
                                   'owner.json', 'attempt.json', 'prepared.json', 'source-pins.json'))
    pins = read(campaign/'source-pins.json')
    require(pins.get(str(campaign/'inputs/soc_campaign.py')) == CAMPAIGN_SHA, 'Campaign source identity differs')
    verify(pins)
    c = load(campaign/'inputs/soc_campaign.py', CAMPAIGN_SHA, 'frozen_terminal_campaign')
    s, b, plan, inherited = c.verify_prepared(campaign, review)
    merge(pins, inherited)
    builds = {}
    binding = {}
    for arm in ('candidate', 'baseline'):
        path = Path(plan[arm])
        builds[arm], extra = c.checked_build(s, path)
        merge(pins, extra)
        binding[arm] = dict(path=str(path), sha256=sha(path/'build.json'))
    c.same_sources(b, Path(plan['candidate']), Path(plan['baseline']))
    equal(read(campaign/'build-binding.json'), binding, 'Build binding differs')
    require(result['build_binding_sha256'] == sha(campaign/'build-binding.json'), 'Result build binding hash differs')
    owner = read(campaign/'owner.json')
    b.direct_owner(owner['cgroup'], c.unit(campaign), owner['main_pid'], owner['owner_pid'])
    equal(read(campaign/'attempt.json'), dict(review_sha256=review, **owner), 'Original attempt ownership differs')
    for name, program in plan['programs'].items():
        require(sha(program['elf']) == program['elf_sha256'], 'Wrong ELF: ' + name)
    sys.path.insert(0, str(campaign/'inputs/verification'))
    protocol = importlib.import_module('ara_verify.uvm_dut')
    require(Path(protocol.__file__).resolve().is_relative_to(campaign/'inputs/verification'), 'Wrong protocol import')
    proofs, cases = {}, []
    for row in rows:
        work = campaign/(row['arm']+'_'+row['case'])
        proof, record = case_check(c, protocol, campaign, work, row, plan, builds[row['arm']])
        proofs[(row['arm'], row['case'])] = proof
        cases.append(record)
        merge(evidence, record['artifacts'])
    comparison = c.compare_cycles(
        proofs[('baseline', 'resident_sdk')]['numerical']['full_call_cycles_diagnostic_only'],
        proofs[('candidate', 'resident_sdk')]['numerical']['full_call_cycles_diagnostic_only'])
    equal(result['full_call_comparison'], comparison, 'Original result comparison differs')
    equal(read(campaign/'full-call-comparison.json'), dict(rows=comparison, same_elf=True,
        only_fma_macro_differs=True, model_speedup_claim=False, all_shapes_no_regression_claim=False),
        'Stored comparison differs from equal-work recomputation')
    extra_cases, qbs_comparison = audit_pair(pair, pair_review, pair_source, campaign, c,
        protocol, plan, builds, proofs, evidence)
    cases.extend(extra_cases)
    merge(evidence, pins)
    verify(evidence)
    return dict(state='INDEPENDENT_SOC_TERMINAL_AUDIT_PASS', original_worker_state=result['state'],
        original_reports_modified=False, simulator_executed=False, cases=cases,
        resident_comparison=comparison, qbs_comparison=qbs_comparison, evidence=evidence, pins=len(pins),
        buildwait_scope='Both original builds reached complete successful terminals; '
                        'potential wait race was not an observed failure; fix belongs to a future successor',
        input_pins_checked=True, image_pins_checked=True,
        whole_model=False, physical_or_fpga_acceptance=False)


def prepare(campaign, out, pair, pair_review, pair_source):
    require(out.parent == OUT and out.name.startswith('enablement_soc_terminal_audit_') and not out.exists(),
            'Fresh independent audit output required')
    require(sha(campaign/'source-pins.json') == CAMPAIGN_PINS, 'Wrong campaign snapshot')
    require(sha(campaign/'inputs/soc_campaign.py') == CAMPAIGN_SHA, 'Wrong campaign worker')
    require(sha(pair/'source-pins.json') == pair_review and
            sha(pair/'inputs/soc_qbs_pair.py') == pair_source, 'Wrong extra QBS pair identity')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    pins = snapshot(campaign, ('source-pins.json', 'inputs/soc_campaign.py', 'owner.json'))
    merge(pins, snapshot(pair, ('source-pins.json', 'inputs/soc_qbs_pair.py', 'owner.json')))
    import shutil
    for name in ('soc_terminal_audit.py', 'soc_terminal_audit_test.py'):
        source, dest = HERE/name, inputs/name
        shutil.copyfile(source, dest)
        pins[str(source)] = pins[str(dest)] = sha(source)
    save(out/'config.json', dict(campaign=str(campaign), campaign_pins_sha256=CAMPAIGN_PINS,
        original_unit=read(campaign/'owner.json')['unit'], pair=str(pair), pair_review=pair_review,
        pair_source_sha256=pair_source, pair_unit=read(pair/'owner.json')['unit'], wait_seconds=80000))
    pins[str(out/'config.json')] = sha(out/'config.json')
    verify(pins); save(out/'source-pins.json', pins)
    return dict(state='AUDIT_PREPARED_WAITING_FOR_TERMINAL', review_sha256=sha(out/'source-pins.json'))


def service(out, review):
    require(sha(out/'source-pins.json') == review, 'Audit review drift')
    verify(read(out/'source-pins.json'))
    return ['/usr/bin/systemd-run', '--user', '--unit=enablement-terminal-'+out.name+'.service',
        '--property=Type=exec', '--property=MemoryMax=8G', '--property=CPUQuota=100%',
        '--property=RuntimeMaxSec=92000', '--property=KillMode=control-group',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        '/usr/bin/python3.11', '-B', str(out/'inputs/soc_terminal_audit.py'), 'execute',
        '--output', str(out), '--review-sha256', review]


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/soc_terminal_audit.py', 'Frozen audit worker required')
    require(sha(out/'source-pins.json') == review, 'Audit input review differs')
    pins = read(out/'source-pins.json'); verify(pins)
    unit = 'enablement-terminal-'+out.name+'.service'
    pid = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit,
                                  '--property=MainPID', '--value'], text=True, timeout=10).strip()
    require(pid == str(os.getpid()) and '/'+unit in Path('/proc/self/cgroup').read_text(), 'Direct auditor service required')
    require(not (out/'result.json').exists(), 'One audit attempt only')
    config = read(out/'config.json'); campaign = Path(config['campaign'])
    report = dict(state='INDEPENDENT_SOC_TERMINAL_AUDIT_FAIL', original_reports_modified=False,
                  simulator_executed=False)
    started = time.monotonic()
    try:
        print('WAIT_WORKER_EXIT_EVENT', flush=True)
        deadline = time.monotonic() + config['wait_seconds']
        wait_worker(campaign, config['original_unit'], max(0, deadline-time.monotonic()))
        wait_worker(Path(config['pair']), config['pair_unit'], max(0, deadline-time.monotonic()))
        print('TERMINAL_AUDIT_BEGIN', flush=True)
        verify(pins)
        report = audit(campaign, config['campaign_pins_sha256'], Path(config['pair']),
                       config['pair_review'], config['pair_source_sha256'])
        verify(pins)
    except BaseException as exc:
        report['error'] = repr(exc)
    report['elapsed_seconds_including_event_wait'] = time.monotonic()-started
    report['auditor_source_sha256'] = sha(Path(__file__))
    report['audit_source_pins_sha256'] = review
    report['campaign'] = str(campaign)
    report['qbs_pair'] = config['pair']
    save(out/'result.json', report)
    print(report['state'], flush=True)
    return int(report['state'] != 'INDEPENDENT_SOC_TERMINAL_AUDIT_PASS')


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Audit signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'service-command', 'execute'))
    p.add_argument('--campaign', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--review-sha256')
    p.add_argument('--qbs-pair', type=Path)
    p.add_argument('--qbs-pair-review')
    p.add_argument('--qbs-pair-source-sha256')
    a = p.parse_args(); out = a.output.resolve()
    if a.action == 'prepare': print(json.dumps(prepare(a.campaign.resolve(), out,
        a.qbs_pair.resolve(), a.qbs_pair_review, a.qbs_pair_source_sha256)))
    elif a.action == 'service-command': print(json.dumps(service(out, a.review_sha256)))
    else: raise SystemExit(execute(out, a.review_sha256))
