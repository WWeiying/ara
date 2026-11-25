#!/usr/bin/env python3
"""One-shot successor of chain.py: require campaign PASS AND exited owner PASS.

A vanished unit is not success evidence. If systemd has unloaded it, admission
still requires pinned PASS receipts, the immutable owner attempt and its dead
PID. Query errors other than an explicitly unloaded unit are fatal.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def save(path,value):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2)+'\n'); tmp.replace(path)


def verify(pins):
    for path,expected in pins.items():
        if sha(path)!=expected:
            raise ValueError('Frozen owner-chain input drift: '+path)


def bind(pins,path):
    path=str(Path(path).resolve()); value=sha(path)
    if path in pins and pins[path]!=value:
        raise ValueError('Conflicting/drifted dependency: '+path)
    pins[path]=value
    return value


def inventory(pins,directory):
    path=directory/'source-pins.json'; bind(pins,path)
    for name,value in json.loads(path.read_text()).items():
        if name in pins and pins[name]!=value:
            raise ValueError('Conflicting owner/source identity: '+name)
        pins[name]=value


def pid_alive(pid):
    if not Path('/proc/'+str(pid)).exists():
        return False
    try:
        os.kill(pid,0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def service_state(unit):
    result=subprocess.run(['systemctl','--user','show',unit,
        '-p','LoadState','-p','ActiveState','-p','MainPID','-p','ExecMainPID',
        '-p','Result','-p','ExecMainStatus'],stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,timeout=30)
    fields=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if fields.get('LoadState')=='not-found':
        return dict(available=False)
    if result.returncode or not {'LoadState','ActiveState','MainPID','Result','ExecMainStatus'}<=fields.keys():
        raise ValueError('Cannot establish prerequisite service state: '+unit)
    return dict(fields,available=True)


def owner_ready(plan):
    owner=Path(plan['owner_output']); prior=Path(plan['prerequisite'])
    unit=service_state(plan['unit'])
    receipt=json.loads((owner/'result.json').read_text()) if (owner/'result.json').exists() else None
    campaign=json.loads((prior/'result.json').read_text()) if (prior/'result.json').exists() else None
    if receipt is not None and receipt.get('state')!='PASS':
        raise ValueError('Prerequisite owner failed; successor not dispatched')
    if campaign is not None and (campaign.get('state')!='PASS' or
                                  campaign.get('post_source_image_pins_match') is not True):
        raise ValueError('Prerequisite campaign not accepted')
    active=unit.get('ActiveState') in ('active','activating','reloading','deactivating')
    attempt=owner/'attempt.json'
    if not attempt.exists():
        if active:
            return None
        raise ValueError('Owner stopped/missing without an attempt receipt')
    pid=json.loads(attempt.read_text()).get('owner_pid')
    if type(pid) is not int or pid<=1:
        raise ValueError('Invalid owner-attempt MainPID')
    if unit['available']:
        main=int(unit['MainPID'])
        recorded=int(unit.get('ExecMainPID','0'))
        if main not in (0,pid) or recorded not in (0,pid):
            raise ValueError('Owner service PID changed; no restart allowed')
        if unit['ActiveState']=='failed' or (not active and
                (unit['Result']!='success' or unit['ExecMainStatus']!='0')):
            raise ValueError('Prerequisite service failed')
        if not active and unit['ActiveState']!='inactive':
            raise ValueError('Unknown prerequisite service terminal state')
    live=pid_alive(pid)
    if active or live:
        return None
    if receipt is None or campaign is None:
        raise ValueError('Owner exited without both final PASS receipts')
    if receipt.get('post_source_image_pins_match') is False:
        raise ValueError('Owner reported a failed source/image audit')
    return dict(owner_pid=pid,service=unit,
        exit_evidence='attempt PID exited; owner and campaign PASS; service success if queryable')


def wait_owner(plan,pins,out):
    save(out/'status.json',dict(state='WAITING_FOR_OWNER',campaign=plan['prerequisite'],
                               owner_output=plan['owner_output'],unit=plan['unit']))
    deadline=time.monotonic()+86400
    while True:
        observation=owner_ready(plan)
        if observation is not None:
            owner=Path(plan['owner_output']); prior=Path(plan['prerequisite'])
            for directory in (owner,prior):
                inventory(pins,directory)
                bind(pins,directory/'result.json')
            bind(pins,owner/'attempt.json')
            receipt=json.loads((owner/'result.json').read_text())
            completed=receipt.get('completed',[])
            if 'campaign' in receipt:
                if Path(receipt['campaign']).resolve()!=prior.resolve():
                    raise ValueError('Owner PASS belongs to a different campaign')
            elif not completed or Path(completed[-1]['campaign']).resolve()!=prior.resolve() or \
                    completed[-1]['result_sha256']!=sha(prior/'result.json'):
                raise ValueError('Owner PASS does not bind this final campaign result')
            for name,value in receipt.get('dependency_pins',{}).items():
                if name in pins and pins[name]!=value:
                    raise ValueError('Owner dependency receipt identity conflict: '+name)
                pins[name]=value
            if 'source_pins_sha256' in receipt and receipt['source_pins_sha256']!=sha(owner/'source-pins.json'):
                raise ValueError('Owner receipt/inventory identity mismatch')
            if 'attempt_sha256' in receipt and receipt['attempt_sha256']!=sha(owner/'attempt.json'):
                raise ValueError('Owner receipt/attempt identity mismatch')
            verify(pins)
            if owner_ready(plan) is not None:
                return observation
        if time.monotonic()>deadline:
            raise TimeoutError('Owner wait expired; no restart')
        time.sleep(60)


def prepare(a,out):
    if out.exists() or not all((a.prerequisite,a.unit,a.owner_output,a.soc,a.manifest,a.campaign)):
        raise ValueError('Fresh complete owner-chain description required')
    if a.campaign.resolve().exists():
        raise ValueError('Successor campaign already exists; never prepare/retry it')
    pins={}
    owner=a.owner_output.resolve()
    inventory(pins,owner)
    prior=a.prerequisite.resolve()
    if (prior/'source-pins.json').exists():
        inventory(pins,prior)
    bind(pins,a.manifest)
    for c in json.loads(a.manifest.read_text())['cases']:
        path=Path(c['source_pins'])
        # Some manifests deliberately use runner-source-pins.json.
        bind(pins,path)
        for name,value in json.loads(path.read_text()).items():
            if name in pins and pins[name]!=value:
                raise ValueError('Conflicting successor identity: '+name)
            pins[name]=value
        if sha(c['elf'])!=c['elf_sha256']:
            raise ValueError('Successor ELF identity mismatch')
        bind(pins,c['elf'])
    inventory(pins,a.soc.resolve())
    build=json.loads((a.soc/'build.json').read_text())
    bind(pins,a.soc/'build.json')
    for name,value in build['image_pins'].items():
        if name in pins and pins[name]!=value:
            raise ValueError('Conflicting successor image identity')
        pins[name]=value
    verify(pins)
    out.mkdir(); (out/'inputs').mkdir()
    for name in ('chain_owner_v3.py','campaign.py','collect.py','monitor_metrics.py','test_chain_owner_v3.py'):
        target=out/'inputs'/name
        shutil.copyfile(Path(__file__).with_name(name),target); bind(pins,target)
    plan=dict(prerequisite=str(prior),owner_output=str(owner),unit=a.unit,
        soc=str(a.soc.resolve()),manifest=str(a.manifest.resolve()),campaign=str(a.campaign.resolve()),
        parallel=4,automatic_retry=False)
    save(out/'plan.json',plan); bind(pins,out/'plan.json')
    verify(pins); save(out/'source-pins.json',pins)
    save(out/'status.json',dict(state='PREPARED_NOT_RUN'))


def execute(out):
    if Path(__file__).resolve()!=out/'inputs/chain_owner_v3.py':
        raise ValueError('Only the frozen one-shot owner-chain can execute')
    with (out/'attempt.json').open('x') as stream:
        stream.write(json.dumps(dict(owner_pid=os.getpid(),started=time.time()))+'\n')
    result=dict(state='FAIL',automatic_retry=False,post_source_image_pins_match=False)
    pins={}
    try:
        source=out/'source-pins.json'
        pins=json.loads(source.read_text()); bind(pins,source); bind(pins,out/'attempt.json')
        if pins.get(str(Path(__file__).resolve()))!=sha(__file__):
            raise ValueError('Worker is not pinned')
        verify(pins)
        plan=json.loads((out/'plan.json').read_text())
        result['owner_gate']=wait_owner(plan,pins,out)
        prior=Path(plan['prerequisite'])
        subprocess.run([sys.executable,'-B',str(out/'inputs/collect.py'),'--campaign',str(prior),
            '--output',str(out/'prerequisite-report')],check=True,timeout=1200)
        verify(pins)
        if owner_ready(plan) is None:
            raise ValueError('Owner resumed after admission; successor not dispatched')
        campaign=Path(plan['campaign'])
        if campaign.exists():
            raise ValueError('Successor already exists; never reprepare or retry')
        save(out/'status.json',dict(state='PREPARING_SUCCESSOR',campaign=str(campaign)))
        subprocess.run([sys.executable,'-B',str(out/'inputs/campaign.py'),'prepare',
            '--soc',plan['soc'],'--manifest',plan['manifest'],'--output',str(campaign),
            '--parallel',str(plan['parallel'])],check=True,timeout=1200)
        inventory(pins,campaign); verify(pins)
        save(out/'status.json',dict(state='SUCCESSOR_EXECUTING',campaign=str(campaign)))
        with (out/'campaign.stdout.log').open('x') as stream:
            completed=subprocess.run([sys.executable,'-B','-u',str(campaign/'inputs/campaign.py'),
                'execute','--output',str(campaign)],stdout=stream,stderr=subprocess.STDOUT)
        verify(pins)
        final=json.loads((campaign/'result.json').read_text()); bind(pins,campaign/'result.json')
        if final.get('post_source_image_pins_match') is True:
            subprocess.run([sys.executable,'-B',str(out/'inputs/collect.py'),'--campaign',str(campaign),
                '--output',str(out/'successor-report')],check=True,timeout=1200)
        if completed.returncode or final['state']!='PASS' or final.get('post_source_image_pins_match') is not True:
            raise ValueError('Successor incomplete; original numerical evidence retained, no retry')
        verify(pins)
        result.update(state='PASS',cases=len(final['cases']),campaign=str(campaign))
    except Exception as exc:
        result['error']=repr(exc)
    try:
        verify(pins)
        result['post_source_image_pins_match']=True
    except Exception as exc:
        result.update(state='FAIL',post_source_image_pins_match=False,pin_error=repr(exc))
    result.update(source_pins=str(out/'source-pins.json'),source_pins_sha256=sha(out/'source-pins.json'),
        attempt_sha256=sha(out/'attempt.json'),dependency_pins={p:h for p,h in pins.items()
            if Path(p).name in ('attempt.json','result.json','source-pins.json')})
    # Publish the final receipt last; a failed status write cannot leave a PASS receipt.
    save(out/'status.json',result); save(out/'result.json',result)
    print(json.dumps(result),flush=True)
    return result['state']!='PASS'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',nargs='?',choices=('prepare','execute'))
    p.add_argument('--prepare',action='store_true',help='Alias for the prepare action; never executes a worker')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prerequisite',type=Path)
    p.add_argument('--owner-output',type=Path)
    p.add_argument('--unit')
    p.add_argument('--soc',type=Path)
    p.add_argument('--manifest',type=Path)
    p.add_argument('--campaign',type=Path)
    a=p.parse_args(argv)
    if a.prepare:
        if a.action is not None:
            p.error('Use either --prepare or the prepare action')
        a.action='prepare'
    if a.action is None:
        p.error('prepare or execute action required')
    out=a.output.resolve()
    if a.action=='prepare':
        prepare(a,out); return 0
    return execute(out)


if __name__=='__main__':
    raise SystemExit(main())
