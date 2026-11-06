#!/usr/bin/env python3
"""No target execution: strict handoff terminal and DPI preload admission policy."""
import argparse
import json
from pathlib import Path
import unittest

import wide_soc_memory_smoke_handoff_build as build


class HandoffTests(unittest.TestCase):
    def test_exact_pass_zero_traps_only(self):
        self.assertEqual(build.check_log(build.PASS+'\n')['expected_exceptions'], 0)
        for bad in (build.PASS.replace('traps=0', 'traps=1'), build.PASS+'\n'+build.PASS,
                    'QBS/AKV handoff smoke: SKIP (QBS disabled)\n',
                    'QBS/AKV handoff smoke: SKIP (AKV-v2 disabled)\n',
                    build.PASS+'\nRVV mismatch[0]\n', build.PASS+'\nFatal: unrelated\n',
                    build.PASS.replace('PASS', 'FAIL'), build.PASS+'\nmcause_val: 2\n'):
            with self.assertRaises(ValueError):
                build.check_log(bad)

    def test_loader_rounding_and_bss(self):
        sections = ('  [ 1] .text PROGBITS 0000000080000000 001000 00003f 00 AX 0 0 4\n'
                    '  [ 2] .bss NOBITS 0000000080000040 00103f 000008 00 WA 0 0 32\n')
        programs = ' LOAD 0x001000 0x0000000080000000 0x0000000080000000 0x00003f 0x000048 RWE 0x1000\n'
        proof = build.loader_admission(sections, programs)
        self.assertEqual(proof['dpi_enumerated_segments'][0]['rounded_end'], 0x80000060)
        self.assertEqual(len(proof['allocated_sections']), 2)
        for bad_s, bad_p in ((sections.replace('80000040', '80000030'), programs),
                             (sections.replace('00003f', '000041'), programs),
                             (sections, programs.replace('0x00003f', '0x000000')),
                             (sections, programs+programs),
                             (sections, programs.replace('0x000048', '0x000040'))):
            with self.assertRaises(ValueError):
                build.loader_admission(bad_s, bad_p)

    def test_loader_is_program_segment_not_section_enumeration(self):
        loader = build.memory.MAIN/'hardware/tb/dpi/elfloader.cc'
        text = loader.read_text()
        self.assertIn('p_paddr,p_memsz', build.loader_contract(text))
        with self.assertRaises(ValueError):
            build.loader_contract(text.replace('ph[i].p_memsz));', 'ph[i].p_filesz));'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path)
    args, rest = parser.parse_known_args()
    if args.log:
        print(json.dumps(build.check_log(args.log.read_text()), indent=2))
    else:
        unittest.main(argv=[__file__, *rest])
