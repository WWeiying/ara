#!/usr/bin/env python3
"""SoftFloat-golden RVV ADD/MUL/FMA restart, mask, tail and sticky-flag checks."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import run_operand_ext as api


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(api.ROOT/'verification/fpnew_upstream_20261009/oracle.py',out/'oracle.py')
    spec=importlib.util.spec_from_file_location('fma_edges_oracle',out/'oracle.py')
    oracle=importlib.util.module_from_spec(spec); spec.loader.exec_module(oracle)
    sf=oracle.SoftFloat()
    code=['.section .text.init','.globl _start','_start:',
          'li t0,0x6600','csrs mstatus,t0','la t0,trap','csrw mtvec,t0',
          'li t0,0xd0000020','li t1,1','sd t1,0(t0)']
    data=['.section .data']; checks=[]; phases=[]
    unit={8:'byte',16:'half',32:'word',64:'dword'}
    load={16:'lhu',32:'lwu',64:'ld'}
    def emit(label,values,width):
        data.extend(['.balign 128',label+':'])
        data.extend(f'.{unit[width]} 0x{value:x}' for value in values)
    for width in (16,64,32):
        frac,exp={16:(10,5),32:(23,8),64:(52,11)}[width]
        one=((1 << (exp-1))-1) << frac
        inf=((1 << exp)-1) << frac
        sign=1 << (width-1)
        values=[0,one,one+1,one-1,1,inf-1,inf,inf|1,inf|(1 << (frac-1)),one|sign]
        for lmul in (1,4):
            capacity=1024*lmul//width; vl=capacity-3
            for op in ('vfadd','vfmul','vfmacc'):
                for restart in (0,1,vl//2,vl):
                    for masked in (False,True):
                        ident=len(phases)+1; label=str(ident); rm=ident%5; sticky=ident%2
                        va=[values[(i+ident)%len(values)] for i in range(capacity)]
                        vb=[values[(3*i+ident+2)%len(values)] for i in range(capacity)]
                        vc=[values[(7*i+ident+4)%len(values)] for i in range(capacity)]
                        result=list(vc); flags=sticky
                        for i in range(restart,vl):
                            if masked and i%2==0: continue
                            if op=='vfadd': y,ex=sf.evaluate('fma',width,width,rm,one,va[i],vb[i])
                            elif op=='vfmul': y,ex=sf.evaluate('mul',width,width,rm,va[i],vb[i])
                            else: y,ex=sf.evaluate('fma',width,width,rm,va[i],vb[i],vc[i])
                            result[i]=y; flags|=ex
                        for prefix,arr in (('a',va),('b',vb),('c',vc),('g',result),('o',[0]*capacity)):
                            emit(prefix+label,arr,width)
                        emit('m'+label,[0xaa]*((capacity+7)//8),8)
                        suffix=',v0.t' if masked else ''
                        code += [f'li s1,{ident}',f'li t0,{capacity}',
                            f'vsetvli t1,t0,e{width},m{lmul},tu,mu','bne t0,t1,fail',
                            f'la a1,a{label}',f'la a2,b{label}',f'la a3,c{label}',f'la a4,m{label}',
                            f'vle{width}.v v8,(a1)',f'vle{width}.v v16,(a2)',
                            f'vle{width}.v v24,(a3)','vlm.v v0,(a4)',
                            f'li t0,{vl}',f'vsetvli t1,t0,e{width},m{lmul},tu,mu','bne t0,t1,fail',
                            f'csrwi frm,{rm}',f'csrwi fflags,{sticky}',f'li t0,{restart}','csrw vstart,t0',
                            f'{op}.vv v24,v8,v16{suffix}','csrr t0,vstart','bnez t0,fail',
                            'csrr t0,fflags',f'li t1,{flags}','bne t0,t1,fail',
                            f'li t0,{capacity}',f'vsetvli t1,t0,e{width},m{lmul},tu,mu',
                            f'la a3,o{label}',f'vse{width}.v v24,(a3)']
                        checks += [f'li s1,{ident}',f'la a1,o{label}',f'la a2,g{label}',
                            f'li t2,{capacity}',f'check{label}:',f'{load[width]} t0,0(a1)',
                            f'{load[width]} t1,0(a2)','bne t0,t1,fail',
                            f'addi a1,a1,{width//8}',f'addi a2,a2,{width//8}',
                            'addi t2,t2,-1',f'bnez t2,check{label}']
                        phases.append(dict(id=ident,op=op,sew=width,lmul=lmul,vl=vl,vstart=restart,
                            masked=masked,frm=rm,initial_fflags=sticky,expected_fflags=flags))
    code += ['fence rw,rw',*checks,'li a0,0','j exit','fail:','mv a0,s1','j exit',
             '.balign 4','trap:','csrr a0,mcause','addi a0,a0,1024','exit:',
             'li t0,0xd0000020','sd zero,0(t0)','li t0,0xd0000000','sd a0,0(t0)','hang:','j hang']
    src=out/'fma_edges.S'; src.write_text('\n'.join(code+data)+'\n')
    api.save(out/'phases.json',phases)
    shutil.copy2(api.ROOT/'apps/common/link.ld',out/'link.ld')
    compiler=api.ROOT/'install/riscv-llvm/bin/clang'
    cmd=[str(compiler),'--target=riscv64-unknown-elf','-march=rv64gcv_zvfh','-mabi=lp64d',
         '-mno-relax','-nostdlib','-fuse-ld=lld','-Wl,-T,'+str(out/'link.ld'),str(src),'-o',str(out/'fma_edges.elf')]
    subprocess.run(cmd,check=True)
    shutil.copy2(__file__,out/'builder.py')
    pins={str(f):api.sha(f) for f in out.rglob('*') if f.is_file()}
    pins[str(oracle.LIB)]=api.sha(oracle.LIB); pins[str(compiler.resolve())]=api.sha(compiler.resolve())
    api.save(out/'source-pins.json',pins)
    api.save(out/'manifest.json',dict(state='BUILT',phases=len(phases),command=cmd,
                                    oracle='Spike SoftFloat',elf_sha256=api.sha(out/'fma_edges.elf')))
    print(f'Built {len(phases)} phases: {out}/fma_edges.elf')


if __name__=='__main__': main()
