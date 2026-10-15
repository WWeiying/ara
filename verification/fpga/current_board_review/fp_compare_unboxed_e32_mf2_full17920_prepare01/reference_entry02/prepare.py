#!/usr/bin/env python3
"""One bounded cache-successor preparation; no reference or target compilation."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'reference_entry01'
from execute_once import sha,save,require


def main():
    require(not(HERE/'spec.json').exists() and not(HERE/'ENTRY.json').exists(),'Exclusive successor preparation')
    require(sha(OLD/'ENTRY.json')=='b14debc5f8a29115b534dafd515c1d02e634abc48aa9fc029283a02852e4c57a','Frozen original entry')
    require(not(OLD/'reference01').exists() and not(HERE/'reference01').exists(),'Neither reference entry has run')
    entry=json.loads((OLD/'ENTRY.json').read_text())
    pins=json.loads((OLD/'input_pins.json').read_text())
    require(all(sha(Path(p))==h for p,h in pins.items()),'All inherited original input pins')
    shutil.copyfile(OLD/'spec.json',HERE/'spec.json')
    require(sha(HERE/'spec.json')==entry['spec_sha256'],'Same exact original FP32 spec')
    for name in ('execute_once.py','audit_once.py'):
        require(sha(HERE/name)==sha(OLD/name),'Unmodified reference executor/audit wrapper')
    for p in [OLD/'ENTRY.json',OLD/'input_pins.json',HERE/'spec.json',HERE/'README.md',*HERE.glob('*.py')]:
        pins[str(p)]=sha(p)
    save(HERE/'inputs_before.json',pins)
    command=[sys.executable,'-B',str(HERE/'test_cache.py')]
    save(HERE/'host.command.json',command)
    t=time.monotonic()
    with (HERE/'host.log').open('x') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        save(HERE/'host.started.json',dict(pid=child.pid,timeout_s=120))
        try:rc=child.wait(timeout=120);timed=False
        except subprocess.TimeoutExpired:child.kill();rc=child.wait();timed=True
    save(HERE/'host.wait.json',dict(actual_wait_exit=rc,timed_out=timed,
                                  elapsed_s=time.monotonic()-t,log_sha256=sha(HERE/'host.log')))
    require(type(rc) is int and rc==0 and timed is False,'Short differential Host failed, preserve stop')
    profile=json.loads((HERE/'cache_profile.json').read_text())
    require(profile['old_builder_calls']==294 and profile['new_builder_calls']==6 and
            profile['actual_store_events_each']==294,'Actual small construction-count proof')
    require(all(sha(Path(p))==h for p,h in pins.items()),'Old/new input drift during short tests')
    save(HERE/'inputs_after.json',pins)
    for p in [HERE/'host.command.json',HERE/'host.started.json',HERE/'host.wait.json',HERE/'host.log',
              HERE/'cache_profile.json',HERE/'inputs_before.json',HERE/'inputs_after.json']:
        pins[str(p)]=sha(p)
    save(HERE/'input_pins.json',pins)
    entry.update(status='PREPARED_FP32_CACHE_SUCCESSOR_PENDING_AVERROES_AND_PARENT_ADMISSION',
                 predecessor_entry=str(OLD/'ENTRY.json'),predecessor_entry_sha256=sha(OLD/'ENTRY.json'),
                 input_pins_sha256=sha(HERE/'input_pins.json'),checker_sha256=sha(HERE/'checker.py'),
                 reference_executor_sha256=sha(HERE/'execute_once.py'),host_wait_sha256=sha(HERE/'host.wait.json'),
                 cache_profile_sha256=sha(HERE/'cache_profile.json'),
                 cache_scope='Instance-local current ordinal; immutable49 source tuples; all actual stores still checked',
                 command='python3 -B '+str(HERE/'execute_once.py')+' --review ACTUAL_REVIEW_JSON --review-sha256 ACTUAL_SHA --parent-authorization ACTUAL_PARENT_JSON --parent-authorization-sha256 ACTUAL_PARENT_SHA')
    save(HERE/'ENTRY.json',entry)
    print('CACHE_SUCCESSOR_PREPARED_NOT_EXECUTED',sha(HERE/'ENTRY.json'),flush=True)


if __name__=='__main__':main()
