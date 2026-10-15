#!/usr/bin/env python3
"""One parameterized source preparation; no DUT launcher or RTL build."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import observer as o
HERE=Path(__file__).resolve().parent
C=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
S=C/'rvv_small_exceptions01'
R=Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
RUNTIME=Path('/tmp/current-board-integration-fast01/prepared')
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ISA='rv64gcv_zfh_zvfh_zvl1024b'
M9=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09')
M9_PLAN=HERE.parent.parent/'memory_candidate09_controls16/prepared01/plan.json'
need=o.require

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,data):
    import os
    with Path(path).open('x') as f:
        json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def verify(pins):
    for p,h in pins.items():need(sha(p)==h,'Input drift '+p)
def key(sew,sc):return f'e{sew}_sc{sc}'
def logged(cmd,path,timeout=120):
    cmd=list(map(str,cmd));start=time.monotonic()
    with path.open('x') as f:
        child=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
        timed=False
        try:rc=child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    receipt=dict(command=cmd,actual_wait_returncode=rc,timeout=timed,elapsed_s=time.monotonic()-start)
    save(path.with_suffix(path.suffix+'.execution.json'),receipt)
    need(type(rc) is int and rc==0 and not timed,'Command failed; no retry: '+str(path))
    return receipt
def symbols(elf):
    t=subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=30)
    return {m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',t,re.M)}

def source(sew,sc):
    name=f'rvv_small_exceptions_e{sew}_scenario{sc}';src=S/name
    manifest=read(S/'manifest.json')
    record=next(x for x in manifest['cases'] if x['name']==name)
    need(record['sew']==sew and record['measured_stimulus']==dict(scenario=sc,round=0,vl=8,sew=sew),'Exact original single')
    pins={str(S/'binaries'/name):record['sha256']}
    pins.update({str(src/n):h for n,h in record['scenario_sources'].items()});verify(pins)
    original=R/'exception_oracle.c'
    need(sha(original)=='af36b5d8475b2949e09957ad742bbb863d0b5a59c5cf9cd959edc2dc6bc86794','Original C')
    delta=[x for x in difflib.ndiff(original.read_text().splitlines(),(src/'scenario.c').read_text().splitlines()) if x.startswith(('- ','+ '))]
    need(delta==['-     for(unsigned round=0;round<16;++round)for(unsigned scenario=0;scenario<6;++scenario){',
                 f'+     for(unsigned round=0;round<1;++round)for(unsigned scenario={sc};scenario<{sc+1};++scenario){{'], 'Only archived single selection')
    asm=C/'rvv_exception_detail01'/f'rvv_exceptions_detail_e{sew}.S'
    need(asm.read_bytes()==(src/'scenario.S').read_bytes(),'Archived assembly identity')
    symptom=next(x for x in read(C/'rvv_exception_symptoms02/symptoms.json')['cases'] if x['name']==name)
    need(symptom['confirmed'] is True and symptom['status']=='failed' and symptom['trap']['cause']==13,'Actual original failure')
    need(symptom['trap']['offset']==(4*(sew//8) if sc<3 else 0),'Actual original fault geometry')
    files=[original,asm,S/'manifest.json',C/'rvv_exception_detail01/manifest.json']
    files += [C/'rvv_exception_symptoms02'/n for n in ('original_report.json','sampled_report.json','symptoms.json')]
    files += sorted(HERE.glob('*.py'))+sorted(HERE.glob('fixture.*'))
    files += [HERE.parent/'unit_fof_e64_sc0_sc3_prepare01'/n for n in ('fixture.c','fixture.h','fixture.S','observer.py','csv_check.py','source_owners.py','prepare.py')]
    files += [HERE.parent/'unit_fof_e64_sc0_sc3_checker_recovery01'/n for n in ('successor.py','successor_handler.py')]
    files += [RUNTIME/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
    files += [CC.resolve(),CC.with_name('riscv64-unknown-elf-objdump').resolve(),CC.with_name('riscv64-unknown-elf-nm').resolve(),SPIKE,o.UTIL,o.u.DECODER]
    pins.update({str(p):sha(p) for p in files})
    return pins,dict(manifest=record,measured_failure=symptom,original_loop_delta=delta),src

def bind_image():
    p=read(M9_PLAN);pins={k:v for k,v in p['pins'].items() if k.startswith(str(M9)+'/')}
    need(len(pins)>500 and pins[str(M9/'campaign/image/image.json')]=='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a','Frozen M9')
    verify(pins)
    save(HERE/'M9_BINDING.json',dict(image=str(M9/'campaign/image'),image_sha256=pins[str(M9/'campaign/image/image.json')],
         pins=pins,parent_plan=str(M9_PLAN),parent_plan_sha256=sha(M9_PLAN),DUT_run=False))

def build():
    out=HERE/'software01';out.mkdir();bind_image()
    for sew,sc in o.MEMBERS:
        p=out/key(sew,sc);p.mkdir();prepared=p/'prepared';prepared.mkdir()
        pins,provenance,src=source(sew,sc)
        pins[str(HERE/'M9_BINDING.json')]=sha(HERE/'M9_BINDING.json');save(p/'input_pins.json',pins)
        for n in ('fixture.h','fixture.c','fixture.S'):shutil.copyfile(HERE/n,prepared/n)
        for n in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(RUNTIME/n,prepared/n)
        shutil.copyfile(src/'scenario.S',prepared/'original.S')
        logged(['/usr/bin/cc','-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DSCENARIO={sc}','-DHOST_ORACLE',prepared/'fixture.c','-o',p/'host'],p/'host.compile.log')
        logged([p/'host'],p/'host.stdout');rows=o.host_check((p/'host.stdout').read_text(),sew,sc)
        objdump=CC.with_name('riscv64-unknown-elf-objdump')
        logged([objdump,'-d',S/'binaries'/provenance['manifest']['name']],p/'original.dis')
        old=o.disassemble((p/'original.dis').read_text());target=provenance['measured_failure']['trap']['epc']
        selected='load_0' if sc in (1,3) else 'load_1'
        load0=target-(12 if selected=='load_0' else 52)
        oldpcs={'load_0':o.window(old,load0,11),'load_1':o.window(old,load0+40,11),'capacity':o.window(old,load0-8,3)}
        proof={};flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
              '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
              '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
              '-Wl,--build-id=none','-Wl,--gc-sections',f'-DSEW={sew}',f'-DSCENARIO={sc}','-T',prepared/'replay.ld']
        for backend in ('soc','spike'):
            elf=p/(backend+'.elf')
            logged([CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),*[prepared/n for n in ('fixture.c','fixture.S','original.S','startup.S','runtime.c')],'-lgcc','-o',elf],p/(backend+'.compile.log'))
            logged([objdump,'-d',elf],p/(backend+'.dis'))
            s=symbols(elf);save(p/(backend+'.symbols.json'),s);code=o.disassemble((p/(backend+'.dis')).read_text())
            need(s['__bss_end']<0x800f0000 and s['fx_guard_lo']==s['fx_pages']-64 and s['fx_guard_hi']==s['fx_pages']+20480,'Physical memory fit')
            helpers={}
            for n,opcs in oldpcs.items():
                pcs=o.window(code,s[n],len(opcs));need([code[a] for a in pcs]==[old[a] for a in opcs],'Original helper code '+n)
                helpers[n]=dict(pcs=pcs,original_pcs=opcs,encodings=[f'{code[a]:08x}' for a in pcs])
            targetcode=(0x00050c07 if selected=='load_0' else 0x01050c07)|({8:0,16:5,32:6}[sew]<<12)
            need(code[helpers[selected]['pcs'][3]]==targetcode==old[target],'Exact measured opcode')
            proof[backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,target_pc=helpers[selected]['pcs'][3],bss_end=s['__bss_end'])
            if backend=='soc':
                exits=[a for a in o.window(code,s['replay_exit'],5) if code[a]==0x00a2b023]
                restores=[pc for pc,insn in code.items() if s['main']<=pc<s['fx_handler'] and insn&0xfe00707f==0x80007057]
                need(len(exits)==len(restores)==1 and 'tohost' not in s,'Real SoC CTRL and CSR restore')
                spec=dict(backend='soc',sew=sew,scenario=sc,symbols=s,code=code,elf=str(elf),elf_sha256=sha(elf),
                     exit_store=exits[0],park=exits[0]+4,restore_pc=restores[0],helper=helpers[selected]['pcs'],
                     unused=helpers['load_1' if selected=='load_0' else 'load_0']['pcs'],capacity=helpers['capacity']['pcs'],CTRL_raw_returncode=0,HTIF_applicable=False)
                import abi_check
                spec['abi_profile']=abi_check.profile(spec)
                save(p/'soc.spec.json',spec)
                abi_check.Checker(spec)
        save(p/'source_proof.json',dict(source=provenance,backend=proof,sew=sew,scenario=sc,isa=ISA,
             original_helper_instructions=11,capacity_instructions=3,allocation_elements=130,mask_bytes=16,VL=8,
             original_guards=[0,9],allowed_undefined_output_indices=[5,6,7,8] if sc==0 else [],
             linux_elf_byte_identity=False,linux_signal_equivalence=False,source_single_round=0,source_single_calls=1))
        save(p/'host_oracle.json',dict(status='PASS_INDEPENDENT_C_GOLD',rows=rows));verify(pins)
        print('BUILT',key(sew,sc),flush=True)

def host():
    receipt=logged([sys.executable,'-B',HERE/'test_host.py'],HERE/'host01.log')
    save(HERE/'host01.json',dict(**receipt,test_sha256=sha(HERE/'test_host.py'),log_sha256=sha(HERE/'host01.log')))

def reference(sew,sc):
    need((sew,sc) in o.MEMBERS,'Exact member');p=HERE/'software01'/key(sew,sc)
    out=HERE/'reference01'/key(sew,sc);out.mkdir(parents=True)
    need(read(HERE/'host01.json')['actual_wait_returncode']==0,'Host must pass')
    pins=read(p/'input_pins.json');pins.update(read(HERE/'M9_BINDING.json')['pins'])
    for f in p.rglob('*'):
        if f.is_file():pins[str(f)]=sha(f)
    pins[str(HERE/'host01.json')]=sha(HERE/'host01.json');verify(pins);save(out/'input_pins.json',pins)
    cmd=[str(SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2','--instructions=800000','-l','--log-commits',str(p/'spike.elf')]
    save(out/'attempt.json',dict(command=cmd,one_attempt=True,started=time.time(),record_limit=800000,wall_s=120,bytes_limit=256*1024**2))
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
    start=time.monotonic();timed=False
    with (out/'stdout.log').open('x') as stdout,(out/'spike.trace').open('x') as stderr:
        child=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,preexec_fn=limit)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    save(out/'spike_exit.json',dict(actual_wait_returncode=rc,timeout=timed,elapsed_s=time.monotonic()-start,raw_bytes=(out/'spike.trace').stat().st_size))
    need(type(rc) is int and rc==0 and not timed,'Reference failed: retain, no retry')
    verify(pins)
    logged([sys.executable,'-B',HERE/'parse_reference.py','--sew',str(sew),'--scenario',str(sc)],out/'parser.log')
    verify(pins);save(out/'pins_post.json',pins)
    print('REFERENCE_PASS',key(sew,sc),flush=True)

def finalize():
    entries=[];pins={}
    for sew,sc in o.MEMBERS:
        p=HERE/'software01'/key(sew,sc);r=HERE/'reference01'/key(sew,sc)
        status=read(r/'status.json');sx=read(r/'spike_exit.json');px=read(r/'parser.log.execution.json')
        need(status['status']=='REFERENCE_CHECKER_PASS_NOT_DUT' and type(sx['actual_wait_returncode']) is int and sx['actual_wait_returncode']==0
             and type(px['actual_wait_returncode']) is int and px['actual_wait_returncode']==0 and not sx['timeout'] and not px['timeout'],'Actual reference and parser exit')
        pre=read(r/'input_pins.json');need(pre==read(r/'pins_post.json'),'Reference pins unchanged');verify(pre);pins.update(pre)
        for f in r.iterdir():
            if f.is_file():pins[str(f)]=sha(f)
        entries.append(dict(member=key(sew,sc),sew=sew,scenario=sc,soc_elf=str(p/'soc.elf'),soc_elf_sha256=sha(p/'soc.elf'),
             source_proof=str(p/'source_proof.json'),spec=str(p/'soc.spec.json'),reference=str(r/'status.json'),
             actual_spike_exit=sx,actual_parser_exit=px,firmware_retired=status['firmware_to_htif'],records=status['commits'],checks=status['scalar_checks'],
             estimate_at_273_retired_per_s=status['firmware_to_htif']/273,case_budget_s=1800))
    need(len(entries)==14,'Exact14');save(HERE/'input_pins.json',pins)
    save(HERE/'READY.json',dict(status='READY_14_ORIGINAL_SOURCE_SV39_REFERENCES_NOT_DUT',members=entries,pins_sha256=sha(HERE/'input_pins.json'),
         image_binding_sha256=sha(HERE/'M9_BINDING.json'),reference_attempts=14,DUT_runs=0,scope='14 single-call source ports, not Linux parent closure'))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['build','host','reference','finalize']);ap.add_argument('--sew',type=int);ap.add_argument('--scenario',type=int)
    a=ap.parse_args()
    if a.mode=='build':build()
    elif a.mode=='host':host()
    elif a.mode=='finalize':finalize()
    else:reference(a.sew,a.scenario)
