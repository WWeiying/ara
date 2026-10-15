#!/usr/bin/env python3
"""One bounded reference per exact direction/privilege; never a DUT build/run."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import check as o
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('sv39_scaffold',HERE.parent/'masked_translation/sv39_adapter.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
ISA='rv64gcv_zfh_zvfh_zvl1024b'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):
    with p.open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def command(cmd,out,timeout=30):
    cmd=list(map(str,cmd));save(out.with_suffix(out.suffix+'.command.json'),cmd)
    start=time.monotonic()
    with out.open('x') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    save(out.with_suffix(out.suffix+'.exit.json'),dict(returncode=p.returncode,elapsed_s=time.monotonic()-start))
    o.need(p.returncode==0,'Command failed: '+str(out))

def negatives(spec,st,sv):
    s=spec['symbols'];tests=[]
    for label,index in [('firstcheck',0),('trapvstart',12),('guard',36),('finalcheck',len(o.gold(s,st,sv))-1)]:
        c=o.Observer(spec,st,sv);c.calls=index;c.regs[10]=c.g[index]^1;c.regs[11]=c.g[index]
        try:c.step(s['mt_check'],c.code[s['mt_check']],{})
        except ValueError:tests.append(label);continue
        raise ValueError('Negative accepted '+label)
    c=o.Observer(spec,st,sv);c.retry=True
    try:c.step(s['mt_restore_start'],c.code[s['mt_restore_start']],{})
    except ValueError:tests.append('missing_known_vstart')
    else:raise ValueError('Untracked vstart accepted')
    return tests

def main():
    ap=argparse.ArgumentParser();ap.add_argument('member',choices=['load_m','store_m','load_sv39','store_sv39']);a=ap.parse_args()
    st=a.member.startswith('store');sv=a.member.endswith('sv39')
    out=HERE/('reference_'+a.member+'01');out.mkdir(exist_ok=False)
    try:
        base.prepare.check(base.PARENT)
        sources=[HERE/n for n in ('fixture.c','fixture.S','check.py','reference.py')]
        sources += [Path(base.__file__),Path(o.decoder.__file__),base.CC.resolve(),base.SPIKE,Path('/usr/bin/cc').resolve()]
        sources += [base.PARENT/n for n in ('startup.S','runtime.c','replay.ld','provenance.json')]
        pins={str(p):sha(p) for p in sources};save(out/'input_pins.json',pins)
        p=out/'prepared';p.mkdir()
        for n in ('fixture.c','fixture.S'):shutil.copyfile(HERE/n,p/n)
        for n in ('startup.S','runtime.c','replay.ld'):shutil.copyfile(base.PARENT/n,p/n)
        save(p/'provenance.json',dict(scope='New M9 precise strided-alignment boundary, not original Linux replay',store=st,sv39=sv,
                                     runtime_parent=str(base.PARENT),files={q.name:sha(q) for q in p.iterdir() if q.is_file()}))
        command(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DALIGN_HOST',p/'fixture.c','-o',out/'host'],out/'host.compile.log')
        command([out/'host'],out/'host.stdout',10)
        gold=[f'{i} {o.seed(i):016x} {o.data(0,i):016x} {o.data(1,i):016x}' for i in range(16)]
        o.need((out/'host.stdout').read_text().splitlines()==gold,'Independent Host source oracle')
        flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
               '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
               '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
               '-Wl,--build-id=none','-Wl,--gc-sections','-T',p/'replay.ld',f'-DSTORE={int(st)}',f'-DSV39={int(sv)}']
        specs={}
        for backend in ('soc','spike'):
            elf=out/(backend+'.elf')
            command([base.CC,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                     *[p/n for n in ('fixture.c','fixture.S','startup.S','runtime.c')],'-lgcc','-o',elf],out/(backend+'.compile.log'))
            command([base.CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],out/(backend+'.dis'))
            command([base.CC.with_name('riscv64-unknown-elf-nm'),'-n',elf],out/(backend+'.nm'))
            s={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',(out/(backend+'.nm')).read_text(),re.M)}
            code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
                     (out/(backend+'.dis')).read_text(),re.M)}
            o.need(s['__bss_end']<0x800f0000 and s['mt_root']%4096==0,'Small runtime geometry')
            o.need(code[s['mt_target']]==(0x0a757c27 if st else 0x0a757c07),'Exact target opcode')
            specs[backend]=dict(symbols=s,code=code,elf=str(elf),elf_sha256=sha(elf))
            save(out/(backend+'.spec.json'),specs[backend])
        rejected=negatives(specs['spike'],st,sv)
        save(out/'host.json',dict(status='HOST_PASS_NOT_DUT',oracle_rows=16,negative_rejections=rejected,
             full_scalar_checks=len(o.gold(specs['spike']['symbols'],st,sv))+14))
        cmd=[str(base.SPIKE),'--isa='+ISA,'--priv=msu','--pmpregions=0','-m2','--instructions=200000',
             '-l','--log-commits',str(out/'spike.elf')]
        save(out/'reference_attempt.json',dict(command=cmd,timeout_s=120,instruction_bound=200000,
              raw_limit_bytes=64*1024**2,one_attempt_only=True))
        def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
        start=time.monotonic()
        with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as stderr:
            proc=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=120,preexec_fn=limit)
        receipt=dict(returncode=proc.returncode,elapsed_s=time.monotonic()-start,raw_bytes=(out/'spike.trace').stat().st_size)
        save(out/'reference_exit.json',receipt);o.need(proc.returncode==0,'Reference exit failed')
        result=o.reference(out/'spike.trace',specs['spike'],st,sv)
        result.update(status='HOST_SPIKE_PASS_NOT_DUT',member=a.member,actual_profile=ISA,receipt=receipt)
        o.need(all(sha(k)==v for k,v in pins.items()),'Reference pins drift')
        save(out/'status.json',result)
        save(out/'READY.json',dict(status='HOST_SPIKE_PASS_NOT_DUT',member=a.member,
             input_pins=pins,outputs={str(q.relative_to(out)):sha(q) for q in out.rglob('*') if q.is_file()},VCS_launched=False))
        print(json.dumps(result,indent=2))
    except BaseException as e:
        save(out/'not_completed.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=repr(e)))
        raise

if __name__=='__main__':main()
