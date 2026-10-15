#!/usr/bin/env python3
"""Full original16 software/Host and one bounded Spike execution; no DUT."""
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
from newscope import CAP,ALLOC,MASK_BYTES,VTYPE,LMUL,CHECKS,ORIGINAL_PCS,BOOTSTRAP_PCS
import importlib.util

HERE=Path(__file__).resolve().parent
OUT=HERE/'software01'
C=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
R=Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
SOURCE=C/'rvv_zero_stride_reference57/source_nf1_m2'
NAME='rvv_fault_replay_strided_zero_stride_e64_m2'
ORIGINAL=SOURCE/'overlay/opt/ara-tests'/NAME
RUNTIME=Path('/tmp/current-board-integration-fast01/prepared')
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ISA='rv64gcv_zfh_zvfh_zvl1024b'
require=obs.require
EXPECTED={R/'fault_replay_oracle.c':'631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a',
 R/'fault_replay.py':'47765b894cde708521c8a32ce02539e9bd140ebc1be464824252817a05755ff9',
 SOURCE/'manifest.json':'71cf869dbf839a4eb8b9482f8e772a400af155b3506bf0daac276176975839b9',
 SOURCE/(NAME+'.S'):'2d750527bf6c5636ffa61de05133661086c2bb486408ba11f24353e1f645d74c'}
for _p in (ORIGINAL,C/'rvv_additions57/binaries'/NAME,C/'rvv_recovery08_12/terminal_scene'/NAME):
    EXPECTED[_p]='3fc3207f555099fce31489fa5e4e93b0aa178bef89b3ad11cb30caa600babf60'

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def save(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def read(p):return json.loads(Path(p).read_text())
def pinscheck(pins):
    for p,h in pins.items():require(sha(p)==h,'Input drift '+str(p))
def logged(cmd,path):
    cmd=list(map(str,cmd));start=time.monotonic()
    with path.open('x') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=120)
    save(path.with_suffix(path.suffix+'.execution.json'),dict(command=cmd,returncode=p.returncode,elapsed_s=time.monotonic()-start))
    require(p.returncode==0,'Command failed; retained '+str(path))
