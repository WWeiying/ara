#!/usr/bin/env python3
"""Freeze eight successor probes; import sealed builder/runtime without edits."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
COMPARISON=PARENT.parent/'comparison'
sys.path.insert(0,str(COMPARISON))
from prepare_build import build,sha,save,INTEGRATION

CASES=[
    ('prestart_snan_eq',0,5,0,0x7c55,1),
    ('inactive_snan_eq',0,17,1,0x7c55,1),
    ('active_snan_eq',0,21,0,0x7c55,17),
    ('active_qnan_eq',0,21,1,0x7e55,1),
    ('active_qnan_ne',1,21,0,0x7e55,1),
    ('active_qnan_lt',2,21,1,0x7e55,17),
    ('prestart_snan_le',3,5,1,0x7c55,1),
    ('tail_snan_lt',2,37,0,0x7c55,1),
]

def main():
    parent=json.loads((PARENT/'preflight01.json').read_text())
    for p,digest in parent['pins'].items():
        if sha(Path(p))!=digest: raise ValueError('Sealed parent input drift: '+p)
    out=HERE/'prepared01'; out.mkdir(exist_ok=False)
    host=HERE/'host01'; host.mkdir(exist_ok=False)
    for name in ('startup.S','runtime.c','replay.ld','capture.S'):
        shutil.copyfile(PARENT/'prepared01'/name,out/name)
    records=[]; host_results=[]
    for name,op,index,side,bits,flags in CASES:
        directory=out/name; (directory/'original').mkdir(parents=True)
        shutil.copyfile(HERE/'control.c',directory/'case.c')
        mnemonic=('vmfeq','vmfne','vmflt','vmfle')[op]
        assembly=(PARENT/'compare.S').read_text().replace('vmfeq.vv v24,v8,v16,v0.t',mnemonic+'.vv v24,v8,v16,v0.t')
        (directory/'original/scenario.S').write_text(assembly)
        defines=[f'SOURCE_MAIN={name}_main',f'OP={op}',f'NAN_INDEX={index}',f'NAN_SIDE={side}',f'NAN_BITS={bits}',f'EXPECTED_FLAGS={flags}']
        command=['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-DHOST_CHECK',f'-DCASE_NAME="{name}"',
                 *['-D'+d for d in defines],str(directory/'case.c'),'-o',str(host/name)]
        compiled=subprocess.run(command,text=True,capture_output=True)
        if compiled.returncode: raise RuntimeError(compiled.stderr)
        result=subprocess.run([str(host/name)],text=True,capture_output=True)
        host_results.append(dict(name=name,compile_command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
        save(host/'results.json',host_results)
        if result.returncode: raise RuntimeError(name+' host failure '+str(result.returncode))
        marker=f'FP_NV_PASS {name} cases=1 errors=0 data=0 setup=0 csr=0 flag_errors=0 expected_flags={flags} actual_flags={flags} start_after=0'
        records.append(dict(id=name,sew=16,control=0,defines=defines,pass_marker=marker,
            opcode=mnemonic+'.vv',nan_index=index,nan_side='rhs' if side else 'lhs',nan_bits=hex(bits),
            expected_fflags=flags,vl=32,vstart=16,lmul='m1',predicate16_31='0xd6ad'))
    dependencies=[PARENT/'compare.S',PARENT/'control.c',PARENT/'preflight01.json',COMPARISON/'prepare_build.py',
                  COMPARISON/'reference.py',INTEGRATION/'prepare.py',INTEGRATION/'run.py']
    provenance=dict(schema_version=1,vlen=1024,nr_lanes=4,cases=records,
        scope='NEW directed successor controls, not archived original cases; original/ is builder API naming only',
        dependencies={str(p):sha(p) for p in dependencies},
        source_pins={str(p):sha(p) for p in (HERE/'control.c',Path(__file__))})
    provenance['files']={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    save(out/'provenance.json',provenance)
    build(out,provenance,True,HERE/'spike01')
    build(out,provenance,False,HERE/'soc01')
    print('HOST_NV_8_PASS; source/ELFs prepared; no VCS launch')

if __name__=='__main__': main()
