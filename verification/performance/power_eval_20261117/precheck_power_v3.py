#!/usr/bin/env python3
"""One-shot relative-power precheck; preserve strict results and wait for VCS slots."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
SUCCESS = 'POWER_ELIGIBLE'
SLOT_LOCK = OUT / '.power-vcs-slots-20261117.lock'


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(ok, message):
    if not ok:
        raise ValueError(message)


def live_simulators(proc=Path('/proc')):
    live = []
    for directory in proc.iterdir():
        if not directory.name.isdigit():
            continue
        try:
            if (directory / 'comm').read_text().strip() != 'simv':
                continue
            status = (directory / 'stat').read_text().rsplit(') ', 1)[1].split()[0]
            if status != 'Z':
                live.append(int(directory.name))
        except FileNotFoundError:
            continue
    return sorted(live)


def prepare(output, image, manifest):
    v2, base = load('precheck_v2'), load('precheck')
    data = json.loads(manifest.read_text())
    require(len(data['cases']) == 1, 'One independent image/case per frozen worker')
    case = data['cases'][0]
    require(case.get('checker_success_state') == SUCCESS and 'eligibility' in case['checker'] and
            '--commit' in case['checker'], 'Explicit power eligibility checker required')
    # Reuse v2 preparation, not its PASS-only executor. Its frozen files remain unchanged.
    v2.prepare(output, image, manifest, 1)
    for name in ('precheck_power_v3.py', 'precheck_v2.py', 'test_precheck_power_v3.py'):
        (output / 'inputs' / name).write_bytes((HERE / name).read_bytes())
    with (output / 'host-tests.log').open('x') as log:
        subprocess.run([sys.executable, '-B', str(output / 'inputs/test_precheck_power_v3.py'), '-v'],
            stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    plan = json.loads((output / 'plan.json').read_text())
    plan.update(success_state=SUCCESS, max_global_simv=4, slot_wait_seconds=21600,
                slot_lock=str(SLOT_LOCK), strict_failure_reclassified=False,
                scope='Relative-power eligibility ONLY; never strict numerical PASS or measured power')
    build = json.loads((image / 'build.json').read_text())
    require(build['state'] in v2.ALLOWED, 'Admitted RTL image required')
    base.save(output / 'plan.json', plan)
    pins = json.loads((output / 'source-pins.json').read_text())
    pins.update(build['image_pins'])
    pins.update({str(image / name): base.sha(image / name) for name in ('build.json', 'plan.json')})
    # Firmware receipts are part of this worker's identity, not just ELF/payload pins.
    build_index = case['checker'].index('--build') + 1
    firmware = Path(case['checker'][build_index]) / 'build.json'
    pins[str(firmware)] = base.sha(firmware)
    pins[str(output / 'host-tests.log')] = base.sha(output / 'host-tests.log')
    for p in (output / 'inputs').rglob('*'):
        if p.is_file():
            pins[str(p)] = base.sha(p)
    pins[str(output / 'plan.json')] = base.sha(output / 'plan.json')
    base.save(output / 'source-pins.json', pins)
    base.verify(pins)
    base.save(output / 'status.json', dict(state='PREPARED_POWER_ELIGIBILITY', total=1, completed=0))


def check_eligibility(case, numeric, strict):
    require(case.get('checker_success_state') == SUCCESS and numeric.get('state') == SUCCESS,
            'Scoped eligibility state required, not PASS')
    require(strict.get('state') in ('PASS', 'FAIL') and
            numeric.get('strict_numerical_state') == strict['state'], 'Strict result disagreement')
    for field in ('relative_power_eligible', 'execution_path_checked', 'exhaustive_target_comparisons',
                  'strict_failure_preserved'):
        require(numeric.get(field) is True, 'Missing eligibility proof: ' + field)
    require(numeric.get('hash_only_validation') is False and numeric.get('power_acceptance') is False and
            numeric.get('original_numerical_result_reclassified') is False, 'Eligibility scope drift')


def check_protocol(proof, case, simv_hash, log_hash, vector_hash):
    require(proof.get('status') == 'PASS' and proof.get('issues') == [], 'Independent protocol gate')
    counts = proof.get('contract_counts', {})
    require(all(counts.get(k) == 0 for k in ('exceptions', 'protocol_errors', 'outstanding')),
            'Protocol exception/outstanding work')
    for key, expected in (('elf_sha256', case['elf_sha256']), ('simv_sha256', simv_hash),
                          ('log_sha256', log_hash), ('vector_trace_sha256', vector_hash)):
        require(proof.get(key) == expected, 'Protocol identity: ' + key)


def strict_command(case, substitutions):
    argv = [s.format(**substitutions) for s in case['checker']]
    index = argv.index('eligibility')
    argv[index] = 'check'
    commit = argv.index('--commit')
    del argv[commit:commit+2]
    argv[argv.index('--output')+1] = substitutions['strict']
    return argv


def launch_when_available(argv, work, env, plan, pins, base):
    deadline = time.monotonic() + plan['slot_wait_seconds']
    with (work / 'VCS.log').open('x') as log:
        while True:
            with Path(plan['slot_lock']).open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                live = live_simulators()
                if len(live) < plan['max_global_simv']:
                    base.verify(pins)
                    proc = subprocess.Popen(list(map(str, argv)), cwd=work, env=env,
                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    base.save(work / 'dispatch.json', dict(pid=proc.pid, existing_simv=live,
                        max_global_simv=4, command=list(map(str, argv)), started=time.time()))
                    base.save(work.parent.parent / 'status.json', dict(state='VCS_RUNNING',
                        pid=os.getpid(), simulator_pid=proc.pid, case=work.name))
                    return proc
            base.save(work.parent.parent / 'status.json', dict(state='WAITING_FOR_VCS_SLOT',
                pid=os.getpid(), live_simv=live, cap=4, deadline_seconds=plan['slot_wait_seconds']))
            require(time.monotonic() < deadline, 'Bounded simulator-slot wait expired')
            time.sleep(15)


def execute(output):
    base, v2 = load('precheck'), load('precheck_v2')
    require(Path(__file__).resolve() == output / 'inputs/precheck_power_v3.py' and
            not (output / 'attempt.json').exists(), 'Frozen one-shot successor required')
    base.save(output / 'attempt.json', dict(pid=os.getpid(), started=time.time()))
    plan = json.loads((output / 'plan.json').read_text())
    pins = json.loads((output / 'source-pins.json').read_text())
    case = plan['cases'][0]
    work = output / 'runs' / case['id']
    work.mkdir()
    result = dict(state='FAIL', id=case['id'], scope=plan['scope'], strict_failure_reclassified=False,
                  power_measured=False, original_worker_reclassified=False)
    started = time.monotonic()
    try:
        base.verify(pins)
        require(plan['success_state'] == SUCCESS and plan['max_global_simv'] == 4, 'Dispatch policy drift')
        image = Path(plan['image'])
        build = json.loads((image / 'build.json').read_text())
        require(build['state'] in v2.ALLOWED, 'Admitted RTL image required')
        result.update(image=str(image), image_state=build['state'], elf_sha256=case['elf_sha256'])
        base.verify(build['image_pins'])
        base.verify(json.loads((image / 'source-pins.json').read_text()))
        simv = image / 'sim/simv'
        env = dict(json.loads((image / 'plan.json').read_text())['environment'],
            PYTHONPATH=plan['protocol_pythonpath'], PYTHONDONTWRITEBYTECODE='1')
        argv = [simv, '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD='+case['elf'],
            '+TESTCASE='+case['id'], '+NO_FSDB', '+NO_INSTR_TRACE',
            '+VECTOR_TRACE='+str(work / 'vector.csv'), '+COMMIT_TRACE='+str(work / 'commit.csv'),
            '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000', *case.get('plusargs', [])]
        proc = launch_when_available(argv, work, env, plan, pins, base)
        try:
            require(proc.wait(timeout=case['timeout_seconds']) == 0, 'VCS process exit')
        except BaseException:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            raise
        subst = dict(run=str(work), log=str(work / 'run.vcs.log'), result=str(work / 'eligibility.json'),
                     strict=str(work / 'strict-numerical.json'))
        # Preserve the actual strict checker outcome before the independent scoped decision.
        with (work / 'STRICT.log').open('x') as log:
            strict_proc = subprocess.run(strict_command(case, subst), cwd=work, env=env,
                stdout=log, stderr=subprocess.STDOUT, timeout=600)
        strict = json.loads((work / 'strict-numerical.json').read_text())
        require(strict_proc.returncode == (0 if strict['state'] == 'PASS' else 1), 'Strict checker execution error')
        base.run_command([s.format(**subst) for s in case['checker']], work, 'ELIGIBILITY', env, 600)
        numeric = json.loads((work / 'eligibility.json').read_text())
        check_eligibility(case, numeric, strict)
        require(numeric.get('log_sha256') == base.sha(work / 'run.vcs.log') and
                numeric.get('commit_sha256') == base.sha(work / 'commit.csv') and
                numeric.get('build_sha256') == base.sha(Path(case['checker'][case['checker'].index('--build')+1]) / 'build.json'),
                'Eligibility evidence identity mismatch')
        # No fabricated SUCCESS text and no changes to the archived protocol checker.
        base.run_command([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
            '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace', work / 'vector.csv',
            '--log', work / 'run.vcs.log', '--simv', simv, '--elf', case['elf'],
            '--output', work / 'protocol.json'], work, 'PROTOCOL', env, 1200)
        proof = json.loads((work / 'protocol.json').read_text())
        check_protocol(proof, case, build['image_pins'][str(simv)],
                       base.sha(work / 'run.vcs.log'), base.sha(work / 'vector.csv'))
        base.verify(pins)
        base.verify(build['image_pins'])
        base.verify(json.loads((image / 'source-pins.json').read_text()))
        result.update(state=SUCCESS, strict_numerical_state=strict['state'],
            strict_result=str(work / 'strict-numerical.json'), eligibility=str(work / 'eligibility.json'),
            independent_protocol_checked=True, protocol=str(work / 'protocol.json'))
    except Exception as exc:
        result.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
    result['wall_seconds'] = time.monotonic()-started
    for destination in (work, output):
        base.save(destination / 'result.json', result)
        base.save(destination / 'status.json', dict(state=result['state'], completed=1, total=1))
    return int(result['state'] != SUCCESS)


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'execute', 'status'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image', type=Path)
    p.add_argument('--manifest', type=Path)
    a = p.parse_args()
    output = a.output.resolve()
    if a.action == 'prepare':
        prepare(output, a.image.resolve(), a.manifest.resolve())
        return 0
    if a.action == 'status':
        print((output / 'status.json').read_text())
        return 0
    return execute(output)


if __name__ == '__main__':
    raise SystemExit(main())
