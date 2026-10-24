"""Synthetic checker tests only; no simulator or execution evidence."""
import unittest
import rtl_check as r


def fixture():
    cases = [dict(c, fcsr=9) for c in r.SHAPES]
    golden = b''.join(bytes(8*c['d'])+b'\xa5'*(1024-8*c['d']) for c in cases)
    lines, rows = [r.CAP], []
    for case in cases:
        for mode in (0, 1):
            lines.append(r.begin(case, mode))
            for command in r.work(case, mode):
                row = dict.fromkeys(r.PERF_FIELDS, 0)
                row.update(r.prior.expected_record(case, mode, command, len(rows)+1))
                row.update(id=0, busy_cycles=10)
                if command == 4:
                    row.update(ar=131, r_beats=2000, read_outstanding_max=2)
                lines.append('[AKV_PERF] '+' '.join(f'{k}={v}' for k,v in row.items()))
                rows.append(row)
            lines.append(r.end(case, mode, golden))
    lines += [r.SUITE, r.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']
    lines.append('[AKV_PERF_SUMMARY] '+' '.join(f'{k}={v}' for k,v in r.totals(rows).items()))
    return '\n'.join(lines)+'\n', cases, golden


class CheckerTests(unittest.TestCase):
    def test_complete(self):
        text, cases, golden = fixture()
        result = r.check_log(text, cases, golden)
        self.assertEqual(result['state'], 'PASS')
        self.assertEqual(result['hardware_totals']['records'], 396)
        self.assertEqual(result['hardware_totals']['replay_bytes'], 85824)

    def test_failures(self):
        text, cases, golden = fixture()
        replacements = [('errors=0','errors=1'), ('fcsr=9','fcsr=8'),
            ('vcsr=5','vcsr=0'), ('inputbytes=35072','inputbytes=35008'),
            ('guardbytes=1024','guardbytes=896'), ('success=1','success=0'),
            ('command=2','command=6'), ('seq=1 ','seq=2 '),
            ('v2_row_load=1','v2_row_load=0'), ('busy_cycles=10','busy_cycles=0'),
            ('F32_PV_BEGIN case=0 mode=0','F32_PV_BEGIN case=0 mode=1'),
            (r.SUITE,r.SUITE+'_BOGUS'), (r.TERMINAL,''),
            ('UVM_ERROR : 0','UVM_ERROR : 1')]
        for old,new in replacements:
            self.assertIn(old,text)
            with self.subTest(old=old), self.assertRaises(ValueError):
                r.check_log(text.replace(old,new,1),cases,golden)
        perf = next(x for x in text.splitlines() if x.startswith('[AKV_PERF] '))
        for bad in (text.replace(perf+'\n','',1), text+perf+'\n',
                    text.replace(perf,perf+' unknown=0',1)):
            with self.assertRaises(ValueError):
                r.check_log(bad,cases,golden)


if __name__ == '__main__':
    unittest.main()
