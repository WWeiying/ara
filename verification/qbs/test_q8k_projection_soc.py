import csv
from pathlib import Path
import tempfile
import unittest
from run_q8k_projection_soc import check_result,check_trace


def log():
    rows=[f"Q8K_PROJECTION trial={i} path={'vector' if i in (1,2) else 'generic'} prep=20 matmul=100 total=120 flags=1 checksum=1234567890abcdef" for i in range(4)]
    return "\n".join(rows+["Q8K_PROJECTION_RESULT errors=0 m=4 n=1536 k=1536 outputs=6144 calls=4 commands=192 golden=independent"])


class TestProjection(unittest.TestCase):
    def test_records(self):
        self.assertEqual(len(check_result(log())),4)
        for old,new in [("errors=0","errors=1"),("total=120","total=121"),("prep=20","prep=0"),
            ("flags=1","flags=2"),("1234567890abcdef","0234567890abcdef"),("trial=1","trial=3")]:
            with self.subTest(old=old),self.assertRaises(ValueError):check_result(log().replace(old,new,1))

    def test_command_and_write_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"trace.csv"
            rows=[]
            for i in range(192):
                rows.append(dict(event="alloc",insn="06b5045b",arch_seq=i,vl=128,vd=8,eew=2,be="00"))
                rows.extend(dict(event="write",insn="06b5045b",arch_seq=i,vl=128,vd=8,eew=2,be="ff") for _ in range(64))
            def write():
                with path.open("w",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
            write();self.assertEqual(check_trace(path),dict(commands=192,result_bytes=98304))
            rows.pop();write()
            with self.assertRaises(ValueError):check_trace(path)
            rows[0]["insn"]="00b5045b";write()
            with self.assertRaises(ValueError):check_trace(path)


if __name__ == "__main__":unittest.main()
