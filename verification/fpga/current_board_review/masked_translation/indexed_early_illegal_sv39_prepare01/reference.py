#!/usr/bin/env python3
"""Prepare one member, then its unique bounded Spike reference; never DUT."""
import argparse
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
import oracle as o
base=o.base
HERE=Path(__file__).resolve().parent
ISA='rv64gcv_zfh_zvfh_zvl1024b'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n')


def command(cmd,out,timeout=30):
    cmd=list(map(str,cmd));save(out.with_suffix(out.suffix+'.command.json'),cmd)
    start=time.monotonic()
    with out.open('x') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    save(out.with_suffix(out.suffix+'.exit.json'),dict(returncode=p.returncode,elapsed_s=time.monotonic()-start))
    o.require(p.returncode==0,'Command failed: '+str(out))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('member',choices=['indexed']);a=ap.parse_args()
    store=0;out=HERE/('reference_'+a.member+'01');out.mkdir(exist_ok=False)
    try:
        parent=base.prepare.check(base.PARENT)
        files=[HERE/n for n in ('fixture.c','fixture.S','oracle.py','reference.py')]
        files += [HERE.parent/n for n in ('sv39_fixture.c','sv39_fixture.S','sv39_adapter.py')]
        files += [HERE.parent/'mask_drain_sv39_prepare01'/n for n in ('fixture.c','fixture.S','oracle.py','reference.py')]
        files += [base.PARENT/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
        files += [base.BASE/'prepare.py',base.CC.resolve(),base.SPIKE,
                  base.ROOT/'verification/coverage/scoped_rv64c_memory.py',Path('/usr/bin/cc').resolve()]
        pins={str(p):sha(p) for p in files};save(out/'input_pins.json',pins)
        prepared=out/'prepared';prepared.mkdir()
        for n in ('fixture.c','fixture.S'):shutil.copyfile(HERE/n,prepared/n)
        for n in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(base.PARENT/n,prepared/n)
        save(prepared/'provenance.json',dict(files={p.name:sha(p) for p in prepared.iterdir()},
             parent_runtime_sha256={n:parent['files'][n] for n in ('startup.S','runtime.c','replay.ld')},
             scope='New indexed VL3 prefix/alignment recovery; not archived Linux replay',store=bool(store)))
        command(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DMD_HOST',f'-DSTORE={store}',
                 prepared/'fixture.c','-o',out/'host'],out/'host.compile.log')
        command([out/'host'],out/'host.stdout',10)
        host_rows=o.host_check((out/'host.stdout').read_text(),store)
        flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding',
               '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
               '-msmall-data-limit=0','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror',
               '-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections','-T',prepared/'replay.ld']
        allsymbols={}
        for backend in ('soc','spike'):
            elf=out/(backend+'.elf')
            command([base.CC,*flags,f'-DSTORE={store}',*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                     *[prepared/n for n in ('fixture.c','fixture.S','startup.S','runtime.c')],'-lgcc','-o',elf],out/(backend+'.compile.log'))
            command([base.CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],out/(backend+'.dis'))
            command([base.CC.with_name('riscv64-unknown-elf-nm'),'-n',elf],out/(backend+'.nm'))
            symbols={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',(out/(backend+'.nm')).read_text(),re.M)}
            save(out/(backend+'.symbols.json'),symbols);allsymbols[backend]=symbols
            o.require(symbols['__bss_end']<0x800f0000,'Runtime memory bound')
            dis=(out/(backend+'.dis')).read_text()
            for label,insn in o.SITES.items():
                o.require(re.search(r'<'+label+r'>:\n\s*[0-9a-f]+:\s+'+f'{insn:08x}'+r'\b',dis),'Actual opcode mismatch '+label)
        negative=o.negatives(allsymbols['spike'],store)
        save(out/'host.json',dict(status='HOST_ORACLE_AND_NEGATIVES_PASS',oracle_rows=host_rows,rejected=negative))
        cmd=[str(base.SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2',
             '--instructions=500000','-l','--log-commits',str(out/'spike.elf')]
        save(out/'reference_attempt.json',dict(command=cmd,timeout_s=120,raw_limit_bytes=128*1024**2,
             instruction_bound=500000,one_attempt_only=True,started=time.time(),
             elf_sha256=sha(out/'spike.elf')))
        def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,128*1024**2))
        start=time.monotonic()
        with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as stderr:
            p=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=120,preexec_fn=limit)
        receipt=dict(returncode=p.returncode,elapsed_s=time.monotonic()-start,raw_bytes=(out/'spike.trace').stat().st_size)
        save(out/'reference_exit.json',receipt)
        o.require(p.returncode==0,'Spike process failed')
        result=o.validate(out/'spike.trace',allsymbols['spike'],store)
        result.update(receipt=receipt,isa=ISA,host_rows=host_rows,host_negative_count=len(negative),
                      raw_sha256=sha(out/'spike.trace'),soc_elf_sha256=sha(out/'soc.elf'),spike_elf_sha256=sha(out/'spike.elf'))
        o.require(all(sha(p)==h for p,h in pins.items()),'Reference input drift')
        save(out/'status.json',result)
        outputs={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
        save(out/'READY.json',dict(status='HOST_SPIKE_PASS_NOT_DUT',member=a.member,
             runtime_name='indexed_prefix_vl3',outputs=outputs,input_pins=pins,
             reference_status_sha256=sha(out/'status.json'),VCS_launched=False))
        print(json.dumps(result,indent=2))
    except BaseException as e:
        save(out/'not_completed.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=repr(e)))
        raise


if __name__=='__main__':main()

