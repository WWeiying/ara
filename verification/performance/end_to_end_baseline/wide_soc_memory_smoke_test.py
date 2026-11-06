#!/usr/bin/env python3
"""Host oracle/static tests and strict collector for main-owned SoC simulation logs."""
import argparse
import json
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
MASK64 = (1 << 64)-1


def pattern(salt, case, byte):
    return (salt+case*29+byte*37+byte//7) & 255


def selected(mode, lane, vl, phase_index):
    if lane >= vl:
        return False
    return (mode == 0 or mode == 1 and (lane+phase_index) % 2 == 0 or
            mode == 2 and (lane+phase_index) % 2 == 1 or
            mode == 3 and (lane == 0 or lane == vl-1 or lane % 5 == 2))


def configurations(vlenb):
    if vlenb not in (32, 64, 128, 256, 512):
        raise ValueError('Unsupported vector register size')
    for size in (1, 2, 4, 8):
        maximum = vlenb//size
        for phase in range(0, 32, size):
            for mode, vl in enumerate((maximum, maximum-1, 1, (maximum+1)//2)):
                yield size, phase, mode, vl


def expected(vlenb):
    digest, checks = 0xcbf29ce484222325, 0

    def consume(value):
        nonlocal digest, checks
        digest = ((digest ^ value)*1099511628211) & MASK64
        checks += 1

    case = 0
    for size in (1, 2, 4, 8):
        for phase in range(0, 32, size):
            for position in range(3):
                value = (0xfedcba9876543210 ^ (case*0x01030507090b0d0f & MASK64))
                if position == 0:
                    value |= 0x8080808080808080
                elif position == 1:
                    value &= 0x7f7f7f7f7f7f7f7f
                for byte in range(size+32):
                    consume(value >> (8*(byte-16)) & 255 if 16 <= byte < 16+size else pattern(0x69, case, byte))
                case += 1
    source_crossings = target_crossings = 0
    for case, (size, phase, mode, vl) in enumerate(configurations(vlenb)):
        src, dst = 4096-16+phase, 4096-16+(phase+16) % 32
        source_crossings += src < 4096 < src+vl*size
        target_crossings += dst < 4096 < dst+vl*size
        for byte in range(vlenb+32):
            payload = 16 <= byte < 16+vlenb
            active = payload and selected(mode, (byte-16)//size, vl, phase//size)
            consume(pattern(0x31, case, byte))
            consume(pattern(0x31 if active else 0x57, case, byte))
            if not payload or active or mode in (1, 3):
                consume(pattern(0xc3 if not payload else 0x31 if active else 0x91, case, byte))
    return dict(scalar_cases=180, vector_cases=240, value_checks=360, byte_checks=checks,
                vlenb=vlenb, vector_insns=1924, source_crossings=source_crossings,
                target_crossings=target_crossings, digest=f'{digest:016x}')


def check_log(text):
    if re.search(r'(?i)\bFAIL\b|Fatal:|Error[-:]|UVM_(?:ERROR|FATAL)|mcause_val|trap|timeout', text):
        raise ValueError('Failure/trap/tool diagnostic in smoke log')
    lines = text.replace('\r', '').splitlines()
    markers = [line for line in lines if line.startswith('WIDE_SOC_MEMORY_SMOKE_')]
    if len(markers) != 3 or markers[0] != 'WIDE_SOC_MEMORY_SMOKE_BEGIN version=1':
        raise ValueError('Missing/duplicate/unexpected smoke markers')
    if not re.fullmatch(r'WIDE_SOC_MEMORY_SMOKE_END status=PASS cycles=[1-9][0-9]*', markers[1]):
        raise ValueError('Missing exact successful end marker')
    prefix = 'WIDE_SOC_MEMORY_SMOKE_PASS '
    if not markers[2].startswith(prefix):
        raise ValueError('Missing exact PASS terminal')
    fields = {}
    for item in markers[2][len(prefix):].split():
        key, sep, value = item.partition('=')
        if not sep or key in fields:
            raise ValueError('Malformed/duplicate terminal field')
        if key == 'digest':
            if not re.fullmatch('[0-9a-f]{16}', value):
                raise ValueError('Malformed digest')
            fields[key] = value
        else:
            if not re.fullmatch('[0-9]+', value):
                raise ValueError('Malformed numeric terminal field')
            fields[key] = int(value)
    if fields != expected(fields.get('vlenb', 0)):
        raise ValueError('Scalar-oracle accounting/digest mismatch')
    return fields


class MemorySmokeTests(unittest.TestCase):
    def test_geometry_and_alignment(self):
        for vlenb in (32, 64, 128, 256, 512):
            rows = list(configurations(vlenb))
            self.assertEqual(len(rows), 240)
            for size, phase, mode, vl in rows:
                self.assertEqual(phase % size, 0)
                self.assertTrue(1 <= vl <= vlenb//size)
                for at in (4096-16+phase, 4096-16+(phase+16) % 32):
                    self.assertEqual(at % size, 0)
                    self.assertTrue(0 <= at-16 < at+vlenb+16 < 8192)
            self.assertGreater(expected(vlenb)['source_crossings'], 0)
            self.assertGreater(expected(vlenb)['target_crossings'], 0)

    def test_mask_tail_contract(self):
        for size, phase, mode, vl in configurations(128):
            active = [selected(mode, lane, vl, phase//size) for lane in range(128//size)]
            self.assertFalse(any(active[vl:]))
            if mode == 0:
                self.assertTrue(all(active))
            if mode == 3:
                self.assertTrue(active[0] and active[vl-1])
        self.assertFalse(selected(2, 0, 1, 0))
        self.assertTrue(selected(2, 0, 1, 1))

    def test_strict_log_and_mutations(self):
        fields = expected(128)
        terminal = 'WIDE_SOC_MEMORY_SMOKE_PASS '+' '.join(f'{k}={v}' for k,v in fields.items())
        log = 'WIDE_SOC_MEMORY_SMOKE_BEGIN version=1\nWIDE_SOC_MEMORY_SMOKE_END status=PASS cycles=123\n'+terminal+'\n'
        self.assertEqual(check_log(log), fields)
        for bad in (log+terminal+'\n', log+'Fatal: unrelated\n', log+'mcause_val: 2\n',
                    log.replace('scalar_cases=180', 'scalar_cases=179'), log.replace('1924', '1923'),
                    log.replace('digest=', 'extra=1 digest='), log.replace('cycles=123', 'cycles=0'),
                    log.replace('status=PASS', 'status=FAIL'), log.replace('BEGIN version=1', 'BEGIN version=2')):
            with self.assertRaises(ValueError):
                check_log(bad)

    def test_assembly_and_scalar_oracle_stay_independent(self):
        source = (HERE/'wide_soc_memory_smoke.c').read_text()
        assembly = (HERE/'wide_soc_memory_smoke.S').read_text()
        for token in ('sb a2', 'sh a2', 'sw a2', 'sd a2', 'lbu a0', 'lhu a0', 'lwu a0', 'ld a0', 'lb a0', 'lh a0', 'lw a0'):
            self.assertIn(token, assembly)
        self.assertIn('ta, ma', assembly)
        self.assertIn('tu, mu', assembly)
        self.assertIn('v0.t', assembly)
        for bits in (8, 16, 32, 64):
            self.assertIn(f'MEMORY_CASE {bits}', assembly)
        self.assertNotIn('riscv_vector.h', source)
        self.assertNotIn('.insn', assembly)
        self.assertNotIn('QBS', assembly)
        self.assertIn('!payload || selected || undisturbed', source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path)
    args, rest = parser.parse_known_args()
    if args.log:
        print(json.dumps(check_log(args.log.read_text()), indent=2))
    else:
        unittest.main(argv=[__file__, *rest])
