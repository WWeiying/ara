#!/usr/bin/env python3
"""One fresh admission with Tesla reservation released; old attempt immutable."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import candidate03 as replay

HERE = replay.HERE
OUT = HERE / 'vcs_candidate03_02'
replay.OUT = OUT
read, sha, save, require = replay.read, replay.sha, replay.save, replay.require


def launch():
    require(not OUT.exists(), 'Fresh output required; no retry')
    state = subprocess.check_output(['systemctl', '--user', 'show', replay.UNIT, '-p', 'LoadState'], text=True)
    require('LoadState=not-found' in state, 'Service collision')
    old_path = HERE / 'vcs_candidate03_01/plan.json'
    old = read(old_path)
    require(read(old_path.parent / 'complete.json')['status'] == 'CAPACITY_BLOCKED_NO_LAUNCH', 'Previous attempt not a refusal')
    replay.pins_check(old['pins'])
    require(sha(replay.IMAGE / 'image.json') == replay.IMAGE_SHA, 'Wrong image')
    require(sha(replay.PREPARED / 'soc/programs.json') == replay.PROGRAMS_SHA, 'Wrong original47 input')
    require(old['jobs'] == 2 and old['timeout_per_case_s'] == 180 and old['outer_s'] == 5400, 'Original budgets changed')
    pins = dict(old['pins'])
    for path in (Path(__file__), old_path, old_path.parent / 'resource_gate.json', old_path.parent / 'complete.json'):
        pins[str(path)] = sha(path)

    # Exactly one inventory, with completed Tesla controls no longer reserved.
    live = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = [s.decode(errors='replace') for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
            if args and Path(args[0]).name == 'simv':
                live.append(dict(pid=int(proc.name), argv=args))
        except (OSError, ProcessLookupError):
            continue
    reservations = {}
    for label, token, slots in (('nf7', '/indexed_review/', 2), ('alias', '/mask_alias_original/', 1)):
        observed = sum(any(token in arg for arg in row['argv']) for row in live)
        reservations[label] = dict(slots=slots, observed_live=observed, unoccupied=max(0, slots-observed))
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0]) * 1024
    occupied = len(live) + sum(r['unoccupied'] for r in reservations.values())
    gate = dict(observed_at=time.time(), live=live, live_count=len(live), reservations=reservations,
                tesla_reserved=0, tesla_release='Parent reports16controls terminalPASS; no remaining jobs/reservation',
                own_slots=2, total_live_reserved=occupied+2, cap=24,
                available_bytes=available, min_available_bytes=32*1024**3,
                passed=occupied <= 22 and available >= 32*1024**3)
    OUT.mkdir()
    save(OUT / 'resource_gate.json', gate)
    plan = dict(old, pins=pins, admission='Explicitly authorized fresh attempt02; Tesla reservation released',
                previous_refusal_plan_sha256=sha(old_path), resource_gate_sha256=sha(OUT / 'resource_gate.json'))
    save(OUT / 'plan.json', plan)
    if not gate['passed']:
        save(OUT / 'complete.json', dict(status='CAPACITY_BLOCKED_NO_LAUNCH', retries=0))
        print(json.dumps(dict(status='CAPACITY_BLOCKED_NO_LAUNCH', live=len(live),
                             total_live_reserved=occupied+2, available_gib=available/1024**3,
                             reservations=reservations, out=str(OUT)), indent=2))
        return 2
    command = ['systemd-run', '--user', '--unit=' + replay.UNIT, '--collect',
               '--property=RuntimeMaxSec=5400', '--property=TimeoutStopSec=120',
               '--property=KillMode=control-group', '--property=Restart=no',
               '--property=WorkingDirectory=' + str(replay.source.prepare.ROOT),
               '--property=StandardOutput=append:' + str(OUT / 'service.log'),
               '--property=StandardError=append:' + str(OUT / 'service.log'),
               sys.executable, '-B', str(Path(__file__).resolve()), '--work', sha(OUT / 'plan.json')]
    save(OUT / 'service_command.json', command)
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    save(OUT / 'launch.json', dict(returncode=result.returncode, output=result.stdout, started=time.time(), plan_sha256=sha(OUT / 'plan.json')))
    print(json.dumps(dict(returncode=result.returncode, output=result.stdout, live=len(live),
                         total_live_reserved=occupied+2, available_gib=available/1024**3,
                         reservations=reservations, out=str(OUT)), indent=2))
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--work')
    args = parser.parse_args()
    raise SystemExit(replay.work(args.work) if args.work else launch())
