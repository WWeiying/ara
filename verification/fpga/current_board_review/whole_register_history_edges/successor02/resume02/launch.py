#!/usr/bin/env python3
"""Parent-authorized single launch using unchanged successor02 gates/worker."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HELPERS = HERE.parent
OUT = HELPERS/'preflight01'
UNIT = 'ara-whole-history59-candidate04-01.service'
GATHER = 'ara-gather-focused-candidate04-01.service'
PLAN_SHA = '9af488c58cef1ae4e76b171036a254b32814606f3659a4b36d09db89f1f10f81'
DRIVER_SHA = '39461b0782d8a744fd3e35737779a4e72e47df8b54b97a38b7c7423ec856f5e0'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    with (HERE/name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def all_simv():
    rows = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            uid = p.stat().st_uid
            comm = (p/'comm').read_text().strip()
            if comm != 'simv':
                continue
            cgroup = (p/'cgroup').read_text()
            argv = (p/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            rows.append(dict(pid=int(p.name), uid=uid, comm=comm, cgroup=cgroup, argv=argv))
        except (FileNotFoundError, ProcessLookupError):
            continue
        # Unknown potentially live simulators cannot silently bypass global capacity.
    return rows


def main():
    if sha(HELPERS/'driver.py') != DRIVER_SHA or sha(OUT/'plan.json') != PLAN_SHA:
        raise ValueError('Frozen code/plan drift')
    sys.path.insert(0, str(HELPERS))
    import driver as d
    require, read = d.require, d.read
    require(not (OUT/'worker.json').exists() and not list((OUT/'pairs').iterdir()), 'Prior launch artifacts; no duplicate')
    plan = read(OUT/'plan.json')
    d.base.verify_pins(plan['pins'])
    image, _, _ = d.existing.original.identity()
    require(image['files'] == plan['image_files'], 'Frozen M4 image mismatch')
    original = d.OLD.parent
    strict = original/'strict_acceptance01.json'
    validation = original/'strict_acceptance01_validation.json'
    audit = original/'terminal_audit01.json'
    v = read(validation)
    require(v['status'] == 'EXISTING_SUCCESSOR02_TERMINAL_GATE_PASS' and
            v['acceptance_sha256'] == sha(strict) == 'e6afdb36769c33412976793c0c32b75a4be252d71d63bb23e186eb4940b307af' and
            v['audit_sha256'] == sha(audit) and v['gate_sha256'] == DRIVER_SHA and
            v['evidence_pin_count'] == 155 and v['old_pin_count'] == 927,
            'Tesla final strict validation identity differs')
    require(read(audit)['status'] == 'INDEPENDENT_RAW_TERMINAL_20_PARTITIONS_PASS', 'Audit not final PASS')
    review = dict(parent_authorized=True, plan_sha256=PLAN_SHA, image_sha256=plan['image_sha256'], jobs=6,
                  whole1134_acceptance=dict(path=str(strict), sha256=sha(strict)),
                  reserved_units=[dict(unit=GATHER, slots=2)],
                  terminal_validation=dict(path=str(validation), sha256=sha(validation)),
                  independent_audit=dict(path=str(audit), sha256=sha(audit)),
                  authority='Parent explicitly authorized launch after Tesla final confirmation; Confucius confirmed exact Gather focused unit and two-slot reservation.',
                  scope=plan['scope'])
    save('review.json', review)
    strict_gate = d.terminal_gate(review, plan)
    save('strict_gate.json', strict_gate)

    global_live = all_simv()
    actual_gather = sum('/'+GATHER in p['cgroup'] for p in global_live)
    spare_gather = max(0, 2-actual_gather)
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0])*1024
    total = len(global_live)+spare_gather+6
    require(total <= 24 and available >= 32*1024**3, 'All-UID global capacity refused; no retry')
    gate = d.admission(review['reserved_units'])
    save('admission.json', dict(utc=datetime.now(timezone.utc).isoformat(), all_uid_simv=global_live,
         actual_count=len(global_live), other_uid_count=sum(r['uid'] != os.getuid() for r in global_live),
         gather_actual=actual_gather, gather_unused_reservation=spare_gather, own_slots=6,
         total_live_reserved=total, cap=24, available_bytes=available, minimum_available_bytes=32*1024**3,
         sealed_admission=gate))
    raw = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'LoadState', '-p', 'ActiveState', '-p', 'MainPID'],
                                  text=True, timeout=10)
    state = dict(line.split('=', 1) for line in raw.splitlines())
    require(state['LoadState'] == 'not-found' and state['MainPID'] == '0', 'Unit already exists; no duplicate/retry')
    require(sha(strict) == review['whole1134_acceptance']['sha256'] and sha(OUT/'plan.json') == PLAN_SHA and
            sha(HELPERS/'driver.py') == DRIVER_SHA, 'Last-edge identity drift')
    cmd = ['systemd-run', '--user', '--unit='+UNIT, '--property=RuntimeMaxSec=3600',
           '--property=KillMode=control-group', '--property=Restart=no', '--property=WorkingDirectory='+str(HELPERS),
           '--property=StandardOutput=append:'+str(OUT/'service.log'),
           '--property=StandardError=append:'+str(OUT/'service.log'),
           '/usr/bin/python3', '-B', str(HELPERS/'driver.py'), 'worker', '--out', str(OUT),
           '--review', str(HERE/'review.json'), '--authorize-run']
    save('launch_command.json', cmd)
    launch = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    save('launch_result.json', dict(returncode=launch.returncode, stdout=launch.stdout, stderr=launch.stderr,
         utc=datetime.now(timezone.utc).isoformat(), review_sha256=sha(HERE/'review.json'),
         plan_sha256=PLAN_SHA, service=UNIT))
    require(launch.returncode == 0, 'Single service launch refused; preserve, do not retry')
    print(json.dumps(dict(service=UNIT, launch_returncode=launch.returncode, review_sha256=sha(HERE/'review.json'),
         actual_simv_before_launch=len(global_live), total_live_reserved=total,
         available_GiB=available/1024**3, output=str(OUT)), indent=2), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if not (HERE/'failure.json').exists():
            save('failure.json', dict(status='NOT_LAUNCHED_OR_NOT_CONFIRMED', error=repr(error)))
        raise
