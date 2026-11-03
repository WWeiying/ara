#!/usr/bin/env python3
"""Generate an independently calculated bare-metal mixed-SEW SoC test."""
import argparse
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    code=['.section .text.init', '.globl _start', '_start:',
          'li t0,0x6600','csrs mstatus,t0','la t0,trap','csrw mtvec,t0',
          'li t0,0xd0000020','li t1,1','sd t1,0(t0)']
    data=['.section .data','.balign 128']; checks=[]; identity=0
    # Both directions of every SEW transition, tails, multiple issue beats,
    # LMUL=1/2/4 and mask-undisturbed read/modify/write of the destination.
    for lmul in (1,2,4):
        for prev in (8,16,32,64):
            for nxt in (8,64,16,32):
                for sew in (prev,nxt):
                    identity+=1; n=(1024//sew)*lmul-1; mask=(1<<sew)-1
                    av=[(i*37+identity*13) & mask for i in range(n)]
                    bv=[(i*19+identity*7+1) & mask for i in range(n)]
                    gold=[(x*y*y*(2 if i%2 else 1)) & mask for i,(x,y) in enumerate(zip(av,bv))]
                    def emit(label,values,size):
                        data.extend(['.balign 128',label+':'])
                        for v in values: data.append(f'.{size} 0x{v:x}')
                    size={8:'byte',16:'half',32:'word',64:'dword'}[sew]
                    emit(f'a{identity}',av,size); emit(f'b{identity}',bv,size)
                    emit(f'g{identity}',gold,size); emit(f'o{identity}',[0]*n,size)
                    emit(f'm{identity}',[0xaa]*((n+7)//8),'byte')
                    code += [f'li t0,{n}',f'vsetvli t1,t0,e{sew},m{lmul},tu,mu',
                             'bne t0,t1,fail',f'la a1,a{identity}',f'la a2,b{identity}',
                             f'la a3,o{identity}',f'la a4,m{identity}',
                             f'vle{sew}.v v8,(a1)',f'vle{sew}.v v16,(a2)',
                             'vlm.v v0,(a4)','vmul.vv v24,v8,v16',
                             'vmacc.vv v24,v8,v16,v0.t','vmul.vv v24,v24,v16',
                             f'vse{sew}.v v24,(a3)']
                    checks += [f'la a1,o{identity}',f'la a2,g{identity}',f'li t2,{n}',
                               f'check{identity}:',f'l{ {8:"bu",16:"hu",32:"wu",64:"d"}[sew]} t0,0(a1)',
                               f'l{ {8:"bu",16:"hu",32:"wu",64:"d"}[sew]} t1,0(a2)',
                               'bne t0,t1,fail',f'addi a1,a1,{sew//8}',f'addi a2,a2,{sew//8}',
                               'addi t2,t2,-1',f'bnez t2,check{identity}']
    code += ['fence rw,rw',*checks,'li a0,0','j exit','fail:','li a0,1','j exit',
             'trap:','csrr a0,mcause','addi a0,a0,2','exit:',
             'li t0,0xd0000020','sd zero,0(t0)','li t0,0xd0000000','sd a0,0(t0)',
             'hang:','j hang']
    source=out/'mixed.S'; source.write_text('\n'.join(code+data)+'\n')
    cc=root/'install/riscv-llvm/bin/clang'
    cmd=[str(cc),'--target=riscv64-unknown-elf','-march=rv64gcv','-mabi=lp64d',
         '-mno-relax','-nostdlib','-fuse-ld=lld',f'-Wl,-T,{root}/apps/common/link.ld',
         str(source),'-o',str(out/'mixed.elf')]
    subprocess.run(cmd,check=True)
    print(f'BUILT {identity} phases; {out}/mixed.elf')


if __name__=='__main__': main()
