"""Host-only complete and discriminating negative tests for the AUTO evidence parser."""
import unittest
import panel4_check as check
import test_qk_panel4_abba as fixture_old


def fixture():
    old = check.old; source = fixture_old.fixture().splitlines()
    rows = [old.numeric_fields(line[len('[AKV_PERF] '):], old.PERF_FIELDS)
            for line in source if line.startswith('[AKV_PERF] ')]
    rows += [dict(r, seq=r['seq']+2328) for r in rows[:774]]
    lines, offset = [], 0
    for i, mode in enumerate(check.MODES):
        req = check.REQUESTS[i]
        lines.append(f'PANEL4_TRIAL_BEGIN trial={i} selected={mode} request={req}')
        count = len(old.commands(mode))
        lines += [fixture_old.metric('[AKV_PERF]', r) for r in rows[offset:offset+count]]
        offset += count
        lines.append(f'PANEL4_ATTENTION trial={i} selected={mode} request={req} native=1 '
            f'kv=128 outputs=1536 cycles={100000-mode*4000} fcsr=3 vcsr=5 checksum=a7bc111334389dea errors=0')
    lines += [check.SUITE, old.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0',
              fixture_old.metric('[AKV_PERF_SUMMARY]', old.totals(rows))]
    return '\n'.join(lines)+'\n'


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.text = fixture()

    def test_complete(self):
        result = check.check_log(self.text)
        self.assertEqual(result['state'], 'PASS')
        self.assertEqual([t['derived_hardware_totals']['records'] for t in result['trials']], [774,390,390,774,774])
        self.assertAlmostEqual(result['cycle_reduction_percent'], 4)

    def test_old_is_not_current(self):
        with self.assertRaises(ValueError): check.check_log(fixture_old.fixture())
        with self.assertRaises(ValueError): check.old.check_log(self.text)

    def test_corruption(self):
        pairs = [('request=badcap', 'request=auto'), ('request=auto', 'request=off'),
            ('selected=1', 'selected=0'), ('seq=1 ', 'seq=2 '), ('command=4', 'command=5'),
            ('fault=0', 'fault=1'), ('v2_column_panel=1', 'v2_column_panel=0'),
            ('q_external_bytes=1536', 'q_external_bytes=1535'), ('fcsr=3', 'fcsr=1'),
            ('vcsr=5', 'vcsr=0'), ('errors=0', 'errors=1'), ('checksum=a7bc', 'checksum=0000'),
            ('guards=1', 'guards=0'), ('csr_equal=1', 'csr_equal=0'), ('badcap_fallback=1', 'badcap_fallback=0'),
            ('UVM_ERROR : 0', 'UVM_ERROR : 1'), ('records=3102', 'records=3101'),
            (check.old.TERMINAL, ''), (check.SUITE, '')]
        for a,b in pairs:
            with self.subTest(field=a), self.assertRaises(ValueError):
                check.check_log(self.text.replace(a,b,1))

    def test_extra_unknown(self):
        first = next(line for line in self.text.splitlines() if line.startswith('[AKV_PERF] '))
        for extra in (first, check.SUITE, check.old.TERMINAL, 'UVM_ERROR : 0',
                      'PANEL4_BOGUS', '[AKV_PERF_BOGUS]', '[QBS_PERF] seq=1', 'Fatal: crash'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                check.check_log(self.text+extra+'\n')
        with self.assertRaises(ValueError): check.check_log(self.text.replace(first, first+' seq=1', 1))


if __name__ == '__main__': unittest.main()
