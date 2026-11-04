#!/usr/bin/env python3
"""Independent scalar-golden mixed-SEW ALU chain, with tails and restart."""
import argparse
import json
from pathlib import Path
import subprocess


def signed(value, width):
    return value - (1 << width) if value >> (width-1) else value


def average(a, b, width, mode):
    value = signed(a, width) + signed(b, width)
    increment = (value & 1) and (mode == 0 or
        (mode == 1 and (value >> 1) & 1) or (mode == 3 and not ((value >> 1) & 1)))
    return ((value >> 1) + int(increment)) & ((1 << width)-1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    root = args.root.resolve()
    code = ['.section .text.init', '.globl _start', '_start:',
        'li t0,0x6600', 'csrs mstatus,t0', 'la t0,trap', 'csrw mtvec,t0',
        'li t0,0xd0000020', 'li t1,1', 'sd t1,0(t0)']
    data = ['.section .data']; checks = []; phases = []
    for lmul in (1,2,4,8):
        for prev in (8,16,32,64):
            for nxt in (8,64,16,32):
                for sew in (prev,nxt):
                    ident = len(phases)+1
                    capacity = (1024//sew)*lmul; n = capacity-1
                    mask = (1 << sew)-1; lo = -(1 << (sew-1)); hi = (1 << (sew-1))-1
                    mode = ident % 4; restart = (0,1,n//2)[ident % 3]
                    av = [((i*37+ident*13) ^ (mask if i%3 == 0 else (1 << (sew-1)))) & mask for i in range(capacity)]
                    bv = [((i*19+ident*7) ^ (mask if i%4 == 0 else 0)) & mask for i in range(capacity)]
                    expected = []; saturated = False
                    for i,(a,b) in enumerate(zip(av,bv)):
                        if i == n:
                            expected.append(mask); continue
                        value = a  # dependent vadd, vsub pair
                        if i >= restart and i%2:
                            diff = signed(a,sew)-signed(b,sew)
                            saturated |= diff < lo or diff > hi
                            value = max(lo,min(hi,diff)) & mask
                        saturated |= value < b
                        value = max(0,value-b)
                        value = min(mask,value+b)
                        value = average(value,a,sew,mode)
                        expected.append(b if a < b else value)
                    suffix = str(ident); size = {8:'byte',16:'half',32:'word',64:'dword'}[sew]
                    def emit(label, values, unit):
                        data.extend(['.balign 128', label+':'])
                        data.extend(f'.{unit} 0x{value:x}' for value in values)
                    emit('a'+suffix,av,size); emit('b'+suffix,bv,size)
                    emit('g'+suffix,expected,size); emit('o'+suffix,[0]*capacity,size)
                    emit('m'+suffix,[0xaa]*((n+7)//8),'byte')
                    code += [f'li s1,{ident}', f'li t0,{capacity}',
                        f'vsetvli t1,t0,e{sew},m{lmul},tu,mu', 'bne t0,t1,fail',
                        'vmv.v.i v24,-1', f'li t0,{n}', f'vsetvli t1,t0,e{sew},m{lmul},tu,mu',
                        'bne t0,t1,fail', f'la a1,a{suffix}',f'la a2,b{suffix}',
                        f'la a3,o{suffix}',f'la a4,m{suffix}',f'vle{sew}.v v8,(a1)',
                        f'vle{sew}.v v16,(a2)','vlm.v v0,(a4)',
                        'vadd.vv v24,v8,v16','vsub.vv v24,v24,v16',
                        'csrw vxsat,zero', f'li t0,{restart}', 'csrw vstart,t0',
                        'vssub.vv v24,v24,v16,v0.t','vssubu.vv v24,v24,v16',
                        'csrr t0,vxsat', f'li t1,{int(saturated)}','bne t0,t1,fail',
                        'vsaddu.vv v24,v24,v16',f'csrwi vxrm,{mode}',
                        'vaadd.vv v24,v24,v8','vmsltu.vv v0,v8,v16',
                        'vmerge.vvm v24,v24,v16,v0', f'li t0,{capacity}',
                        f'vsetvli t1,t0,e{sew},m{lmul},tu,mu',f'vse{sew}.v v24,(a3)']
                    load = {8:'lbu',16:'lhu',32:'lwu',64:'ld'}[sew]
                    checks += [f'li s1,{ident}', f'la a1,o{suffix}',f'la a2,g{suffix}',
                        f'li t2,{capacity}',f'check{ident}:',f'{load} t0,0(a1)',f'{load} t1,0(a2)',
                        'bne t0,t1,fail',f'addi a1,a1,{sew//8}',f'addi a2,a2,{sew//8}',
                        'addi t2,t2,-1',f'bnez t2,check{ident}']
                    phases.append(dict(id=ident,sew=sew,lmul=lmul,vl=n,vstart=restart,
                        vxrm=mode,vxsat_after_sub=int(saturated)))
    code += ['fence rw,rw',*checks,'li a0,0','j exit','fail:','mv a0,s1','j exit',
        '.balign 4','trap:','csrr a0,mcause','addi a0,a0,1024','exit:',
        'li t0,0xd0000020','sd zero,0(t0)','li t0,0xd0000000','sd a0,0(t0)','hang:','j hang']
    (out/'mixed.S').write_text('\n'.join(code+data)+'\n')
    (out/'phases.json').write_text(json.dumps(phases,indent=2)+'\n')
    cmd = [str(root/'install/riscv-llvm/bin/clang'),'--target=riscv64-unknown-elf',
        '-march=rv64gcv','-mabi=lp64d','-mno-relax','-nostdlib','-fuse-ld=lld',
        f'-Wl,-T,{root}/apps/common/link.ld',str(out/'mixed.S'),'-o',str(out/'mixed.elf')]
    subprocess.run(cmd, check=True)
    print(f'BUILT ALU {len(phases)} phases: {out}/mixed.elf')


if __name__ == '__main__':
    main()
