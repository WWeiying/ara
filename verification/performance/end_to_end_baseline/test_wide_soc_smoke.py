"""Independent loader, physical geometry and result-admission host tests."""
import struct
import unittest

import run_wide_soc_smoke as s


def elf(segments):
    data = bytearray(8192)
    struct.pack_into('<16sHHIQQQIHHHHHH', data, 0, b'\x7fELF\x02\x01' + bytes(10),
                     2, 243, 1, 0x80000000, 64, 0, 0, 64, 56, len(segments), 0, 0, 0)
    for i, (address, size) in enumerate(segments):
        struct.pack_into('<IIQQQQQQ', data, 64+i*56, 1, 7, 4096, address, address, size, size, 4096)
    return bytes(data)


class SmokeAdmissionTests(unittest.TestCase):
    def test_bus_aligned_pt_loads(self):
        for width in (16, 32):
            self.assertEqual(len(s.elf_admission(elf([(0x80000000, 64), (0x80000080, 65)]), width)), 2)
        for data in (elf([(0x80000000, 33), (0x80000030, 32)]),
                     elf([(0x80000010, 32)]), elf([(0x80ffffe0, 33)]),
                     elf([(0x80000000, 65), (0x80000040, 64)])):
            with self.assertRaises(ValueError): s.elf_admission(data, 32)

    def test_unsupported_or_truncated_elf(self):
        for data in (b'', b'\x7fELF', elf([(0x80000000, 32)])[:80]):
            with self.assertRaises(ValueError): s.elf_admission(data, 32)

    def test_physical_geometry_and_actual_activity(self):
        for width in (128, 256):
            good = (f'WIDE_SOC_PLATFORM bits={width} lanes=4 vlen=1024 words={16777216//(width//8)} '
                    f'bytes=16777216 memory_width={width}\n'
                    f'WIDE_SOC_MEMORY bits={width} reads=100 writes=9 upper_writes=3 full_ar=6 returns=99 max_read_run=4\n')
            self.assertEqual(s.check_platform(good, width)['reads'], 100)
            for bad in (good+good, good.replace('lanes=4', 'lanes=8'),
                        good.replace('max_read_run=4', 'max_read_run=1'),
                        good.replace('upper_writes=3', 'upper_writes=0'),
                        good+'[ARA_CONTRACT_TRACE] resp=1/1 fire=1 id=1 exc=1\n',
                        good+'Fatal: wrong\n'):
                with self.assertRaises(ValueError): s.check_platform(bad, width)

    def test_handoff_cannot_skip_or_trap(self):
        self.assertTrue(s.check_program('QBS/AKV handoff smoke: PASS traps=0\n', 'handoff')['handoff_pass'])
        for bad in ('QBS/AKV handoff smoke: SKIP (QBS disabled)\n',
                    'QBS/AKV handoff smoke: PASS traps=1\n',
                    'QBS/AKV handoff smoke: PASS traps=0\n' * 2):
            with self.assertRaises(ValueError): s.check_program(bad, 'handoff')

    def test_uart_checker_is_separate_from_full_protocol(self):
        values = s.memory.expected(128)
        text = ('WIDE_SOC_MEMORY_SMOKE_BEGIN version=1\n'
                'WIDE_SOC_MEMORY_SMOKE_END status=PASS cycles=10\n'
                'WIDE_SOC_MEMORY_SMOKE_PASS ' + ' '.join(k+'='+str(v) for k,v in values.items()) + '\n'
                'UVM_ERROR : 0\nUVM_FATAL : 0\n')
        self.assertEqual(s.check_program(text, 'memory'), values)
        with self.assertRaises(ValueError): s.check_program(text.replace('vector_cases=240', 'vector_cases=239'), 'memory')


if __name__ == '__main__': unittest.main()
