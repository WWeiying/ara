#!/usr/bin/env python3
"""Two exact e64 sc0/sc3 source ports. Software only; no DUT launcher."""
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
CASES={
  0:dict(name='rvv_small_exceptions_e64_scenario0',scenario=0,target=66682,
    elf='a7980422c77c7910fe24c710a50b6bcf892a91056baf945c5e4a1b3ba8bf8fa3',
    c='9883b8afe63695b104ca0915da15f565885b99310803fefcb1baef24e67cc07b',
    asm='79ac02eb05e4dcbb0788c8d65f912168c85416256f84309c82c63f2f5e958c04'),
  3:dict(name='rvv_small_exceptions_e64_scenario3',scenario=3,target=66634,
    elf='a5e9b52df9687e68fc19dadd14c86634b78addc78856266f09cacd7d48851f21',
    c='45a6c005b92933c0cf3315d7ae08dc27377ca51c54df30c291be79bb4495ed03',
    asm='79ac02eb05e4dcbb0788c8d65f912168c85416256f84309c82c63f2f5e958c04')}

require=o.require
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,value):
    import os
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def verify(pins):
    for path,digest in pins.items():require(sha(path)==digest,'Input drift '+path)
def logged(command,path):
    cmd=list(map(str,command));start=time.monotonic()
    with path.open('x') as stream:result=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    save(path.with_suffix(path.suffix+'.execution.json'),dict(command=cmd,actual_wait_returncode=result.returncode,elapsed_s=time.monotonic()-start))
    require(result.returncode==0,'Software/Host command failed, retained '+str(path))
