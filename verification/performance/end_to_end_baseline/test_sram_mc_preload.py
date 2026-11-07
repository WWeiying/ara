#!/usr/bin/env python3
"""Host-only strict ELF, geometry, reversible placement and collector tests."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import sram_mc_preload as p


def fixture(segments=None, entry=p.DEFAULT_BASE):
    # (physical address, initialized bytes, memory bytes, flags)
    if segments is None: segments = [(p.DEFAULT_BASE, b'\x13\x00\x00\x00', 64, 5)]
    result = bytearray(4096)
    struct.pack_into('<16sHHIQQQIHHHHHH', result, 0,
                     b'\x7fELF\x02\x01\x01'+bytes(9), 2, 243, 1, entry, 64, 0, 0, 64, 56, len(segments), 0, 0, 0)
    for i, (address, payload, size, flags) in enumerate(segments):
        offset = len(result)
        struct.pack_into('<IIQQQQQQ', result, 64+i*56, 1, flags, offset, address, address, len(payload), size, 1)
        result.extend(payload)
    return bytes(result)


class PreloadTests(unittest.TestCase):
    def test_geometry(self):
        self.assertEqual((p.Geometry(128).banks, p.Geometry(128).columns), (8, 1))
        self.assertEqual((p.Geometry(256).banks, p.Geometry(256).columns), (4, 2))
        for args in [(0,), (7,), (24,), (True,), (128, 100), (128, 3*8192*16),
                     (128, 1<<20, 3), (128, 1<<20, p.DEFAULT_BASE+16)]:
            with self.subTest(args=args), self.assertRaises(ValueError): p.Geometry(*args)

    def test_zero_bss_gaps_unaligned(self):
        source = fixture([(p.DEFAULT_BASE+3, b'ABCD', 13, 5), (p.DEFAULT_BASE+101, b'', 8, 6)], p.DEFAULT_BASE+3)
        image, info = p.elf_image(source)
        self.assertEqual(image[:110], bytes(3)+b'ABCD'+bytes(103))
        self.assertEqual(info['defined_bytes'], 21)

    def test_overlap(self):
        base = p.DEFAULT_BASE
        image, meta = p.elf_image(fixture([(base, b'AB\x00', 4, 5), (base+1, b'B\x00', 3, 6)]))
        self.assertEqual(image[:4], b'AB\x00\x00')
        self.assertEqual(meta['identical_overlap_bytes'], 3)
        for payload in (b'C', b'B\x01'):
            with self.assertRaisesRegex(ValueError, 'overlap'):
                p.elf_image(fixture([(base, b'AB', 4, 5), (base+1, payload, len(payload), 6)]))

    def test_malformed_headers(self):
        valid = fixture()
        for offset, fmt, value in [(4, 'B', 1), (5, 'B', 2), (8, 'B', 1), (16, 'H', 3),
                                   (18, 'H', 62), (20, 'I', 2), (32, 'Q', 1), (52, 'H', 63),
                                   (54, 'H', 55), (56, 'H', 0), (40, 'Q', 4096), (60, 'H', 2)]:
            raw = bytearray(valid); struct.pack_into('<'+fmt, raw, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError): p.elf_image(raw)
        for short in (b'', valid[:63], valid[:100], valid[:-1]):
            with self.assertRaises(ValueError): p.elf_image(short)

    def test_malformed_segments(self):
        valid = fixture()
        for offset, fmt, value in [(68, 'I', 8), (72, 'Q', 1<<63), (88, 'Q', p.DEFAULT_BASE+1),
                                   (96, 'Q', 65), (104, 'Q', 1<<63), (112, 'Q', 3), (112, 'Q', 8192),
                                   (24, 'Q', p.DEFAULT_BASE+16)]:
            raw = bytearray(valid); struct.pack_into('<'+fmt, raw, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError): p.elf_image(raw)
        for address in (p.DEFAULT_BASE-1, p.DEFAULT_BASE+p.DEFAULT_CAPACITY-1):
            with self.assertRaises(ValueError): p.elf_image(fixture([(address, b'1234', 4, 5)], address))

    def test_all_byte_placement(self):
        # Independently invert physical macro addresses, including partial narrow columns.
        image = bytes((i*19+(i>>12)*37+(i>>17)*11) & 255 for i in range(p.DEFAULT_CAPACITY))
        for width in (64, 128, 256):
            g = p.Geometry(width)
            rebuilt, seen = bytearray(len(image)), bytearray(len(image))
            for bank, column, raw in p.column_images(image, g):
                lines = raw.splitlines()
                self.assertEqual(len(lines), 8192)
                for row, line in enumerate(lines):
                    self.assertEqual(len(line), 32)
                    value = int(line, 16)
                    for b in range(16):
                        byte = (value >> (8*b)) & 255
                        if column*16+b >= width//8:
                            self.assertEqual(byte, 0)
                        else:
                            offset = bank*(8192*width//8)+row*(width//8)+column*16+b
                            self.assertEqual(seen[offset], 0)
                            seen[offset] = 1; rebuilt[offset] = byte
            self.assertEqual(seen, bytes([1])*len(image))
            self.assertEqual(rebuilt, image)

    def test_fresh_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); elf = root/'source.elf'; elf.write_bytes(fixture())
            for width in (128, 256):
                out = root/f'w{width}'
                record = p.prepare(elf, out, width=width)
                self.assertEqual(record['state'], 'SRAM_MC_PRELOAD_IMAGE_PREPARED_NOT_EXECUTED')
                self.assertEqual(len(record['files']), 8)
                for path, sha in record['artifacts'].items(): self.assertEqual(p.sha256(Path(path).read_bytes()), sha)
                self.assertEqual(json.loads((out/'manifest.json').read_text()), record)
                with self.assertRaises(FileExistsError): p.prepare(elf, out, width=width)
            with self.assertRaisesRegex(ValueError, '256 bytes'):
                p.prepare(elf, root/('x'*230), width=128)
            with self.assertRaisesRegex(ValueError, 'non-whitespace'):
                p.prepare(elf, root/'bad name', width=128)

    def test_actual_static_hierarchy(self):
        header = Path(p.__file__).with_suffix('.svh').read_text()
        self.assertIn('`ifdef SRAM_MC_PRELOAD_ENABLE', header)
        self.assertIn('for (genvar mc_bank', header)
        self.assertIn('for (genvar mc_column = 1', header)
        self.assertIn('.gen_dram[mc_bank].i_dram.preloadData(loadfile)', header)
        self.assertIn('.gen_dram[mc_bank].gen_columns[mc_column].i_dram.preloadData(loadfile)', header)

    def test_log_collector(self):
        from run_soc_sram_mc_preload import check, expected_case
        loads = [f'MC_PRELOAD_LOADED width={w} bank={b} column={c} words=8192'
                 for w in (128, 256) for b in range(p.Geometry(w).banks) for c in range(p.Geometry(w).columns)]
        cases = ['MC_PRELOAD_CASE_PASS '+' '.join(f'{k}={v}' for k,v in expected_case(w).items()) for w in (128, 256)]
        text = '\n'.join(loads+cases+['MC_PRELOAD_COMPONENT_PASS cases=2'])
        self.assertEqual(check(text)['checked_bytes'], 2*p.DEFAULT_CAPACITY+48)
        for bad in (text+'\nFatal: test', text.replace('holds=9', 'holds=8'),
                    text.replace('column=1', 'column=0'), '\n'.join(loads+cases), text+'\n'+cases[0],
                    text.replace('reads=65537', 'reads=65536'), text+'\nMC_PRELOAD_EXTRA_PASS cases=1'):
            with self.subTest(bad=bad[-80:]), self.assertRaises(ValueError): check(bad)


if __name__ == '__main__': unittest.main()
