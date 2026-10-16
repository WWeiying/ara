"""Build independently bounded RVV shape tests, not hardware acceptance."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess

OPS = [
    ('vadd.vv','v8, v16'), ('vsub.vv','v8, v16'),
    ('vand.vv','v8, v16'), ('vor.vv','v8, v16'), ('vxor.vv','v8, v16'),
    ('vsll.vv','v8, v16'), ('vsrl.vv','v8, v16'), ('vsra.vv','v8, v16'),
    ('vminu.vv','v8, v16'), ('vmaxu.vv','v8, v16'),
    ('vmin.vv','v8, v16'), ('vmax.vv','v8, v16'),
    ('vmul.vv','v8, v16'), ('vdivu.vv','v8, v16'), ('vremu.vv','v8, v16'),
    ('vdiv.vv','v8, v16'), ('vrem.vv','v8, v16'),
    ('vadd.vx','v8, t3'), ('vadd.vi','v8, 3'),
    ('vslideup.vi','v8, 2'), ('vslidedown.vi','v8, 2'),
    ('vrgather.vv','v8, v16'), ('vredsum.vs','v8, v16'),
    ('vcompress.vm','v8, v0'), ('load','(a0)'),
]
FP_OPS=[('vfadd.vv','v8, v16'),('vfsub.vv','v8, v16'),
        ('vfmul.vv','v8, v16'),('vfdiv.vv','v8, v16'),
        ('vfmin.vv','v8, v16'),('vfmax.vv','v8, v16'),
        ('vfsgnj.vv','v8, v16'),('vfsgnjn.vv','v8, v16'),
        ('vfsgnjx.vv','v8, v16'),('vfsqrt.v','v8')]
FP_VALUES=[-8.0,-2.0,-0.0,0.0,0.5,1.0,2.0,8.0]
LMULS = [('mf8',1,8),('mf4',1,4),('mf2',1,2),
         ('m1',1,1),('m2',2,1),('m4',4,1),('m8',8,1)]
EXTRA_OPS=[(op,'v8, v16') for op in (
    'vmulhu.vv','vmulh.vv','vmulhsu.vv',
    'vsaddu.vv','vsadd.vv','vssubu.vv','vssub.vv',
    'vaaddu.vv','vaadd.vv','vasubu.vv','vasub.vv',
    'vssrl.vv','vssra.vv',
    'vredand.vs','vredor.vs','vredxor.vs',
    'vredminu.vs','vredmaxu.vs','vredmin.vs','vredmax.vs')]

def shapes():
    return [(sew,lmul) for sew in (8,16,32,64) for lmul,num,den in LMULS
            if 64*num >= sew*den]

def assembly(sew,lmul,extra=False,agnostic=False,operations=None,sticky_sat=False,scalar_from_input=False):
    load=f'vle{sew}.v'; store=f'vse{sew}.v'
    policy='ta, ma' if agnostic else 'tu, mu'
    lines=['.text','.global capacity','capacity:',
           f'li t0, -1',f'vsetvli a0, t0, e{sew}, {lmul}, tu, mu','ret']
    if operations is None:operations=EXTRA_OPS if extra else OPS+(FP_OPS if sew>=32 else [])
    for i,(op,args) in enumerate(operations):
        lines += [f'.global op_{i}',f'op_{i}:',
                  f'vsetvli t0, a4, e{sew}, {lmul}, tu, mu',
                  f'{load} v8, (a0)',f'{load} v16, (a1)',
                  f'{load} v24, (a2)','vlm.v v0, (a5)',
                  f'vsetvli t0, a3, e{sew}, {lmul}, {policy}',
                  (f'{ {8:"lb",16:"lh",32:"lw",64:"ld"}[sew]} t3, 0(a1)' if scalar_from_input else 'li t3, 7'),
                  'csrw vstart, a6']
        if extra:
            lines += ['csrr t4, vxrm','csrr t5, vxsat']
            lines += ['andi t2, a7, 3','csrw vxrm, t2'] if sticky_sat else ['csrw vxrm, a7']
            lines += ['srli t2, a7, 2','csrw vxsat, t2'] if sticky_sat else ['csrwi vxsat, 0']
        if op=='vcompress.vm':
            lines += [f'{op} v24, {args}']
        elif op=='load':
            lines += [f'{load} v24, {args}, v0.t']
        else:
            lines += [f'{op} v24, {args}, v0.t']
        lines += ['csrr a0, vstart',
                  *(['csrr t1, vxsat','slli t1, t1, 32','or a0, a0, t1',
                     'csrw vxrm, t4','csrw vxsat, t5'] if extra else []),
                  f'vsetvli t0, a4, e{sew}, {lmul}, tu, mu',
                  f'{store} v24, (a2)','ret']
    return '\n'.join(lines)+'\n'

def fp_header(sew):
    if sew<32:return ''
    fmt='f' if sew==32 else 'd'
    def bits(x):
        if math.isnan(x):return 0x7fc00000 if sew==32 else 0x7ff8000000000000
        return int.from_bytes(struct.pack('<'+fmt,x),'little')
    table=[]
    for op in range(len(FP_OPS)):
        row=[]
        for a in FP_VALUES:
            for b in FP_VALUES:
                if op==0:x=a+b
                elif op==1:x=a-b
                elif op==2:x=a*b
                elif op==3:
                    if b==0:
                        x=float('nan') if a==0 else math.copysign(float('inf'),math.copysign(1,a)*math.copysign(1,b))
                    else:x=a/b
                elif op in (4,5):
                    if a==b==0:
                        negative=(math.copysign(1,a)<0 or math.copysign(1,b)<0) if op==4 else (math.copysign(1,a)<0 and math.copysign(1,b)<0)
                        x=-0.0 if negative else 0.0
                    else:x=min(a,b) if op==4 else max(a,b)
                elif op in (6,7,8):
                    sign=math.copysign(1,b)
                    if op==7:sign=-sign
                    if op==8:sign*=math.copysign(1,a)
                    x=math.copysign(abs(a),sign)
                else:x=math.sqrt(a) if a>=0 else float('nan')
                row.append(bits(x))
        table.append(row)
    literal=lambda x:'UINT64_C(0x%x)'%x
    return ('static const word fp_inputs[8] = {'+', '.join(literal(bits(x)) for x in FP_VALUES)+'};\n'+
            'static const word fp_expected[%d][64] = {\n'%len(FP_OPS)+
            ',\n'.join('{'+', '.join(map(literal,row))+'}' for row in table)+'\n};\n')

def build(out,cross,trace_op0=False,only=None,extra=False,agnostic=False):
    source=Path(__file__).resolve().parent
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests'; binaries.mkdir(parents=True)
    manifest=dict(scope='Integer/permutation/masked-load shape matrix; no exhaustive ISA claim',cases=[],
                  operations=[x[0] for x in (EXTRA_OPS if extra else OPS+FP_OPS)],seeds=3,
                  pending_families=['fp16_flags_rounding_nan_payload','widen_narrow_fixed_point','mask_result',
                                    'strided_indexed_segment_store','fault_first','context_signal'],
                  source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (source/'oracle.c',Path(__file__))})
    selected_shapes=[shape for shape in shapes()
                     if only is None or 'e%d_%s'%shape in only]
    if not selected_shapes:raise ValueError('No legal shapes selected')
    manifest['trace_op0']=trace_op0
    manifest.update(integer_extension=extra,agnostic_policy=agnostic,
                    restart_tested=not extra,rounding_modes=4 if extra else 0)
    for sew,lmul in selected_shapes:
        ops=EXTRA_OPS if extra else OPS+(FP_OPS if sew>=32 else [])
        header_dir=out/f'e{sew}';header_dir.mkdir(exist_ok=True)
        declarations=['extern unsigned long op_%d(const word *, const word *, word *, unsigned long, unsigned long, const uint8_t *, unsigned long, unsigned long);'%i for i in range(len(ops))]
        kinds=[0]*19+[1,1,1,2,3,0]+([0]*len(FP_OPS) if sew>=32 else [])
        if extra:kinds=[4]*13+[2]*7
        header='\n'.join(declarations)+'\n'
        header+='#define OPERATION_COUNT %d\n'%len(ops)
        header+='#define OPERATION_FUNCTIONS '+', '.join('op_%d'%i for i in range(len(ops)))+'\n'
        header+='#define OPERATION_NAMES '+', '.join(json.dumps(x[0]) for x in ops)+'\n'
        header+='#define OPERATION_KINDS '+', '.join(map(str,kinds))+'\n'
        header+='#define INTEGER_EXTENSION %d\n#define AGNOSTIC_POLICY %d\n'%(extra,agnostic)
        if not extra:header+=fp_header(sew)
        (header_dir/'operations.h').write_text(header)
        name=f'rvv_{"extra" if extra else "matrix"}_e{sew}_{lmul}'+('_agnostic' if agnostic else '')
        asm=out/(name+'.S'); asm.write_text(assembly(sew,lmul,extra,agnostic))
        binary=binaries/name
        command=[cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d',
                 '-nostdlib','-static','-ffreestanding','-fno-builtin',
                 '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
                 '-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
                 '-Wall','-Wextra','-Werror',f'-DSEW={sew}','-I'+str(header_dir),
                 str(source/'oracle.c'),str(asm),'-lgcc','-o',str(binary)]
        if trace_op0:command.insert(1,'-DTRACE_OP0=1')
        subprocess.run(command,check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_MATRIX_PASS',timeout_seconds=3600,command=command))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],
                       input=('\n'.join(entries)+'\n').encode(),stdout=stream,
                       cwd=out/'overlay',check=True)
    print('BUILT',len(manifest['cases']),'shapes, up to',len(OPS+FP_OPS),'operations')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True)
    p.add_argument('--trace-op0',action='store_true')
    p.add_argument('--integer-extension',action='store_true')
    p.add_argument('--agnostic',action='store_true')
    p.add_argument('--only',nargs='+',choices=['e%d_%s'%s for s in shapes()])
    a=p.parse_args();build(a.out,a.cross,a.trace_op0,a.only,a.integer_extension,a.agnostic)
