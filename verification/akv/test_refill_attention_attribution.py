import csv
from pathlib import Path
import tempfile
import unittest

from analyze_refill_attention_abba import retirement_trials, refill_windows


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class AttributionTest(unittest.TestCase):
    def test_csr_intervals_and_retirement_partition(self):
        rows = []
        for i in range(4):
            for pc, offset in ((100, 0), (110, 10), (104, 20)):
                rows.append(dict(event="retire", pc=f"{pc:x}", cycle=i*100+offset,
                                 rd_wdata=f"{i*1000+offset:x}", trap="0"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commit.csv"
            write_csv(path, rows)
            got = retirement_trials(path, [(100,24,"main")], (100,104), [{"cycles":20}]*4)
            self.assertEqual([t["instructions"] for t in got], [2]*4)
            self.assertEqual(got[0]["functions"]["main"]["retire_gap_cycles"],20)
            with self.assertRaisesRegex(ValueError,"disagree"):
                retirement_trials(path, [(100,24,"main")], (100,104), [{"cycles":19}]*4)

    def test_real_older_arch_matching_and_missing_completion_rejection(self):
        rows, logs, trials = [], [], []
        for t in range(4):
            trials.append(dict(trial=t,overlap=int(t in (1,2)),
                               begin=dict(cycle=t*1000),end=dict(cycle=(t+1)*1000)))
        for ordinal in range(1,9):
            t=(ordinal-1)//2; start=t*1000+50+(ordinal-1)%2*250
            arch=ordinal*10+6
            for event,cycle in (("start",start),("first_ar",start+5),("terminal",start+100)):
                logs.append(f"[AKV_REFILL_ORDER] event={event} cycle={cycle} ordinal={ordinal} arch={arch} vid=0")
            for a in range(arch-6,arch):
                rows.append(dict(arch_seq=a,cycle=start-2,event="alloc",insn="b2e55057"))
                rows.append(dict(arch_seq=a,cycle=start+28,event="write",insn="b2e55057"))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"vector.csv"
            write_csv(path,rows)
            got=refill_windows("\n".join(logs),path,trials)
            self.assertEqual([w["older_write_overlap_cycles"] for w in got],[23]*8)
            self.assertEqual(got[0]["older_fma_arch"],list(range(10,16)))
            write_csv(path,[row for row in rows if not(row["event"]=="write" and row["arch_seq"]==15)])
            with self.assertRaisesRegex(ValueError,"completion"):
                refill_windows("\n".join(logs),path,trials)


if __name__=="__main__": unittest.main()
