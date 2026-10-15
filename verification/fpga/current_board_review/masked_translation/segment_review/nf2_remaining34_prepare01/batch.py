#!/usr/bin/env python3
"""Shared software builder and one-attempt bounded reference per group; no DUT."""
import argparse
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import difflib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode=True
from scope import HERE,PRIOR,read,save,sha,require,verify,inventory
import model
import reference_core as core
base=model.base
ISA='rv64gcv_zfh_zvfh_zvl1024b'
LIMIT=3000000
TIMEOUT=120
RAW_LIMIT=512*1024**2
STOP_EVENTS=(HERE/'STOP_DISPATCH.json',HERE.parent/'nf2_remaining4_terminal_audit01/wait01/firstfailure.json')

def stop_event():return next((str(p) for p in STOP_EVENTS if p.exists()),None)
def check_dispatch():require(not stop_event(),'Stop new dispatch: '+str(stop_event()))
def configure(group):
    require(read(HERE/'source_manifest.json')==inventory(),'Manifest/source identities drift')
    cfg=read(HERE/group/'group.json')
    require(cfg in read(HERE/'source_manifest.json')['groups'],'Unknown group')
    core.configure(cfg['cases']);return cfg
def header(cases):
    lines=['#define MX_N '+str(len(cases)),'static const struct config configs[MX_N] = {']
    for c in cases:lines.append('  {%d,%d,0x%x,%d,%d},'%(c['base'],c['store'],c['mask'],c['start'],c['unmapped']))
    return '\n'.join(lines+['};',''])
