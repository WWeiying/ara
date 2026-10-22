"""Static contract and Boolean-oracle checks, not an RTL simulation PASS."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
OPS = ('VMXOR', 'VMANDNOT', 'VMXNOR', 'VMORNOT')


def boolean(op, a, b):
    return {'VMXOR': a ^ b, 'VMANDNOT': (1 ^ a) & b,
            'VMXNOR': 1 ^ (a ^ b), 'VMORNOT': (1 ^ a) | b}[op]


class MaskLogicalRepairTests(unittest.TestCase):
    def test_four_identities(self):
        for op in OPS:
            for bit in (0, 1):
                self.assertEqual(boolean(op, bit, bit), int(op in OPS[2:]))

    def test_distinct_sources_cannot_be_constant_folded(self):
        for op in OPS:
            self.assertEqual({boolean(op, a, b) for a in (0, 1) for b in (0, 1)}, {0, 1})

    def test_exact_source_identity_guards_before_existing_merge(self):
        text = (ROOT / 'hardware/src/masku/masku.sv').read_text()
        start = text.index('unique case (vinsn_issue.op)\n')
        end = text.index('if (vinsn_issue.use_vd_op)', start)
        block = text[start:end]
        for op in OPS:
            value = 1 if op in OPS[2:] else 0
            self.assertRegex(block, op + r"\s*: alu_result_vm_m = \(vinsn_issue.vs1 == vinsn_issue.vs2\)\s*\? '" + str(value))
        self.assertNotIn('===', block)
        self.assertNotIn('ready', block)
        self.assertNotIn('valid', block)

    def test_source_identity_is_queued_original_metadata(self):
        text = (ROOT / 'hardware/src/masku/masku.sv').read_text()
        self.assertRegex(text, r'vinsn_queue_d.vinsn\[0\]\s*= pe_req_i;')
        self.assertRegex(text, r'assign vinsn_issue\s*= vinsn_queue_q.vinsn\[0\];')
        seq = (ROOT / 'hardware/src/ara_sequencer.sv').read_text()
        for source in ('vs1', 'vs2'):
            self.assertRegex(seq, source + r'\s*: ara_req_i\.' + source)

    def test_restart_tail_background_algebra(self):
        # Existing implementation sets inactive ALU bits to AND identity, then
        # merges old vd. Fold only the active computation, never the merge.
        for op in OPS:
            constant = int(op in OPS[2:])
            for vl, start in ((1, 0), (63, 7), (257, 0), (511, 255),
                              (1024, 257), (0, 0), (31, 31), (31, 40)):
                for bit in range(1024):
                    active = start <= bit < vl
                    for old in (0, 1):
                        alu = constant if active else 1
                        background = old | int(active)
                        self.assertEqual(alu & background, constant if active else old)

    def test_native_source_four_cold_regs_and_distinct_cases(self):
        source = (ROOT / 'verification/tests/masklogical_same_source_repair.c').read_text()
        for insn, reg in (('vmxor.mm', 24), ('vmandn.mm', 25),
                          ('vmxnor.mm', 26), ('vmorn.mm', 27)):
            self.assertIn('"' + insn + '", "v' + str(reg) + '"', source)
            self.assertNotRegex(source, r'(?:vl\w*\.v|vmv\.\w+) v' + str(reg) + r'\b')
        self.assertIn('v16, v9, v8', source)
        self.assertIn('v16, v8, v8', source)
        self.assertIn('cases=68', source)


if __name__ == '__main__':
    unittest.main()
