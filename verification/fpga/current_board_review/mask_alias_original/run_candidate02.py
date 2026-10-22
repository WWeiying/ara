#!/usr/bin/env python3
"""One authorized candidate02 slot: exact tuples, then original prefixes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import port as full

HERE = full.HERE
OUT = HERE / 'vcs_candidate02_01'
PROGRAMS = HERE / 'bounded01/soc'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign/image')
RUNNER = HERE.parent / 'integration/run.py'
UNIT = 'ara-mask-alias-candidate02.service'


def check_pins(pins):
    for path, digest in pins.items():
        full.require(full.sha(Path(path)) == digest, 'Pin drift: ' + path)


def work(plan_hash):
    full.require(full.sha(OUT / 'plan.json') == plan_hash, 'Plan hash mismatch')
    plan = json.loads((OUT / 'plan.json').read_text())
    check_pins(plan['pins'])
    stages = []
    full.save(OUT / 'worker.json', dict(pid=__import__('os').getpid(), started=time.time(), plan_sha256=plan_hash))
    for kind, timeout in (('tuple', 300), ('prefix', 6000)):
        check_pins(plan['pins'])
        names = [n + '_' + kind for n in full.NAMES]
        command = [sys.executable, '-B', str(RUNNER), 'run', '--image', str(IMAGE),
                   '--programs', str(PROGRAMS), '--out', str(OUT / kind),
                   '--jobs', '1', '--timeout', str(timeout), '--execute']
        for name in names:
            command += ['--case', name]
        full.save(OUT / (kind + '_command.json'), command)
        with (OUT / (kind + '.log')).open('x') as log:
            rc = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT, cwd=full.ROOT)
        summary = OUT / kind / 'summary.json'
        results = json.loads(summary.read_text()) if summary.exists() else []
        passed = (rc == 0 and len(results) == 3 and
                  {r['name'] for r in results} == set(names) and
                  all(r['status'] == 'PASS' for r in results))
        stages.append(dict(stage=kind, returncode=rc, results=results, passed=passed))
        full.save(OUT / 'stage_status.json', dict(stages=stages, updated=time.time()))
        if not passed:
            full.save(OUT / 'complete.json', dict(status='STOPPED_NOT_PASS', stages=stages,
                      finished=time.time(), plan_sha256=plan_hash, retries=0))
            return 1
    check_pins(plan['pins'])
    full.save(OUT / 'complete.json', dict(status='PASS_3_TUPLES_3_PREFIXES_NOT_FULL_MATRICES',
              stages=stages, finished=time.time(), plan_sha256=plan_hash, retries=0))
    return 0


def launch():
    full.require(not OUT.exists(), 'Output collision; no reuse or auto retry')
    unit_state = subprocess.check_output(['systemctl', '--user', 'show', UNIT,
                                         '-p', 'LoadState', '-p', 'ActiveState'], text=True)
    full.require('LoadState=not-found' in unit_state, 'Service collision')
    reference = json.loads((HERE / 'bounded01/status.json').read_text())
    full.require(reference['status'] == 'BOUNDED_PARTITIONS_READY_NOT_DUT' and
                 len(reference['results']) == 6 and
                 all(x['status'] == 'PASS' for x in reference['results']), 'Reference not accepted')
    full.prepare.check(HERE / 'bounded01/prepared')
    ledger = json.loads((HERE / 'bounded01/partition_provenance.json').read_text())
    pins = dict(ledger['files'])
    for path in [Path(__file__), RUNNER, IMAGE / 'image.json', PROGRAMS / 'programs.json',
                 HERE / 'bounded01/partition_provenance.json', HERE / 'bounded01/status.json',
                 HERE / 'bounded01/host/status.json', HERE / 'bounded01/reference/status.json',
                 HERE / 'bounded01/prepared/provenance.json']:
        pins[str(path)] = full.sha(path)
    full.require(pins[str(IMAGE / 'image.json')] ==
                 '384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810', 'Wrong candidate02 image')
    full.require(pins[str(PROGRAMS / 'programs.json')] ==
                 'daf65942945329b9d2ee3a846ed9f4674de05c32feead6c3257e894ccb43a397', 'Reviewed ELF manifest changed')
    image = json.loads((IMAGE / 'image.json').read_text())
    pins.update(image['files'])
    programs = json.loads((PROGRAMS / 'programs.json').read_text())
    pins.update({p['path']: p['sha256'] for p in programs['programs'].values()})
    check_pins(pins)

    # One live inventory. No polling, retries, process termination, or scheduler.
    live = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = proc.joinpath('cmdline').read_bytes().split(b'\0')
            if args and Path(args[0].decode(errors='replace')).name == 'simv':
                live.append(dict(pid=int(proc.name), argv=[a.decode(errors='replace') for a in args if a]))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    memory = dict((line.split(':')[0], int(line.split()[1]))
                  for line in Path('/proc/meminfo').read_text().splitlines())
    gate = dict(observed_at=time.time(), live_simv=live, live_count=len(live),
                nf7_reserved=2, alias_reserved=1, total_live_plus_reserved=len(live) + 3,
                cap=24, available_gib=memory['MemAvailable'] / 1024**2, min_available_gib=32,
                policy='Parent explicit 24 live/reserved and >=32GiB; conservatively add NF7 reservations even if live',
                supersedes='Prior self-imposed global8 cap; no testcase/budget/RTL changes',
                pass_gate=len(live) + 3 <= 24 and memory['MemAvailable'] >= 32 * 1024**2)
    OUT.mkdir()
    full.save(OUT / 'resource_gate.json', gate)
    plan = dict(unit=UNIT, image=str(IMAGE), simv=image['simv'], programs=str(PROGRAMS),
                jobs=1, phases=['tuple', 'prefix'], tuple_timeout_s=300, prefix_timeout_s=6000,
                service_outer_s=19800, prefix_requires_all_three_tuples_PASS=True,
                full_matrices_authorized=False, pins=pins, retries=0,
                gate_sha256=full.sha(OUT / 'resource_gate.json'))
    full.save(OUT / 'plan.json', plan)
    if not gate['pass_gate']:
        full.save(OUT / 'complete.json', dict(status='CAPACITY_BLOCKED_NO_LAUNCH', retries=0))
        print(json.dumps(gate, indent=2))
        return 2
    command = ['systemd-run', '--user', '--unit=' + UNIT, '--collect',
               '--property=RuntimeMaxSec=19800', '--property=TimeoutStopSec=120',
               '--property=KillMode=control-group', '--property=Restart=no',
               '--property=WorkingDirectory=' + str(full.ROOT),
               '--property=StandardOutput=append:' + str(OUT / 'service.log'),
               '--property=StandardError=append:' + str(OUT / 'service.log'),
               sys.executable, '-B', str(Path(__file__).resolve()), '--work', full.sha(OUT / 'plan.json')]
    full.save(OUT / 'service_command.json', command)
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    full.save(OUT / 'launch.json', dict(returncode=result.returncode, output=result.stdout,
              launched_at=time.time(), unit=UNIT, plan_sha256=full.sha(OUT / 'plan.json')))
    print(json.dumps(dict(live_count=len(live), live_plus_reserved=len(live) + 3,
                         available_gib=gate['available_gib'], launch_returncode=result.returncode,
                         service=result.stdout, out=str(OUT)), indent=2))
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--work', metavar='PLAN_SHA256')
    args = parser.parse_args()
    raise SystemExit(work(args.work) if args.work else launch())
