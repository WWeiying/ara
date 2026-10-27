from pathlib import Path
import struct
import tempfile
import unittest
from exact_projection_source import generate
from build_exact_projection import load_ranges

HERE=Path(__file__).resolve().parent


class ExactTest(unittest.TestCase):
    def test_original_timing_windows_unchanged(self):
        for kind,stem,start,end in (
            ('projection','projection_pair_groupcheck','        const uint64_t start=cycles();','        const uint64_t end=cycles();'),
            ('qkv','context_qkv_pair_groupcheck','        uint64_t prep=0,execute=0,start=cycles();','        uint64_t end=cycles();')):
            with self.subTest(kind=kind):
                old=(HERE/(stem+'.c')).read_text();new=generate(old,kind)
                self.assertEqual(old[old.index(start):old.index(end)],new[new.index(start):new.index(end)])
                self.assertNotIn('q8k_integrity_words',new)
                self.assertIn('q8k_integrity_equal_selftest()',new)
                self.assertIn('if(trial==3)' if kind=='qkv' else '(trial==3 &&',new)

    def test_source_drift_rejected(self):
        with self.assertRaises(ValueError):generate('different runtime','projection')

    def test_simulation_load_range(self):
        data=bytearray(256);data[:6]=b'\x7fELF\x02\x01'
        struct.pack_into('<Q',data,32,64);struct.pack_into('<HH',data,54,56,1)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'elf'
            def write(pa,filesz=0,memsz=64):
                struct.pack_into('<IIQQQQQQ',data,64,1,4,0,pa,pa,filesz,memsz,64)
                p.write_bytes(data)
            write(0x80000000)
            self.assertEqual(load_ranges(p),[dict(address=0x80000000,bytes=64)])
            for pa,filesz,memsz in ((0x7ffffff0,0,64),(0x80fffff0,0,64),
                                   (0x80000000,100,64),(0x80000000,300,300)):
                write(pa,filesz,memsz)
                with self.assertRaises(ValueError):load_ranges(p)


if __name__=='__main__':unittest.main()
