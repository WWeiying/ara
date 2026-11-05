#!/usr/bin/env python3
"""Scalar-golden vector shifts with SEW changes, masks, tails and restart."""
import argparse
import json
from pathlib import Path
import subprocess

OPS = ('vsll', 'vsrl', 'vsra', 'vssrl', 'vssra',
       'vnsrl', 'vnsra', 'vnclipu', 'vnclip')


def evaluate(op, bits, amount, width, mode):
    narrow = op in ('vnsrl', 'vnsra', 'vnclip', 'vnclipu')
    sw = width * (2 if narrow else 1)
    bits &= (1 << sw)-1
    amount &= sw-1
    signed = op in ('vsra', 'vssra', 'vnsra', 'vnclip')
    value = bits - (1 << sw) if signed and bits >> (sw-1) else bits
    if op == 'vsll':
        value <<= amount
    else:
        value >>= amount
    if op in ('vssrl', 'vssra', 'vnclip', 'vnclipu') and amount:
        discarded = bits & ((1 << amount)-1)
        halfway = 1 << (amount-1)
        inc = (discarded >= halfway if mode == 0 else
               discarded > halfway or (discarded == halfway and bool(value & 1))
               if mode == 1 else False if mode == 2 else
               bool(discarded) and not bool(value & 1))
        value += int(inc)
    saturated = False
    if op in ('vnclip', 'vnclipu'):
        low = -(1 << (width-1)) if signed else 0
        high = (1 << (width-1))-1 if signed else (1 << width)-1
        saturated = value < low or value > high
        value = min(high, max(low, value))
    return value & ((1 << width)-1), saturated


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--root', type=Path, required=True)
    a = p.parse_args(); out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    code = ['.section .text.init', '.globl _start', '_start:',
            'li t0,0x6600', 'csrs mstatus,t0', 'la t0,trap', 'csrw mtvec,t0',
            'li t0,0xd0000020', 'li t1,1', 'sd t1,0(t0)']
    data = ['.section .data']; checks = []; phases = []
    unit = {8:'byte', 16:'half', 32:'word', 64:'dword'}
    load = {8:'lbu', 16:'lhu', 32:'lwu', 64:'ld'}
    def emit(label, values, width):
        data.extend(['.balign 128', label+':'])
        data.extend(f'.{unit[width]} 0x{x:x}' for x in values)
    for lmul in (1, 2):
        for width in (8, 64, 16, 32):
            for mode in range(4):
                for op in OPS:
                    narrow = op in ('vnsrl', 'vnsra', 'vnclip', 'vnclipu')
                    sw = width * (2 if narrow else 1)
                    if sw > 64: continue
                    ident = len(phases)+1; label = str(ident)
                    capacity = 1024*lmul//width; vl = capacity-3
                    restart = (0, 1, vl//2)[ident%3]
                    masked = ident%2 == 0; sticky = ident%5 == 0
                    wm = (1 << width)-1; sm = (1 << sw)-1
                    values = [0, 1, sm, sm-1, wm, wm+1,
                              (1 << (width-1))-1, 1 << (width-1),
                              -(1 << (width-1)), -(1 << (width-1))-1]
                    inputs = [(values[i%len(values)] ^ (i*71 if i%7 == 0 else 0)) & sm
                              for i in range(capacity)]
                    shifts = [(i*3+ident) & wm for i in range(capacity)]
                    expected = []; saturated = sticky
                    for i, (bits, amount) in enumerate(zip(inputs, shifts)):
                        if i < restart or i >= vl or (masked and i%2 == 0):
                            expected.append(wm); continue
                        result, sat = evaluate(op, bits, amount, width, mode)
                        expected.append(result); saturated |= sat
                    emit('a'+label, inputs, sw); emit('b'+label, shifts, width)
                    emit('g'+label, expected, width); emit('o'+label, [0]*capacity, width)
                    emit('m'+label, [0xaa]*((capacity+7)//8), 8)
                    suffix = ',v0.t' if masked else ''
                    instruction = op+('.wv' if narrow else '.vv')
                    code += [f'li s1,{ident}', f'li t0,{capacity}',
                        f'vsetvli t1,t0,e{width},m{lmul},tu,mu', 'bne t0,t1,fail',
                        'vmv.v.i v24,-1', f'la a1,a{label}', f'la a2,b{label}',
                        f'la a3,o{label}', f'la a4,m{label}',
                        f'vle{sw}.v v8,(a1)', f'vle{width}.v v16,(a2)', 'vlm.v v0,(a4)',
                        f'li t0,{vl}', f'vsetvli t1,t0,e{width},m{lmul},tu,mu',
                        'bne t0,t1,fail', f'csrwi vxrm,{mode}', f'csrwi vxsat,{int(sticky)}',
                        f'li t0,{restart}', 'csrw vstart,t0',
                        f'{instruction} v24,v8,v16{suffix}',
                        'csrr t0,vstart', 'bnez t0,fail', 'csrr t0,vxsat',
                        f'li t1,{int(saturated)}', 'bne t0,t1,fail',
                        f'li t0,{capacity}', f'vsetvli t1,t0,e{width},m{lmul},tu,mu',
                        f'vse{width}.v v24,(a3)']
                    checks += [f'li s1,{ident}', f'la a1,o{label}', f'la a2,g{label}',
                        f'li t2,{capacity}', f'check{label}:',
                        f'{load[width]} t0,0(a1)', f'{load[width]} t1,0(a2)',
                        'bne t0,t1,fail', f'addi a1,a1,{width//8}', f'addi a2,a2,{width//8}',
                        'addi t2,t2,-1', f'bnez t2,check{label}']
                    phases.append(dict(id=ident, op=op, sew=width, lmul=lmul, vl=vl,
                        vstart=restart, masked=masked, vxrm=mode, initial_vxsat=int(sticky),
                        expected_vxsat=int(saturated)))
    code += ['fence rw,rw', *checks, 'li a0,0', 'j exit', 'fail:', 'mv a0,s1',
             'j exit', '.balign 4', 'trap:', 'csrr a0,mcause', 'addi a0,a0,1024',
             'exit:', 'li t0,0xd0000020', 'sd zero,0(t0)', 'li t0,0xd0000000',
             'sd a0,0(t0)', 'hang:', 'j hang']
    src = out/'shift_mixed.S'; src.write_text('\n'.join(code+data)+'\n')
    (out/'phases.json').write_text(json.dumps(phases, indent=2)+'\n')
    subprocess.run([str(a.root/'install/riscv-llvm/bin/clang'),
        '--target=riscv64-unknown-elf', '-march=rv64gcv', '-mabi=lp64d', '-mno-relax',
        '-nostdlib', '-fuse-ld=lld', '-Wl,-T,'+str(a.root/'apps/common/link.ld'),
        str(src), '-o', str(out/'shift_mixed.elf')], check=True)
    print(f'BUILT shift ALU {len(phases)} phases: {out}/shift_mixed.elf')


if __name__ == '__main__':
    main()
