"""Host parser/source checks only; synthetic text is not native acceptance."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('rom_probe_host', Path(__file__).with_name('probe.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


class ProbeTests(unittest.TestCase):
    def fixture(self):
        binding = dict(pc=0x80000200, insn=0x00b5605b)
        log = ('ROM_BEGIN pc=80000200 address=1000 insn=b5605b mstatus=6600\n'
            'ROM_TRAP pc=80000200 cause=5 tval=1000 count=1 fatal=0\n'
            'ROM_CSR before_fcsr=8 after_fcsr=8 before_vcsr=5 after_vcsr=5 before_vstart=0 after_vstart=0 '
            'before_vl=0 after_vl=0 before_vtype=200 after_vtype=200\nROM_DONE traps=1 errors=0\n')
        trace = 'akv_arch_begin seq=1 pc=0x80000200 insn=0x00b5605b rs1=0x1000 rs2=0x0 frm=0 fflags=8\n'
        return binding, log, trace

    def test_sealed_dependencies_unchanged(self): self.assertEqual(len(p.dependencies()), 4)
    def test_exact_positive_fixture_not_native(self):
        binding, log, trace = self.fixture(); result = p.audit_text(log, trace, binding)
        self.assertEqual(result['state'], 'ROM_RAM_ONLY_FAULT_CHECKED'); self.assertFalse(result['qemu_image_checked'])
    def test_backend_illegal_wrong_pc_tval_and_csr_rejected(self):
        binding, log, trace = self.fixture()
        for old, new in (('cause=5', 'cause=2'), ('tval=1000', 'tval=0'), ('count=1', 'count=0'),
                         ('ROM_TRAP pc=80000200', 'ROM_TRAP pc=80000204'), ('after_fcsr=8', 'after_fcsr=0'),
                         ('after_vtype=200', 'after_vtype=0'), ('mstatus=6600', 'mstatus=6000')):
            with self.subTest(old=old), self.assertRaises(ValueError): p.audit_text(log.replace(old, new), trace, binding)
    def test_missing_duplicate_unknown_or_failed_terminal_rejected(self):
        binding, log, trace = self.fixture()
        for value in (log.rsplit('ROM_DONE', 1)[0], log+'ROM_DONE traps=1 errors=0\n',
                      log+'ROM_UNKNOWN errors=0\n', log.replace('errors=0', 'errors=1')):
            with self.assertRaises(ValueError): p.audit_text(value, trace, binding)
    def test_read_end_or_missing_real_begin_rejected(self):
        binding, log, trace = self.fixture()
        for value in ('', trace+trace, trace+'akv_arch_read seq=1 pc=0x80000200 address=0x1000 bytes=64\n',
            trace+'akv_arch_end seq=1 pc=0x80000200 status=1 fflags=0 valid=0 tile=0 tokens=0 tval=0x0\n',
            trace.replace('rs1=0x1000', 'rs1=0x1004')):
            with self.assertRaises(ValueError): p.audit_text(log, value, binding)
    def test_full_encoding_is_not_resident_or_info(self):
        word = 0x00b5605b
        self.assertEqual((word & 127, (word >> 12) & 7, (word >> 15) & 31, (word >> 20) & 31, word >> 25),
                         (0x5b, 6, 10, 11, 0))


if __name__ == '__main__': unittest.main()
