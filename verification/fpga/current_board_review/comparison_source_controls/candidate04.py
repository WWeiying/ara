#!/usr/bin/env python3
"""Same frozen FP3 ELFs/checker on candidate04, only after baseline completes."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import replay

HERE = replay.HERE
BEFORE = HERE / 'vcs_candidate03_01'
OUT = HERE / 'vcs_candidate04_01'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
IMAGE_SHA = 'e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673'
UNIT = 'ara-fp-compare-source-candidate04.service'
read, save, sha, require = replay.read, replay.save, replay.sha, replay.require


def launch():
    require(not OUT.exists(), 'Output collision; no retry')
    state = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'LoadState'], text=True)
    require('LoadState=not-found' in state, 'Service collision')
    before = read(BEFORE / 'complete.json')
    require(before['status'] == 'COMPLETE_3_BASELINE_OBSERVATIONS' and
            [r['name'] for r in before['results']] == replay.NAMES, 'Baseline incomplete')
    plan = read(BEFORE / 'plan.json')
    replay.pins_check(plan['pins'])
    programs = read(HERE / 'soc01/programs.json')['programs']
    old_image = read(replay.IMAGE / 'image.json')
    baseline_audit = []
    baseline_pins = {}
    # Independently recheck the measured baseline, including failure veto and flags.
    for result in before['results']:
        name = result['name']
        artifact = BEFORE / name / 'tests' / name
        text = (artifact / 'console.log').read_text()
        run = read(BEFORE / name / 'run.json')
        summary = read(BEFORE / name / 'summary.json')
        require(run.get('completed_at') and run['tests'] == [name] and len(summary) == 1,
                'Baseline case not terminal')
        require(summary[0]['name'] == name and summary[0]['returncode'] == 0, 'Baseline simulator not terminal')
        require(sha(artifact / 'input.elf') == programs[name]['sha256'], 'Baseline ELF differs')
        inputs = read(artifact / 'inputs.json')
        require(inputs['binary'] == dict(source=programs[name]['path'], path=str(artifact/'input.elf'),
                sha256=programs[name]['sha256']), 'Baseline input identity differs')
        require(inputs['simv'] == dict(path=old_image['simv'], image_sha256=old_image['files']),
                'Baseline image identity differs')
        if name == 'vv_start0':
            require(result['status'] == 'PASS' and result['runner_returncode'] == 0 and
                    run['status'] == 'COMPLETE' and summary[0]['status'] == 'PASS', 'Baseline control failed')
            require(replay.console_pass(text, programs[name], name), 'Baseline PASS vetoed')
            observed_status = 'PASS'
        else:
            require(summary[0]['status'] == 'FAIL' and result['runner_returncode'] != 0,
                    'Baseline lacks measured failure')
            require(text.splitlines().count('FP_SOURCE_FAIL '+name+' cases=1 errors=10 flags=1 start_after=0') == 1
                    and text.splitlines().count('Core Test *** FAILED *** (tohost = 1)') == 1,
                    'Baseline numerical failure not observed')
            require('BOARD_REPLAY_PASS' not in text and 'BOARD_CASE_PASS' not in text,
                    'Contradictory baseline markers')
            observed_status = 'MEASURED_NUMERICAL_FAIL'
        require(any(s.startswith(('FP_SOURCE_PASS '+name, 'FP_SOURCE_FAIL '+name)) and
                    s.endswith('flags=1 start_after=0') for s in text.splitlines()), 'Baseline flags differ')
        baseline_audit.append(dict(name=name, observed_status=observed_status, original_status=result['status'],
            runner_status=run['status'], errors=0 if name == 'vv_start0' else 10, fflags=1, vstart_after=0,
            elapsed_s=summary[0]['elapsed_s'], console_sha256=sha(artifact/'console.log'),
            elf_sha256=programs[name]['sha256']))
        for p in (artifact/'console.log', artifact/'inputs.json', BEFORE/name/'run.json', BEFORE/name/'summary.json'):
            baseline_pins[str(p)] = sha(p)
    audit_path = HERE/'baseline_terminal_audit01.json'
    require(not audit_path.exists(), 'Baseline audit collision')
    save(audit_path, dict(status='BASELINE_FAIL_PASS_FAIL_MEASURED', results=baseline_audit,
        pass_gate_unchanged=True, old_records_unchanged=True,
        explanation='Single-case failure sets runner cancellation and INTERRUPTED; not absence of numerical evidence.'))
    require(sha(IMAGE / 'image.json') == IMAGE_SHA, 'Candidate04 image differs')
    ledger = read(IMAGE / 'image.json')
    snapshot = Path(ledger['snapshot']) / 'snapshot.json'
    require(sha(snapshot) == ledger['snapshot_sha256'], 'Snapshot differs')
    pins = dict(plan['pins'])
    pins.update(baseline_pins)
    for path in (Path(__file__).resolve(), audit_path, BEFORE/'complete.json', IMAGE/'image.json', snapshot):
        pins[str(path)] = sha(path)
    frozen = read(snapshot)
    for path, digest in frozen['files'].items():
        pins[str(Path(frozen['root'])/path)] = digest
    replay.pins_check(pins)
    live = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = [s.decode(errors='replace') for s in (proc/'cmdline').read_bytes().split(b'\0') if s]
            if args and Path(args[0]).name == 'simv': live.append(dict(pid=int(proc.name), argv=args))
        except OSError:
            continue
    observed = sum(any('/indexed_review/' in a for a in p['argv']) for p in live)
    reserved = max(0, 2-observed)
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0])*1024
    total = len(live)+reserved+1
    gate = dict(time=time.time(), live=live, live_count=len(live), nf7_slots=2,
                nf7_observed=observed, nf7_unoccupied_reservation=reserved, own_slots=1,
                total_live_reserved=total, cap=24, available_bytes=available,
                min_available_bytes=32*1024**3, passed=total<=24 and available>=32*1024**3)
    OUT.mkdir()
    save(OUT/'resource_gate.json', gate)
    save(OUT/'plan.json', dict(plan, pins=pins, image=str(IMAGE), image_sha256=IMAGE_SHA,
         baseline=str(BEFORE), same_elf=True, same_checker=True, no_fsdb=True))
    if not gate['passed']:
        save(OUT/'complete.json', dict(status='CAPACITY_BLOCKED_NO_LAUNCH', retries=0))
        print('CAPACITY_BLOCKED_NO_LAUNCH', total, available/1024**3)
        return 2
    command = ['systemd-run', '--user', '--unit='+UNIT, '--collect',
        '--property=RuntimeMaxSec=900', '--property=TimeoutStopSec=60',
        '--property=KillMode=control-group', '--property=Restart=no',
        '--property=StandardOutput=append:'+str(OUT/'service.log'),
        '--property=StandardError=append:'+str(OUT/'service.log'),
        sys.executable, '-B', str(Path(__file__).resolve()), '--work', sha(OUT/'plan.json')]
    result = subprocess.run(command, text=True, capture_output=True)
    save(OUT/'launch.json', dict(command=command, returncode=result.returncode,
                               stdout=result.stdout, stderr=result.stderr))
    print(result.stderr.strip(), 'total_live_reserved='+str(total), 'available_GiB='+str(available/1024**3))
    return result.returncode


def work(digest):
    replay.OUT = OUT
    replay.IMAGE = IMAGE
    code = replay.work(digest)
    terminal = read(OUT/'complete.json')
    terminal['status'] = 'PASS_3_SAME_ELF_CANDIDATE04' if terminal['all_pass'] else 'NOT_ACCEPTED_CANDIDATE04'
    terminal['baseline'] = str(BEFORE)
    terminal['same_elf'] = True
    terminal['same_checker'] = True
    save(OUT/'complete.json', terminal)
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--work')
    args = parser.parse_args()
    raise SystemExit(work(args.work) if args.work else launch())
