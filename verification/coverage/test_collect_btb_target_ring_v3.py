import copy
import csv
import unittest
import collect_btb_target_ring_v3 as c


class Actual(unittest.TestCase):
    def fixture(self):
        p=c.life.OUT/'btb-target-ring-old-image777-agent-20261007-01'
        with (p/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        with (p/'vector_trace.csv').open() as f:vs=list(csv.DictReader(f))
        summaries=[c.original.parse_contract_summary(l) for l in (p/'console.log').read_text().splitlines() if '[ARA_CONTRACT]' in l]
        return rows,vs,summaries[0]

    def test_real_monitor_and_all44_request_retire_bindings(self):
        c.source_contract();r=c.lifecycle(*self.fixture())
        self.assertEqual(r['requests'],44);self.assertEqual(len(r['exact_retire_bindings']),44)
        self.assertNotEqual(r['exact_retire_bindings'][0]['arch_seq'],r['exact_retire_bindings'][0]['retire_order'])

    def test_missing_duplicate_wrong_opcode_early_retire(self):
        for kind in ('missing','duplicate','opcode','early'):
            rows,vs,s=self.fixture();start=next(r for r in rows if r['event']=='arch_start')
            idx=next(i for i,r in enumerate(rows) if r['event']=='retire' and r['insn']==start['insn'])
            if kind=='missing':rows.pop(idx)
            elif kind=='duplicate':rows.insert(idx,copy.deepcopy(rows[idx]))
            elif kind=='opcode':rows[idx]['insn']='00000013'
            else:rows[idx]['cycle']='0'
            with self.assertRaises(ValueError):c.lifecycle(rows,vs,s)


if __name__=='__main__':unittest.main()
