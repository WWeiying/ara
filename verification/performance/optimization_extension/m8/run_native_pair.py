#!/usr/bin/env python3
"""One reviewed SDK-pair simulation, owned directly by a systemd worker."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
SOFTWARE = OUT/'optimization_extension_m8_sdkpair_20261111_01'
CAPABILITY = OUT/'optimization_extension_capability_20261111_05'
ENV = dict(PATH='/usr/bin:/bin', HOME='/home/wangwy', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1',
           READELF='/usr/bin/readelf', SNPSLMD_LICENSE_FILE='27000@t7920')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())
def require(ok, why):
    if not ok: raise ValueError(why)


def save(path, value):
    with Path(path).open('x') as stream: json.dump(value, stream, indent=2, sort_keys=True); stream.write('\n')


def status(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    temporary.replace(path)


def verify(pins):
    for path, digest in pins.items(): require(sha(path) == digest, 'Sealed input drift: '+path)


def stamp(): return datetime.now(timezone.utc).isoformat()
def unit(out): return 'optimization-extension-m8-'+out.name+'.service'


def prepare(out):
    require(out.parent == OUT and out.name.startswith('optimization_extension_m8_native_') and not out.exists(), 'Fresh signoff output')
    require(sha(SOFTWARE/'build.json') == '173f3ad5308bee16994edda3bf12eefbe6cc90405e2e8e9751226fe46dadf2a6', 'Approved SDK pair identity')
    build, proposal = read(SOFTWARE/'build.json'), read(SOFTWARE/'plan.json')
    require(build['state'] == 'BUILT_NOT_EXECUTED' and build['post_pins_match'] and
            sha(SOFTWARE/'plan.json') == build['plan_sha256'] and
            sha(SOFTWARE/'source-pins.json') == build['source_pins_sha256'], 'Approved software seal')
    pins = read(SOFTWARE/'source-pins.json'); verify(pins)
    for path in (SOFTWARE/'build.json', SOFTWARE/'source-pins.json'): pins[str(path)] = sha(path)
    image = read(Path(proposal['image'])/'build.json')
    require(image['simv'] == proposal['simv'] and image['image_pins'][image['simv']] == proposal['simv_sha256'], 'Image binding')
    pins.update(image['image_pins']); verify(pins)
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    def copy(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, destination)
        require(sha(source) == sha(destination), 'Snapshot copy race')
        pins[str(destination)] = sha(destination)
    copy(Path(__file__).resolve(), inputs/'run.py')
    copy(SOFTWARE/'inputs/sdk_check.py', inputs/'sdk_check.py')
    copy(ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', inputs/'check-sim-l2.sh')
    protocol_pins = read(CAPABILITY/'source-pins.json')
    for source in sorted((CAPABILITY/'inputs/verification/ara_verify').rglob('*.py')):
        require(protocol_pins.get(str(source)) == sha(source), 'Audited protocol source drift: '+str(source))
        copy(source, inputs/'verification/ara_verify'/source.relative_to(CAPABILITY/'inputs/verification/ara_verify'))
    for name in ('simulator.conf', 'comp.vcs.log'):
        path = Path(proposal['simv']).parent/name
        if path.is_file(): pins[str(path)] = sha(path)
    environment = dict(ENV, PYTHONPATH=str(inputs/'verification'))
    work = out/'work'
    command = [proposal['simv'], '-no_save', '-l', str(work/'run.vcs.log'), '+PRELOAD='+build['elf'],
        '+TESTCASE=optimization_extension_m8', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
        '+VECTOR_TRACE='+str(work/'vector.csv'), '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
    plan = dict(state='PREPARED_NOT_EXECUTED', unit=unit(out), software=str(SOFTWARE), image=proposal['image'],
        python=str(Path(sys.executable).resolve()), environment=environment, command=command,
        simulation_seconds=3600, protocol_seconds=900, service_seconds=4800, automatic_retry=False,
        expected_sim_image={p: h for p, h in image['image_pins'].items() if p == proposal['simv'] or p.endswith('.so')})
    save(out/'plan.json', plan); pins[str(out/'plan.json')] = sha(out/'plan.json')
    for path in (Path(sys.executable).resolve(), Path('/usr/bin/readelf'), Path('/usr/bin/bash')): pins[str(path)] = sha(path)
    verify(pins); save(out/'source-pins.json', pins)
    review = sha(out/'source-pins.json')
    save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED', review_sha256=review))
    command = ['/usr/bin/systemd-run', '--user', '--unit='+unit(out), '--property=Type=exec',
        '--property=RuntimeMaxSec=4800', '--property=MemoryMax=8G', '--property=CPUQuota=100%',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        plan['python'], '-B', '-u', str(inputs/'run.py'), 'execute', '--output', str(out), '--review-sha256', review]
    save(out/'launch-command.json', command)
    print(json.dumps(dict(state='PREPARED_NOT_EXECUTED', review_sha256=review, command=command)), flush=True)


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/run.py' and sha(out/'source-pins.json') == review, 'Frozen reviewed worker only')
    pins, plan = read(out/'source-pins.json'), read(out/'plan.json'); verify(pins)
    require(not (out/'attempt.json').exists() and not (out/'result.json').exists(), 'Only one VCS attempt')
    owner = int(subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', plan['unit'], '-p', 'MainPID', '--value'], text=True).strip())
    require(owner == os.getpid(), 'systemd must directly own this worker')
    save(out/'attempt.json', dict(started=stamp(), owner_pid=owner, unit=plan['unit'],
        cgroup=Path('/proc/self/cgroup').read_text(), review_sha256=review))
    work = out/'work'; work.mkdir()
    state = dict(state='PREFLIGHT', child_pid=None, owner_pid=owner)
    report = dict(state='FAIL', started=stamp(), automatic_retry=False, performance_measured=False,
                  source_pins_sha256=review, whole_model=False)
    def run(label, argv, seconds, phase):
        argv = list(map(str, argv)); save(work/(label+'.command.json'), dict(argv=argv, environment=plan['environment'], cwd=str(work)))
        with (work/(label+'.log')).open('x') as log:
            child = subprocess.Popen(argv, cwd=work, env=plan['environment'], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            state.update(state=phase, child_pid=child.pid, started=stamp()); status(out/'status.json', state)
            save(work/(label+'.process.json'), dict(child_pid=child.pid, owner_pid=owner, started=stamp()))
            try: rc = child.wait(timeout=seconds)
            except BaseException:
                try: os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=10)
                except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
                except ProcessLookupError: pass
                raise
        state['child_pid'] = None; status(out/'status.json', state)
        save(work/(label+'.exit.json'), dict(returncode=rc, finished=stamp()))
        require(rc == 0, 'Failed '+label+'; no retry')
    try:
        build = read(SOFTWARE/'build.json')
        simv = Path(plan['command'][0]); elf = Path(build['elf'])
        run('image-contract', ['/usr/bin/bash', out/'inputs/check-sim-l2.sh', simv.parent, elf], 120, 'IMAGE_CONTRACT')
        verify(pins)
        run('console', plan['command'], plan['simulation_seconds'], 'RUNNING')
        spec = importlib.util.spec_from_file_location('frozen_m8_checker', out/'inputs/sdk_check.py')
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        numerical = checker.check((work/'run.vcs.log').read_text(), build, (SOFTWARE/'data/expected.bin').read_bytes())
        save(work/'numerical.json', numerical)
        run('protocol', [plan['python'], '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
            '--require-axi', '--require-axi-write', '--vector-trace', work/'vector.csv', '--log', work/'run.vcs.log',
            '--simv', simv, '--elf', elf, '--output', work/'protocol.json'], plan['protocol_seconds'], 'PROTOCOL')
        proof = read(work/'protocol.json')
        require(proof['status'] == 'PASS' and proof['issues'] == [] and proof['elf_sha256'] == sha(elf) and
            proof['simv_sha256'] == sha(simv) and proof['sim_image_sha256'] == plan['expected_sim_image'] and
            proof['log_sha256'] == sha(work/'run.vcs.log') and proof['vector_trace_sha256'] == sha(work/'vector.csv') and
            all(proof['contract_counts'][k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding')), 'Independent protocol/image failure')
        verify(pins)
        m4 = min(r['total'] for r in numerical['trials'] if r['mode'] == 4)
        m8 = min(r['total'] for r in numerical['trials'] if r['mode'] == 8)
        report.update(state='M8_NATIVE_SDK_PAIR_CHECKED', post_pins_match=True, performance_measured=True,
            numerical=numerical, protocol_sha256=sha(work/'protocol.json'), fastest_m4=m4, fastest_m8=m8,
            positive=m8 < m4, reduction_percent=100*(m4-m8)/m4, no_model_or_FPGA_acceptance=True)
    except BaseException as exc: report['error'] = repr(exc)
    report['finished'] = stamp()
    report['artifacts'] = {str(p): sha(p) for p in work.iterdir() if p.is_file()}
    save(out/'result.json', report)
    state.update(state=report['state'], child_pid=None, finished=report['finished']); status(out/'status.json', state)
    print(json.dumps(report, sort_keys=True), flush=True)
    return report['state'] != 'M8_NATIVE_SDK_PAIR_CHECKED'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    if args.action == 'prepare': prepare(args.output.resolve())
    else: raise SystemExit(execute(args.output.resolve(), args.review_sha256))
