import struct
import unittest
import run_gap113_cached_reset as r


class Reset(unittest.TestCase):
    def test_actual_elf_reload(self):
        rows = r.loaded_segments((r.cached.PRE/(r.cached.NAME+'.elf')).read_bytes())
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(x['filesz'] == x['memsz'] for x in rows))

    def test_trailing_bss_rejected(self):
        blob = bytearray((r.cached.PRE/(r.cached.NAME+'.elf')).read_bytes())
        h = struct.unpack_from('<16sHHIQQQIHHHHHH', blob)
        old = struct.unpack_from('<Q', blob, h[5]+40)[0]
        struct.pack_into('<Q', blob, h[5]+40, old+8)
        with self.assertRaises(ValueError): r.loaded_segments(blob)

    def test_fixed_target_and_trace_capacity(self):
        self.assertIn('+ARA_UVM_RESET_STATE_TARGET=qbs_compute_final_drain', r.ARGS)
        self.assertEqual(sum(x.startswith('+ARA_UVM_RESET_ON_AXI=') for x in r.ARGS), 1)
        self.assertIn('+ARA_UVM_TRACE_LIMIT=100000', r.ARGS)

    def test_actual_prepare_no_launch(self):
        _, p = r.prepare()
        self.assertEqual(len(p['targets']), 16)
        self.assertFalse(any(t['before_hit'] for t in p['targets']))
        self.assertEqual(p['timeout_s'], 600)
        self.assertEqual(p['expected_commands'] if 'expected_commands' in p else p['preflight']['commands'], 2)
        self.assertFalse(p['coverage_admitted'])


if __name__ == '__main__': unittest.main()
