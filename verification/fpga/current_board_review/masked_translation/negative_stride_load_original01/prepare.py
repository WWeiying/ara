#!/usr/bin/env python3
"""One original negative-stride single; software/reference only, never DUT."""
import argparse
import hashlib
import json
import re
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode=True
import observer as obs

HERE=Path(__file__).resolve().parent
OUT=HERE/'software01'
ARCHIVE=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01')
NAME='rvv_small_fault_strided_negative_stride_e16_m1_u1_s0_b3_m2_f0_g3'
SOURCE=ARCHIVE/'singles'/NAME
RUNTIME=Path('/tmp/current-board-integration-fast01/prepared')
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ISA='rv64gcv_zfh_zvfh_zvl1024b'
EXPECTED={'scenario.c':'90996937a77228ac31baf0323079d97e8c5004fad163e80a950ac670b82eb563',
          'scenario.S':'597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039',
          'scenario.elf':'4c10f89aeb0d400412b15115b48ad3f11d9296fc881fb2645e573a5807d0e907',
          'case.json':'90e2325772d69fc5353e3cde71e1cb7562b62d863fd68920b562ea8b92057e41'}
require=obs.require
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def save(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def read(p):return json.loads(Path(p).read_text())
def checkpins(pins):
    for p,h in pins.items():require(sha(p)==h,'Input drift '+p)
def logged(cmd,path):
    cmd=list(map(str,cmd));start=time.monotonic()
    with path.open('x') as f:child=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=120)
    save(path.with_suffix(path.suffix+'.execution.json'),dict(command=cmd,returncode=child.returncode,elapsed_s=time.monotonic()-start))
    require(child.returncode==0,'Command failed; retained '+str(path))