def symbols(elf,sizes=False):
    args=[base.CC.with_name('riscv64-unknown-elf-nm'),'-n']+(['-S'] if sizes else [])+[elf]
    text=subprocess.check_output([str(a) for a in args],text=True,timeout=15)
    if sizes:return {m[4]:int(m[2],16) for m in re.finditer(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+(\w)\s+(\S+)$',text,re.M)}
    return {m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',text,re.M)}
def text_new(path,text):
    with path.open('x') as f:f.write(text)

def build_group(group):
    check_dispatch();cfg=configure(group);out=HERE/group/'reference02'
    require(not out.exists(),'No rebuild/overwrite of group')
    out.mkdir();p=out/'prepared';p.mkdir()
    parent=base.prepare.check(base.PARENT)
    for n in ('fixture.c','fixture.h','fixture.S'):shutil.copyfile(HERE/n,p/n)
    text_new(p/'group_config.h',header(cfg['cases']))
    for n in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(base.PARENT/n,p/n)
    save(p/'provenance.json',dict(files={q.name:sha(q) for q in p.iterdir()},
        parent_runtime_sha256={n:parent['files'][n] for n in ('startup.S','runtime.c','replay.ld')},
        cases=[c['id'] for c in cfg['cases']],scope='Archived standalone Sv39 derivatives, not Linux/full parent'))
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
        '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
        '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
        '-Wl,--build-id=none','-Wl,--gc-sections','-T',p/'replay.ld']
    dimensions={k:len(cfg['cases'])*n for k,n in dict(mx_seed=640,mx_fault=640,mx_result=640,mx_out=260,
        mx_mask=16,mx_records=192,mx_post=40,mx_count=8,mx_marker=8,mx_case_checks=8).items()}
    elfs={};compiled={}
    for backend in ('soc','spike'):
        elf=out/(backend+'.elf')
        base.run_logged([base.CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
            *[p/n for n in ('fixture.c','fixture.S','startup.S','runtime.c')],'-lgcc','-o',elf],out/(backend+'.compile.log'))
        base.run_logged([base.CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],out/(backend+'.dis'))
        s=symbols(elf);sizes=symbols(elf,True)
        require(s['__bss_end']<0x800f0000,'ELF outside original L2 runtime')
        require(all(sizes.get(k)==v for k,v in dimensions.items()),'Actual MX_N array size mismatch')
        require(s['mx_guard_lo']+64==s['mx_pages'] and s['mx_guard_hi']==s['mx_pages']+20480,
                'Actual assembly-defined physical page guard addresses differ')
        text=(out/(backend+'.dis')).read_text()
        for label,code in (('mx_segment_load','20055c07'),('mx_segment_store','20055c27')):
            require(re.search(r'<'+label+r'>:\n\s*[0-9a-f]+:\s+'+code+r'\b',text),'Target byte identity')
        save(out/(backend+'.symbols.json'),s)
        compiled[backend]=dict(dimensions={k:sizes[k] for k in dimensions},bss_end=s['__bss_end'])
        elfs[backend]=dict(path=str(elf),sha256=sha(elf))
    n=len(cfg['cases']);refills=sum(c['unmapped'] for c in cfg['cases'])
    charges=dict(memory=2*n*4096*45,segment_path_extra=2*n*16*150,pte=2*n*512*45,
                 page_init=n*4096*12,refill=refills*2048*13,vector_oracle_init=n*1024*120,remaining=200000)
    require(sum(charges.values())<LIMIT,'Static budget insufficient: do not run')
    require(sha(HERE/'fixture.S')==sha(PRIOR/'fixture.S'),'Accepted assembly changed')
    files=[HERE/n for n in ('scope.py','source_manifest.json','batch.py','model.py','reference_core.py','csv_check.py','host.py','fixture.c','fixture.h','fixture.S')]
    files += [HERE/group/'group.json',Path(base.__file__),base.BASE/'prepare.py',base.CC.resolve(),base.SPIKE,
              base.ROOT/'verification/coverage/scoped_rv64c_memory.py',HERE/'STATIC_COST.md']
    files += [base.PARENT/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
    files += [PRIOR/n for n in ('fixture.c','fixture.h','fixture.S','oracle.py','reference.py','READY.json')]
    pins={**read(HERE/'source_manifest.json')['pins'],**{str(f):sha(f) for f in files}}
    pins.update({str(q):sha(q) for q in p.iterdir()})
    save(out/'input_pins.json',pins)
    save(out/'source_proof.json',dict(status='COMPILED_NOT_REFERENCE_OR_DUT',group=cfg,elfs=elfs,
        MX_N=n,compiled=compiled,counts=list(model.COUNTS),total_checks=model.TOTAL,
        mask_domain=dict(original_bytes=128,fixture_bytes=16,consumed_bytes=8),
        full_outputs_per_case=128,guards_per_case=2,memory_bytes_per_case=8192,
        original_linux_byte_identity=False,assembly_unchanged=True,
        fixture_delta=list(difflib.unified_diff((PRIOR/'fixture.c').read_text().splitlines(),
                                               (HERE/'fixture.c').read_text().splitlines()))))
    save(out/'bound.json',dict(admit_once=True,static_charges=charges,static_steps=sum(charges.values()),
        instructions=LIMIT,timeout_s=TIMEOUT,raw_bytes=RAW_LIMIT,isa=ISA,elfs=elfs,
        reference_only=True,automatic_retry=False))
    verify(pins);print('COMPILED',group,n,sum(charges.values()),flush=True)

def run_group(group):
    check_dispatch();cfg=configure(group);out=HERE/group/'reference02'
    host=read(HERE/'host01/status.json');require(host['status']=='PASS_HOST_ONLY','Shared Host gates incomplete')
    verify(host['pins'])
    pins=read(out/'input_pins.json');verify(pins)
    bound=read(out/'bound.json');proof=read(out/'source_proof.json')
    require(bound['admit_once'] and bound['instructions']==LIMIT and bound['timeout_s']==TIMEOUT and
            bound['raw_bytes']==RAW_LIMIT and bound['static_steps']<LIMIT,'Fixed reference bound')
    for e in proof['elfs'].values():require(sha(e['path'])==e['sha256'],'Compiled ELF drift')
    require(not (out/'reference_attempt.json').exists(),'At most one reference per ELF')
    cmd=[str(base.SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2',
         '--instructions='+str(LIMIT),'-l','--log-commits',str(out/'spike.elf')]
    save(out/'reference_attempt.json',dict(command=cmd,started=time.time(),bound_sha256=sha(out/'bound.json'),
        host_sha256=sha(HERE/'host01/status.json'),one_attempt=True))
    start=time.monotonic();rc=None
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(RAW_LIMIT,RAW_LIMIT))
    try:
        with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as stderr:
            child=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=TIMEOUT,preexec_fn=limit)
        rc=child.returncode;require(rc==0,'Reference numeric returncode '+str(rc))
        result=core.validate((out/'spike.trace').read_text(),read(out/'spike.symbols.json'))
        result.update(reference_elapsed_s=time.monotonic()-start,process_returncode=rc,isa=ISA,
                      raw_bytes=(out/'spike.trace').stat().st_size,raw_sha256=sha(out/'spike.trace'))
        verify(pins);save(out/'status.json',result)
        print('REFERENCE_PASS',group,result['commits'],result['checks'],flush=True)
    except BaseException as error:
        save(out/'not_completed.json',dict(status='NOT_ACCEPTED_NO_RETRY',returncode=rc,error=f'{type(error).__name__}: {error}'))
        raise

def references():
    require(not (HERE/'reference_batch.json').exists(),'No batch retry')
    groups=read(HERE/'source_manifest.json')['groups'];pending=iter(groups);results=[];stopped=None
    def job(group):
        p=HERE/group['id']/'reference_worker.log'
        with p.open('x') as f:
            proc=subprocess.run([sys.executable,'-B',str(Path(__file__)),'reference','--group',group['id']],
                stdout=f,stderr=subprocess.STDOUT,timeout=240)
        return dict(group=group['id'],returncode=proc.returncode)
    with ThreadPoolExecutor(max_workers=3) as pool:
        active={}
        def dispatch():
            nonlocal stopped
            event=stop_event()
            if event:stopped=event
            while not stopped and len(active)<3:
                g=next(pending,None)
                if g is None:break
                active[pool.submit(job,g)]=g['id']
        dispatch()
        while active:
            done,_=wait(active,return_when=FIRST_COMPLETED)
            for future in done:
                group=active.pop(future)
                try:r=future.result()
                except BaseException as error:r=dict(group=group,returncode=None,error=str(error))
                results.append(r);print(json.dumps(r),flush=True)
                if r['returncode']!=0:stopped='REFERENCE_FAILURE:'+group
            dispatch()
    save(HERE/'reference_batch.json',dict(status='PASS_REFERENCE9_NOT_DUT' if len(results)==9 and not stopped else 'STOPPED_NOT_FULL_PASS',
        results=results,stop_reason=stopped,max_parallel=3,no_retry=True,not_dispatched=[g['id'] for g in groups if g['id'] not in {r['group'] for r in results}]))
    require(len(results)==9 and not stopped,'Batch stopped; retained all attempted raw evidence')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','build-all','reference','references']);p.add_argument('--group')
    args=p.parse_args()
    if args.mode=='references':references()
    elif args.mode=='build-all':
        for g in read(HERE/'source_manifest.json')['groups']:build_group(g['id'])
    else:
        require(args.group in {g['id'] for g in read(HERE/'source_manifest.json')['groups']},'Exact group required')
        (build_group if args.mode=='build' else run_group)(args.group)
