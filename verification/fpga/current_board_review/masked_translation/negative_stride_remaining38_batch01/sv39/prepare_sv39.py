#!/usr/bin/env python3
"""Once-only build/reference preparation. No DUT/image/service entry point."""
import argparse
import importlib.util
import json
import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode=True
import checker
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ns_batch_source',HERE.parent/'prepare.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
require,sha,save=source.require,source.sha,source.save
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
RUNTIME=HERE.parent.parent/'negative_stride_load_original01/software01/prepared'
ISA='rv64gcv_zfh_zvfh_zvl1024b'
OUT=HERE/'software01'
LIMIT=8000000


def read(p):return json.loads(Path(p).read_text())
def verify(pins):
    for p,h in pins.items():require(sha(p)==h,'Input drift '+p)


def execute(cmd,out,timeout,raw=None,raw_limit=None):
    start=time.monotonic();timed_out=False
    def limits():
        if raw_limit:resource.setrlimit(resource.RLIMIT_FSIZE,(raw_limit,raw_limit))
    with out.open('x') as stdout:
        stderr=raw.open('x') if raw else subprocess.STDOUT
        try:
            p=subprocess.Popen(list(map(str,cmd)),stdout=stdout,stderr=stderr,preexec_fn=limits if raw_limit else None)
            try:rc=p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True;p.kill();rc=p.wait()
        finally:
            if raw:stderr.close()
    receipt=dict(command=list(map(str,cmd)),pid=p.pid,actual_wait_returncode=rc,timeout=timed_out,
                 elapsed_s=time.monotonic()-start,stdout=str(out),stderr=str(raw) if raw else 'STDOUT')
    save(out.with_suffix(out.suffix+'.wait.json'),receipt)
    require(type(rc) is int and rc==0 and not timed_out,'Child failed; actual outcome saved '+str(out))
    return receipt


