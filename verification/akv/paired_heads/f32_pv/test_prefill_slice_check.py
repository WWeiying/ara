"""Synthetic strict-checker tests, not native evidence."""
import unittest
import prefill_slice_check as r


def fixture(cycles=(120000,110000,110000,120000)):
    lines,records = [r.SOURCE],[]
    for trial,mode in enumerate(r.ORDER):
        lines.append(f'PREFILL_PV_BEGIN trial={trial} paired={mode}')
        for command in r.sequence(mode):
            row = dict.fromkeys(r.s.PERF_FIELDS,0)
            row.update(r.expected_record(dict(d=64,heads=3,kv=36),(command,0,36),len(records)+1))
            row.update(id=0,busy_cycles=10)
            if command == 4:
                row.update(ar=76,r_beats=1000,read_outstanding_max=2)
            records.append(row)
            lines.append('[AKV_PERF] '+' '.join(f'{k}={v}' for k,v in row.items()))
        lines.append(f'PREFILL_PV_RESULT trial={trial} paired={mode} outputs=2304 '
                     f'cycles={cycles[trial]} fcsr=1 vcsr=5 hash=0123456789abcdef guards=256 errors=0')
    lines += [r.SUITE,r.s.TERMINAL,'UVM_ERROR : 0','UVM_FATAL : 0']
    lines.append('[AKV_PERF_SUMMARY] '+' '.join(f'{k}={v}' for k,v in r.s.totals(records).items()))
    return '\n'.join(lines)+'\n'


class LogTests(unittest.TestCase):
    def test_counts_and_neutral_negative_performance(self):
        result = r.check_log(fixture())
        self.assertEqual([t['hardware_totals']['records'] for t in result['trials']],[3552,3138,3138,3552])
        self.assertEqual(result['sums'],{'0':240000,'1':220000})
        self.assertEqual(r.check_log(fixture((120000,130000,130000,120000)))['performance'],'regressed')
        self.assertEqual(r.check_log(fixture((120000,120000,120000,120000)))['performance'],'neutral')

    def test_mutations(self):
        text = fixture()
        for old,new in [('errors=0','errors=1'),('fcsr=1','fcsr=2'),('vcsr=5','vcsr=0'),
            ('hash=0123456789abcdef','hash=fedcba9876543210'),('paired=0','paired=1'),
            ('command=4','command=5'),('seq=1 ','seq=2 '),('replay_bytes=72','replay_bytes=66'),
            ('v2_k_view_bank_cycles=5','v2_k_view_bank_cycles=8'),('success=1','success=0'),
            ('busy_cycles=10','busy_cycles=0'),(r.SUITE,r.SUITE+'_BOGUS'),(r.s.TERMINAL,''),
            ('UVM_ERROR : 0','UVM_ERROR : 1')]:
            self.assertIn(old,text)
            with self.subTest(old=old),self.assertRaises(ValueError):
                r.check_log(text.replace(old,new,1))
        first = next(x for x in text.splitlines() if x.startswith('[AKV_PERF] '))
        for bad in (text.replace(first+'\n','',1),text+first+'\n',text.replace(first,first+' unknown=0',1)):
            with self.assertRaises(ValueError):
                r.check_log(bad)


if __name__ == '__main__':
    unittest.main()
