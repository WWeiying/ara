#!/usr/bin/env python3
"""One startup identity/progress observation; no retry or terminal polling."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
OUT = HERE/'prepared01'
UNIT = 'ara-negative-stride-remaining38-m6-01.service'


def need(ok,message):
    if not ok:raise ValueError(message)


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def sample(path):
    with path.open('rb') as f:
        f.seek(0,2);size=f.tell();start=max(0,size-65536);f.seek(start)
        raw=f.read().split(b'\n')
    rows=raw[1:-1] if start else raw[:-1]
    decoded=[r for line in rows for r in csv.reader([line.decode()]) if len(r)==14 and r[0].isdigit()]
    retires=[r for r in decoded if r[1]=='retire']
    need(decoded and retires,'No complete retired startup rows in bounded tail')
    return dict(bytes=size,cycle=int(decoded[-1][0]),retire_order=int(retires[-1][2]))


if __name__=='__main__':
    result=dict(status='STARTUP_NOT_CONFIRMED',DUT_accepted=False,observation=time.time())
    try:
        plan=read(OUT/'plan.json');digest=sha(OUT/'plan.json')
        need(digest=='cf1358b4511d3c40e15ba0368cd025e0d89bc8e4bebcc5320ab6e54f84330974','Plan identity')
        query=subprocess.run(['systemctl','--user','show',UNIT,
                              '--property=Id,ActiveState,SubState,MainPID,ControlGroup'],text=True,capture_output=True,timeout=10)
        result['service_query']=dict(returncode=query.returncode,stdout=query.stdout,stderr=query.stderr)
        need(query.returncode==0,'Service query')
        props=dict(x.split('=',1) for x in query.stdout.splitlines())
        need(props['Id']==UNIT and props['ActiveState']=='active' and props['SubState']=='running' and
             int(props['MainPID'])>0,'Actual direct worker not running')
        launch=read(OUT/'launch.json')
        need(launch['plan_sha256']==digest and launch['owner']['pid']==int(props['MainPID']),'Admission/worker identity')
        cgroup=props['ControlGroup']
        pids=[int(p) for p in (Path('/sys/fs/cgroup')/cgroup.lstrip('/')/'cgroup.procs').read_text().split()]
        wanted={x['id']:x for x in plan['cases'][:2]}
        evidence=[]
        for pid in pids:
            proc=Path('/proc')/str(pid)
            if (proc/'comm').read_text().strip()!='simv':continue
            argv=(proc/'cmdline').read_bytes().decode().strip('\0').split('\0')
            name=next((x.split('=',1)[1] for x in argv if x.startswith('+TESTCASE=')),None)
            need(name in wanted,'Unexpected owned simv testcase')
            root=OUT/'replay/tests'/name
            image=read(root/'inputs.json')['simv']
            need(str((proc/'exe').resolve())==str(Path(image['path']).resolve()) and
                 Path(image['path']).is_relative_to(Path(plan['image'])),'Actual executable not pinned M6')
            need('+PRELOAD='+str(root/'input.elf') in argv and '+NO_FSDB' in argv and
                 '+COMMIT_TRACE='+str(root/'commit_trace.csv') in argv and
                 str((proc/'cwd').resolve())==str(root/'work'),'Actual private paths/flags')
            need(sha(root/'input.elf')==wanted[name]['sha256'],'Actual private ELF hash')
            evidence.append(dict(pid=pid,name=name,exe=str((proc/'exe').resolve()),argv=argv,
                                 private_elf_sha256=sha(root/'input.elf'),sample1=sample(root/'commit_trace.csv')))
        need(len(evidence)==2 and {x['name'] for x in evidence}==set(wanted),'Exactly two original first groups')
        time.sleep(2)
        for e in evidence:
            e['sample2']=sample(OUT/'replay/tests'/e['name']/'commit_trace.csv')
            need(e['sample2']['cycle']>e['sample1']['cycle'] and
                 e['sample2']['retire_order']>e['sample1']['retire_order'],'No startup retirement progress')
        result.update(status='ACTUAL_TWO_SIMV_STARTUP_CONFIRMED_NOT_PASS',worker_pid=int(props['MainPID']),
                      cgroup=cgroup,simulators=evidence,plan_sha256=digest,admission=launch['resources'])
    except Exception as e:
        result['error']=f'{type(e).__name__}: {e}'
    with (OUT/'startup_confirmation.json').open('x') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('admission','service_query')}))
    raise SystemExit(int(result['status']=='STARTUP_NOT_CONFIRMED'))