def symbols(elf):
    text=subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=30)
    return {m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',text,re.M)}

def source_pins(scenario):
    case=CASES[scenario];src=S/case['name']
    pins={str(S/'binaries'/case['name']):case['elf'],str(src/'scenario.c'):case['c'],str(src/'scenario.S'):case['asm']}
    verify(pins)
    original=R/'exception_oracle.c'
    require(sha(original)=='af36b5d8475b2949e09957ad742bbb863d0b5a59c5cf9cd959edc2dc6bc86794','Canonical detail source')
    delta=[line for line in difflib.ndiff(original.read_text().splitlines(),(src/'scenario.c').read_text().splitlines()) if line.startswith(('- ','+ '))]
    require(len(delta)==2 and delta[0].strip().startswith('-     for(unsigned round=0;round<16;') and
            delta[1]==f'+     for(unsigned round=0;round<1;++round)for(unsigned scenario={case["scenario"]};scenario<{case["scenario"]+1};++scenario){{','Only original loop selection delta')
    detailasm=C/'rvv_exception_detail01'/'rvv_exceptions_detail_e64.S'
    require(detailasm.read_bytes()==(src/'scenario.S').read_bytes(),'Actual archived assembly identity')
    manifest=read(S/'manifest.json');record=next(x for x in manifest['cases'] if x['name']==case['name'])
    require(record['sha256']==case['elf'] and record['scenario_sources']=={'scenario.c':case['c'],'scenario.S':case['asm']},'Archive manifest identity')
    symptom=next(x for x in read(C/'rvv_exception_symptoms02/symptoms.json')['cases'] if x['name']==case['name'])
    require(symptom['confirmed'] and symptom['status']=='failed' and symptom['trap']['epc']==case['target'],'Exact measured failure')
    files=[original,detailasm,S/'manifest.json',C/'rvv_exception_detail01/manifest.json']
    files += [C/'rvv_exception_symptoms02'/n for n in ('original_report.json','sampled_report.json','symptoms.json')]
    files += [HERE/n for n in ('fixture.h','fixture.c','fixture.S','observer.py','csv_check.py','prepare.py','test_host.py','source_owners.py','finalize.py')]
    files += [HERE.parent/'unit_fof_e64_suffix_two_prepare01'/n for n in ('fixture.h','fixture.c','fixture.S','observer.py','csv_check.py','prepare.py')]
    files += [HERE.parent/'unit_fof_e64_suffix_two_vcs_m9_plan01/source_owners.py']
    files += [RUNTIME/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
    files += [CC.resolve(),CC.with_name('riscv64-unknown-elf-objdump').resolve(),CC.with_name('riscv64-unknown-elf-nm').resolve(),SPIKE,o.UTIL,o.u.DECODER]
    pins.update({str(p):sha(p) for p in files})
    return pins,dict(manifest=record,measured_failure={k:v for k,v in symptom.items() if k not in ('trap','original_matching_traps')},
                     trap={k:v for k,v in symptom['trap'].items() if k!='output'},loop_delta=delta)

def bind_image():
    original=read(M9_PLAN)
    pins={k:v for k,v in original['pins'].items() if k.startswith(str(M9)+'/')}
    require(len(pins)>500,'Full accepted M9 image/source pin set')
    require(pins[str(M9/'campaign/image/image.json')]=='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a','Exact M9 identity')
    verify(pins)
    save(HERE/'M9_BINDING.json',dict(image=str(M9/'campaign/image'),image_sha256=pins[str(M9/'campaign/image/image.json')],
         derived_from=str(M9_PLAN),parent_plan_sha256=sha(M9_PLAN),pins=pins,DUT_run=False,
         limits=dict(reference_records=800000,reference_wall_s=120,raw_bytes=256*1024**2)))

def soc_spec(path,s,code,scenario):
    exits=[a for a in o.window(code,s['replay_exit'],5) if code[a]==0x00a2b023]
    require(len(exits)==1 and 'tohost' not in s,'SoC actual CTRL store and no HTIF')
    restores=[pc for pc,insn in code.items() if s['main']<=pc<s['fx_handler'] and insn&0xfe00707f==0x80007057]
    require(len(restores)==1,'Single CSR restore vsetvl')
    return dict(backend='soc',scenario=scenario,sew=64,symbols=s,code=code,elf=str(path/'soc.elf'),
        elf_sha256=sha(path/'soc.elf'),exit_store=exits[0],park=exits[0]+4,restore_pc=restores[0],
        helper=o.window(code,s['load_0' if scenario==3 else 'load_1'],11),
        unused=o.window(code,s['load_1' if scenario==3 else 'load_0'],11),
        capacity=o.window(code,s['capacity'],3),CTRL_raw_returncode=0,HTIF_applicable=False)

def build():
    out=HERE/'software01';require(not out.exists(),'Fresh software directory only');out.mkdir()
    bind_image()
    for scenario in CASES:
        sew=64
        path=out/f'scenario{scenario}';path.mkdir();prepared=path/'prepared';prepared.mkdir()
        pins,provenance=source_pins(scenario);
        pins[str(HERE/'M9_BINDING.json')]=sha(HERE/'M9_BINDING.json');save(path/'input_pins.json',pins)
        for name in ('fixture.c','fixture.h','fixture.S'):shutil.copyfile(HERE/name,prepared/name)
        for name in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(RUNTIME/name,prepared/name)
        shutil.copyfile(S/CASES[scenario]['name']/'scenario.S',prepared/'original.S')
        logged(['/usr/bin/cc','-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DSCENARIO={scenario}','-DHOST_ORACLE',prepared/'fixture.c','-o',path/'host'],path/'host.compile.log')
        logged([path/'host'],path/'host.stdout')
        rows=o.host_check((path/'host.stdout').read_text(),sew,scenario)
        objdump=CC.with_name('riscv64-unknown-elf-objdump')
        logged([objdump,'-d',S/'binaries'/CASES[scenario]['name']],path/'original.dis')
        old=o.disassemble((path/'original.dis').read_text());target=CASES[scenario]['target']
        load0=target-(12 if scenario==3 else 52)
        oldpcs={'load_0':o.window(old,load0,11),'load_1':o.window(old,load0+40,11),'capacity':o.window(old,load0-8,3)}
        proof={}
        flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
               '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
               '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
               '-Wl,--build-id=none','-Wl,--gc-sections',f'-DSEW={sew}',f'-DSCENARIO={scenario}','-T',prepared/'replay.ld']
        for backend in ('soc','spike'):
            elf=path/(backend+'.elf')
            logged([CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                    *[prepared/n for n in ('fixture.c','fixture.S','original.S','startup.S','runtime.c')],'-lgcc','-o',elf],path/(backend+'.compile.log'))
            logged([objdump,'-d',elf],path/(backend+'.dis'))
            s=symbols(elf);save(path/(backend+'.symbols.json'),s);code=o.disassemble((path/(backend+'.dis')).read_text())
            require(s['__bss_end']<0x800f0000 and s['fx_guard_lo']==s['fx_pages']-64 and s['fx_guard_hi']==s['fx_pages']+20480,'Physical runtime layout')
            helpers={}
            for name,opcs in oldpcs.items():
                pcs=o.window(code,s[name],len(opcs));require([code[a] for a in pcs]==[old[a] for a in opcs],'Original helper bytes differ '+name)
                helpers[name]=dict(pcs=pcs,original_pcs=opcs,encodings=[f'{code[a]:08x}' for a in pcs])
            require(code[helpers['load_1']['pcs'][3]]==int('01050c07' if sew==8 else '01057c07',16),'Exact original FOF encoding')
            selected='load_0' if scenario==3 else 'load_1'
            require(code[helpers[selected]['pcs'][3]]==(0x00057c07 if scenario==3 else 0x01057c07),'Original selected target, not substitution')
            proof[backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,target_pc=helpers[selected]['pcs'][3],bss_bytes=s['__bss_end']-s['__bss_start'])
            if backend=='soc':save(path/'soc.spec.json',soc_spec(path,s,code,scenario))
        save(path/'host_oracle.json',dict(status='HOST_C_INDEPENDENT_ORACLE_PASS',rows=rows))
        save(path/'source_proof.json',dict(source=provenance,backend=proof,sew=sew,scenario=CASES[scenario]['scenario'],
            original_allocation_elements=130,mask_bytes=16,source_words=4,original_helper_instructions=11,capacity_instructions=3,
            original_result_elements=8,original_defined_result_elements=4 if scenario==0 else 8,
            original_guards=[0,9],allowed_undefined_output_indices=[5,6,7,8] if scenario==0 else [],
            isa=ISA,linux_elf_byte_identity=False,linux_signal_equivalence=False,parent8_ELFs_accepted=False,
            actual_protection='True S-mode Sv39; readable first leaf, invalid second leaf, not Linux PROT_NONE encoding'))
        verify(pins)
    print('SOFTWARE_TWO_CASES_BUILT_NO_REFERENCE_OR_DUT',flush=True)

def run_one(scenario):
    sew=64
    path=HERE/'software01'/f'scenario{scenario}';out=HERE/f'reference_scenario{scenario}_01'
    require(not out.exists(),'Exactly one reference per final ELF; no retry')
    bound=read(HERE/'M9_BINDING.json')
    require(bound['limits']==dict(reference_records=800000,reference_wall_s=120,raw_bytes=256*1024**2),'Fixed authorized reference limits')
    verify(bound['pins']);pins=read(path/'input_pins.json');verify(pins)
    require(read(HERE/'host01.json')['actual_wait_returncode']==0,'Host negatives must pass before reference')
    pins.update(bound['pins']);pins[str(HERE/'M9_BINDING.json')]=sha(HERE/'M9_BINDING.json')
    pins[str(HERE/'host01.json')]=sha(HERE/'host01.json')
    for f in path.rglob('*'):
        if f.is_file():pins[str(f)]=sha(f)
    out.mkdir();save(out/'input_pins.json',pins)
    cmd=[str(SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2','--instructions=800000','-l','--log-commits',str(path/'spike.elf')]
    save(out/'attempt.json',dict(command=cmd,started=time.time(),one_attempt=True,sew=sew,scenario=scenario))
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
    started=time.monotonic();timeout=False
    with (out/'stdout.log').open('x') as stdout,(out/'spike.trace').open('x') as stderr:
        child=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,preexec_fn=limit)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timeout=True;child.kill();rc=child.wait()
    execution=dict(actual_wait_returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-started,
                   raw_bytes=(out/'spike.trace').stat().st_size,command=cmd)
    save(out/'execution.json',execution)
    try:
        verify(pins);require(rc==0 and not timeout,'Reference actual exit/bound failure')
        parse_started=time.monotonic()
        result=o.analyze(out/'spike.trace',read(path/'spike.symbols.json'),o.disassemble((path/'spike.dis').read_text()),path/'spike.elf',sew,scenario)
        verify(pins);result.update(execution=execution,raw_sha256=sha(out/'spike.trace'),pins_unchanged=True,parser_elapsed_s=time.monotonic()-parse_started)
        save(out/'status.json',result)
        print(json.dumps({k:result[k] for k in ('status','commits','firmware_commits','scalar_checks')},indent=2),flush=True)
    except BaseException as error:
        save(out/'not_completed.json',dict(status='REFERENCE_NOT_ACCEPTED_NO_RETRY',error=f'{type(error).__name__}: {error}',execution=execution));raise

def host():
    require(not (HERE/'host01.json').exists(),'Fresh Host receipt')
    started=time.monotonic()
    with (HERE/'host01.log').open('x') as stream:
        result=subprocess.run([sys.executable,'-B',str(HERE/'test_host.py')],stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    save(HERE/'host01.json',dict(actual_wait_returncode=result.returncode,elapsed_s=time.monotonic()-started,
         test_sha256=sha(HERE/'test_host.py'),log_sha256=sha(HERE/'host01.log')))
    require(result.returncode==0,'Host negatives failed; stop')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','host','reference'])
    p.add_argument('--scenario',type=int,choices=[0,3]);args=p.parse_args()
    if args.mode=='build':build()
    elif args.mode=='host':host()
    else:require(args.scenario is not None,'Exact case selection required');run_one(args.scenario)
