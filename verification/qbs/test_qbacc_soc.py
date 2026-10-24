import csv
from pathlib import Path
import tempfile
import unittest

from run_qbacc_soc import check_probe


class ProbeChecker(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.trace = Path(self.temp.name) / "trace.csv"
        shapes = [(1,1),(1,1),(3,17),(3,17),(4,32),(4,32),(5,7),(5,7),
                  (8,15),(8,15),(8,16),(8,16),(4,0)]
        lines = []
        with self.trace.open("w") as stream:
            writer = csv.DictWriter(stream,fieldnames=("event","insn","vd","eew","vl","vstart"))
            writer.writeheader()
            for i,(m,n) in enumerate(shapes,1):
                lines.append(f"[QBS_PERF] seq={i} m={m} n={n} success={int(i!=13)} "
                             f"fault={int(i==13)} validation_fault={int(i==13)}")
                lines.append(f"[QBACC_START] seq={i} id=0 m={m} vd=8 vl={m*32} sew=2")
                lines.extend([f"[QBACC_SEED] seq={i} fire=1111 owner=1 store_valid=0000"]*(4*m))
                lines.append(f"[QBACC_END] seq={i} success={int(i!=13)} fault={int(i==13)}")
                word=((m-1+8)<<25)|(11<<20)|(10<<15)|(8<<7)|0x5b
                writer.writerow(dict(event="alloc",insn=f"{word:08x}",vd=8,eew=2,vl=m*32,vstart=0))
        lines.append("QBACC_SOC_PASS cases=13 computed=12 validation_faults=1 csr_preserved=1 tail_policy_checked=1 padding_preserved=1")
        self.log="\n".join(lines)

    def test_valid(self):
        self.assertEqual(check_probe(self.log,self.trace)["source_words_per_lane"],248)

    def test_missing_source_word(self):
        text=self.log.replace("[QBACC_SEED] seq=1 fire=1111 owner=1 store_valid=0000\n","",1)
        with self.assertRaises(ValueError):check_probe(text,self.trace)

    def test_store_leak(self):
        with self.assertRaises(ValueError):
            check_probe(self.log.replace("store_valid=0000","store_valid=0001",1),self.trace)

    def test_bad_source_geometry(self):
        with self.assertRaises(ValueError):
            check_probe(self.log.replace("vd=8 vl=32 sew=2","vd=8 vl=7 sew=1",1),self.trace)

    def test_missing_fault(self):
        with self.assertRaises(ValueError):
            check_probe(self.log.replace("seq=13 m=4 n=0 success=0 fault=1",
                                         "seq=13 m=4 n=0 success=1 fault=0"),self.trace)

    def test_software_failure_or_duplicate(self):
        for text in (self.log+"\nQBACC_DATA_FAIL", self.log+"\n"+self.log.splitlines()[-1]):
            with self.assertRaises(ValueError):check_probe(text,self.trace)

    def test_missing_real_allocation(self):
        self.trace.write_text("\n".join(self.trace.read_text().splitlines()[:-1])+"\n")
        with self.assertRaises(ValueError):check_probe(self.log,self.trace)


if __name__=="__main__":unittest.main()
