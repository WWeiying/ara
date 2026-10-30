import csv
from pathlib import Path
import tempfile
import unittest

from run_vrf_panel_bench import check_log,check_trace


def fixture():
    lines=[];seq=0;words=[]
    for trial,striped in enumerate((False,True,True,False)):
        for stripe,kb in enumerate(([4]*8+[3]) if striped else [35]):
            for tile in range(2):
                seq+=1
                weight=32*kb*210;activation=kb*1168 if not striped or tile==0 else 0
                counters=dict(seq=seq,m=4,n=32,vlen=1024,lanes=4,success=1,fault=0,
                    validation_fault=0,validation_error=0,read_fault=0,payload_bytes=weight+activation+16,
                    weight_bytes=weight,context_fill_count=int(striped and tile==0),
                    context_reuse_count=int(striped and tile==1),
                    activation_axi_bytes_saved=kb*1168 if striped and tile==1 else 0,
                    read_ranges=1,ar=1,r_beats=1,busy_cycles=20,commit_groups=16)
                lines.append("[QBS_PERF] "+" ".join(f"{k}={v}" for k,v in counters.items()))
                word=(0x16b5045b if striped and stripe else 0x06b5045b)+(tile<<10)
                words.append(word)
                if striped and stripe:
                    lines.extend([f"[QBACC_SEED] seq={seq} fire=1111 owner=1 store_valid=0000"]*16)
        lines.append(f"VRF_PANEL_TRIAL trial={trial} path={'striped' if striped else 'direct'} "
                     f"cycles={700 if striped else 800} flags=1 checksum=1234567890abcdef")
    lines.append("VRF_PANEL_RESULT errors=0 m=4 n=64 k=8960 outputs=256 calls=4 commands=40 preparation_timed=0 descriptor_setup_timed=1")
    return "\n".join(lines),words


class PanelBenchChecker(unittest.TestCase):
    def test_checked_work(self):
        log,_=fixture();result=check_log(log)
        self.assertEqual(result["sums"],dict(direct=1600,striped=1400))
        self.assertAlmostEqual(result["matrix_speedup"],8/7)

    def test_wrong_bytes_or_flags_or_output(self):
        log,_=fixture()
        for old,new in (("payload_bytes=276096","payload_bytes=276112"),
                        ("flags=1 checksum","flags=0 checksum"),
                        ("errors=0","errors=1"),("preparation_timed=0","preparation_timed=1"),
                        ("seq=5 fire=1111","seq=5 fire=1110"),
                        ("store_valid=0000","store_valid=0001"),
                        ("flags=1 checksum=1234567890abcdef","flags=1 checksum=2234567890abcdef")):
            self.assertIn(old,log)
            with self.subTest(old=old),self.assertRaises(ValueError):check_log(log.replace(old,new,1))

    def test_missing_source_and_duplicate_command(self):
        log,_=fixture()
        with self.assertRaises(ValueError):
            check_log(log.replace("[QBACC_SEED] seq=5 fire=1111 owner=1 store_valid=0000\n","",1))
        with self.assertRaises(ValueError):check_log(log+"\n"+log.splitlines()[0])

    def test_actual_vector_writes(self):
        _,words=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"trace.csv"
            rows=[]
            for word in words:
                common=dict(insn=f"{word:08x}",vd=str((word>>7)&31),eew="2",vl="128",vstart="0")
                rows.append(dict(common,event="alloc",be="00"))
                rows.extend(dict(common,event="write",be="ff") for _ in range(64))
            def write():
                with path.open("w",newline="") as stream:
                    writer=csv.DictWriter(stream,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
            write();self.assertEqual(check_trace(path)["result_bytes"],20480)
            rows.pop();write()
            with self.assertRaises(ValueError):check_trace(path)


if __name__=="__main__":unittest.main()
