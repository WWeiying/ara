"""Conditional single GCC build per backend; never execute generated binaries."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
GEN=ROOT/'generated01'
OLD=ROOT.parent/'full777_optimized_prepare01/prepared01'
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
CC_SHA='7af14c2b2b9f8ce5dc7b07521a929537a5306078df2a3a20bb367b7448828bbc'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def save(p,d):
    with p.open('x') as f: json.dump(d,f,indent=2); f.write('\n')
def require(c,s):
    if not c: raise ValueError(s)
def run(stem,args):
    rc=subprocess.run([sys.executable,str(HERE/'run_bound.py'),'--stem',str(stem),
        '--timeout','120','--',*map(str,args)],check=False).returncode
    require(rc==0,'Compile/artifact tool failed; no retry: '+str(stem))

def main():
    host=HERE/'host01'
    completed=HERE/'ubsan_trap01/HOST_COMPOSITE.json'
    done=read(completed)
    require(done['status']=='ORIGINAL_C_FULL10752_HOST_COMPOSITE_ACCEPTED','Host not accepted')
    require(len(done['accepted_receipts'])==18,'Sixteen planned receipts plus compile/run UB trap control')
    for p,w in done['accepted_receipts'].items():
        require(read(Path(p))==w and type(w['actual_wait_exit']) is int and
            w['actual_wait_exit']==w['expected_exit'] and not w['timed_out'] and w['error'] is None,'Host outcome '+p)
    inputs=read(HERE/'ubsan_trap01/inputs_after.json')
    require(inputs==read(host/'inputs_before.json')==done['input_pins'],'Host pins changed')
    inputs.update(done['evidence_pins'])
    for p,h in inputs.items(): require(sha(Path(p))==h,'Host/source drift '+p)
    review=ROOT/'source_review01/HOST_ENTRY_REVIEW01.json'
    require(sha(review)=='cc0d15956cde6fa50c7ed4972533d1c77151b89afbe09265bf8203627dc6bc54',
            'Exact independent Host entry review')
    inputs[str(review)]=sha(review)
    require(sha(CC)==CC_SHA,'Mature GCC identity; no compiler substitute')
    inputs.update({str(CC):CC_SHA,str(completed):sha(completed)})
    for p in (HERE/'main.c',HERE/'compile_stage.py'):
        inputs[str(p)]=sha(p)
    oldpins=read(OLD/'input_pins.json')
    for name in ('runtime.c','startup.S','replay.ld'):
        p=OLD/'prepared'/name
        require(sha(p)==oldpins[str(p)],'Sealed mature runtime identity '+str(p))
        inputs[str(p)]=sha(p)
    out=HERE/'compile01'; out.mkdir(exist_ok=False)
    save(out/'inputs_before.json',inputs)
    try:
        for name in ('runtime.c','startup.S','replay.ld'):
            with (out/name).open('xb') as f: f.write((OLD/'prepared'/name).read_bytes())
        flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
            '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
            '-Wl,--build-id=none','-Wl,--gc-sections','-T',str(out/'replay.ld')]
        for backend in ('soc','spike'):
            d=out/backend; d.mkdir()
            elf=d/'program.elf'
            command=[CC,*flags,'-DSEW=8','-DFRACTIONAL_SUITE=1','-I'+str(GEN)]
            if backend=='spike': command+=['-DSPIKE_REFERENCE=1']
            command+=[GEN/'case.c',GEN/'scenario.S',HERE/'main.c',out/'startup.S',out/'runtime.c',
                '-lgcc','-Wl,-Map,'+str(d/'program.map'),'-o',elf]
            run(d/'compile',command)
            run(d/'dis',[CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf])
            run(d/'symbols',[CC.with_name('riscv64-unknown-elf-nm'),'-n','-S',elf])
            run(d/'sections',[CC.with_name('riscv64-unknown-elf-readelf'),'-l','-S',elf])
        for p,h in inputs.items(): require(sha(Path(p))==h,'Compile input drift '+p)
        save(out/'inputs_after.json',inputs)
        save(out/'COMPILED.json',dict(status='COMPILED_ONCE_EACH_ARTIFACT_CFG_AUDIT_PENDING',
            backends={b:dict(elf_sha256=sha(out/b/'program.elf'),
                actual_compile_wait=read(out/b/'compile.wait.json')) for b in ('soc','spike')},
            pins_unchanged=True,reference_executed=False,DUT_executed=False))
    except Exception as exc:
        save(out/'FIRST_FAILURE.json',dict(status='STOPPED',error=repr(exc))); raise

if __name__=='__main__': main()