def build():
    require(not OUT.exists(),'Fresh software output only')
    verify(read(HERE.parent/'prepared01/input_pins.json'))
    verify(read(HERE.parent/'prepared01/artifact_pins.json'))
    manifest=read(HERE.parent/'prepared01/manifest.json')
    allcases={c['name']:c for c in manifest['original40']}
    pins=read(HERE.parent/'prepared01/input_pins.json')
    for p in (HERE.parent/'prepared01').rglob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    for p in HERE.glob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    for p in (CC.resolve(),SPIKE,checker.PILOT,checker.old.DECODER):pins[str(p)]=sha(p)
    for n in ('startup.S','runtime.c','replay.ld'):pins[str(RUNTIME/n)]=sha(RUNTIME/n)
    OUT.mkdir();save(OUT/'input_pins.json',pins)
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
           '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
           '-Wl,--build-id=none','-Wl,--gc-sections']
    groups=[]
    for batch in manifest['groups']:
        label=f'group{batch["group"]:02d}';d=OUT/label;d.mkdir();p=d/'prepared';p.mkdir()
        cases=[allcases[n] for n in batch['cases']];save(d/'cases.json',cases)
        for name in ('fixture.h','fixture.c','fixture.S'):shutil.copyfile(HERE/name,p/name)
        shutil.copyfile(HERE.parent/'prepared01'/label/'cases.h',p/'cases.h')
        for name in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(RUNTIME/name,p/name)
        shutil.copyfile(Path(cases[0]['source'])/'scenario.S',p/'original.S')
        execute(['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror','-DHOST_ORACLE',p/'fixture.c','-o',d/'host'],d/'host.compile.log',60)
        execute([d/'host'],d/'host.stdout',60)
        rows=checker.host_check(d/'host.stdout',[c['parameters'] for c in cases])
        proof={}
        helpers=read(source.BASE/'negative_stride_load_original01/software01/source_proof.json')['backend']['soc']['helpers']
        for backend in ('soc','spike'):
            elf=d/(backend+'.elf')
            execute([CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),'-T',p/'replay.ld',
                     *[p/n for n in ('fixture.c','fixture.S','original.S','startup.S','runtime.c')],'-lgcc','-o',elf],d/(backend+'.compile.log'),120)
            execute([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],d/(backend+'.dis'),60)
            execute([CC.with_name('riscv64-unknown-elf-nm'),'-n',elf],d/(backend+'.nm'),60)
            import re
            symbols={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',(d/(backend+'.nm')).read_text(),re.M)}
            save(d/(backend+'.symbols.json'),symbols)
            require(symbols['__bss_end']<0x800f0000,'Runtime memory bound')
            matched=source.helper_locations(elf,helpers)
            code=checker.disassemble((d/(backend+'.dis')).read_text())
            for name,entry in matched.items():require(int(entry['pc'],16)==symbols[name],'Helper byte/symbol mismatch')
            if backend=='spike':require(code.get(symbols['_start']+0x7e)==0xa001,'Original startup park identity')
            proof[backend]=dict(elf=str(elf),sha256=sha(elf),helpers=matched,targets={str(i):dict(pc=hex(symbols[f'fault_{i}_pc']),encoding=hex(code[symbols[f'fault_{i}_pc']])) for i in (0,1)})
        save(d/'source_proof.json',dict(status='SOURCE_DERIVED_NOT_LINUX_IDENTITY',cases=[c['name'] for c in cases],backends=proof,host_phase_rows=rows))
        groups.append(dict(group=label,count=len(cases),host_phase_rows=rows,source_proof_sha256=sha(d/'source_proof.json')))
    execute([sys.executable,'-B',HERE/'test_checker.py'],OUT/'host_negatives.log',120)
    verify(pins)
    save(OUT/'built.json',dict(status='ELF_HOST_READY_REFERENCE_NOT_RUN',groups=groups,actual_isa=ISA))
    save(OUT/'artifact_pins.json',{str(p):sha(p) for p in OUT.rglob('*') if p.is_file()})
    print(json.dumps(dict(status='BUILD_HOST_COMPLETE',groups=len(groups))))


def reference():
    r=HERE/'reference01';require(not r.exists(),'No automatic retry: fresh reference01 required')
    pins={**read(OUT/'input_pins.json'),**read(OUT/'artifact_pins.json')};verify(pins)
    r.mkdir();save(r/'input_pins.json',pins)
    results=[]
    try:
        for group in read(OUT/'built.json')['groups']:
            label=group['group'];d=OUT/label;o=r/label;o.mkdir()
            cmd=[SPIKE,'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2',f'--instructions={LIMIT}','-l','--log-commits',d/'spike.elf']
            save(o/'attempt.json',dict(command=list(map(str,cmd)),started=time.time(),attempt=1,instruction_limit=LIMIT,timeout_s=180,raw_limit_bytes=1024**3))
            execution=execute(cmd,o/'spike.stdout',180,o/'spike.trace',1024**3)
            parse=execute([sys.executable,'-B',HERE/'check_reference.py',d,o],o/'parser.stdout',900)
            verify(pins)
            status=read(o/'status.json')
            save(o/'complete.json',dict(status='REFERENCE_ACCEPTED_NOT_DUT',spike_actual_wait=execution['actual_wait_returncode'],parser_actual_wait=parse['actual_wait_returncode'],
                result_sha256=sha(o/'status.json'),raw_sha256=sha(o/'spike.trace'),raw_bytes=(o/'spike.trace').stat().st_size,pins_unchanged=True))
            results.append(dict(group=label,cases=status['case_count'],firmware_records=status['firmware_records_through_htif'],
                scalar_checks=status['scalar_checks'],spike_elapsed_s=execution['elapsed_s'],parser_elapsed_s=parse['elapsed_s'],
                conservative_m6_estimate_s=status['firmware_records_through_htif']/(858371/1111.6245557051152)*1.2))
            print(json.dumps(results[-1]),flush=True)
        verify(pins);require(sum(g['cases'] for g in results)==38,'Exact38 reference coverage')
        save(r/'complete.json',dict(status='REFERENCE_38_PASS_NOT_DUT',groups=results,pins_unchanged=True,no_dut=True))
        save(r/'artifact_pins.json',{str(p):sha(p) for p in r.rglob('*') if p.is_file()})
    except BaseException as e:
        save(r/'NOT_ACCEPTED.json',dict(status='REFERENCE_INCOMPLETE_STOP_NO_RETRY',error=f'{type(e).__name__}: {e}',completed_groups=results))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','reference']);a=p.parse_args()
    {'build':build,'reference':reference}[a.mode]()
