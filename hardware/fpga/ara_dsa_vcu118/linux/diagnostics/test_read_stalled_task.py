import struct
import unittest

from read_stalled_task import progress_key, saved_user_context, translate


class PageWalkTest(unittest.TestCase):
    def test_three_levels(self):
        va = 0x3f93ee20dc
        memory = {}
        for level, table, target in ((2, 0x82000000, 0x82001000),
                                     (1, 0x82001000, 0x82002000),
                                     (0, 0x82002000, 0x80166000)):
            memory[table + ((va >> (12 + 9 * level)) & 511) * 8] = (
                ((target >> 12) << 10) | (0x5b if level == 0 else 1))
        pa, entries = translate(memory.__getitem__, 0x82000000, va)
        self.assertEqual(pa, 0x801660dc)
        self.assertEqual([entry['level'] for entry in entries], [2, 1, 0])

    def test_superpage(self):
        pa, _ = translate(lambda _: (0x80000 << 10) | 0xcf,
                          0x82000000, 0x81234567)
        self.assertEqual(pa, 0x81234567)

    def test_invalid_pte(self):
        for pte in (0, 5, (0x80001 << 10) | 0x5b):
            with self.assertRaises(ValueError):
                translate(lambda _: pte, 0x82000000, 0x123)

    def test_cycle_change_alone_is_not_retirement(self):
        core = dict(retired=1, last_pc=2, head_pc=3, trap_count=4, cycles=5)
        self.assertEqual(progress_key(dict(core=core)),
                         progress_key(dict(core=dict(core, cycles=6))))
        self.assertNotEqual(progress_key(dict(core=core)),
                            progress_key(dict(core=dict(core, retired=2))))

    def test_saved_context_layout(self):
        stack = bytearray(4096)
        for offset, value in ((0, 0x1234), (16, 0x3fe60559a0), (272, 8)):
            struct.pack_into('<Q', stack, 4096 - 288 + offset, value)
        saved = saved_user_context(stack)
        self.assertEqual(saved['sp'], 0x3fe60559a0)
        self.assertEqual(saved['cause'], 8)
        self.assertEqual(saved['epc'], 0x1234)
        struct.pack_into('<Q', stack, 4096 - 288 + 256, 0x100)
        with self.assertRaises(ValueError):
            saved_user_context(stack)
        with self.assertRaises(ValueError):
            saved_user_context(stack[:-1])


if __name__ == '__main__':
    unittest.main()
