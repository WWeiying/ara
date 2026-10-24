"""Synthetic strict-checker fixtures; no simulator execution."""
import unittest
import native_runtime_check as r


def fixture():
    lines,records = [r.CAP],[]
    for i,case in enumerate(r.CASES):
        for trial in range(3):
            lines.append(r.begin(i,trial))
            for item in r.work(case,trial == 1):
                row = dict.fromkeys(r.s.PERF_FIELDS,0)
                row.update(r.expected_record(case,item,len(records)+1))
                row.update(id=0,busy_cycles=10)
                if item[0] in (4,5):
                    row.update(ar=row['read_ranges'],r_beats=2000,read_outstanding_max=2)
                records.append(row)
                lines.append('[AKV_PERF] '+' '.join(f'{k}={v}' for k,v in row.items()))
            lines.append(f"NATIVE_PAIR_RESULT case={i} trial={trial} requested={int(trial == 1)} "
                f"outputs={case['d']*case['heads']} compared=4096 hash=0123456789abcdef fcsr=3 vcsr=5 errors=0")
    lines += [r.SUITE,r.s.TERMINAL,'UVM_ERROR : 0','UVM_FATAL : 0']
    lines.append('[AKV_PERF_SUMMARY] '+' '.join(f'{k}={v}' for k,v in r.s.totals(records).items()))
    return '\n'.join(lines)+'\n'


class CheckerTests(unittest.TestCase):
    def test_short_resident_tile_counter_semantics(self):
        # Engine byte enables use resident tile length, not arithmetic VL. The
        # context issues ceil(resident_tokens/8) bank groups for each K column.
        c = r.CASES[0]
        panel = r.expected_record(c,(6,1,1),1)
        single = r.expected_record(c,(6,0,1),2)
        self.assertEqual((panel['replay_bytes'],panel['v2_k_view_bank_cycles']),(8,1))
        self.assertEqual((single['replay_bytes'],single['v2_k_view_bank_cycles']),(2,1))
        last = r.expected_record(r.CASES[1],(5,0,1),3)
        self.assertEqual((last['kv_external_bytes'],last['read_ranges'],last['read_payload_bytes']),
                         (384,2,384))

    def test_whole_schedule(self):
        text = fixture()
        result = r.check_log(text)
        self.assertEqual([t['hardware_totals']['records'] for t in result['trials']],
                         [197,84,197,774,373,774,137,137,137,386,98,386])
        self.assertEqual(result['raw_hardware_summary']['records'],3680)

    def test_mutations(self):
        text = fixture()
        mutations = [('errors=0','errors=1'),('fcsr=3','fcsr=2'),('vcsr=5','vcsr=0'),
            ('hash=0123456789abcdef','hash=fedcba9876543210'),('requested=1','requested=0'),
            ('command=4','command=5'),('seq=1 ','seq=2 '),('v2_column_panel=1','v2_column_panel=0'),
            ('success=1','success=0'),('busy_cycles=10','busy_cycles=0'),
            (r.SUITE,r.SUITE+'_BOGUS'),(r.s.TERMINAL,''),('UVM_ERROR : 0','UVM_ERROR : 1')]
        for old,new in mutations:
            self.assertIn(old,text)
            with self.subTest(old=old),self.assertRaises(ValueError):
                r.check_log(text.replace(old,new,1))
        first = next(x for x in text.splitlines() if x.startswith('[AKV_PERF] '))
        for bad in (text+first+'\n',text.replace(first+'\n','',1)):
            with self.assertRaises(ValueError):
                r.check_log(bad)


if __name__ == '__main__':
    unittest.main()
