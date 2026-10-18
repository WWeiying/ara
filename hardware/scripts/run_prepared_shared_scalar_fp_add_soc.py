#!/usr/bin/env python3
"""Execute one frozen SoC preparation once, then compare complete baseline suites."""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared',type=Path)
    args=parser.parse_args()
    out=args.prepared.resolve()
    prepared=json.loads((out/'manifest.json').read_text())
    statusfile=out/'execution.json'
    assert not statusfile.exists(),'Execution already attempted; never restart automatically'
    mem=int(next(line for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')).split()[1])/1024**2
    assert mem>=80, f'MemAvailable {mem:.2f} GiB <80GiB'
    runner=out/Path(__file__).name
    shutil.copy2(Path(__file__),runner)
    root=Path(__file__).resolve().parents[2]
    audit=root/'hardware/scripts/run_reduction_audit.py'
    comparator=root/'hardware/scripts'/('compare_production_shared_runs.py'
        if prepared.get('comparison_mode')=='report_cycle_differences' else 'compare_ordered_add_runs.py')
    extra={str(runner):sha(runner),str(audit):sha(audit),str(comparator):sha(comparator)}
    expected={**prepared['dependencies'],**prepared['frozen_files'],**extra}
    def verify():
        for path,digest in expected.items():
            assert sha(Path(path))==digest,'Frozen input changed: '+path
    verify()
    lock=threading.Lock()
    status={'state':'RUNNING','driver_pid':os.getpid(),'driver_proc_stat':Path('/proc/self/stat').read_text(),
            'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'mem_available_gib':mem,'extra_dependencies':extra,'candidates':{}}
    def save():
        with lock:
            tmp=statusfile.with_suffix('.tmp')
            tmp.write_text(json.dumps(status,indent=2)+'\n');tmp.replace(statusfile)
    def execute(entry,stage,cmd,cwd,logpath):
        verify()
        entry[stage]={'state':'STARTING','command':cmd,'cwd':str(cwd),'log':str(logpath)}
        save()
        with logpath.open('w') as log:
            process=subprocess.Popen(cmd,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            identity=Path(f'/proc/{process.pid}/stat')
            entry[stage].update(state='RUNNING',pid=process.pid,pgid=os.getpgid(process.pid),
                                proc_stat=identity.read_text() if identity.exists() else None,
                                started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            save()
            rc=process.wait()
        text=logpath.read_text(errors='replace')
        errors=re.findall(r'^.*(?:Error-|Error:|Fatal:|FAILED|\bFAIL\b|started at .*failed at|watchdog_timeout: 1).*$',text,re.M)
        passed=rc==0 and not errors
        entry[stage].update(state='COMPLETE' if passed else 'FAILED',returncode=rc,errors=errors,
                            log_sha256=sha(logpath),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        save()
        assert passed,f'{stage} failed; preserved {logpath}'
    def candidate(mode,data):
        entry=status['candidates'][mode]={'state':'RUNNING'};save()
        directory=Path(data['cwd'])
        try:
            execute(entry,'compile',data['compile_command'],directory,directory/'compile.stdout.log')
            assert (directory/'simv').is_file(),'Compiler did not produce simulator'
            entry['simulator_sha256']=sha(directory/'simv');save()
            execute(entry,'audit',data['audit_command'],root,directory/'audit.log')
            report=json.loads((directory/'regression/manifest.json').read_text())
            assert report['state']=='COMPLETE' and len(report['tests'])==len(prepared['apps'])
            assert all(test['pass'] for test in report['tests'])
            entry['state']='COMPLETE';save()
        except Exception as exc:
            entry.update(state='FAILED',error=repr(exc));save();raise
    save()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(candidate,mode,data) for mode,data in prepared['candidates'].items()]
        failures=[]
        for job in jobs:
            try: job.result()
            except Exception as exc: failures.append(repr(exc))
    if failures:
        status.update(state='FAILED',errors=failures);save();raise SystemExit(1)
    baseline=Path(prepared['baseline'])
    status['state']='WAITING_FOR_BASELINE_COMPLETE';save()
    while True:
        try: report=json.loads((baseline/'regression/manifest.json').read_text())
        except (FileNotFoundError,json.JSONDecodeError): report={}
        if report.get('state')=='COMPLETE': break
        time.sleep(10)
    for mode in prepared['candidates']:
        entry=status['candidates'][mode]
        comparison=out/('compare_'+mode);comparison.mkdir()
        (comparison/'baseline').symlink_to(baseline,target_is_directory=True)
        (comparison/'scalar').symlink_to(out/mode,target_is_directory=True)
        (comparison/'configuration.json').write_text(json.dumps({'apps':prepared['apps']},indent=2)+'\n')
        try:
            execute(entry,'comparison',[sys.executable,str(comparator),str(comparison)],root,comparison/'console.log')
        except Exception as exc:
            status.update(state='FAILED',error=repr(exc));save();raise
    verify()
    status['state']='COMPLETE';save()


if __name__=='__main__':
    main()
