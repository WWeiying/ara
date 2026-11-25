#!/usr/bin/env python3
"""Own a finite precheck queue after a known live RTL compiler finishes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2)+'\n')
    tmp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worker', type=Path, required=True)
    p.add_argument('--service', required=True)
    p.add_argument('--wait-service', action='append', default=[])
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Fresh queue output required')
    a.output.mkdir()
    (a.output/'inputs').mkdir()
    shutil.copyfile(__file__,a.output/'inputs/after_compile.py')
    shutil.copyfile(a.worker,a.output/'inputs'/a.worker.name)
    if a.worker.name == 'precheck_v2.py':
        shutil.copyfile(a.worker.with_name('precheck.py'),a.output/'inputs/precheck.py')
    shutil.copyfile(a.manifest,a.output/'inputs/manifest.json')
    a.manifest = a.output/'inputs/manifest.json'
    a.worker = a.output/'inputs'/a.worker.name
    frozen = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (a.output/'inputs').iterdir() if path.is_file()}
    save(a.output/'source-pins.json',frozen)
    save(a.output/'status.json', dict(state='WAITING_FOR_RTL_COMPILE', pid=os.getpid(),
                                     image=str(a.image), service=a.service))
    start = time.monotonic()
    try:
        while True:
            result = a.image/'build.json'
            if result.exists():
                state = json.loads(result.read_text())['state']
                if state not in ('DC_MATCHED_RTL_BUILT_NOT_EXECUTED',
                                  'RECONSTRUCTED_BASELINE_RTL_BUILT_NOT_EXECUTED'):
                    raise ValueError('RTL build failed: '+state)
                break
            proc = subprocess.run(['systemctl','--user','show',a.service,
                                   '-p','ActiveState','-p','MainPID'],capture_output=True,text=True,check=True)
            fields = dict(line.split('=',1) for line in proc.stdout.splitlines())
            if fields.get('ActiveState') not in ('active','activating'):
                raise ValueError('Compiler stopped without terminal build receipt')
            pid = int(fields.get('MainPID','0'))
            if not pid or not Path('/proc',str(pid)).exists():
                raise ValueError('Compiler owner is not live')
            if time.monotonic()-start > 7800:
                raise TimeoutError('RTL compile wait budget')
            time.sleep(60)
        # Do not add four baseline simulations while the earlier native
        # queues still occupy slots. Failed originals retain their evidence.
        for unit in a.wait_service:
            while True:
                proc = subprocess.run(['systemctl','--user','show',unit,
                    '-p','ActiveState','-p','MainPID'],capture_output=True,text=True,check=True)
                fields = dict(line.split('=',1) for line in proc.stdout.splitlines())
                if fields.get('ActiveState') not in ('active','activating','deactivating'):
                    break
                if time.monotonic()-start > 14400:
                    raise TimeoutError('Earlier queue did not release simulator slots')
                time.sleep(60)
        campaign = a.output.with_name(a.output.name+'_runs')
        if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest
               for path,digest in frozen.items()):
            raise ValueError('Frozen controller input drift')
        prepare = [sys.executable,'-B',str(a.worker),'prepare','--output',str(campaign),
                   '--image',str(a.image),'--manifest',str(a.manifest),'--parallel','4']
        with (a.output/'prepare.log').open('x') as stream:
            subprocess.run(prepare,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=300)
        save(a.output/'status.json', dict(state='RTL_PRECHECKS_RUNNING',campaign=str(campaign),pid=os.getpid()))
        with (a.output/'worker.log').open('x') as stream:
            proc = subprocess.run([sys.executable,'-B',str(campaign/'inputs'/a.worker.name),
                                   'execute','--output',str(campaign)],
                                  stdout=stream,stderr=subprocess.STDOUT)
        result = json.loads((campaign/'result.json').read_text())
        if proc.returncode or result['state'] != 'PASS':
            raise ValueError('RTL prechecks incomplete: '+str(campaign))
        save(a.output/'result.json',dict(state='RTL_PRECHECKS_PASS',campaign=str(campaign),
                                        power_measured=False,gate_simulation_started=False))
        save(a.output/'status.json',dict(state='RTL_PRECHECKS_PASS',campaign=str(campaign)))
        return 0
    except Exception as exc:
        save(a.output/'result.json',dict(state='FAIL',error=repr(exc),power_measured=False))
        save(a.output/'status.json',dict(state='FAIL',error=repr(exc)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
