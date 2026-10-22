#!/usr/bin/env python3
"""Software/Host and one bounded Spike reference per original FOF single. No DUT path."""
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
CASES={8:dict(name='rvv_small_exceptions_e8_scenario0',scenario=0,target=0x10498,
             elf='24f4844318a01f821681aa568aee42c1560b0f1705218dca0efa44eed34c9cbe',
             c='9883b8afe63695b104ca0915da15f565885b99310803fefcb1baef24e67cc07b',
             asm='d99047d4adb47d622c32a675ab485cd1f5c4cccd2e805f5b419056b25ab0d715'),
       64:dict(name='rvv_small_exceptions_e64_scenario5',scenario=5,target=0x10472,
             elf='a688dbfe9f1887fa028764d2e7decbdcfb3fd55460aa1e572b89f88b1c85a316',
             c='3fd4798e476ad168f5795d13ff3c770e00ff555616f603a5ef5c6b51fcbfac4b',
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

def source_pins(sew):
    case=CASES[sew];src=S/case['name']
    pins={str(S/'binaries'/case['name']):case['elf'],str(src/'scenario.c'):case['c'],str(src/'scenario.S'):case['asm']}
    verify(pins)
    original=R/'exception_oracle.c'
    require(sha(original)=='af36b5d8475b2949e09957ad742bbb863d0b5a59c5cf9cd959edc2dc6bc86794','Canonical detail source')
    delta=[line for line in difflib.ndiff(original.read_text().splitlines(),(src/'scenario.c').read_text().splitlines()) if line.startswith(('- ','+ '))]
    require(len(delta)==2 and delta[0].strip().startswith('-     for(unsigned round=0;round<16;') and
            delta[1]==f'+     for(unsigned round=0;round<1;++round)for(unsigned scenario={case["scenario"]};scenario<{case["scenario"]+1};++scenario){{','Only original loop selection delta')
    detailasm=C/'rvv_exception_detail01'/f'rvv_exceptions_detail_e{sew}.S'
    require(detailasm.read_bytes()==(src/'scenario.S').read_bytes(),'Actual archived assembly identity')
    manifest=read(S/'manifest.json');record=next(x for x in manifest['cases'] if x['name']==case['name'])
    require(record['sha256']==case['elf'] and record['scenario_sources']=={'scenario.c':case['c'],'scenario.S':case['asm']},'Archive manifest identity')
    symptom=next(x for x in read(C/'rvv_exception_symptoms02/symptoms.json')['cases'] if x['name']==case['name'])
    require(symptom['confirmed'] and symptom['status']=='failed' and symptom['trap']['epc']==case['target'],'Exact measured failure')
    files=[original,detailasm,S/'manifest.json',C/'rvv_exception_detail01/manifest.json']
    files += [C/'rvv_exception_symptoms02'/n for n in ('original_report.json','sampled_report.json','symptoms.json')]
    files += [HERE/n for n in ('fixture.h','fixture.c','fixture.S','observer.py','prepare.py','test_host.py')]
    files += [RUNTIME/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
    files += [CC.resolve(),CC.with_name('riscv64-unknown-elf-objdump').resolve(),CC.with_name('riscv64-unknown-elf-nm').resolve(),SPIKE,o.UTIL,o.u.DECODER]
    pins.update({str(p):sha(p) for p in files})
    return pins,dict(manifest=record,measured_failure={k:v for k,v in symptom.items() if k not in ('trap','original_matching_traps')},
                     trap={k:v for k,v in symptom['trap'].items() if k!='output'},loop_delta=delta)

def build():
    out=HERE/'software01';require(not out.exists(),'Fresh software directory only');out.mkdir()
    for sew in CASES:
        path=out/f'e{sew}';path.mkdir();prepared=path/'prepared';prepared.mkdir()
        pins,provenance=source_pins(sew);save(path/'input_pins.json',pins)
        for name in ('fixture.c','fixture.h','fixture.S'):shutil.copyfile(HERE/name,prepared/name)
        for name in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(RUNTIME/name,prepared/name)
        shutil.copyfile(S/CASES[sew]['name']/'scenario.S',prepared/'original.S')
        logged(['/usr/bin/cc','-Wall','-Wextra','-Werror',f'-DSEW={sew}','-DHOST_ORACLE',prepared/'fixture.c','-o',path/'host'],path/'host.compile.log')
        logged([path/'host'],path/'host.stdout')
        rows=o.host_check((path/'host.stdout').read_text(),sew)
        objdump=CC.with_name('riscv64-unknown-elf-objdump')
        logged([objdump,'-d',S/'binaries'/CASES[sew]['name']],path/'original.dis')
        old=o.disassemble((path/'original.dis').read_text());target=CASES[sew]['target']
        oldpcs={'load_1':o.window(old,target-12,11),'load_0':o.window(old,target-52,11),'capacity':o.window(old,target-60,3)}
        proof={}
        flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
               '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
               '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
               '-Wl,--build-id=none','-Wl,--gc-sections',f'-DSEW={sew}','-T',prepared/'replay.ld']
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
            proof[backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,target_pc=helpers['load_1']['pcs'][3],bss_bytes=s['__bss_end']-s['__bss_start'])
        save(path/'host_oracle.json',dict(status='HOST_C_INDEPENDENT_ORACLE_PASS',rows=rows))
        save(path/'source_proof.json',dict(source=provenance,backend=proof,sew=sew,scenario=CASES[sew]['scenario'],
            original_allocation_elements=130,mask_bytes=16,source_words=4,original_helper_instructions=11,capacity_instructions=3,
            original_result_elements=4 if sew==8 else 8,original_guards=[0,9],allowed_undefined_output_indices=[5,6,7,8] if sew==8 else [],
            isa=ISA,linux_elf_byte_identity=False,linux_signal_equivalence=False,parent8_ELFs_accepted=False,
            actual_protection='True S-mode Sv39; readable first leaf, invalid second leaf, not Linux PROT_NONE encoding'))
        verify(pins)
    print('SOFTWARE_TWO_CASES_BUILT_NO_REFERENCE_OR_DUT',flush=True)

def run_one(sew):
    path=HERE/'software01'/f'e{sew}';out=HERE/f'reference_e{sew}_01'
    require(not out.exists(),'Exactly one reference per final ELF; no retry')
    bound=read(HERE/'STATIC_BOUND.json');require(bound['admit_once'] and bound['instruction_limit']==1500000 and bound['timeout_s']==120 and bound['raw_bytes']==256*1024**2,'Fixed bound admission')
    verify(bound['pins']);pins=read(path/'input_pins.json');verify(pins)
    pins.update(bound['pins']);pins[str(HERE/'STATIC_BOUND.json')]=sha(HERE/'STATIC_BOUND.json')
    for f in path.rglob('*'):
        if f.is_file():pins[str(f)]=sha(f)
    out.mkdir();save(out/'input_pins.json',pins)
    cmd=[str(SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2','--instructions=1500000','-l','--log-commits',str(path/'spike.elf')]
    save(out/'attempt.json',dict(command=cmd,started=time.time(),one_attempt=True,sew=sew))
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
        result=o.analyze(out/'spike.trace',read(path/'spike.symbols.json'),o.disassemble((path/'spike.dis').read_text()),path/'spike.elf',sew)
        verify(pins);result.update(execution=execution,raw_sha256=sha(out/'spike.trace'),pins_unchanged=True)
        save(out/'status.json',result)
        print(json.dumps({k:result[k] for k in ('status','commits','firmware_commits','scalar_checks')},indent=2),flush=True)
    except BaseException as error:
        save(out/'not_completed.json',dict(status='REFERENCE_NOT_ACCEPTED_NO_RETRY',error=f'{type(error).__name__}: {error}',execution=execution));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','reference']);p.add_argument('--sew',type=int,choices=[8,64]);args=p.parse_args()
    if args.mode=='build':build()
    else:require(args.sew is not None,'Exact single selection required');run_one(args.sew)
