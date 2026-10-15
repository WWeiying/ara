"""One bounded, filesystem-event-driven startup confirmation; no progress polling."""
import argparse
import csv
import os
from pathlib import Path
import select
import subprocess
import time
import vcs_adapter as a
from support import read,save

def confirm(out,unit):
    events=a.live_tail.DirectoryEvents(out)
    streams={}; pending={}; observed={}
    deadline=time.monotonic()+180
    try:
        while True:
            for trial in a.TRIALS[:2]:
                path=out/'cases'/f'trial{trial:02d}'/'run/tests'/a.name(trial)/'commit_trace.csv'
                if trial not in streams and path.exists():
                    streams[trial]=path.open(); pending[trial]=''
                if trial not in streams: continue
                lines=(pending[trial]+streams[trial].read()).split('\n'); pending[trial]=lines.pop()
                for line in lines:
                    values=next(csv.reader([line]))
                    if values==a.csv_oracle.FIELDS: continue
                    if len(values)!=len(a.csv_oracle.FIELDS): raise ValueError('Malformed startup CSV')
                    row=dict(zip(a.csv_oracle.FIELDS,values))
                    if row['event']=='retire': observed[trial]=row
            if len(observed)==2 and all(int(r['order'])>=100 for r in observed.values()): break
            if (out/'complete.json').exists(): raise ValueError('Service completed before live confirmation')
            remaining=deadline-time.monotonic()
            if remaining<=0: raise ValueError('Bounded startup confirmation expired; no retry')
            if select.select([events.fd],[],[],remaining)[0]: events.drain()
        state=dict(line.split('=',1) for line in subprocess.check_output(
            ['systemctl','--user','show',unit,'-p','ActiveState','-p','MainPID','-p','ControlGroup','-p','RuntimeMaxUSec'],
            text=True,timeout=10).splitlines())
        a.require(state['ActiveState']=='active' and state['MainPID']!='0','Unit not live')
        root=Path('/sys/fs/cgroup')/state['ControlGroup'].lstrip('/')
        pids={int(p) for path in [root/'cgroup.procs',*root.rglob('cgroup.procs')] for p in path.read_text().split()}
        processes=[]
        for pid in sorted(pids):
            proc=Path('/proc')/str(pid)
            try:
                if (proc/'comm').read_text().strip()!='simv': continue
                exe=(proc/'exe').resolve(strict=True); cwd=(proc/'cwd').resolve(strict=True)
                argv=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
            except (FileNotFoundError,ProcessLookupError): continue
            a.require(exe==a.IMAGE/'_build/vcs/simv','Owned simv uses wrong image')
            a.require(cwd.is_relative_to(out),'Owned simv outside run directory')
            processes.append(dict(pid=pid,exe=str(exe),cwd=str(cwd),argv=argv))
        a.require(len(processes)==2,'Expected two actual owned simv processes')
        plan=read(out/'plan.json'); a.require(a.sha(a.IMAGE/'image.json')==plan['image_sha256'],'Startup image drift')
        result=dict(status='LIVE_CONFIRMED_ONCE_NOT_PASS',unit=unit,state=state,simv=processes,
                    retiring_rows=observed,observed_unix=time.time(),further_polling=False)
        save(out/'startup_observation.json',result)
        print('LIVE_CONFIRMED_ONCE_NOT_PASS',[(p['pid'],p['cwd']) for p in processes],flush=True)
        print('rows',[(t,r['cycle'],r['order'],r['pc']) for t,r in observed.items()],flush=True)
    finally:
        for stream in streams.values(): stream.close()
        events.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True); p.add_argument('--unit',required=True)
    args=p.parse_args(); confirm(args.out.resolve(),args.unit)