def symbols(elf):
    text=subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=30)
    return {m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',text,re.M)}

def build():
    require(not OUT.exists(),'Fresh software output only');pinscheck(EXPECTED)
    gen_spec=importlib.util.spec_from_file_location('archived_generator',R/'fault_replay.py')
    gen=importlib.util.module_from_spec(gen_spec);gen_spec.loader.exec_module(gen)
    require(gen.assembly(64,lmul='m'+str(LMUL),fields=1,strided=True)==(SOURCE/(NAME+'.S')).read_text(),'Archived ASM != original generator')
    manifest=read(SOURCE/'manifest.json')
    item=next(x for x in manifest['cases'] if x['name']==NAME)
    require(item['sha256']==sha(ORIGINAL) and item['configurations']==16 and item['expected_signals']==12 and manifest['lmul']=='m'+str(LMUL) and manifest['zero_stride'] and manifest['fault_boundaries']==[0],'Actual manifest shape')
    require(gen.LMULS['m'+str(LMUL)][0]*128==ALLOC,'Source CAPACITY_LIMIT')
    OUT.mkdir();p=OUT/'prepared';p.mkdir()
    inputs=list(EXPECTED)+[HERE/n for n in ('fixture.c','fixture.S','observer.py','prepare.py','host_tests.py','newscope.py','seal.py','bound.py')]
    inputs += [RUNTIME/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
    inputs += [CC.resolve(),CC.with_name('riscv64-unknown-elf-objdump').resolve(),CC.with_name('riscv64-unknown-elf-nm').resolve(),SPIKE,obs.BASE,obs.DECODER]
    save(OUT/'input_pins.json',{str(f):sha(f) for f in inputs})
    for n in ('fixture.c','fixture.S'):shutil.copyfile(HERE/n,p/n)
    for n in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(RUNTIME/n,p/n)
    shutil.copyfile(SOURCE/(NAME+'.S'),p/'original.S')
    logged(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DHOST_ORACLE',p/'fixture.c','-o',OUT/'host'],OUT/'host.compile.log')
    logged([OUT/'host'],OUT/'host.stdout')
    rows=obs.host_check((OUT/'host.stdout').read_text())
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
      '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
      '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
      '-Wl,--build-id=none','-Wl,--gc-sections','-T',p/'replay.ld']
    logged([CC.with_name('riscv64-unknown-elf-objdump'),'-d',ORIGINAL],OUT/'original.dis')
    old=obs.disassemble((OUT/'original.dis').read_text());proof={}
    for backend in ('soc','spike'):
        elf=OUT/(backend+'.elf')
        logged([CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                *[p/n for n in ('fixture.c','fixture.S','original.S','startup.S','runtime.c')],'-lgcc','-o',elf],OUT/(backend+'.compile.log'))
        logged([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],OUT/(backend+'.dis'))
        s=symbols(elf);save(OUT/(backend+'.symbols.json'),s)
        require(s['__bss_end']<0x800f0000,'Runtime memory ceiling')
        code=obs.disassemble((OUT/(backend+'.dis')).read_text());helpers={}
        for name,start,count in (('capacity',ORIGINAL_PCS[0],3),('replay_0',ORIGINAL_PCS[1],10),('replay_1',ORIGINAL_PCS[2],10)):
            pcs=obs.window(code,s[name],count);oldpcs=obs.window(old,start,count)
            require([code[a] for a in pcs]==[old[a] for a in oldpcs],'Original helper bytes differ '+name)
            helpers[name]=dict(pcs=[hex(a) for a in pcs],encodings=[f'{code[a]:08x}' for a in pcs])
        bootstrap=[0xcdb1f057,0x0207f407,0x0205f427]
        require([old[a] for a in BOOTSTRAP_PCS]==bootstrap,'Original compiler bootstrap differs')
        bp=obs.window(code,s['mx_bootstrap'],8)
        require([code[a] for a in bp][4:7]==bootstrap,'Adapted compiler bootstrap differs')
        proof[backend]=dict(elf_sha256=sha(elf),helpers=helpers,bootstrap_encodings=[hex(v) for v in bootstrap],
          load_target_pc=hex(s['fault_0_pc']),store_target_pc=hex(s['fault_1_pc']))
    save(OUT/'source_proof.json',dict(status='SOURCE_DERIVATIVE_SOFTWARE_ONLY',original_name=NAME,
      original_hashes={str(p):h for p,h in EXPECTED.items()},actual_isa=ISA,backends=proof,
      original_order=[dict(case=c,unmapped=c//8,store=(c//4)%2,mode=c%4,boundary=0,split=0,stride=0) for c in range(16)],
      scope=dict(cases=16,predecessors_preserved=15,cap=CAP,vl=8,sew=64,lmul=LMUL,
        output_elements=16*CAP,guards=32,memory_words=16384,returned_vstart=16,
        expected_faults=12,expected_ecalls=16,unmapped_refills=8,helper_original_instructions=23,
        input_allocation_words=ALLOC,input_initialized_words=CAP,output_allocation_words=ALLOC+2,
        mask_allocation_bytes=MASK_BYTES,offsets_words=ALLOC,target_registers=list(range(24,24+LMUL)),neighbor_register_guards=False,snapshot_guards='memory-only'),
      changes=['Linux VM/signal wrapper replaced by real Sv39 S-mode/M-mode repair',
        'Virtual mapping fixed at 0x40000000; original relative geometry unchanged',
        'Original sigaction RVV bootstrap instructions retained with relocated handler pointer',
        'Additional nonmutating full-memory checkpoints and complete group snapshots',
        'Unused offsets explicitly retained even if eliminated by original compiler'],
      original_linux_byte_identity=False,linux_signal_frame_equivalence=False,
      original_unknown_stall_trial_identified=False,historical_linux_stall_closed=False))
    pinscheck(read(OUT/'input_pins.json'))
    print(json.dumps(dict(status='SOFTWARE_HOST_ORACLE_PASS_REFERENCE_NOT_RUN',host_rows=rows,proof=proof),indent=2))

def run():
    r=HERE/'reference01';require(not r.exists(),'One actual Spike execution; no automatic retry')
    bound=read(OUT/'bound.json')
    require(bound['admit_once'] and bound['instruction_limit']==obs.LIMIT and bound['timeout_s']==120 and
            bound['raw_bytes']==1024**3 and bound['static_upper_instructions']<obs.LIMIT,'Bound absent/different')
    require(bound['isa']==ISA and bound['soc_elf_sha256']==sha(OUT/'soc.elf') and bound['spike_elf_sha256']==sha(OUT/'spike.elf'),'ELF/profile bound differs')
    pins=read(OUT/'input_pins.json');pinscheck(pins)
    pins.update({str(f):sha(f) for f in OUT.rglob('*') if f.is_file()})
    r.mkdir();save(r/'input_pins.json',pins);pinscheck(pins)
    cmd=[str(SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2','--instructions='+str(obs.LIMIT),'-l','--log-commits',str(OUT/'spike.elf')]
    save(r/'attempt.json',dict(command=cmd,started=time.time(),one_attempt=True,bound_sha256=sha(OUT/'bound.json')))
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(bound['raw_bytes'],bound['raw_bytes']))
    start=time.monotonic();timeout=False
    with (r/'stdout.log').open('x') as stdout,(r/'spike.trace').open('x') as stderr:
        child=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,preexec_fn=limit)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timeout=True;child.kill();rc=child.wait()
        execution=dict(returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-start,command=cmd,child_pid=child.pid,actual_popen_wait=True,architectural_acceptance=False)
        save(r/'execution.json',execution)
    # Numeric wait is durable before raw metadata, pins, or observer code.
    execution['raw_bytes']=(r/'spike.trace').stat().st_size
    save(r/'raw_metadata.json',dict(raw_bytes=execution['raw_bytes']))
    try:
        pinscheck(pins);require(rc==0 and not timeout,'Reference failed/bounded out; no retry')
        result=obs.analyze(r/'spike.trace',read(OUT/'spike.symbols.json'),obs.disassemble((OUT/'spike.dis').read_text()),OUT/'spike.elf')
        pinscheck(pins);result.update(execution=execution,raw_sha256=sha(r/'spike.trace'),pins_unchanged=True)
        save(r/'status.json',result)
        print(json.dumps({k:result[k] for k in ('status','commits','firmware_commits','scalar_checks','cases','faults')},indent=2))
    except BaseException as e:
        save(r/'not_completed.json',dict(status='REFERENCE_NOT_ACCEPTED_NO_RETRY',error=f'{type(e).__name__}: {e}',execution=execution));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','run']);{'build':build,'run':run}[p.parse_args().mode]()

