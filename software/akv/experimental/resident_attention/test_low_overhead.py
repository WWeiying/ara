#!/usr/bin/env python3
"""Check assembled preparation identity and bounded stackless scalar paths.

No custom arithmetic or board performance is simulated by this audit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
CC = '/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc'
OBJDUMP = str(Path(CC).with_name('riscv64-unknown-elf-objdump'))
NM = str(Path(CC).with_name('riscv64-unknown-elf-nm'))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    out = parser.parse_args().output.resolve()
    out.mkdir(exist_ok=False)
    paths = [HERE / n for n in ('pv.S', 'qk.S', 'pv_prepare.S', 'pv_fast.inc', 'test_low_overhead.py')]
    pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result = dict(state='FAIL', arithmetic_executed=False, board_executed=False)
    try:
        obj = out / 'pv.o'
        subprocess.run([CC, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-c',
                        str(HERE / 'pv.S'), '-o', str(obj)], check=True)
        qk_obj = out / 'qk.o'
        subprocess.run([CC, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-c',
                        str(HERE / 'qk.S'), '-o', str(qk_obj)], check=True)
        elf = out / 'leaves.elf'
        subprocess.run([CC, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-nostdlib',
                        '-Wl,--no-relax,-Ttext=0x10000,-e,akv_experimental_resident_qk_prepared',
                        str(obj), str(qk_obj), '-o', str(elf)], check=True)
        dis = subprocess.check_output([OBJDUMP, '-d', str(elf)], text=True)
        (out / 'pv.dump').write_text(dis)
        symbols = subprocess.check_output([NM, '-S', str(elf)], text=True)
        def body(name):
            m = re.search(r'(?m)^([0-9a-f]+) ([0-9a-f]+) \w ' + name + '$', symbols)
            require(m is not None, 'missing symbol ' + name)
            start, size = int(m[1], 16), int(m[2], 16)
            rows = [(int(a, 16), int(w, 16)) for a, w in
                    re.findall(r'(?m)^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s', dis)
                    if start <= int(a, 16) < start + size]
            require(len(rows) * 4 == size, 'non-32-bit or missing code')
            return b''.join(w.to_bytes(4, 'little') for _, w in rows)
        prep = body('akv_experimental_resident_pv_prepare')
        fast = body('akv_experimental_resident_pv_fast')
        require(prep[-4:] == bytes.fromhex('67800000'), 'prep no longer ends in ret')
        require(fast.count(prep[:-4]) == 1, 'FP/vector payload not byte-identical')
        prepared = body('akv_experimental_resident_pv_prepared')
        require(len(prepared) == 8 and prepared[:4] == bytes.fromhex('930f0800'), 'prepared PV ABI')
        def address(name):
            return int(re.search(r'(?m)^([0-9a-f]+) [0-9a-f]+ \w ' + name + '$', symbols)[1], 16)
        jump = int.from_bytes(prepared[4:], 'little')
        require(jump & 0xfff == 0x6f, 'prepared PV must jump without changing RA')
        offset = ((jump >> 31) << 20) | (((jump >> 12) & 255) << 12) | \
                 (((jump >> 20) & 1) << 11) | (((jump >> 21) & 1023) << 1)
        if offset & (1 << 20):
            offset -= 1 << 21
        require(address('akv_experimental_resident_pv_prepared') + 4 + offset ==
                address('akv_experimental_resident_pv_fast') + fast.index(prep[:-4]),
                'linked prepared PV does not enter the identical payload')
        old_qk = body('akv_experimental_resident_qk')
        new_qk = body('akv_experimental_resident_qk_prepared')
        qk_word = bytes.fromhex('5b700506')
        require(old_qk[old_qk.index(qk_word):] == new_qk[new_qk.index(qk_word):],
                'QK instruction/store tail changed')
        moves = [int.from_bytes(new_qk[i:i+4], 'little') for i in range(0, 16, 4)]
        require(moves == [(src << 15) | (dest << 7) | 0x13
                         for dest, src in ((5, 10), (6, 11), (7, 12), (10, 13))], 'prepared QK ABI')
        source = (HERE / 'pv_fast.inc').read_text()
        payload = source.split('.Lfast_payload:\n', 1)[1].split('    mv              a0, t6', 1)[0]
        require('t6' not in payload and not re.search(r'^\s*(?:addi|li|mv|ld|add|or)\s+a[0-5]\s*,', payload, re.M),
                'payload changed control or argument registers')
        code, labels = [], {}
        for raw in source.splitlines():
            line = raw.split('//')[0].strip()
            if not line or (line.startswith('.') and not line.endswith(':') and not line.startswith('.word')):
                continue
            if line.endswith(':'):
                labels[line[:-1]] = len(code)
            else:
                op, *rest = line.split(None, 1)
                code.append((op, [x.strip() for x in rest[0].split(',')] if rest else []))
        begin, end = labels['.Lfast_payload'], next(i for i, x in enumerate(code) if x == ('mv', ['a0', 't6']))
        counts = []
        for tokens in range(1, 65):
            for dim in (64, 96, 128):
                for heads in (1, 2):
                    r = dict(zero=0, a0=0x1000, a1=0x2000, a2=0x3000,
                             a3=tokens, a4=dim, a5=heads, sp=0x4000, ra=0x5000)
                    pc, count, issue, stores = labels['akv_experimental_resident_pv_fast'], 0, [], []
                    for _ in range(100):
                        if pc == begin:
                            # Byte-identical preparation, already checked above.
                            r.update(t0=128, t1=1)
                            pc = end
                        op, a = code[pc]
                        pc += 1
                        count += 1
                        if op in ('addi', 'slli', 'ori'):
                            x, y = r[a[1]], int(a[2], 0)
                            r[a[0]] = x + y if op == 'addi' else x << y if op == 'slli' else x | y
                        elif op == 'or': r[a[0]] = r[a[1]] | r[a[2]]
                        elif op == 'li': r[a[0]] = int(a[1], 0)
                        elif op == 'mv': r[a[0]] = r[a[1]]
                        elif op == 'beq':
                            if r[a[0]] == r[a[1]]: pc = labels[a[2]]
                        elif op == 'j': pc = labels[a[0]]
                        elif op == '.word':
                            require(a == ['0x0485705b'], 'wrong PV opcode')
                            issue.append(r['a0'])
                        elif op == 'vsetvli':
                            require(a == ['zero', 'a4', 'e16', 'm2', 'ta', 'ma'], 'store vtype')
                        elif op == 'vse16.v': stores.append((a[0], r[a[1][1:-1]], dim))
                        elif op == 'ret': break
                        else: raise ValueError('unexpected wrapper instruction: ' + op)
                    else: raise ValueError('wrapper does not terminate')
                    expected = tokens - 1 | (heads - 1) << 6 | {64: 0, 96: 2, 128: 1}[dim] << 7
                    require(issue == [expected], 'PV control mismatch')
                    require(stores == [('v0', 0x2000, dim)] + ([('v2', 0x2200, dim)] if heads == 2 else []),
                            'result store footprint')
                    require(r['sp'] == 0x4000 and r['ra'] == 0x5000, 'ABI damage')
                    counts.append(count)
        require(all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in pins.items()), 'input drift')
        result.update(state='ASSEMBLY_AND_CONTROL_PASS', geometry_cases=len(counts),
                      prepared_pv_link_target_checked=True, prepared_qk_tail_identical=True,
                      preparation_bytes_identical=len(prep)-4, stack_accesses=0, nested_calls=0,
                      removed_per_leaf='4 stack stores + 4 stack loads + 2 SP updates + call/return; one MV added',
                      post_pins_match=True)
    finally:
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
