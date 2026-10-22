#!/usr/bin/env python3
"""Owned NF2 four-case reference, one bounded Spike execution and no DUT."""
import argparse
import difflib
import json
import re
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode=True
from oracle import *
from scope import provenance,sha,RUNTIME_ID
ISA='rv64gcv_zfh_zvfh_zvl1024b'
PRIOR=HERE.parent/'sv39'
OUT=HERE/'reference01'
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def symbols(elf):
    text=subprocess.check_output([str(base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True)
    return {m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',text,re.M)}
def pincheck(pins):
    for p,h in pins.items():require(sha(p)==h,'Input drift '+p)

def validate(trace,s):
    memory,regs,points,exits={}, {0:0}, [], []
    actions=[[] for _ in range(4)]
    events=[[] for _ in range(4)]
    commits=0
    for line in trace.splitlines():
        m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
        if not m: continue
        mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4]
        commits+=1
        base.require(pc!=s['trap_entry'],'Default trap handler executed')
        c=readint(memory,s['mx_current'])
        access=[(int(a,16),int(v,16) if v else None)
                for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if pc in (s['mx_segment_load'],s['mx_segment_store']):
            base.require(c<4 and pc==s[SITE[c]] and mode==1,'Wrong target or privilege')
            base.require(insn==(0x20055c27 if CASES[c]['store'] else 0x20055c07),'Original NF2 masked opcode differs')
            actions[c].append('target')
            events[c].append(dict(opcode=hex(insn),access=access))
        if pc==s['mx_younger_store']:
            base.require(mode==1,'Younger store not S-mode'); actions[c].append('younger')
        if pc==s['mx_repair_sfence']:
            base.require(mode==3 and regs.get((insn>>15)&31)==VA+4096,'Wrong repair SFENCE')
            actions[c].append('repair_sfence')
        if pc==s['mx_trap_mret'] and readint(memory,s['mx_marker']+8*c)==0:
            actions[c].append('retry_mret')
        if pc==s['mx_refill_page']: actions[c].append('refill')
        if pc==s['mx_cleanup_sfence']:
            base.require(mode==3 and regs.get((insn>>15)&31)==VA+4096,'Wrong cleanup SFENCE')
            actions[c].append('cleanup_sfence')
        if pc==s['mx_checkpoint']:
            phase=readint(memory,s['mx_phase'])
            checked=compare(memory,s,c,phase)
            points.append(dict(id=c,name=NAMES[c],phase=phase,checked_bytes=checked,commit=commits))
            actions[c].append({1:'fault_checkpoint',2:'final_checkpoint',3:'precleanup_checkpoint'}[phase])
        for a,v in access:
            if v is None: continue
            opcode,funct=insn&127,(insn>>12)&7
            if insn&3!=3:
                d=base.compressed_memory(insn)
                base.require(d is not None and d['kind']=='write','Unknown compressed store')
                width=d['size']
                base.require(a==(regs.get(d['base'],-1)+d['offset'])&((1<<64)-1),'Compressed address differs')
            else:
                base.require(opcode in (0x23,0x27),'Unknown store opcode')
                width=(1<<funct) if opcode==0x23 else {0:1,5:2,6:4,7:8}[funct]
            physical=s['mx_pages']+a-VA if VA<=a<VA+8192 else a
            for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')): memory[physical+i]=b
            if a==s['tohost']: exits.append(v)
        regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
    traps=re.findall(r'exception\s+(\w+), epc 0x([0-9a-f]+)',trace)
    wanted_traps=[]
    for c in range(4):
        if CASES[c]['fault']:
            wanted_traps.append(('trap_store_page_fault' if CASES[c]['store'] else 'trap_load_page_fault','%016x'%s[SITE[c]]))
        wanted_traps.append(('trap_supervisor_ecall','%016x'%s['mx_ecall']))
        if CASES[c]['fault']:
            order=['target','fault_checkpoint','repair_sfence']
            if CASES[c]['unmapped']:order+=['refill']
            order+=['retry_mret','target','younger','final_checkpoint']
        else:
            order=['target','younger','precleanup_checkpoint','cleanup_sfence']
            if CASES[c]['unmapped']:order+=['refill']
            order+=['final_checkpoint']
        base.require(actions[c]==order,'Exact fault/nofault/cleanup order differs: '+str((c,actions[c])))
        base.require(len(events[c])==1+int(CASES[c]['fault']),'Attempt/retry count differs')
        def accesses(indices):
            return [(VA+OFF[c]+4*i+2*f,seed(c,f+1,i) if CASES[c]['store'] else None)
                    for i in indices for f in (0,1)]
        if CASES[c]['fault']:
            before=[i for i in range(CASES[c]['start']) if active(c,i)]
            after=[i for i in range(CASES[c]['start'],8) if active(c,i)]
            base.require(events[c][0]['access']==accesses(before),'Fault-attempt access list differs')
            base.require(events[c][1]['access']==accesses(after),'Restart access list differs')
        else:base.require(events[c][0]['access']==[],'Alloff target performed memory access')
    base.require(traps==wanted_traps,'Exception ledger differs '+str(traps))
    base.require([(x['id'],x['phase']) for x in points]==[(c,p) for c in range(4) for p in phases(c)],'Checkpoint coverage differs')
    base.require(exits==[1] and readint(memory,s['mx_errors'])==0 and readint(memory,s['mx_unexpected'])==0,'Software failure')
    base.require(readint(memory,s['mx_completed'])==DONE,'Missing completion magic')
    base.require(commits<3000000,'Reference instruction bound exceeded')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',cases=list(NAMES),checkpoints=points,
                checks=readint(memory,s['mx_checks']),case_checks=[readint(memory,s['mx_case_checks']+8*c) for c in range(4)],
                commits=commits,traps=traps,actions=actions,target_events=events,
                VCS_launched=False,Linux_launched=False)


def negative_oracle(s):
    def synthetic(c,p):
        memory,choices=expected(s,c,p)
        for a,n,values in choices:
            for i,b in enumerate(values[0].to_bytes(n,'little')):memory[a+i]=b
        for n in range(record_count(c,p)):
            for i,b in enumerate((0x800).to_bytes(8,'little')):
                memory[s['mx_records']+192*c+96*n+24+i]=b
        compare(memory,s,c,p)
        return memory
    tests=[]
    for c in range(4):
        for p in phases(c):
            synthetic(c,p)
    mutations=[
        (0,1,'wrong_start',s['mx_records']+56),
        (0,1,'inactive_prefix',s['mx_fault']+64+128+2),
        (0,2,'field1_tail',s['mx_out']+2+128+126),
        (0,2,'neighbor',s['mx_result']+64),
        (1,2,'prefix_field0_poison',s['mx_pages']+OFF[1]+8),
        (1,2,'prefix_field1_poison',s['mx_pages']+OFF[1]+10),
        (1,2,'refill_page_word',s['mx_pages']+8000),
        (2,3,'alloff_store_before_cleanup',s['mx_pages']+OFF[2]),
        (2,2,'alloff_field1_result',s['mx_result']+640*2+64+256),
        (2,2,'extra_fault_record',s['mx_records']+192*2+96),
        (3,3,'unmapped_before_refill',s['mx_pages']+4096),
        (3,3,'premature_mapping',s['mx_pages']+16392),
        (3,2,'post_vstart',s['mx_post']+120+16),
        (3,2,'output_guard',s['mx_out']+780+258),
        (3,2,'pte_neighbor',s['mx_pages']+16384+16),
        (3,2,'mask',s['mx_mask']+48),
    ]
    for c,p,name,a in mutations:
        memory=synthetic(c,p);memory[a]^=1
        try:compare(memory,s,c,p)
        except ValueError:tests.append(dict(name=name,rejected=True));continue
        raise ValueError('Negative oracle accepted '+name)
    memory=synthetic(0,1)
    for r in (1,2):
        for i,b in enumerate(vg(0,2,r,2).to_bytes(2,'little')):
            memory[s['mx_fault']+64+128*r+4+i]=b
    compare(memory,s,0,1)
    return dict(positive_checkpoints=8,rejected=tests,allowed_fault_segment_snapshot=True)


def build():
    require(not OUT.exists(),'Fresh reference preparation only')
    source=provenance()
    require(source==json.loads((HERE/'source_manifest.json').read_text()),'Selected identities drift')
    parent=base.prepare.check(base.PARENT)
    pins=dict(source['pins'])
    files=[HERE/n for n in ('scope.py','source_manifest.json','fixture.h','fixture.c','fixture.S','oracle.py','reference.py')]
    files += [PRIOR/n for n in ('fixture.c','fixture.h','fixture.S','reference.py','csv_check.py','reference01/status.json')]
    files += [base.PARENT/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
    files += [Path(base.__file__),base.BASE/'prepare.py',base.CC.resolve(),base.SPIKE,
              base.ROOT/'verification/coverage/scoped_rv64c_memory.py']
    pins.update({str(p):sha(p) for p in files});pincheck(pins)
    OUT.mkdir();p=OUT/'prepared';p.mkdir()
    for n in ('fixture.c','fixture.S','fixture.h'):shutil.copyfile(HERE/n,p/n)
    for n in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(base.PARENT/n,p/n)
    save(p/'provenance.json',dict(files={q.name:sha(q) for q in p.iterdir()},
        parent_runtime_sha256={n:parent['files'][n] for n in ('startup.S','runtime.c','replay.ld')},
        cases=list(NAMES),scope='Four archived NF2 failure derivatives; not Linux replay'))
    save(OUT/'input_pins.json',pins)
    base.run_logged(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DMX_HOST',p/'fixture.c','-o',OUT/'host'],OUT/'host.compile.log')
    base.run_logged([OUT/'host'],OUT/'host.stdout')
    host_rows=check_host((OUT/'host.stdout').read_text())
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
           '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
           '-Wl,--build-id=none','-Wl,--gc-sections','-T',p/'replay.ld']
    for backend in ('soc','spike'):
        elf=OUT/(backend+'.elf')
        base.run_logged([base.CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                        *[p/n for n in ('fixture.c','fixture.S','startup.S','runtime.c')],'-lgcc','-o',elf],OUT/(backend+'.compile.log'))
        base.run_logged([base.CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],OUT/(backend+'.dis'))
        syms=symbols(elf);require(syms['__bss_end']<0x800f0000,'ELF exceeds original runtime memory')
        save(OUT/(backend+'.symbols.json'),syms)
    neg=negative_oracle(json.loads((OUT/'spike.symbols.json').read_text()))
    save(OUT/'host.json',dict(status='PASS_HOST_ONLY',oracle_rows=host_rows,negative=neg))
    require(sha(HERE/'fixture.S')==sha(PRIOR/'fixture.S'),'Established assembly changed')
    proof=dict(status='COMPILED_SOURCE_DERIVATIVE_NOT_REFERENCE_OR_DUT',cases=source['cases'],
        pins=pins,isa=ISA,elf_sha256={b:sha(OUT/(b+'.elf')) for b in ('soc','spike')},
        assembly_unchanged_from_prior_sv39=True,original_target_encodings=['20055c07','20055c27'],
        original_mask_allocation_bytes=128,fixture_mask_allocation_bytes=16,helper_consumed_mask_bytes=8,
        original_linux_byte_identity=False,full_oracle=dict(output_halfwords=128,guards=2,memory_bytes=8192),
        nofault_precleanup_memory_check=True,reference_launched=False)
    for b in ('soc','spike'):
        dis=(OUT/(b+'.dis')).read_text()
        for label,encoding in (('mx_segment_load','20055c07'),('mx_segment_store','20055c27')):
            require(re.search(r'<'+label+r'>:\n\s*[0-9a-f]+:\s+'+encoding+r'\b',dis), 'Actual segment opcode drift')
    save(OUT/'source_proof.json',proof)
    pincheck(pins)
    print('COMPILED_HOST_PASS_REFERENCE_NOT_RUN',host_rows)


def run():
    require((OUT/'bound.json').is_file(),'Static cost admission required before unique reference')
    bound=json.loads((OUT/'bound.json').read_text())
    require(bound['admit_once'] is True and bound['instructions']==3000000 and
            bound['timeout_s']==120 and bound['raw_bytes']==512*1024**2,'Reference resource drift')
    require(not (OUT/'reference_attempt.json').exists(),'One reference execution; no retry')
    pins=json.loads((OUT/'input_pins.json').read_text());pincheck(pins)
    for b,h in json.loads((OUT/'source_proof.json').read_text())['elf_sha256'].items():
        require(sha(OUT/(b+'.elf'))==h,'Compiled ELF drift')
    cmd=[str(base.SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2',
         '--instructions=3000000','-l','--log-commits',str(OUT/'spike.elf')]
    save(OUT/'reference_attempt.json',dict(command=cmd,bound_sha256=sha(OUT/'bound.json'),
         started=time.time(),one_attempt_only=True))
    start=time.monotonic()
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(bound['raw_bytes'],bound['raw_bytes']))
    try:
        with (OUT/'spike.stdout').open('x') as stdout,(OUT/'spike.trace').open('x') as stderr:
            child=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=120,preexec_fn=limit)
        elapsed=time.monotonic()-start
        require(child.returncode==0,'Reference process failure '+str(child.returncode))
        result=validate((OUT/'spike.trace').read_text(),json.loads((OUT/'spike.symbols.json').read_text()))
        result.update(reference_elapsed_s=elapsed,process_returncode=child.returncode,isa=ISA,
                      raw_bytes=(OUT/'spike.trace').stat().st_size,raw_sha256=sha(OUT/'spike.trace'))
        pincheck(pins);save(OUT/'status.json',result)
        print(json.dumps({k:result[k] for k in ('status','commits','checks','case_checks','reference_elapsed_s')},indent=2))
    except BaseException as error:
        save(OUT/'not_completed.json',dict(status='REFERENCE_NOT_ACCEPTED_NO_RETRY',error=f'{type(error).__name__}: {error}'))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['build','run'])
    {'build':build,'run':run}[parser.parse_args().mode]()
