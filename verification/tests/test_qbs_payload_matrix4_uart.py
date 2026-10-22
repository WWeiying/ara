import copy
import json
import unittest
import build_qbs_payload_matrix4_uart as m


class UARTBinding(unittest.TestCase):
    def test_failed_elf_rejected(self):
        p=m.ROOT/'verification/out/qbs-payload-matrix4-preflight764-agent-20261007-02'
        meta=json.loads((p/'dut.metadata.log').read_bytes())[0]
        with self.assertRaises(ValueError):m.printf_gate(meta,(p/'qbs_payload_matrix4.elf').read_bytes())

    def test_exact_source_only_binding(self):
        source=(m.APP/'main.c').read_text()
        self.assertEqual(source,'#include <stdio.h>\n#ifndef MATRIX_HOST\n#include "../common/printf.h"\n#endif\n#include "../qbs_payload_matrix4/main.c"\n')
        self.assertEqual(m.base.common.sha(m.ROOT/'apps/qbs_payload_matrix4/main.c'),m.APP_SHA)

    def test_missing_uart_rejected(self):
        p=m.ROOT/'verification/out/qbs-payload-phase-preflight763-agent-20261007-01'
        meta=json.loads((p/'dut.metadata.log').read_bytes())[0]
        meta['Symbols']=[r for r in meta['Symbols'] if r['Symbol']['Name']['Name']!='printf_']
        with self.assertRaises(ValueError):m.printf_gate(meta,(p/'qbs_payload_phase763.elf').read_bytes())

    def test_signed_offsets(self):
        self.assertEqual(m.signed(0xfff,12),-1)
        self.assertEqual(m.signed(0xffff8000,32),-32768)


if __name__=='__main__':unittest.main()
