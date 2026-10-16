import hashlib
import struct
import unittest
from unittest.mock import patch

import analyze_loader_core as audit


def fixture():
    base, stack = 0x3f00000000, 0x3ff0000000
    status = bytearray(376)
    struct.pack_into('<H', status, 12, 11)
    struct.pack_into('<i', status, 32, 267)
    regs = [0]*32
    regs[0], regs[10] = base+0xf750, stack+0x80
    struct.pack_into('<32Q', status, 112, *regs)

    def note(kind, payload):
        return struct.pack('<III', 5, len(payload), kind)+b'CORE\0\0\0\0'+payload

    notes = note(1, status)+note(6, struct.pack('<4Q', 7, base, 0, 0))
    core = bytearray(0x7000)
    core[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<HH', core, 16, 4, 243)
    struct.pack_into('<Q', core, 32, 64)
    struct.pack_into('<HH', core, 54, 56, 3)
    for i, (kind, flags, offset, va, size) in enumerate((
        (4, 0, 0x200, 0, len(notes)),
        (1, 6, 0x1000, base+0x21000, 0x4000),
        (1, 6, 0x5000, stack, 0x1000),
    )):
        struct.pack_into('<IIQQQQQQ', core, 64+i*56,
                         kind, flags, offset, va, 0, size, size, 4096)
    core[0x200:0x200+len(notes)] = notes
    struct.pack_into('<4Q', core, 0x5100, 2, stack+0x200, stack+0x210, 0)
    core[0x5200:0x5204] = b'cat\0'
    core[0x5210:0x5216] = b'/tmp/\0'
    return bytes(core), bytes(0x24000), base, stack


class CoreAuditTests(unittest.TestCase):
    def test_saved_cursor_and_globals_are_reported_not_rtl_proof(self):
        core, loader, base, stack = fixture()
        with patch.object(audit, 'LOADER_SHA', hashlib.sha256(loader).hexdigest()):
            result = audit.analyze(core, loader)
        self.assertEqual(result['startup_stack'], hex(stack+0x100))
        self.assertEqual(result['globals']['__environ']['startup_expected'], hex(stack+0x120))
        self.assertEqual(result['environment_cursor']['saved'], '0x0')
        self.assertEqual(result['pid'], 267)
        self.assertNotIn('passed', result)
        self.assertIn('not_cycle_level_rtl_attribution', result['scope'])

    def test_absent_bytes_are_not_zero_memory(self):
        core, _, base, _ = fixture()
        core = bytearray(core)
        struct.pack_into('<Q', core, 64+56+32, 0)
        with self.assertRaises(ValueError):
            audit.captured(core, base+0x22cb8, 8)

    def test_truncated_file_is_rejected(self):
        core, _, _, stack = fixture()
        with self.assertRaises(ValueError):
            audit.captured(core[:0x5000], stack+0x100, 8)

    def test_truncated_notes_are_rejected(self):
        core, _, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            audit.notes(core[:0x210])

    def test_wrong_reference_loader_is_rejected(self):
        core, loader, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, 'Wrong reference'):
            audit.analyze(core, loader)

    def test_bad_pmd_precedes_fault_but_does_not_identify_its_address(self):
        image = bytearray(0x6000)
        image[0x58ee:0x58f0] = bytes.fromhex('1461')
        image[0x590a:0x590e] = bytes.fromhex('23b00400')
        uart = ('[ 1570.595215] mm/pgtable-generic.c:56: bad pmd 000000002005ac5b.\n'
                '[ 1570.605381] rm: unhandled signal 11 in ld-linux-riscv64-lp64d.so.1\n')
        with patch.object(audit, 'IMAGE_SHA', hashlib.sha256(image).hexdigest()):
            result = audit.page_directory_evidence(uart, image)
        entry = result['bad_pmd'][0]
        self.assertTrue(entry['precedes_loader_fault'])
        self.assertTrue(entry['has_leaf_permissions'])
        self.assertFalse(entry['aligned_for_2m_leaf'])
        self.assertEqual(entry['physical_base'], '0x8016b000')
        self.assertIn('does not contain the PMD pointer', result['limitation'])

    def test_kernel_clear_opcode_must_match(self):
        image = bytes(0x6000)
        with patch.object(audit, 'IMAGE_SHA', hashlib.sha256(image).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'instructions'):
                audit.page_directory_evidence('', image)


if __name__ == '__main__':
    unittest.main()
