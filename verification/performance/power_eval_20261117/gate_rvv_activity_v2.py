#!/usr/bin/env python3
"""Scheduling-only successor: Q8 GLS has priority; idle DC followers use no VCS slot."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
BASE_SHA='f5c014d3eedff20493a89f2c8cd117032a22e617d45633d18b85e35e6edf7d42'
spec=importlib.util.spec_from_file_location('rvv_activity_original_unchanged',HERE/'gate_rvv_activity.py')
b=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
b.require(b.sha(HERE/'gate_rvv_activity.py')==BASE_SHA,'Sealed activity collector drift')
DEFAULT=b.OUT/'power_gls_20261117_baseline_rvv_activity_02'


def filter_q8_gls(text):
    units=[line.split()[0] for line in text.splitlines() if line.strip()]
    return [unit for unit in units if unit.startswith('power-gls-') and 'q8' in unit and unit.endswith('.service')]


def q8_gls_units():
    proc=subprocess.run(['systemctl','--user','list-units','--type=service',
        '--state=active,activating,deactivating','--plain','--no-legend','--no-pager','power-gls-*q8*.service'],
        capture_output=True,text=True,check=True,timeout=30)
    return filter_q8_gls(proc.stdout)


def prepare(out):
    b.prepare(out)
    pins=b.read(out/'source-pins.json')
    for name in ('gate_rvv_activity_v2.py','test_gate_rvv_activity_v2.py'):
        source,dest=HERE/name,out/'inputs'/name
        shutil.copyfile(source,dest)
        pins[str(source)]=b.sha(source)
        pins[str(dest)]=b.sha(dest)
    with (out/'successor-host-tests.log').open('x') as log:
        subprocess.run([sys.executable,'-B',str(out/'inputs/test_gate_rvv_activity_v2.py'),'-v'],
            stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    pins[str(out/'successor-host-tests.log')]=b.sha(out/'successor-host-tests.log')
    plan=b.read(out/'plan.json')
    plan.update(priority='Active Q8 GLS jobs and their gate control chains only; DC is not a VCS slot consumer',
                scheduling_successor='Q8_GLS_ONLY_PRIORITY_V2',parent_worker_sha256=BASE_SHA)
    b.save(out/'plan.json',plan)
    pins[str(out/'plan.json')]=b.sha(out/'plan.json')
    b.save(out/'scheduling-policy.json',dict(original_worker_unmodified=True,hdl_and_elf_unmodified=True,
        shared_locks_unmodified=True,slot_accounting_unmodified=True,gate_validation_unmodified=True,
        change='Filter Q8 priority to power-gls-*q8*.service; never block on idle DC follow services'),True)
    pins[str(out/'scheduling-policy.json')]=b.sha(out/'scheduling-policy.json')
    b.save(out/'source-pins.json',pins)
    b.verify(pins)
    ready=b.read(out/'ready-command.json')
    argv=ready['service']
    argv[argv.index(str(out/'inputs/gate_rvv_activity.py'))]=str(out/'inputs/gate_rvv_activity_v2.py')
    argv[argv.index('--plan-sha256')+1]=b.sha(out/'plan.json')
    ready.update(service=argv,scheduling_successor='Q8_GLS_ONLY_PRIORITY_V2')
    b.save(out/'ready-command.json',ready)


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('action',choices=('prepare','execute'))
    p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--plan-sha256')
    p.add_argument('--authorize-capture',action='store_true')
    a=p.parse_args()
    out=a.output.resolve()
    if a.action=='prepare':
        b.require(not a.authorize_capture,'Preparation never launches')
        prepare(out)
        print(json.dumps(dict(state='IMAGE_BOUND_NOT_LAUNCHED',output=str(out))))
        return 0
    b.require(Path(__file__).resolve()==out/'inputs/gate_rvv_activity_v2.py','Frozen scheduling successor required')
    # Private imported successor instance only: no sealed file or running worker is changed.
    # Numerical, image, VCD, process ownership and shared-capacity gates are untouched.
    b.q8_units=q8_gls_units
    return b.execute(out,a.plan_sha256,a.authorize_capture)


if __name__=='__main__':raise SystemExit(main())
