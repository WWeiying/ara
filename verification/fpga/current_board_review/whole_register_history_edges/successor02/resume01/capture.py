#!/usr/bin/env python3
"""One-shot read-only resume identity/resource capture; never invokes a worker."""
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
ROOT = HELPERS.parents[4]
sys.path.insert(0, str(HELPERS))


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    with Path(p).open('rb') as f:
        h = hashlib.sha256()
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    with (HERE/name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def main():
    expected = {
        'driver.py': '39461b0782d8a744fd3e35737779a4e72e47df8b54b97a38b7c7423ec856f5e0',
        'csv_adapter.py': '8107496f63e320e369355ebe59e4e4601c61497a06ed8509dc1bc6debefb64cb',
        'preflight01/plan.json': '9af488c58cef1ae4e76b171036a254b32814606f3659a4b36d09db89f1f10f81',
        'host01/complete.json': '6ac919ff950cc492154d76b4aafd169d4d1c80ccf3caa8cfcc2db22bdd70aeb6',
        'test_adapter.py': '20aa8040d5ba73a386f81fb413861c1070cf8bc6acf104e979c92245bbe6f1c2',
    }
    actual = {n: sha(HELPERS/n) for n in expected}
    if actual != expected:
        raise ValueError('Frozen helper/plan/reference identity drift')
    plan = read(HELPERS/'preflight01/plan.json')
    for p, digest in plan['pins'].items():
        if sha(p) != digest:
            raise ValueError('Plan pin drift: '+p)
    host = read(HELPERS/'host01/complete.json')
    for p, digest in host['pins'].items():
        if sha(p) != digest:
            raise ValueError('Host pin drift: '+p)
    import driver
    image, _, _ = driver.existing.original.identity()
    if image['files'] != plan['image_files']:
        raise ValueError('Compiled M4 image drift')
    dry = read(HELPERS/'preflight01/dryrun/summary.json')
    if (len(dry) != 59 or {r['name'] for r in dry} != {c['id'] for c in plan['cases']}
            or any(r['status'] != 'DRY_RUN' for r in dry)):
        raise ValueError('Dry-run membership/status differs')
    if (HELPERS/'preflight01/worker.json').exists() or list((HELPERS/'preflight01/pairs').iterdir()):
        raise ValueError('Previous launch artifacts exist; do not duplicate launch')
    identity = dict(status='RESUME_FROZEN_IDENTITY_PASS_NOT_LAUNCHED', utc=datetime.now(timezone.utc).isoformat(),
                    helper_hashes=actual, plan_pins=len(plan['pins']), host_pins=len(host['pins']),
                    dryrun_cases=59, frozen_sources=539, image_files=len(image['files']),
                    image_sha256=plan['image_sha256'], worker_exists=False, pair_outputs=0)
    save('identity.json', identity)

    # Capture all visible UIDs, not just the sealed worker's same-UID inventory.
    live, unknown, owners = [], [], []
    scanned = 0
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            uid = proc.stat().st_uid
            comm = (proc/'comm').read_text().strip()
            scanned += 1
            cgroup = (proc/'cgroup').read_text()
            try:
                argv = (proc/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            except PermissionError:
                argv = None
            owned = driver.OLD_UNIT in cgroup or (argv is not None and str(driver.OLD) in argv)
            if comm == 'simv' or owned:
                stat = (proc/'stat').read_text().rsplit(') ', 1)[1].split()
                row = dict(pid=int(proc.name), uid=uid, comm=comm, cgroup=cgroup, argv=argv,
                           ppid=int(stat[1]), start_ticks=stat[19])
                if comm == 'simv':
                    live.append(row)
                if owned:
                    owners.append(row)
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as e:
            unknown.append(dict(pid=int(proc.name), error=str(e)))
    listing = subprocess.run(['systemctl', '--user', 'list-units', '--all', '--type=service',
                              '--no-pager', '--plain', '--output=json'], text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    if listing.returncode:
        raise ValueError('User service inventory failed: '+listing.stderr)
    units = json.loads(listing.stdout)
    save('service_inventory.json', dict(utc=datetime.now(timezone.utc).isoformat(), units=units, stderr=listing.stderr))
    relevant = [u for u in units if u['unit'].startswith('ara-') and u['active'] in ('active', 'activating', 'deactivating')]
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0])*1024
    total = int(memory['MemTotal'].split()[0])*1024
    by_unit = Counter(next((p for p in reversed(r['cgroup'].strip().split('/')) if p.endswith('.service')), 'OUTSIDE_SERVICE') for r in live)
    resources = dict(status='RESOURCE_OBSERVATION_ONLY_NOT_LAUNCH_ADMISSION', utc=datetime.now(timezone.utc).isoformat(),
                     cpu_count=os.cpu_count(), mem_available_bytes=available, mem_total_bytes=total,
                     processes_scanned=scanned, inaccessible=unknown, simv=live, simv_count=len(live),
                     other_uid_simv_count=sum(r['uid'] != os.getuid() for r in live),
                     simv_by_unit=dict(by_unit), active_ara_units=relevant, old_whole_owners=owners,
                     own_future_slots=6, total_cap=24, memory_floor_bytes=32*1024**3,
                     raw_actual_plus_own=len(live)+6,
                     note='Reservations require current parent ownership roster; no task progress files queried.')
    save('resources.json', resources)
    old = driver.OLD.parent
    files = {name: dict(exists=(old/name).exists(), sha256=sha(old/name) if (old/name).is_file() else None)
             for name in ('terminal_audit01.md', 'terminal_audit01.json', 'strict_acceptance01.json')}
    save('terminal_binding_inventory.json', dict(status='INVENTORY_ONLY_NOT_STRICT_ACCEPTANCE', files=files))
    print(json.dumps(dict(identity=identity, simv_count=len(live), simv_by_unit=dict(by_unit),
                         other_uid_simv_count=resources['other_uid_simv_count'], inaccessible=len(unknown),
                         mem_available_GiB=available/1024**3, old_whole_owners=owners,
                         active_ara_units=relevant, terminal_files=files), indent=2), flush=True)


if __name__ == '__main__':
    main()
