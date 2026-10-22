"""Build packed-mask and scalar-mask-result oracles using the matrix toolchain."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build

OPS=['vmseq.vv','vmsne.vv','vmsltu.vv','vmslt.vv','vmsleu.vv','vmsle.vv',
     'vmadc.vvm','vmsbc.vvm','vmand.mm','vmnand.mm','vmandn.mm',
     'vmxor.mm','vmor.mm','vmnor.mm','vmorn.mm','vmxnor.mm',
     'vcpop.m','vfirst.m','viota.m','vid.v','vmsbf.m','vmsif.m','vmsof.m']
CARRY_SPECS=[
    ('vmadc.vvm','v8,v16',6,0,0,1),('vmadc.vxm','v8,t3',6,1,0,1),
    ('vmadc.vim','v8,-16',6,2,-16,1),('vmadc.vim','v8,15',6,2,15,1),
    ('vmsbc.vvm','v8,v16',7,0,0,1),('vmsbc.vxm','v8,t3',7,1,0,1),
    ('vmadc.vv','v8,v16',6,0,0,0),('vmadc.vx','v8,t3',6,1,0,0),
    ('vmadc.vi','v8,-16',6,2,-16,0),('vmadc.vi','v8,15',6,2,15,0),
    ('vmsbc.vv','v8,v16',7,0,0,0),('vmsbc.vx','v8,t3',7,1,0,0)]

def assembly(sew,lmul,scalar_forms=False,aliases=False,comparison_aliases=False,carry_forms=False,restart=False):
    if restart and not (scalar_forms or comparison_aliases or aliases):
        raise ValueError('Restart requires comparisons or mask-logic aliases')
    lines=['.text','.global capacity','capacity:',
           f'li t0,-1',f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    operations=[x[0] for x in CARRY_SPECS] if carry_forms else OPS[:6]*2 if comparison_aliases else OPS[8:16]*2 if aliases else OPS[:6]+OPS[:6] if scalar_forms else OPS
    for i,op in enumerate(operations):
        lines += [f'.global op_{i}',f'op_{i}:',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'vle{sew}.v v8,(a0)',f'vle{sew}.v v16,(a1)',
                  'vlm.v v0,(a5)']
        destination='v8' if comparison_aliases and i<6 or aliases and i<8 else 'v16' if aliases or comparison_aliases else 'v24'
        if aliases or comparison_aliases:pass
        elif scalar_forms or i<16 or i>=20:lines+=['vlm.v v24,(a2)']
        elif i>=18:lines+=[f'vle{sew}.v v24,(a2)']
        lines += [f'vsetvli t0,a3,e{sew},{lmul},tu,mu']
        if restart:lines += ['csrw vstart,a6']
        if carry_forms:
            _,args,_,source,_,carry=CARRY_SPECS[i]
            if source==1:lines += [f'{ {8:"lb",16:"lh",32:"lw",64:"ld"}[sew]} t3,0(a1)']
            lines += [f'{op} v24,{args}'+(',v0' if carry else '')]
        elif comparison_aliases:lines += [f'{op} {destination},v8,v16,v0.t']
        elif aliases:lines += [f'{op} {destination},v8,v16']
        elif scalar_forms:
            stem=op.split('.')[0]
            if i<6:lines += ['li t3,-3',f'{stem}.vx v24,v8,t3,v0.t']
            else:lines += [f'{stem}.vi v24,v8,-3,v0.t']
        elif i<6:lines += [f'{op} v24,v8,v16,v0.t']
        elif i<8:lines += [f'{op} v24,v8,v16,v0']
        elif i<16:lines += [f'{op} v24,v8,v16']
        elif i<18:lines += [f'{op} t2,v8,v0.t']
        elif i==18:lines += [f'{op} v24,v8,v0.t']
        elif i==19:lines += [f'{op} v24,v0.t']
        else:lines += [f'{op} v24,v8,v0.t']
        lines += ['csrr a0,vstart',f'vsetvli t0,a4,e{sew},{lmul},tu,mu']
        if comparison_aliases or aliases or scalar_forms or i<16 or i>=20:lines+=[f'vsm.v {destination},(a2)']
        elif i<18:lines+=['sd t2,(a2)']
        else:lines+=[f'vse{sew}.v v24,(a2)']
        lines+=['ret']
    return '\n'.join(lines)+'\n'

def run(out,cross,scalar_forms=False,aliases=False,comparison_aliases=False,carry_forms=False,restart=False):
    if restart and not (scalar_forms or comparison_aliases or aliases):
        raise ValueError('Restart requires comparisons or mask-logic aliases')
    if sum((scalar_forms,aliases,comparison_aliases,carry_forms))>1:
        raise ValueError('Select one mask family')
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('mask_oracle.c')
    operations=[x[0] for x in CARRY_SPECS] if carry_forms else OPS[:6]*2 if comparison_aliases else OPS[8:16]*2 if aliases else ([op.replace('.vv','.'+form) for form in ('vx','vi') for op in OPS[:6]]
                if scalar_forms else OPS)
    manifest=dict(scope='Carry/borrow mask results, vector/scalar/immediate with and without carry input; vstart=0' if carry_forms else
                  'Masked comparison destinations alias both vector sources; vstart=0' if comparison_aliases else
                  'Mask logic destination aliases both sources; vstart=0' if aliases else
                  'Scalar/immediate packed comparisons; vstart=0' if scalar_forms else
                  'Packed mask / count / first / iota / vid; vstart=0',
                  cases=[],operations=operations,restart_tested=False)
    if restart:
        manifest.update(scope='Packed mask restart; '+('mask logic with both source aliases' if aliases else 'both vector-source comparison aliases' if comparison_aliases else 'scalar/immediate comparisons'),
                        restart_tested=True,configurations_per_elf=len(operations)*3*7*4*4,
                        restart_points=['one','half_vl','vl_if_representable','last_capacity_element'])
    if comparison_aliases:
        manifest['inactive_overlap_policy']='Old or one for different-EEW source overlap; prestart/no-body unchanged'
    if carry_forms:manifest.update(carry_specs=CARRY_SPECS,configurations_per_elf=1008)
    for sew,lmul in build.shapes():
        name=f'rvv_masks'+('_carry' if carry_forms else '_cmp_alias' if comparison_aliases else '_alias' if aliases else '_scalar' if scalar_forms else '')+('_restart' if restart else '')+f'_e{sew}_{lmul}'
        asm=out/(name+'.S');asm.write_text(assembly(sew,lmul,scalar_forms,aliases,comparison_aliases,carry_forms,restart))
        header=out/'operations.h'
        header.write_text('\n'.join('extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long);'%i for i in range(len(operations)))+
                          '\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(len(operations)))+
                          f'\n#define OP_COUNT {len(operations)}\n')
        if carry_forms:
            macros={
                'CARRY_ORACLE':[x[2] for x in CARRY_SPECS],
                'CARRY_SCALAR':[int(x[3]==1) for x in CARRY_SPECS],
                'CARRY_IMMEDIATE':[int(x[3]==2) for x in CARRY_SPECS],
                'CARRY_VALUES':[x[4] for x in CARRY_SPECS],
                'CARRY_INPUT':[x[5] for x in CARRY_SPECS]}
            with header.open('a') as stream:
                for key,values in macros.items():
                    stream.write('#define '+key+' '+','.join(map(str,values))+'\n')
        binary=binaries/name
        command=[cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib',
                 '-static','-ffreestanding','-fno-builtin','-fno-stack-protector',
                 '-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
                 '-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',
                 f'-DSEW={sew}',f'-DSCALAR_FORMS={int(scalar_forms)}',f'-DALIASES={int(aliases)}',f'-DCOMPARISON_ALIASES={int(comparison_aliases)}',
                 f'-DCARRY_FORMS={int(carry_forms)}',
                 f'-DRESTART_MASKS={int(restart)}',
                 '-I'+str(out),str(source),str(asm),'-o',str(binary)]
        subprocess.run(command,check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_MASK_PASS',timeout_seconds=180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],
                       input=('\n'.join(entries)+'\n').encode(),stdout=stream,
                       cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True)
    modes=p.add_mutually_exclusive_group();modes.add_argument('--scalar-forms',action='store_true')
    modes.add_argument('--aliases',action='store_true')
    modes.add_argument('--comparison-aliases',action='store_true')
    modes.add_argument('--carry-forms',action='store_true')
    p.add_argument('--restart',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.scalar_forms,a.aliases,a.comparison_aliases,a.carry_forms,a.restart)
