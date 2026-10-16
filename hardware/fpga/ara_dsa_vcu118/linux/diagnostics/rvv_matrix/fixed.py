"""Fractional multiply and sticky saturation; share the existing scalar model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build

OPS=[(op,'v8, v16') for op in ('vsmul.vv','vsadd.vv','vsaddu.vv','vssub.vv')]
SCALAR_OPS=[(op,'v8, t3') for op in ('vsmul.vx','vsadd.vx','vsaddu.vx','vssub.vx','vssubu.vx',
            'vaadd.vx','vaaddu.vx','vasub.vx','vasubu.vx','vssrl.vx','vssra.vx')]+[
            (op,'v8, -3' if op.startswith('vsadd') else 'v8, 29')
            for op in ('vsadd.vi','vsaddu.vi','vssrl.vi','vssra.vi')]
SCALAR_ORACLE=[20,4,3,6,5,8,7,10,9,11,12,4,3,11,12]

def run(out,cross,scalar_forms=False,restart=False):
    out.mkdir(parents=True,exist_ok=False);binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('oracle.c')
    ops=SCALAR_OPS if scalar_forms else OPS
    header='\n'.join('extern unsigned long op_%d(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);'%i for i in range(len(ops)))
    header+='\n#define OPERATION_COUNT '+str(len(ops))+'\n#define OPERATION_FUNCTIONS '+','.join(f'op_{i}' for i in range(len(ops)))
    header+='\n#define OPERATION_NAMES '+','.join(json.dumps(x[0]) for x in ops)
    header+='\n#define OPERATION_KINDS '+','.join('4' for _ in ops)+'\n#define INTEGER_EXTENSION 1\n#define AGNOSTIC_POLICY 0\n'
    if restart:header+='\n#define RESTART_SUITE 1\n#define TRACE_RESTART_BOUNDARIES 1\n'
    if scalar_forms:
        header+='\n#define FIXED_SCALAR_SUITE 1\n#define SCALAR_ORACLE '+','.join(map(str,SCALAR_ORACLE))
        header+='\n#define SCALAR_IMMEDIATE '+','.join('1' if x[0].endswith('.vi') else '0' for x in ops)+'\n'
        header+='\n#define SCALAR_IMMEDIATE_VALUES '+','.join(
            '29' if x[0] in ('vssrl.vi','vssra.vi') else '-3' for x in ops)+'\n'
    (out/'operations.h').write_text(header)
    manifest=dict(scope=('Scalar/immediate saturation, averaging, rounding shifts and fractional multiply' if scalar_forms else 'Fractional multiply and vector saturation')+
                  '; four vxrm and sticky vxsat 0/1, four predicates'+('; restart' if restart else '; vstart=0'),cases=[],
                  operations=[x[0] for x in ops],restart_tested=restart,scalar_forms=scalar_forms,
                  restart_points=['one','half_vl','vl_if_representable','last_capacity_element'] if restart else ['zero'],
                  max_vstart='8*vlenb-1',configurations_per_elf=len(ops)*3*7*4*8*(4 if restart else 1))
    for sew,lmul in build.shapes():
        name=f'rvv_fixed_{"scalar_" if scalar_forms else ""}{"restart_" if restart else ""}e{sew}_{lmul}';asm=out/(name+'.S')
        asm.write_text(build.assembly(sew,lmul,extra=True,operations=ops,sticky_sat=True,scalar_from_input=scalar_forms))
        binary=binaries/name
        subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
            '-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',
            f'-DSEW={sew}','-DFRACTIONAL_SUITE=1','-I'+str(out),str(source),str(asm),'-lgcc','-o',str(binary)],check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                                     pass_marker='RVV_MATRIX_PASS',timeout_seconds=180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,Path(__file__),Path(build.__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),stdout=stream,cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--cross',required=True)
    p.add_argument('--scalar-forms',action='store_true')
    p.add_argument('--restart',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.scalar_forms,a.restart)
