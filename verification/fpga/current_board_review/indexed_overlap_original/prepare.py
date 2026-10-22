#!/usr/bin/env python3
"""Rebuild archived identities and prepare three source-faithful Sv39 references. No VCS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
sys.path.insert(0, str(HERE.parent / 'masked_translation'))
import sv39_adapter as base

NAMES = ('d32m2_i64_fault_ov1', 'd32m2_i64_resident_ov1', 'd32m2_i64_fault_ov0')
ISA = 'rv64gcv_zfh_zvfh_zvl1024b'

def prepare(out):
    base.require(out.parent == HERE and not out.exists(), 'Fresh direct child output required')
    out.mkdir()
    source = ARCHIVE / 'vector_width_probe.c'
    assembly = ARCHIVE / 'vector_width_probe.S'
    base.require(base.sha(source) == '64f95f20d87d405c81f8e0848efc72390391d1b0312037c6001ac3e66558c74b', 'C changed')
    base.require(base.sha(assembly) == 'ea838ecf30290c56134d4ad5972f08288bc573d92d8217ff41349e6d00748fa8', 'ASM changed')
    manifest = ARCHIVE / 'width_restart04_live.json'
    cases = {c['name']: c for c in json.loads(manifest.read_text())['inputs']['cases']}
    pins = {str(p):base.sha(p) for p in (source, assembly, manifest, Path(__file__), HERE/'fixture.c', HERE/'fixture.S', HERE/'check_reference.py', base.CC, base.SPIKE)}
    for n in ('startup.S', 'runtime.c', 'replay.ld'):
        p = base.PARENT/n
        pins[str(p)] = base.sha(p)
        shutil.copyfile(p, out/n)
    shutil.copyfile(source, out/'original.c')
    shutil.copyfile(assembly, out/'original.S')
    for n in ('fixture.c','fixture.S','check_reference.py','test_oracle.py'): shutil.copyfile(HERE/n,out/n)
    pins[str(HERE/'test_oracle.py')]=base.sha(HERE/'test_oracle.py')
    for p in (Path(base.__file__),base.BASE/'prepare.py',base.ROOT/'verification/coverage/scoped_rv64c_memory.py'):
        pins[str(p)]=base.sha(p)
    base.run_logged([sys.executable,HERE/'test_oracle.py'],out/'host_negative.json')
    shutil.copytree(HERE/'compat',out/'compat')
    pins[str(HERE/'compat/sys/resource.h')]=base.sha(HERE/'compat/sys/resource.h')
    # Host only: replace the Linux inline-assembly syscall boundary, not the oracle.
    ctext = source.read_text()
    a, b = ctext.index('static long call('), ctext.index('static void text(')
    (out/'host_original.c').write_text(ctext[:a] + 'static long call(long,long,long,long,long,long,long);\n' + ctext[b:])
    identities=[]
    for name in NAMES:
        case=cases[name]; work=out/name; work.mkdir()
        cmd=case['command'].copy(); original=Path(cmd[-1]); cmd[-1]=str(work/'original.elf')
        base.require(base.sha(original)==case['sha256'],'Archived ELF identity changed')
        pins[str(original)]=case['sha256']; pins[cmd[0]]=base.sha(Path(cmd[0]).resolve())
        base.run_logged(cmd,work/'original.compile.log')
        base.require(base.sha(work/'original.elf')==case['sha256'],'Original C/ASM does not reconstruct ELF '+name)
        identities.append(dict(name=name,metadata=case,rebuild_command=cmd,byte_identical=True))
        base.save(out/'identities.json',identities)
        base.save(out/'pins.json',pins)
        defines=[x for x in cmd if x.startswith('-D')]
        common=['-I',out/'compat','-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
            '-nostdlib','-static','-Wl,--build-id=none','-T',out/'replay.ld',*defines]
        base.run_logged(['/usr/bin/cc','-O2','-DIO_HOST',*defines,out/'fixture.c','-o',work/'host'],work/'host.compile.log')
        base.run_logged([work/'host'],work/'host.stdout')
        for backend in ('soc','spike'):
            elf=work/(backend+'.elf')
            base.run_logged([base.CC,*common,*(['-DSPIKE_REFERENCE'] if backend=='spike' else []),
                out/'fixture.c',out/'fixture.S',out/'original.S',out/'startup.S',out/'runtime.c','-lgcc','-o',elf],work/(backend+'.compile.log'))
            base.run_logged([base.CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],work/(backend+'.dis'))
            nm=subprocess.check_output([str(base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True)
            symbols={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
            base.save(work/(backend+'.symbols.json'),symbols)
            base.require(symbols['__bss_end']<0x800e0000,'Memory budget exceeded')
        base.run_logged([base.SPIKE,'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2','-l','--log-commits',work/'spike.elf'],
            work/'spike.stdout',work/'spike.trace',timeout=180)
        import check_reference
        status=check_reference.validate(work,case)
        base.save(work/'status.json',status)
        print(name,status['status'],status['commits'],flush=True)
    for p,h in pins.items(): base.require(base.sha(p)==h,'Input changed '+p)
    base.save(out/'identities.json',identities)
    base.save(out/'pins.json',pins)
    base.save(out/'status.json',dict(status='THREE_HOST_SPIKE_REFERENCES_PASS_NOT_DUT',isa=ISA,cases=list(NAMES),VCS_launched=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True)
    prepare(p.parse_args().out.resolve())
