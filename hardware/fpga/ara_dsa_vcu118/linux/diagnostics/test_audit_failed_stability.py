import struct
import unittest
from audit_failed_stability import metadata_fault, snapshot_classification


class FailureAuditTests(unittest.TestCase):
    def setUp(self):
        self.loader = bytearray(0x12000)
        for off, insn in ((0x10902,0x3aa7bd23),(0x11c44,0x0009bd83),(0x11c4c,0x000db683)):
            struct.pack_into('<I', self.loader, off, insn)
        self.output = ('cat: unhandled signal 11\n'
                       'epc : 0000003f8f11ec4c s3 : 0000003f8f12fcb8\n'
                       's11: 0000000000000000 status: 8000000200004620\n'
                       'badaddr: 0000000000000000 cause: 000000000000000d\n'
                       'BUG: Bad rss-counter state\n')

    def test_exact_fault_is_not_memory_or_rtl_proof(self):
        result = metadata_fault(self.output, self.loader)
        self.assertFalse(result['global_memory_at_fault_captured'])
        self.assertFalse(result['rtl_cause_proven_for_this_event'])
        self.assertTrue(result['rss_warning_follows_user_fault'])
        self.assertEqual(result['direct_return_lane'], 3)

    def test_wrong_executable_rejected(self):
        self.loader[0x11c44] ^= 1
        with self.assertRaisesRegex(ValueError, 'instruction'):
            metadata_fault(self.output, self.loader)

    def test_bad_global_address_rejected(self):
        with self.assertRaisesRegex(ValueError, 'global'):
            metadata_fault(self.output.replace('3f8f12fcb8','3f8f12fcb0'),self.loader)

    def test_kernel_fault_not_misreported_as_user(self):
        with self.assertRaisesRegex(ValueError, 'privilege'):
            metadata_fault(self.output.replace('00004620','00004720'),self.loader)

    def test_multiple_fault_records_are_ambiguous(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            metadata_fault(self.output+self.output,self.loader)

    def test_pc_signature_not_claimed_as_identical_code(self):
        result = snapshot_classification({'core':dict(
            retired=100,last_pc=0x3fbec64b4a,head_pc=0x3fbec64b32,
            last_trap_pc=0x3fbec67502,last_trap_cause=8,last_trap_tval=0)}, b'')
        self.assertTrue(result['one_snapshot_is_not_stall_proof'])
        self.assertTrue(result['code_page_readback_required'])
        self.assertEqual(result['candidate_target'], '0x3fbec600dc')


if __name__ == '__main__':
    unittest.main()
