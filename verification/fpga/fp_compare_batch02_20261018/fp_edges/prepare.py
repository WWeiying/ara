#!/usr/bin/env python3
"""New directed FP edge cases; not original Linux ELF replays. No VCS launch."""
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('edge_parent', HERE.parent/'scenarios.py')
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
base = parent.base
OPS = ('eq', 'ne', 'lt', 'le', 'gt', 'ge')
FORMATS = {16: (5, 10, 'e'), 32: (8, 23, 'f'), 64: (11, 52, 'd')}


def patterns(width):
    exp, frac, _ = FORMATS[width]
    sign = 1 << (width-1)
    inf = ((1 << exp)-1) << frac
    one = ((1 << (exp-1))-1) << frac
    return [0, sign, one, sign | one, inf, sign | inf,
            inf | (1 << (frac-1)) | 3, inf | 1, 1, inf-1]


def integer_compare(width, op, x, y):
    exp, frac, _ = FORMATS[width]
    fraction_mask = (1 << frac)-1
    exponent_mask = (1 << exp)-1
    def classify(v):
        nan = ((v >> frac) & exponent_mask) == exponent_mask and bool(v & fraction_mask)
        return nan, nan and not bool(v & (1 << (frac-1)))
    xn, xs = classify(x)
    yn, ys = classify(y)
    nv = xs or ys or (op not in ('eq', 'ne') and (xn or yn))
    if xn or yn:
        return int(op == 'ne'), 16 if nv else 0
    sign = 1 << (width-1)
    limit = (1 << width)-1
    # Monotone integer keys, with both signed zeros canonicalized.
    x = 0 if not (x & (sign-1)) else x
    y = 0 if not (y & (sign-1)) else y
    kx = (~x & limit) if x & sign else x | sign
    ky = (~y & limit) if y & sign else y | sign
    bits = dict(eq=kx == ky, ne=kx != ky, lt=kx < ky,
                le=kx <= ky, gt=kx > ky, ge=kx >= ky)
    return int(bits[op]), 16 if nv else 0


