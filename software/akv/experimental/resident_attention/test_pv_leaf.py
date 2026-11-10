#!/usr/bin/env python3
"""PV source/control and GNU object audit only; no native or FP execution."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SEALED = ROOT / 'verification/performance/resident_rvv/pv_prepare'
PREP_SHA = '8d039dd90da0b00497429be90483d0ed9f3576c1400f458889e9e8cd380968be'
SYMBOL = 'akv_experimental_resident_pv'
PREP_SYMBOL = SYMBOL + '_prepare'
GNU = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-')
ASSEMBLY_DIR = None

spec = importlib.util.spec_from_file_location('sealed_pv_preparation_checks', SEALED / 'test_prepare.py')
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
prep.SOURCE = HERE / 'pv_prepare.S'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wrapper_program(text):
    body = text.split(SYMBOL + ':', 1)[1].split('.size ' + SYMBOL, 1)[0]
    code, labels = [], {}
    for raw in body.splitlines():
        line = raw.split('//', 1)[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            require(line[:-1] not in labels, 'Duplicate label')
            labels[line[:-1]] = len(code)
        else:
            op, args = line.split(None, 1) if ' ' in line or '\t' in line else (line, '')
            code.append((op, tuple(a.strip() for a in args.split(','))))
    return code, labels


def check_shape(text, tokens, dimensions, heads):
    """Bounded scalar control-path audit; payloads/FPU/custom op are not modeled."""
    code, labels = wrapper_program(text)
    regs = dict(zero=0, sp=0x400000, ra=0x500000, a0=0x100000,
                a1=0x200000, a2=0x300000, a3=tokens, a4=dimensions, a5=heads)
    stack, stores, calls, issues = {}, [], 0, []
    stack_writes, stack_reads = [], []
    pc, vl = 0, None
    for _ in range(64):
        op, a = code[pc]
        pc += 1
        if op == 'addi':
            regs[a[0]] = regs[a[1]] + int(a[2], 0)
        elif op == 'li':
            regs[a[0]] = int(a[1], 0)
        elif op in ('slli', 'ori'):
            x, y = regs[a[1]], int(a[2], 0)
            regs[a[0]] = x << y if op == 'slli' else x | y
        elif op == 'or':
            regs[a[0]] = regs[a[1]] | regs[a[2]]
        elif op in ('sd', 'ld'):
            m = re.fullmatch(r'(\d+)\(sp\)', a[1])
            require(m is not None, 'Only private stack scalar memory allowed')
            address = regs['sp'] + int(m[1])
            require(0x400000 - 32 <= address <= 0x400000 - 8 and address % 8 == 0,
                    'Outside private stack frame')
            if op == 'sd':
                stack[address] = regs[a[0]]
                stack_writes.append(address)
            else:
                regs[a[0]] = stack[address]
                stack_reads.append(address)
        elif op == 'beq':
            if regs[a[0]] == regs[a[1]]:
                pc = labels[a[2]]
        elif op == 'j':
            pc = labels[a[0]]
        elif op == 'call':
            require(a == (PREP_SYMBOL,) and calls == 0 and not issues, 'Unexpected call')
            require(regs['sp'] == 0x400000 - 32, 'Unaligned/wrong call stack')
            require(tuple(regs[f'a{i}'] for i in range(6)) ==
                    (0x100000, 0x200000, 0x300000, tokens, dimensions, heads),
                    'Preparation arguments changed')
            events, _ = prep.trace(tokens, dimensions, heads)
            reads = [address for event in events for address in event.get('reads', ())]
            expected = [0x200000 + 512*h + 2*i for h in range(heads) for i in range(dimensions)]
            expected += [0x300000 + 4*h for h in range(heads)]
            expected += [0x100000 + 256*h + 4*i for h in range(heads) for i in range(tokens)]
            require(reads == expected, 'Preparation active input spans')
            regs.update(ra=0xDEAD, t0=0xBAD0, t1=0xBAD1)
            calls += 1
        elif op == '.word':
            require(a == ('0x0485705b',) and calls == 1 and not issues,
                    'Wrong opcode/order/count')
            expected = tokens - 1 | (heads - 1) << 6 | {64: 0, 96: 2, 128: 1}[dimensions] << 7
            require(regs['a0'] == expected, 'Wrong PV control')
            issues.append(regs['a0'])
        elif op == 'vsetvli':
            require(len(issues) == 1 and a == ('zero', 'a4', 'e16', 'm2', 'ta', 'ma'),
                    'Vector work between preparation and issue/wrong store mode')
            vl = regs['a4']
        elif op == 'vse16.v':
            require(len(issues) == 1 and vl == dimensions, 'Wrong active store length/order')
            m = re.fullmatch(r'\((\w+)\)', a[1])
            require(m is not None, 'Unexpected result store address')
            stores.append((a[0], regs[m[1]], vl))
        elif op == 'ret':
            require(regs['sp'] == 0x400000 and regs['ra'] == 0x500000, 'SP/RA not restored')
            require(calls == len(issues) == 1, 'Missing preparation or issue')
            require(sorted(stack_reads) == sorted(stack_writes) ==
                    list(range(0x400000 - 32, 0x400000, 8)), 'Stack save/restore mismatch')
            require(stores == [('v0', 0x200000, dimensions)] +
                    ([('v2', 0x200200, dimensions)] if heads == 2 else []),
                    'Active-head store footprint mismatch')
            return
        else:
            raise ValueError('Unreviewed instruction: ' + op)
    raise ValueError('Control path did not return')


def object_rows(text, symbol):
    match = re.search(r'(?m)^\s*([0-9a-f]+) <' + symbol + r'>:\s*$', text)
    require(match is not None, 'Missing object symbol: ' + symbol)
    body = text[match.end():]
    end = re.search(r'(?m)^\s*[0-9a-f]+ <[^>]+>:', body)
    if end:
        body = body[:end.start()]
    rows = []
    for line in body.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*?)\s*$', line)
        if m:
            args = re.sub(r'\s*<[^>]+>', '', m[4].split('#', 1)[0]).strip()
            rows.append((int(m[1], 16), int(m[2], 16), m[3], args.split(',')))
        elif re.match(r'^\s*[0-9a-f]+:', line):
            raise ValueError('Non-32-bit/unrecognized object instruction')
    return int(match[1], 16), rows


def signed(value, bits):
    return value - (1 << bits) if value >> (bits - 1) else value


def check_object(text):
    code, labels = wrapper_program((HERE / 'pv.S').read_text())
    base, rows = object_rows(text, SYMBOL)
    prep_base, _ = object_rows(text, PREP_SYMBOL)
    addresses, offset = [], 0
    for op, _ in code:
        addresses.append(base + offset)
        offset += 8 if op == 'call' else 4
    require(len(rows) * 4 == offset, 'Wrapper object length changed')
    require([r[0] for r in rows] == list(range(base, base + offset, 4)), 'Noncontiguous object')
    index = 0
    for (op, args), address in zip(code, addresses):
        row = rows[index]
        index += 1
        if op == 'call':
            second = rows[index]
            index += 1
            hi, lo = row[1], second[1]
            require(hi & 0xfff == 0x097 and lo & 0xfffff == 0x080e7, 'Wrong preparation call encoding')
            target = address + signed(hi & 0xfffff000, 32) + signed(lo >> 20, 12)
            require(target == prep_base, 'Call does not target included preparation')
            continue
        if op == '.word':
            require(row[1] == 0x0485705b, 'Wrong custom instruction encoding')
            continue
        wanted = [re.sub(r'\b(?:' + '|'.join(prep.REGISTERS) + r')\b',
                        lambda m: prep.REGISTERS[m[0]], arg) for arg in args]
        if op == 'li':
            op, wanted = 'addi', [wanted[0], 'x0', wanted[1]]
        elif op == 'ret':
            op, wanted = 'jalr', ['x0', '0(x1)']
        elif op == 'j':
            op, wanted = 'jal', ['x0', f'{addresses[labels[args[0]]]:x}']
        elif op == 'beq':
            wanted[2] = f'{addresses[labels[args[2]]]:x}'
        elif op == 'slli':
            wanted[2] = hex(int(wanted[2], 0))
        require((row[2], row[3]) == (op, wanted), f'Wrapper instruction mismatch at {address:x}')
    old_symbol = prep.SYMBOL
    try:
        prep.SYMBOL = PREP_SYMBOL
        prep.check_disassembly(text, (HERE / 'pv_prepare.S').read_text().replace(old_symbol, PREP_SYMBOL))
    finally:
        prep.SYMBOL = old_symbol


class PreparationSuccessorChecks(prep.PrepareTests):
    """Run the unchanged preparation contract suite on the successor bytes."""


class PvLeafSourceChecks(unittest.TestCase):
    def test_preparation_identity_and_mechanical_namespace(self):
        self.assertEqual(sha(HERE / 'pv_prepare.S'), PREP_SHA)
        self.assertEqual((HERE / 'pv_prepare.S').read_bytes(), (SEALED / 'prepare.S').read_bytes())
        text = (HERE / 'pv.S').read_text()
        self.assertEqual(re.findall(r'^#.*$', text, re.M), [
            '#define resident_pv_prepare ' + PREP_SYMBOL,
            '#include "pv_prepare.S"', '#undef resident_pv_prepare'])
        self.assertIn('.hidden ' + PREP_SYMBOL, text)

    def test_declaration_uses_scalar_c_abi(self):
        text = (HERE / 'pv.h').read_text()
        declaration = ('void akv_experimental_resident_pv(const float *probability, '
                       'uint16_t *accumulator, const float *old_scale, uint32_t tokens, '
                       'uint32_t dimensions, uint32_t heads);')
        self.assertIn(declaration, ' '.join(text.split()))
        self.assertIn('extern "C" {', text)
        self.assertNotIn('riscv_vector_cc', text)

    def test_all_384_control_and_active_memory_paths(self):
        text = (HERE / 'pv.S').read_text()
        for d in (64, 96, 128):
            for h in (1, 2):
                for t in range(1, 65):
                    with self.subTest(t=t, d=d, h=h):
                        check_shape(text, t, d, h)

    def test_wrapper_has_no_global_csr_or_fp_work(self):
        code, _ = wrapper_program((HERE / 'pv.S').read_text())
        allowed = {'addi', 'sd', 'ld', 'call', 'slli', 'or', 'li', 'beq',
                   'ori', 'j', '.word', 'vsetvli', 'vse16.v', 'ret'}
        self.assertLessEqual({op for op, _ in code}, allowed)
        for op, a in code:
            if op in ('addi', 'ld', 'slli', 'or', 'li', 'ori'):
                self.assertIn(a[0], ('sp', 'ra', 'a0', 'a1', 'a4', 'a5', 't0'))
        self.assertEqual([a for op, a in code if op == 'call'], [(PREP_SYMBOL,)])

    def test_control_store_and_abi_mutations_fail(self):
        text = (HERE / 'pv.S').read_text()
        mutations = (
            ('slli            t0, t0, 6', 'slli            t0, t0, 7'),
            ('ori             a0, a0, 256', 'ori             a0, a0, 128'),
            ('0x0485705b', '0x0605705b'),
            ('beq             a5, t0, .Lsdk_pv_done', 'beq             a5, zero, .Lsdk_pv_done'),
            ('addi            t0, a1, 512', 'addi            t0, a1, 256'),
            ('vse16.v         v2, (t0)', 'vse16.v         v0, (t0)'),
            ('vsetvli         zero, a4,', 'vsetvli         zero, a3,'),
            ('ld              ra, 0(sp)', 'ld              ra, 8(sp)'),
            ('addi            sp, sp, 32', 'addi            sp, sp, 16'),
            ('addi            a0, a3, -1', 'csrwi fcsr, 0\n    addi a0, a3, -1'),
            ('addi            a0, a3, -1', 'call wrong_helper\n    addi a0, a3, -1'),
            ('addi            a0, a3, -1', 'vsetvli zero, a4, e16, m2, ta, ma\n    addi a0, a3, -1'),
        )
        for old, new in mutations:
            self.assertIn(old, text)
            mutant = text.replace(old, new, 1)
            with self.subTest(mutation=old), self.assertRaises(ValueError):
                for h in (1, 2):
                    check_shape(mutant, 9, 96, h)


class PvLeafObjectChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(ASSEMBLY_DIR) if ASSEMBLY_DIR else Path(tempfile.mkdtemp(prefix='pv-leaf-static-'))
        if ASSEMBLY_DIR:
            cls.directory.mkdir(exist_ok=False)
        directory = cls.directory
        obj, elf = directory / 'pv.o', directory / 'pv.elf'
        commands = [
            [str(GNU) + 'gcc', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
             '-x', 'assembler-with-cpp', '-c', str(HERE / 'pv.S'), '-o', str(obj)],
            [str(GNU) + 'ld', '--no-relax', '-Ttext=0x10000', '-e', SYMBOL, str(obj), '-o', str(elf)],
            [str(GNU) + 'objdump', '-d', '-M', 'no-aliases,numeric', str(elf)],
            [str(GNU) + 'readelf', '-sW', str(elf)],
        ]
        pins = {str(p): sha(p) for p in (HERE / 'pv.S', HERE / 'pv.h', HERE / 'pv_prepare.S',
                 Path(__file__), SEALED / 'test_prepare.py', SEALED / 'prepare.S')}
        pins.update({argv[0]: sha(argv[0]) for argv in commands})
        (directory / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        (directory / 'commands.json').write_text(json.dumps([
            dict(argv=argv, cwd=str(directory), timeout=30) for argv in commands], indent=2) + '\n')
        for name, argv in zip(('assembly', 'link', 'disassembly', 'symbols'), commands):
            with (directory / (name + '.log')).open('x') as log:
                subprocess.run(argv, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=30)
        cls.disassembly = (directory / 'disassembly.log').read_text()
        cls.symbols = (directory / 'symbols.log').read_text()
        require(all(sha(p) == h for p, h in pins.items()), 'Static-build source/tool drift')
        print('GNU_STATIC_OBJECT_DIRECTORY=' + str(directory), flush=True)

    def test_exact_assembled_wrapper_and_preparation(self):
        check_object(self.disassembly)
        self.assertRegex(self.symbols, r'FUNC\s+GLOBAL\s+HIDDEN\s+\d+\s+' + PREP_SYMBOL + r'\b')
        self.assertNotRegex(self.symbols, r'\bresident_pv_prepare\s*$')
        self.assertNotIn('resident_pv_rotation_selected', self.symbols)

    def test_object_mutations_fail(self):
        check_object(self.disassembly)
        for old, new in (('0485705b', '0605705b'),
                         ('vse16.v\tv2,', 'vse16.v\tv0,'),
                         ('fcvt.h.s\tf0,f0', 'fcvt.h.s\tf1,f0')):
            self.assertIn(old, self.disassembly)
            with self.subTest(mutation=old), self.assertRaises(ValueError):
                check_object(self.disassembly.replace(old, new, 1))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembly-dir', type=Path, help='Fresh directory; retain static objects and command logs')
    args, unittest_args = parser.parse_known_args()
    ASSEMBLY_DIR = args.assembly_dir
    result = unittest.main(argv=[sys.argv[0], *unittest_args], exit=False).result
    report = dict(status='STATIC_CHECKS_PASS_NOT_EXECUTED' if result.wasSuccessful() else 'FAIL',
                  tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  shapes=384, numerical_execution=False, hardware_acceptance=False)
    if hasattr(PvLeafObjectChecks, 'directory'):
        with (PvLeafObjectChecks.directory / 'result.json').open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
