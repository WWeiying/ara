#!/usr/bin/env python3
"""Generate and host-audit scalar-only packed prefixes; bounded Spike on request."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'prepared02'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
POPCOUNTS = tuple(bin(v).count('1') for v in range(256))
CASES = {
    '319': ('rvv_fp_compare_unmasked_alias_v8_e32_m4', 128, 1, 0, 319),
    '15286': ('rvv_fp_compare_unboxed_unmasked_alias_v16_e32_m1', 32, 2, 1, 15286),
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, x):
    p.write_text(json.dumps(x, indent=2) + '\n')


def command(argv, dest, label, expected=0, timeout=60):
    argv = list(map(str, argv))
    save(dest / (label + '.command.json'), dict(argv=argv, timeout_s=timeout))
    started = time.monotonic()
    with (dest / (label + '.log')).open('x') as log:
        def limits():
            if label == 'spike':
                resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
        child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, preexec_fn=limits)
        try:
            rc = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            raise RuntimeError('Bound exceeded: ' + label)
    result = dict(returncode=rc, elapsed_s=time.monotonic() - started, pid=child.pid)
    save(dest / (label + '.exit.json'), result)
    assert rc == expected, (label, result)
    return (dest / (label + '.log')).read_text()


def compare(op, a, b):
    def info(v):
        nan = v & 0x7f800000 == 0x7f800000 and v & 0x7fffff != 0
        return nan, nan and not v & 0x400000
    an, sn = info(a); bn, tn = info(b)
    unordered = an or bn
    equal = not unordered and (a == b or a & 0x7fffffff == b & 0x7fffffff == 0)
    key = lambda v: (~v & 0xffffffff) if v >> 31 else v | 0x80000000
    less = not unordered and not equal and key(a) < key(b)
    bit = (equal, not equal, less, less or equal,
           not unordered and not equal and not less, not unordered and not less)[op]
    nv = (sn or tn) if op < 2 else unordered
    return int(bit), 16 if nv else 0


def model(original, cap, destination, unboxed, bound):
    fixture = (original / 'fixtures.h').read_text()
    raw = [int(x, 16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)', fixture)]
    assert len(raw) == 16
    gold = json.loads(fixture.split('expected[6][16][16]=')[1].split(';')[0].replace('{', '[').replace('}', ']'))
    assert all(compare(op, a, b) == tuple(gold[op][i][j])
               for op in range(6) for i, a in enumerate(raw) for j, b in enumerate(raw))
    rows, inputs = [], []
    exhaustive = 0
    for seed in range(32):
        for op in range(10):
            for vl in (0, 1, 2, 3, cap // 2, cap - 1, cap):
                for mode in range(4):
                    for sticky in range(2):
                        a = [raw[(i + seed + 7 * (seed // 16)) % 16] for i in range(cap)]
                        b = [raw[(i * 3 + seed * 5 + seed // 16) % 16 if op < 4 else seed % 16]
                             for i in range(cap)]
                        indices = []
                        for values in (a, b):
                            packed = tuple(values[i] | (values[i + 1] << 32) for i in range(0, cap, 2))
                            if packed not in inputs: inputs.append(packed)
                            indices.append(inputs.index(packed))
                        flags, allowed = sticky, []
                        for i in range(cap):
                            bi = raw[14] if unboxed and op >= 4 else b[i]
                            bit, nv = compare(op if op < 4 else op - 4, a[i], bi)
                            old = ((a if destination == 1 else b)[i // 32] >> (i % 32)) & 1
                            allowed.append({bit} if i < vl else {old} if vl == 0 else {old, 1, bit})
                            if i < vl: flags |= nv
                        zero, one = [], []
                        for byte in range(cap // 8):
                            z = sum((1 not in allowed[byte * 8 + j]) << j for j in range(8))
                            o = sum((0 not in allowed[byte * 8 + j]) << j for j in range(8))
                            zero.append(z); one.append(o)
                            for v in range(256):
                                scalar = sum(((v >> j) & 1) not in allowed[byte * 8 + j] for j in range(8))
                                assert scalar == POPCOUNTS[(v & z) | (~v & o)]
                                exhaustive += 1
                        rows.append(dict(seed=seed, op=op, vl=vl, mode=mode, sticky=sticky,
                                         ai=indices[0], bi=indices[1], flags=flags, zero=zero, one=one))
                        if len(rows) == bound:
                            return rows, inputs, exhaustive
    raise AssertionError('Bad bound')


def tables(rows, inputs, cap):
    text = '#include <stdint.h>\n#define CAP %d\n#define BOUND %d\n' % (cap, len(rows))
    text += 'static const uint64_t input_rows[][%d]={\n' % (cap // 2)
    text += ''.join('{' + ','.join('UINT64_C(%s)' % hex(x) for x in row) + '},\n' for row in inputs) + '};\n'
    text += 'static const uint64_t mask_rows[]={0xffffffffffffffffULL,0xaaaaaaaaaaaaaaaaULL,0x2424242424242424ULL,0};\n'
    text += 'struct packed_case {uint16_t vl; uint8_t seed,op,mode,sticky,ai,bi,flags; uint8_t must_zero[%d],must_one[%d];};\n' % (cap // 8, cap // 8)
    text += 'static const struct packed_case records[]={\n'
    for g in rows:
        text += '{' + ','.join(str(g[k]) for k in ('vl', 'seed', 'op', 'mode', 'sticky', 'ai', 'bi', 'flags'))
        text += ',{' + ','.join(map(str, g['zero'])) + '},{' + ','.join(map(str, g['one'])) + '}},\n'
    text += '};\nstatic const uint8_t popcounts[256]={' + ','.join(map(str, POPCOUNTS)) + '};\n'
    return text


def prepare(args):
    dest = args.out.resolve()
    assert dest.is_relative_to(HERE) and not dest.exists()
    dest.mkdir()
    name, cap, destination, unboxed, bound = CASES[args.case]
    original = PARENT / name / 'original'
    plan = json.loads((PARENT / 'prepared.json').read_text())
    for group in ('pins', 'files'):
        assert all(sha(p) == d for p, d in plan[group].items())
    rows, inputs, exhaustive = model(original, cap, destination, unboxed, bound)
    (dest / 'tables.h').write_text(tables(rows, inputs, cap))
    # Existing original prefix keeps every predecessor and the exact scalar oracle.
    source = (PARENT / name / 'prefix/case.c').read_text()
    entry = name + '_prefix_main'
    assert source.count(entry) == 1
    (dest / 'original.c').write_text(source.replace(entry, 'original_main'))
    (dest / 'packed.c').write_text((HERE / 'checker.c').read_text())
    defines = ['-DSEW=32', '-DUNMASKED_COMPARISONS=1', '-DRESTART_COMPARISONS=0',
               '-DDESTINATION_KIND=%d' % destination, '-DUNBOXED_COMPARISONS=%d' % unboxed]
    include = ['-I' + str(original), '-I' + str(dest)]
    host_flags = ['gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-tree-vectorize', '-fno-tree-slp-vectorize']
    for variant in ('original', 'packed'):
        command([*host_flags, *defines, *include, '-DENTRY=' + variant + '_main',
                 dest / (variant + '.c'), HERE / 'host.c', '-o', dest / variant], dest, variant + '_compile')
    for mutation in range(10):
        logs = [command([dest / variant, mutation], dest, variant + str(mutation), expected=int(mutation >= 3))
                for variant in ('original', 'packed')]
        assert logs[0] == logs[1], (mutation, logs)
    flags = ['-O2', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-nostdlib', '-static',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize',
             '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-ffunction-sections', '-fdata-sections',
             '-Wl,--build-id=none', '-Wl,--gc-sections', '-Wall', '-Wextra', '-Werror']
    runtime = PARENT / name / 'single'
    (dest / 'main.c').write_text('''#include <stdint.h>
extern int packed_main(void);
extern void replay_text(const char *);
int main(void) {uint64_t v; __asm__ volatile("csrr %0,vlenb":"=r"(v));
if(v!=128)return 90;
int rc=packed_main();
if(!rc){replay_text("BOARD_REPLAY_PASS\\n");}
return rc;}
''')
    specs = {}
    for backend in ('soc', 'spike'):
        command([CC, *flags, *defines, *include, *(['-DSPIKE_REFERENCE=1'] if backend == 'spike' else []),
                 '-T', runtime / 'replay.ld', dest / 'packed.c', original / 'scenario.S', dest / 'main.c',
                 runtime / 'startup.S', runtime / 'runtime.c', '-lgcc', '-o', dest / (backend + '.elf')],
                dest, backend + '_compile')
        text = subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-objdump')), '-d', dest / (backend + '.elf')], text=True)
        (dest / (backend + '.dis')).write_text(text)
        old = subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-objdump')), '-d', PARENT / name / 'prefix' / (backend + '.elf')], text=True)
        def functions(dis):
            result, current = {}, None
            for line in dis.splitlines():
                m = re.match(r'^[0-9a-f]+ <([^>]+)>:', line)
                if m: current = m[1]; result[current] = []
                m = re.match(r'^\s*[0-9a-f]+:\s+([0-9a-f]+)\s+', line)
                if m and current: result[current].append(m[1])
            return result
        newf, oldf = functions(text), functions(old)
        assert all(newf[k] == oldf[k] for k in ['capacity'] + ['op_%d' % i for i in range(10)])
        # Scalar compilation must not introduce vector instructions outside original helpers.
        current = ''
        for line in text.splitlines():
            m = re.match(r'^[0-9a-f]+ <([^>]+)>:', line)
            if m: current = m[1]
            m = re.match(r'^\s*[0-9a-f]+:\s+[0-9a-f]+\s+(v\w+)', line)
            if m: assert current == 'capacity' or current.startswith('op_'), (current, line)
        specs[backend] = sha(dest / (backend + '.elf'))
    size = command([CC.with_name('riscv64-unknown-elf-size'), dest / 'soc.elf'], dest, 'size')
    reference = None
    if args.spike:
        assert args.case == '319', 'Long prefix is prepare-only pending cost review'
        nm = subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')), '-n', dest / 'spike.elf'], text=True)
        syms = {x.split()[2]: x.split()[0] for x in nm.splitlines() if len(x.split()) == 3}
        (dest / 'spike.cmd').write_text('until pc 0 ' + syms['replay_exit'] + '\nreg 0 a0\nstr ' + syms['replay_log'] + '\nrs\n')
        log = command([SPIKE, '-d', '--debug-cmd=' + str(dest / 'spike.cmd'),
                       '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m2', '--log-commits',
                       '--log=' + str(dest / 'commits.log'), dest / 'spike.elf'], dest, 'spike', timeout=120)
        assert 'RVV_FP_COMPARE_PASS sew=32 cases=319 errors=0' in log and 'BOARD_REPLAY_PASS' in log
        assert not re.search('COMPARE_(FAIL|DETAIL)|REPLAY_(TRAP|SERVICE_FAIL)', log)
        with (dest / 'commits.log').open() as stream:
            retired = sum(bool(re.match(r'^core\s+0:\s+[0-3]\s+0x[0-9a-f]+\s+\(0x[0-9a-f]+\)', line)) for line in stream)
        reference = dict(status='SPIKE_PASS_NOT_DUT', retired_to_htif_exit=retired,
                         commit_log_bytes=(dest / 'commits.log').stat().st_size,
                         max_log_bytes=128 * 1024**2, timeout_s=120)
    pins = {str(p): sha(p) for p in [*HERE.glob('*.py'), HERE / 'checker.c', HERE / 'host.c',
                                   PARENT / 'prepared.json', CC, SPIKE]}
    result = dict(status='HOST_EQUIVALENT_COMPILED_NOT_DUT', bound=bound, cap=cap, endpoint=rows[-1],
                  fixture_checks=1536, exhaustive_byte_values=exhaustive,
                  flow_pairs=10, allowed_variants=3, negative_variants=7, unique_input_rows=len(inputs),
                  helper_instruction_bytes_identical=True, scalar_only_outside_helpers=True,
                  size_output=size, reference=reference, elfs=specs, pins=pins,
                  limitations='No VCS/FPGA. Scalar timing changes; no claim of cycle history equivalence. Long prefix not executed.')
    result['files'] = {str(p): sha(p) for p in dest.iterdir() if p.is_file()}
    save(dest / 'result.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'bound', 'exhaustive_byte_values', 'size_output', 'reference')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--spike', action='store_true')
    prepare(parser.parse_args())
