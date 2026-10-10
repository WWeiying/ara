from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import build_itlb_asid_exec_bulk as b


class Bulk(unittest.TestCase):
    def test_source_only_allowed_transform(self):
        self.assertEqual(b.APP.read_text(),b.transform(b.linear.APP.read_text()))
        proof,pins=b.source_contract()
        self.assertEqual(proof['code_guard_reads'],8192)
        self.assertEqual(proof['checks_unchanged'],10966)
        self.assertIn(str(b.HEADER),pins)

    def test_mapping_trap_asid_and_guard_changes_rejected(self):
        expected=b.transform(b.linear.APP.read_text())
        for a,z in [('0xaaaaul','0xfful'),('0x73ul','0x13ul'),('0x4b','0xcf'),
            ('checks!=10966','checks!=42'),('entry<16','entry<1')]:
            actual=expected.replace(a,z)
            self.assertNotEqual(actual,expected)
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'foreign.c';path.write_text(actual)
                with patch.object(b,'APP',path):
                    with self.assertRaisesRegex(ValueError,'outside exact bulk'):b.source_contract()

    def test_instrumented_actual_scalar_header_every_word_and_exact_fault_count(self):
        source=b.ROOT/'verification/tests/itlb_bulk_scalar_host.c'
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'host'
            subprocess.run(['/usr/bin/gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(exe)],check=True,timeout=30)
            result=subprocess.run([str(exe)],check=True,timeout=10,capture_output=True,text=True)
            self.assertEqual(result.stdout,'ITLB_BULK_HOST_EXACT8192_STORE_READ_512_SINGLE_FAULTS_AND_512_MULTI_FAILS_PASS\n')

    def test_old_nobits_ELF_not_eligible(self):
        path=b.PRIOR.parent/'input.elf'
        with self.assertRaisesRegex(ValueError,'PROGBITS'):b.elf_contract(path)

    def test_reference_exact_entry_and_terminal(self):
        def c(pc,mem=()):return SimpleNamespace(pc=pc,memory_accesses=mem)
        rows=[c(0x1000),c(0x80000000),c(0x80000004,((0x80001000,1),)),c(0x80000008)]
        self.assertEqual(b.reference_interval(rows),rows[1:3])
        for bad in [rows[2:],rows+[c(0x80000000)],rows[:2],
            [c(0x80000000),c(0x80000004,((0x80001000,3),))],
            rows+[c(0x80000008,((0x80001000,1),))]]:
            with self.assertRaises(ValueError):b.reference_interval(bad)


if __name__=='__main__':unittest.main()