def symbols(elf):
    text=subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=30)
    return {m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',text,re.M)}

def host_negatives(s):
    def sample(phase):
        memory=obs.expected(s,phase)
        for n in range(2 if phase==3 else 1 if phase else 0):
            for i,b in enumerate((0x800).to_bytes(8,'little')):memory[s['mx_records']+96*n+24+i]=b
        obs.compare(memory,s,phase)
        return memory
    for p in range(4):sample(p)
    mutations=[(1,'historical_wrong_tval',s['mx_records']+16),(1,'historical_wrong_vstart',s['mx_records']+56),
      (1,'completed_prefix_missing',s['mx_fault']+64+128+4),(1,'inactive_prefix_corruption',s['mx_fault']+64+128+6),
      (2,'prefix_poison_missing',s['mx_pages']+4102),(2,'lower_refill_corruption',s['mx_pages']+2),
      (3,'restart_reloaded_poison',s['mx_out']+6),(3,'active_element5_wrong',s['mx_out']+12),
      (3,'full_tail',s['mx_out']+128),(3,'guard',s['mx_out']+130),
      (3,'extra_allocation_sentinel',s['mx_out']+258),(3,'pte_neighbor',s['mx_pages']+16384+16),
      (3,'memory_unaddressed',s['mx_pages']+8190),(3,'post_vstart',s['mx_post']+16),
      (3,'fcsr',s['mx_post']+24),(3,'input_unused',s['mx_input']+126),
      (3,'offsets_unused',s['mx_offsets']+254),(3,'negative_stride',s['mx_stride']),
      (0,'initial_mapping',s['mx_pages']+16384),(0,'mask_input',s['mx_mask'])]
    result=[]
    for phase,name,a in mutations:
        memory=sample(phase);memory[a]^=1
        try:obs.compare(memory,s,phase)
        except ValueError:result.append(dict(name=name,rejected=True));continue
        raise ValueError('Negative accepted '+name)
    memory=sample(3);del memory[s['mx_pages']+8191]
    try:obs.compare(memory,s,3)
    except ValueError:result.append(dict(name='missing_final_byte',rejected=True))
    else:raise ValueError('Missing data accepted')
    return dict(positive_checkpoints=4,negative=result)

def build():
    require(not OUT.exists(),'Fresh preparation only')
    checkpins({str(SOURCE/n):h for n,h in EXPECTED.items()})
    OUT.mkdir();p=OUT/'prepared';p.mkdir()
    inputs=[SOURCE/n for n in EXPECTED]
    inputs += [ARCHIVE/'evidence'/n for n in ('single_manifest.json','single_board_report.json','single_symptoms.json')]
    inputs += [HERE/n for n in ('fixture.h','fixture.c','fixture.S','observer.py','prepare.py')]
    inputs += [RUNTIME/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
    inputs += [CC.resolve(),SPIKE,obs.DECODER]
    save(OUT/'input_pins.json',{str(f):sha(f) for f in inputs})
    for n in ('fixture.h','fixture.c','fixture.S'):shutil.copyfile(HERE/n,p/n)
    for n in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(RUNTIME/n,p/n)
    shutil.copyfile(SOURCE/'scenario.S',p/'original.S')
    logged(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DHOST_ORACLE',p/'fixture.c','-o',OUT/'host'],OUT/'host.compile.log')
    logged([OUT/'host'],OUT/'host.stdout')
    rows=obs.host_check((OUT/'host.stdout').read_text())
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
           '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
           '-Wl,--build-id=none','-Wl,--gc-sections','-T',p/'replay.ld']
    proof={}
    # Also retain the archived stripped ELF disassembly; helper bytes, not labels, prove identity.
    logged([CC.with_name('riscv64-unknown-elf-objdump'),'-d','--start-address=68078','--stop-address=68170',SOURCE/'scenario.elf'],OUT/'original.dis')
    original=obs.disassemble((OUT/'original.dis').read_text())
    for backend in ('soc','spike'):
        elf=OUT/(backend+'.elf')
        logged([CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                *[p/n for n in ('fixture.c','fixture.S','original.S','startup.S','runtime.c')],'-lgcc','-o',elf],OUT/(backend+'.compile.log'))
        logged([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],OUT/(backend+'.dis'))
        s=symbols(elf);save(OUT/(backend+'.symbols.json'),s)
        require(s['__bss_end']<0x800f0000,'Runtime memory bound')
        code=obs.disassemble((OUT/(backend+'.dis')).read_text())
        helpers={}
        for name,old,count in (('capacity',0x109f6,3),('replay_0',0x109fe,10),('replay_1',0x10a24,10)):
            pcs=obs.window(code,s[name],count);opcs=obs.window(original,old,count)
            require([code[a] for a in pcs]==[original[a] for a in opcs],'Original helper bytes differ '+name)
            helpers[name]=dict(pcs=[hex(a) for a in pcs],encodings=[f'{code[a]:08x}' for a in pcs])
        proof[backend]=dict(elf_sha256=sha(elf),helpers=helpers,target_pc=hex(s['fault_0_pc']),
                            target_encoding=f'{code[s["fault_0_pc"]]:08x}')
    negative=host_negatives(read(OUT/'spike.symbols.json'))
    save(OUT/'host.json',dict(status='HOST_PASS_NOT_REFERENCE',oracle_rows=rows,**negative))
    save(OUT/'source_proof.json',dict(status='SOURCE_DERIVATIVE_SOFTWARE_ONLY',original_name=NAME,
        original_hashes=EXPECTED,case=read(SOURCE/'case.json'),actual_isa=ISA,backend=proof,
        scope=dict(cases=1,predecessors=0,vl=8,cap=64,stride=-8,mask_bytes=16,mask_value=36,
                   output_elements=64,guards=2,full_memory_bytes=8192,unused_offsets=128),
        original_linux_byte_identity=False,linux_signal_frame_equivalence=False,
        original_parent96_accepted=False,environment='Real Sv39 S-mode with M-mode repair, original helper bytes'))
    checkpins(read(OUT/'input_pins.json'))
    print(json.dumps(dict(status='HOST_SOFTWARE_PASS_REFERENCE_NOT_RUN',rows=rows,negative=len(negative['negative']),elf_sha256={b:proof[b]['elf_sha256'] for b in proof}),indent=2))

def run():
    r=HERE/'reference01';require(not r.exists(),'Exactly one reference execution, no retry')
    b=read(OUT/'bound.json')
    require(b['admit_once'] and b['instruction_limit']==1500000 and b['timeout_s']==120 and
            b['raw_bytes']==256*1024**2 and b['static_upper_instructions']<1500000,'Static admission absent/different')
    build_pins=read(OUT/'input_pins.json')
    # Compilation is already complete. The observer/executor are finalized after
    # disassembly review; record that pre-reference delta without rebuilding ELF.
    pins={p:h for p,h in build_pins.items() if p not in (str(HERE/'observer.py'),str(HERE/'prepare.py'))}
    checkpins(pins)
    for name,h in b['final_checker_sha256'].items():
        require(sha(HERE/name)==h,'Final checker drift '+name);pins[str(HERE/name)]=h
    pins.update({str(f):sha(f) for f in OUT.rglob('*') if f.is_file()})
    r.mkdir();save(r/'input_pins.json',pins);checkpins(pins)
    save(r/'pre_reference_checker_delta.json',{p:dict(build_hash=h,final_hash=pins[p]) for p,h in build_pins.items() if pins[p]!=h})
    cmd=[str(SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2',
         '--instructions=1500000','-l','--log-commits',str(OUT/'spike.elf')]
    save(r/'attempt.json',dict(command=cmd,started=time.time(),one_attempt=True,bound_sha256=sha(OUT/'bound.json')))
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(b['raw_bytes'],b['raw_bytes']))
    start=time.monotonic();timeout=False
    with (r/'stdout.log').open('x') as stdout,(r/'spike.trace').open('x') as stderr:
        child=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,preexec_fn=limit)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timeout=True;child.kill();rc=child.wait()
    execution=dict(returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-start,
                   raw_bytes=(r/'spike.trace').stat().st_size,command=cmd)
    save(r/'execution.json',execution)
    try:
        checkpins(pins);require(rc==0 and not timeout,'Reference process failed/bounded out')
        result=obs.analyze(r/'spike.trace',read(OUT/'spike.symbols.json'),obs.disassemble((OUT/'spike.dis').read_text()),OUT/'spike.elf')
        checkpins(pins);result.update(execution=execution,raw_sha256=sha(r/'spike.trace'),pins_unchanged=True)
        save(r/'status.json',result)
        print(json.dumps({k:result[k] for k in ('status','commits','firmware_commits','scalar_checks','helper_retirements')},indent=2))
    except BaseException as error:
        save(r/'not_completed.json',dict(status='REFERENCE_NOT_ACCEPTED_NO_RETRY',error=f'{type(error).__name__}: {error}',execution=execution))
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run'])
    {'build':build,'run':run}[p.parse_args().mode]()
