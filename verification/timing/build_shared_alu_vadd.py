#!/usr/bin/env python3
"""Self-checking 1024-element VADD application, isolated bare-metal ELF."""
import argparse
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(); p.add_argument('output',type=Path); p.add_argument('--root',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
    n=1024; mask=(1<<32)-1
    x=[(i*1234567+0x7fffff00)&mask for i in range(n)]
    y=[(i*7654321+0xfedcba98)&mask for i in range(n)]
    code=''' .section .text.init
.globl _start
_start:
li t0,0x6600
csrs mstatus,t0
la t0,trap
csrw mtvec,t0
li t0,0xd0000020
li t1,1
sd t1,0(t0)
li a0,1024
la a1,x
la a2,y
la a3,z
loop:
vsetvli t0,a0,e32,m2,ta,ma
vle32.v v0,(a1)
vle32.v v8,(a2)
vadd.vv v16,v0,v8
vse32.v v16,(a3)
sub a0,a0,t0
slli t1,t0,2
add a1,a1,t1
add a2,a2,t1
add a3,a3,t1
bnez a0,loop
fence rw,rw
li t0,0xd0000020
sd zero,0(t0)
la a1,z
la a2,g
li t2,1024
check:
lwu t0,0(a1)
lwu t1,0(a2)
bne t0,t1,fail
addi a1,a1,4
addi a2,a2,4
addi t2,t2,-1
bnez t2,check
li a0,0
j exit
fail:
li a0,1
j exit
.balign 4
trap:
csrr a0,mcause
addi a0,a0,1024
exit:
li t0,0xd0000000
sd a0,0(t0)
hang:
j hang
.section .data
'''
    for name,values in [('x',x),('y',y),('z',[0]*n),('g',[(u+v)&mask for u,v in zip(x,y)])]:
        code+='\n.balign 128\n'+name+':\n'+'\n'.join(f'.word 0x{v:x}' for v in values)+'\n'
    src=a.output/'vadd.S'; src.write_text(code)
    subprocess.run([str(a.root/'install/riscv-llvm/bin/clang'),'--target=riscv64-unknown-elf',
        '-march=rv64gcv','-mabi=lp64d','-mno-relax','-nostdlib','-fuse-ld=lld',
        '-Wl,-T,'+str(a.root/'apps/common/link.ld'),str(src),'-o',str(a.output/'vadd.elf')],check=True)


if __name__=='__main__': main()
