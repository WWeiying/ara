#!/usr/bin/env python3
"""Fixed original47 replay; no build, jobs2, strict terminal postacceptance."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import prepare47 as source

HERE = source.HERE
PREPARED = HERE / 'prepared01'
OUT = HERE / 'vcs_candidate03_01'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate03/campaign/image')
IMAGE_SHA = 'e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6'
PROGRAMS_SHA = '9f36fdf5b60ad89ac9a3aede4975d7a3d39ba55d86a5db3af5e40730f5b78fcb'
UNIT = 'ara-fp-moves-original47-candidate03.service'
RUNNER = source.BASE / 'run.py'
sha, save, require = source.prepare.sha, source.prepare.save, source.require
FAIL = re.compile(
    r'RVV_FP_MOVE_[A-Z_]*FAIL|BOARD_CASE_FAIL|BOARD_REPLAY_[A-Z_]*(?:FAIL|TRAP|MISMATCH)|'
    r'Core Test \*\*\* FAILED \*\*\*|\bUVM_FATAL\b(?![ \t]*:[ \t]*0\b)|'
    r'\$fatal\b|\bFatal\s*:|(?:Error|Fatal)[^\n]*(?:assertion|assert)[^\n]*fail|'
    r'^\s*(?:Index\s+\d+\s+)?(?:FAIL(?:ED|URE)?|FATAL)\b', re.I | re.M)


def read(path):
    return json.loads(Path(path).read_text())


def pins_check(pins):
    for path, digest in pins.items():
        require(sha(Path(path)) == digest, 'Input drift: ' + path)


def console_check(text, name, sew):
    require(not FAIL.search(text), name + ': failure-marker veto')
    lines = text.splitlines()
    for prefix, wanted in (
        ('RVV_REDUCED_BEGIN', 'RVV_REDUCED_BEGIN cases=1'),
        ('RVV_FP_MOVE_PASS', f'RVV_FP_MOVE_PASS sew={sew} cases=1 errors=0'),
        ('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN ' + name),
        ('BOARD_CASE_PASS', 'BOARD_CASE_PASS ' + name),
        ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS'),
        ('Core Test *** SUCCESS ***', 'Core Test *** SUCCESS *** (tohost = 0)'),
    ):
        require([line for line in lines if line.startswith(prefix)] == [wanted], name + ': missing/ambiguous ' + prefix)


def postaccept(plan, rc):
    pins_check(plan['pins'])
    run = read(OUT / 'replay/run.json')
    summary = read(OUT / 'replay/summary.json')
    programs = read(PREPARED / 'soc/programs.json')['programs']
    names = plan['names']
    require(rc == 0 and run['status'] == 'COMPLETE' and run.get('completed_at'), 'Runner not successful/COMPLETE')
    require(run['tests'] == names and run['status_counts'] == {'PASS': 47}, 'Runner membership/count differs')
    require(len(summary) == 47 and [r['name'] for r in summary] == names, 'Summary membership differs')
    image = read(IMAGE / 'image.json')
    require(run['simv'] == image['simv'], 'Wrong runner image')
    results = []
    for result in summary:
        name = result['name']
        artifact = OUT / 'replay/tests' / name
        entry = programs[name]
        require(result['status'] == 'PASS' and result['returncode'] == 0 and not result['reason'], name + ': runner failed')
        require(result['artifact_dir'] == str(artifact), name + ': wrong result directory')
        inputs = read(artifact / 'inputs.json')
        private = artifact / 'input.elf'
        require(sha(private) == entry['sha256'], name + ': private ELF drift')
        require(inputs['binary'] == dict(source=entry['path'], path=str(private), sha256=entry['sha256']), name + ': ELF provenance mismatch')
        require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), name + ': image provenance mismatch')
        command = read(artifact / 'command.json')
        require(command['command'][0] == image['simv'] and command['cwd'] == str(artifact / 'work'), name + ': command image/cwd mismatch')
        for prefix, value in (('+PRELOAD=', str(private)), ('+TESTCASE=', name)):
            require([s for s in command['command'] if s.startswith(prefix)] == [prefix + value], name + ': command identity mismatch')
        sew = int(re.search(r'_e(16|32|64)_', name)[1])
        console_check((artifact / 'console.log').read_text(), name, sew)
        results.append(dict(name=name, status='PASS', returncode=0, elapsed_s=result['elapsed_s'],
                            elf_sha256=entry['sha256'], console_sha256=sha(artifact / 'console.log')))
    pins_check(plan['pins'])
    return results


def work(plan_hash):
    require(sha(OUT / 'plan.json') == plan_hash, 'Plan mismatch')
    plan = read(OUT / 'plan.json')
    pins_check(plan['pins'])
    command = [sys.executable, '-B', str(RUNNER), 'run', '--image', str(IMAGE),
               '--programs', str(PREPARED / 'soc'), '--out', str(OUT / 'replay'),
               '--jobs', '2', '--timeout', '180', '--execute']
    for name in plan['names']:
        command += ['--case', name]
    save(OUT / 'runner_command.json', command)
    save(OUT / 'worker.json', dict(pid=os.getpid(), started=time.time(), plan_sha256=plan_hash))
    with (OUT / 'runner.log').open('x') as log:
        rc = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT, cwd=source.prepare.ROOT)
    try:
        results = postaccept(plan, rc)
        final = dict(status='PASS_47_ORIGINAL_SINGLES_CANDIDATE03', results=results,
                     runner_returncode=rc, failure_marker_veto=True, pins_unchanged=True,
                     full_parent_matrices=False, finished=time.time(), plan_sha256=plan_hash)
        code = 0
    except Exception as error:
        final = dict(status='NOT_ACCEPTED', reason=str(error), runner_returncode=rc,
                     finished=time.time(), plan_sha256=plan_hash, retries=0)
        code = 1
    save(OUT / 'complete.json', final)
    return code


def launch():
    require(not OUT.exists(), 'Output collision; no retry')
    unit = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'LoadState'], text=True)
    require('LoadState=not-found' in unit, 'Service collision')
    require(read(PREPARED / 'status.json')['status'] == 'HOST_SPIKE_47_PASS_READY_NOT_DUT', 'Reference not ready')
    require(sha(PREPARED / 'soc/programs.json') == PROGRAMS_SHA, 'Reviewed programs changed')
    require(sha(IMAGE / 'image.json') == IMAGE_SHA, 'Wrong candidate03 image')
    image = read(IMAGE / 'image.json')
    snapshot_path = Path(image['snapshot']) / 'snapshot.json'
    require(sha(snapshot_path) == image['snapshot_sha256'], 'Wrong snapshot')
    snapshot = read(snapshot_path)
    programs = read(PREPARED / 'soc/programs.json')['programs']
    original = read(PREPARED / 'original_provenance.json')
    require(list(programs) == [r['name'] for r in original['records']] and len(programs) == 47, 'Wrong47 membership')
    reference = read(PREPARED / 'reference.json')
    require(reference['status'] == 'SPIKE_47_PASS_NOT_DUT' and len(reference['results']) == 47 and
            all(r['status'] == 'PASS' for r in reference['results']), 'Missing reference completion')
    pins = dict(original['pins'])
    pins.update(image['files'])
    pins.update({str(Path(snapshot['root']) / name): digest for name, digest in snapshot['files'].items()})
    prepared = PREPARED / 'prepared'
    pins.update({str(prepared / name): digest for name, digest in read(prepared / 'provenance.json')['files'].items()})
    pins.update({entry['path']: entry['sha256'] for entry in programs.values()})
    for path in (Path(__file__), HERE / 'test_candidate03.py', HERE / 'postaccept_host.json', IMAGE / 'image.json', snapshot_path,
                 RUNNER, PREPARED / 'soc/programs.json', PREPARED / 'reference.json', PREPARED / 'host.json',
                 PREPARED / 'status.json', PREPARED / 'address_map.json', PREPARED / 'original_provenance.json', prepared / 'provenance.json'):
        pins[str(path)] = sha(path)
    require(read(HERE / 'postaccept_host.json')['returncode'] == 0, 'Host checker validation failed')
    pins_check(pins)

    # Single launch gate, counting already-live reserved groups only once.
    live = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = [s.decode(errors='replace') for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
            if args and Path(args[0]).name == 'simv':
                live.append(dict(pid=int(proc.name), argv=args))
        except (OSError, ProcessLookupError):
            continue
    reservations = {}
    for label, token, slots in (('tesla_controls', '/fp_moves/', 2), ('nf7', '/indexed_review/', 2), ('alias', '/mask_alias_original/', 1)):
        observed = sum(any(token in arg for arg in r['argv']) for r in live)
        reservations[label] = dict(slots=slots, observed_live=observed, unoccupied=max(0, slots-observed))
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0]) * 1024
    total = len(live) + sum(r['unoccupied'] for r in reservations.values()) + 2
    gate = dict(observed_at=time.time(), live=live, live_count=len(live), reservations=reservations,
                own_slots=2, total_live_reserved=total, cap=24, available_bytes=available,
                min_available_bytes=32*1024**3, passed=total <= 24 and available >= 32*1024**3)
    OUT.mkdir()
    save(OUT / 'resource_gate.json', gate)
    plan = dict(names=list(programs), image=str(IMAGE), image_sha256=IMAGE_SHA, pins=pins,
                snapshot_source_files=len(snapshot['files']), jobs=2, timeout_per_case_s=180, outer_s=5400,
                unit=UNIT, required_postacceptance=True, retries=0, resource_gate_sha256=sha(OUT / 'resource_gate.json'))
    save(OUT / 'plan.json', plan)
    if not gate['passed']:
        save(OUT / 'complete.json', dict(status='CAPACITY_BLOCKED_NO_LAUNCH', retries=0))
        print(json.dumps(gate, indent=2))
        return 2
    command = ['systemd-run', '--user', '--unit=' + UNIT, '--collect',
               '--property=RuntimeMaxSec=5400', '--property=TimeoutStopSec=120',
               '--property=KillMode=control-group', '--property=Restart=no',
               '--property=WorkingDirectory=' + str(source.prepare.ROOT),
               '--property=StandardOutput=append:' + str(OUT / 'service.log'),
               '--property=StandardError=append:' + str(OUT / 'service.log'),
               sys.executable, '-B', str(Path(__file__).resolve()), '--work', sha(OUT / 'plan.json')]
    save(OUT / 'service_command.json', command)
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    save(OUT / 'launch.json', dict(returncode=result.returncode, output=result.stdout, started=time.time(), plan_sha256=sha(OUT / 'plan.json')))
    print(json.dumps(dict(returncode=result.returncode, output=result.stdout, live=len(live), total_live_reserved=total,
                         available_gib=available/1024**3, reservations=reservations, out=str(OUT)), indent=2))
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--launch', action='store_true')
    modes.add_argument('--work')
    args = parser.parse_args()
    raise SystemExit(work(args.work) if args.work else launch())