def host_float_compare(width, op, x, y):
    _, frac, fmt = FORMATS[width]
    xf = struct.unpack('<'+fmt, x.to_bytes(width//8, 'little'))[0]
    yf = struct.unpack('<'+fmt, y.to_bytes(width//8, 'little'))[0]
    unordered = math.isnan(xf) or math.isnan(yf)
    signaling = any(math.isnan(f) and not (v & (1 << (frac-1)))
                    for v, f in ((x, xf), (y, yf)))
    nv = signaling or (unordered and op not in ('eq', 'ne'))
    bits = dict(eq=xf == yf, ne=xf != yf, lt=xf < yf,
                le=xf <= yf, gt=xf > yf, ge=xf >= yf)
    return int(bits[op]), 16 if nv else 0


def bit(data, i):
    return (data[i//8] >> (i % 8)) & 1


def make_cases():
    cases = []
    for width in (16, 32, 64):
        cap = 1024//width
        # Eight selected cases per width, not a Cartesian product.
        specs = [
            ('eq', 'vv', 8, False, 1, True, 1, cap-1),
            ('ne', 'vv', 16, False, 0, False, 0, cap-1),
            ('lt', 'vv', 8, True, 1, True, 3, cap//2),
            ('le', 'vv', 16, False, 1, True, 1, cap-1),
            ('gt', 'vf', 8, False, 1, False, 0, 1),
            ('ge', 'vf', 24, False, 0, True, 1, cap-1),
            ('eq', 'vv', 24, False, 1, False, 0, 0),
            ('ne', 'vv', 8, True, 0, True, 1, 1),
        ]
        p = patterns(width)
        a = [(p[(3*i+7) % len(p)]) for i in range(cap)]
        b = [(p[(7*i+2) % len(p)]) for i in range(cap)]
        raw_a = b''.join(v.to_bytes(width//8, 'little') for v in a)
        raw_b = b''.join(v.to_bytes(width//8, 'little') for v in b)
        old = bytes((0x5b ^ (i*13)) & 255 for i in range(128))
        for op, form, dest, triple, context, masked, start, vl in specs:
            c = dict(id=len(cases), sew=width, lmul='m1', op=op, form=form, dest=dest,
                     triple=triple, context=context, masked=masked, start=start, vl=vl,
                     capacity=cap, scalar_bits=p[2], a=a, b=b,
                     raw_a=list(raw_a), raw_b=list(raw_b), old=list(old), mask=[0xaa]*128)
            prior = raw_a if dest == 8 else raw_b if dest == 16 else old
            choices, flags = [], 1
            for i in range(cap):
                y = c['scalar_bits'] if form == 'vf' else a[i] if triple else b[i]
                value, nv = integer_compare(width, op, a[i], y)
                assert (value, nv) == host_float_compare(width, op, a[i], y)
                active = i >= start and i < vl and (not masked or bit(c['mask'], i))
                previous = bit(prior, i)
                if active:
                    allowed = {value}
                    flags |= nv
                elif start >= vl or i < start:
                    allowed = {previous}
                elif i < vl:
                    source_alias = dest == 8 or (dest == 16 and form == 'vv')
                    allowed = {previous, 1} if source_alias else {previous}
                else:
                    allowed = {previous, 1, value}
                choices.append(sorted(allowed))
            must_one, must_zero = [0]*(cap//8), [0]*(cap//8)
            for i, allowed in enumerate(choices):
                if allowed == [1]: must_one[i//8] |= 1 << (i % 8)
                if allowed == [0]: must_zero[i//8] |= 1 << (i % 8)
            c.update(allowed_bits=choices, must_one=must_one, must_zero=must_zero,
                     expected_flags=flags)
            cases.append(c)
    return cases


def host_selftest(cases):
    pairs = 0
    for width in FORMATS:
        for op in OPS:
            for x in patterns(width):
                for y in patterns(width):
                    assert integer_compare(width, op, x, y) == host_float_compare(width, op, x, y)
                    pairs += 1
    negatives = 0
    for c in cases:
        def accept(data, flags, guards=(0x5b, 0x5b)):
            return (flags == c['expected_flags'] and guards == (0x5b, 0x5b) and
                    all(not ((v & z) | ((~v & 255) & o)) for v, z, o in
                        zip(data, c['must_zero'], c['must_one'])))
        baseline = bytearray(len(c['must_one']))
        for i, allowed in enumerate(c['allowed_bits']):
            baseline[i//8] |= allowed[0] << (i % 8)
        assert accept(baseline, c['expected_flags'])
        for i, allowed in enumerate(c['allowed_bits']):
            mutated = bytearray(baseline)
            mutated[i//8] ^= 1 << (i % 8)
            direct = all(bit(mutated, j) in allowed_j
                         for j, allowed_j in enumerate(c['allowed_bits']))
            assert accept(mutated, c['expected_flags']) == direct
            if len(allowed) == 1:
                assert not direct
                negatives += 1
        assert not accept(baseline, c['expected_flags'] ^ 16)
        assert not accept(baseline, c['expected_flags'], (0, 0x5b))
        assert not accept(baseline, c['expected_flags'], (0x5b, 0))
        negatives += 3
    return dict(state='PASS', independent_fp_pair_checks=pairs,
                rejected_bit_flags_guard_mutations=negatives,
                note='Integer ordered-key oracle cross-checked against Python IEEE float comparisons. '
                     'Negative tests run on host only; no DUT negative-test loops.')


def assembly(c):
    width = c['sew']
    lines = ['.text', '.balign 4', f'.global fp_edge_{c["id"]}', f'fp_edge_{c["id"]}:',
             'addi sp,sp,-16', 'sd ra,0(sp)', f'vsetvli t0,zero,e{width},m1,tu,mu',
             f'vle{width}.v v8,(a0)', f'vle{width}.v v16,(a1)']
    if c['dest'] == 24:
        lines += ['vsetvli t0,zero,e8,m1,tu,mu', 'vle8.v v24,(a2)',
                  f'vsetvli t0,zero,e{width},m1,tu,mu']
    lines += ['vlm.v v0,(a3)']
    if c['form'] == 'vf':
        lines += ['ld t0,0(a5)', 'fmv.d.x ft0,t0']
    lines += [f'li t0,{c["vl"]}', f'vsetvli t0,t0,e{width},m1,tu,mu',
              f'li t0,{c["start"]}', 'csrw vstart,t0']
    if c['context']:
        lines += ['call context_roundtrip']
    rhs = 'ft0' if c['form'] == 'vf' else 'v8' if c['triple'] else 'v16'
    suffix = ',v0.t' if c['masked'] else ''
    lines += ['csrwi fflags,1', f'vmf{c["op"]}.{c["form"]} v{c["dest"]},v8,{rhs}{suffix}',
              'csrr t2,vstart', 'csrr t1,fflags', 'slli t1,t1,32', 'or a0,t2,t1',
              f'vsetvli t0,zero,e{width},m1,tu,mu', f'vsm.v v{c["dest"]},(a4)',
              'csrr zero,vl', 'fence rw,rw', 'ld ra,0(sp)', 'addi sp,sp,16', 'ret']
    return '\n'.join(lines)+'\n'


def c_source(cases, name):
    lines = ['#include <stdint.h>', 'extern void replay_text(const char *);',
             'extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);',
             'extern volatile unsigned long replay_case;',
             'static uint8_t output[10] __attribute__((aligned(64)));']
    for c in cases:
        n = c['id']
        lines += [f'extern unsigned long fp_edge_{n}(const void *,const void *,const void *,const void *,void *,const void *);']
        for field in ('raw_a', 'raw_b', 'old', 'mask', 'must_one', 'must_zero'):
            lines += [f'static const uint8_t {field}_{n}[] __attribute__((aligned(64))) = {{'+
                      ','.join(map(str, c[field]))+'};']
        scalar = c['scalar_bits'] | (((1 << 64)-1) ^ ((1 << c['sew'])-1))
        lines += [f'static const uint64_t scalar_{n}=UINT64_C(0x{scalar:016x});']
    lines += ['int main(void) {', 'unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));',
              'if(vb!=128) return 90;']
    for c in cases:
        n, count = c['id'], c['capacity']//8
        lines += ['{', f'replay_case={n};', 'for(unsigned i=0;i<10;++i)output[i]=0x5b;',
                  f'unsigned long status=fp_edge_{n}(raw_a_{n},raw_b_{n},old_{n},mask_{n},output+1,&scalar_{n});',
                  f'if(status!=((unsigned long){c["expected_flags"]}<<32)) return replay_mismatch({n},1000,((unsigned long){c["expected_flags"]}<<32),status);',
                  f'if(output[0]!=0x5b || output[{count+1}]!=0x5b) return replay_mismatch({n},1001,0x5b,output[{count+1}]);',
                  f'for(unsigned i=0;i<{count};++i) {{',
                  f'unsigned bad=(output[i+1]&must_zero_{n}[i])|((~output[i+1]&255)&must_one_{n}[i]);',
                  f'if(bad) return replay_mismatch({n},i,0,bad);', '}', '}']
    lines += [f'replay_text("FP_EDGES_PASS group={name} cases=4 errors=0\\n");',
              'replay_text("BOARD_REPLAY_PASS\\n");', 'return 0;', '}']
    return '\n'.join(lines)+'\n'


def main():
    configs = make_cases()
    assert len(configs) == 24
    root = HERE/'build01'
    root.mkdir(exist_ok=False)
    base.save(root/'cases.json', configs)
    base.save(root/'host_oracle_selftest.json', host_selftest(configs))
    pins = {str(p): base.sha(p) for p in
            (Path(__file__), HERE.parent/'scenarios.py', HERE.parent/'run.py',
             base.helper.CC, base.helper.SPIKE)}
    programs = {}
    counts = {}
    for start in range(0, len(configs), 4):
        group = configs[start:start+4]
        name = f'e{group[0]["sew"]}_g{(start//4)%2}'
        out = root/name
        out.mkdir()
        (out/'main.c').write_text(c_source(group, name))
        (out/'scenario.S').write_text(''.join(assembly(c) for c in group)+parent.context_assembly())
        for filename in ('startup.S', 'runtime.c', 'replay.ld'):
            source = base.RUNTIME/filename
            shutil.copyfile(source, out/filename)
            pins[str(source)] = base.sha(source)
        flags = ['-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static','-ffreestanding',
                 '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
                 '-msmall-data-limit=0','-Wl,--build-id=none','-Wall','-Wextra','-Werror',
                 '-mcmodel=medany','-ffunction-sections','-fdata-sections','-Wl,--gc-sections']
        for backend in ('soc', 'spike'):
            r = base.command([base.helper.CC,*flags,'-T',out/'replay.ld',
                              *(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                              *[out/n for n in ('main.c','scenario.S','startup.S','runtime.c')],
                              '-lgcc','-o',out/(backend+'.elf')],out,backend+'_compile')
            assert r['returncode']==0, (out/(backend+'_compile.log')).read_text()
        nm = subprocess.check_output([str(base.helper.CC.with_name('riscv64-unknown-elf-nm')),
                                      '-n',out/'spike.elf'],text=True)
        symbols = {r.split()[2]:r.split()[0] for r in nm.splitlines() if len(r.split())==3}
        (out/'spike.cmd').write_text('until pc 0 '+symbols['replay_exit']+
                                   '\nreg 0 a0\nreg 0 minstret\nstr '+symbols['replay_log']+'\nrs\n')
        r = base.command([base.helper.SPIKE,'-d','--debug-cmd='+str(out/'spike.cmd'),
                          '--isa=rv64gcv_zfh_zvfh_zvl1024b','-m2',out/'spike.elf'],out,'spike')
        log = (out/'spike.log').read_text()
        markers = [f'FP_EDGES_PASS group={name} cases=4 errors=0','BOARD_REPLAY_PASS']
        values = re.findall(r'^0x([0-9a-f]+)$', log, re.M)
        assert r['returncode']==0 and all(m in log for m in markers) and len(values)==2 and int(values[0],16)==0, log
        counts[name] = int(values[1],16)
        programs[name] = dict(directory=str(out),elf_sha256=base.sha(out/'soc.elf'),
                              pass_markers=markers,reference_elf_sha256=base.sha(out/'spike.elf'),
                              spike_exit_code=0,spike_retired_instructions=counts[name],
                              case_ids=[c['id'] for c in group],
                              attribution='New directed FP edge tests; not original Linux ELF.')
    manifest = dict(programs=programs,pins=pins,
                    files={str(p):base.sha(p) for p in root.rglob('*') if p.is_file()},
                    scope='24 new directed FP16/32/64 tests, six four-case ELFs; '
                          'precomputed byte allowed-set oracle; host-only negative selftests; '
                          'Spike reference only, no DUT run, not original Linux ELF attribution.')
    base.save(HERE/'programs.json', manifest)
    base.save(HERE/'prepared.json', manifest)
    checked = 0
    for category in ('pins','files'):
        for path,digest in manifest[category].items():
            assert base.sha(path)==digest, path
            checked += 1
    base.save(HERE/'seal.json',dict(state='sealed_ready_for_fixed_vcs',
              manifest='programs.json',manifest_sha256=base.sha(HERE/'programs.json'),
              prepared_sha256=base.sha(HERE/'prepared.json'),checked_hashes=checked,
              hash_mismatches=[],spike_exit_code=0,spike_programs_passed=len(programs),
              cases=24,spike_retired_instructions=counts,
              host_oracle_selftest='build01/host_oracle_selftest.json',
              vcs_launched=False,
              budget='Four cases per ELF, no DUT negative-test loops; instruction counts measured '
                     'on Spike, VCS wall time not measured. Target four-way jobs below ten minutes per ELF.'))
    print(json.dumps(dict(state='SEALED_SPIKE_6_ELF_24_CASE_PASS',
                         programs=str(HERE/'programs.json'),prepared=str(HERE/'prepared.json'),
                         seal=str(HERE/'seal.json'),instruction_counts=counts),indent=2))


if __name__ == '__main__':
    main()
