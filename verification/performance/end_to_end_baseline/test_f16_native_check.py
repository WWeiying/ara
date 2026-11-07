import unittest

from check_f16_native import BINDING, SCOPE, TERMINAL, ORDER, check, expected_calls, hardware, work
from native_runtime_check import expected_record


def fixture(overhead=.01):
    lines=[SCOPE,BINDING];all_records=[]
    for phase in (0,1):
        for trial,probed in enumerate(ORDER):
            lines.append(f'F16_REAL_BEGIN phase={phase} trial={trial} probed={probed}')
            for item in work(phase):
                r={k:0 for k in hardware.PERF_FIELDS}
                r.update(expected_record(dict(d=128,heads=2),item,len(all_records)+1))
                r.update(id=0,busy_cycles=1)
                if r['command'] in (4,5):r.update(ar=r['read_ranges'],r_beats=r['read_ranges'],read_outstanding_max=1)
                all_records.append(r)
                lines.append('[AKV_PERF] '+' '.join(f'{k}={v}' for k,v in r.items()))
            cycles=int((100000 if not phase else 3000000)*(1+overhead*probed))
            words=256 if not phase else 16384
            lines.append(f'F16_REAL_RESULT phase={phase} trial={trial} probed={probed} cycles={cycles} '
                         f'preparation=20 words={words} fcsr=9 vcsr=5 vstart=0 errors=0')
            for index,n in enumerate(expected_calls(phase)):
                calls=n*probed;cycles=100*probed if n and index<12 else 0
                lines.append(f'F16_REAL_PHASE phase={phase} trial={trial} id={index} calls={calls} cycles={cycles}')
            for row in range(1 if not phase else 64):
                lines.append(f'F16_REAL_ROW phase={phase} trial={trial} row={row} hash={phase*100+row:016x}')
    lines.extend((TERMINAL,'Core Test *** SUCCESS *** (tohost = 0)',
                  '[AKV_PERF_SUMMARY] '+' '.join(f'{k}={v}' for k,v in hardware.totals(all_records).items()),
                  'UVM_ERROR : 0','UVM_FATAL : 0'))
    return '\n'.join(lines)


class F16NativeChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.text=fixture()

    def test_complete_actual_work_and_scope(self):
        r=check(self.text)
        self.assertEqual(r['native_commands'],17468)
        self.assertEqual(r['words_checked_on_target'],66560)
        self.assertTrue(r['quantitative_phase_fractions_allowed'])
        self.assertFalse(r['independent_protocol_checked'])
        self.assertFalse(r['hardware_speedup_claim'])
        self.assertEqual(r['hardware_summary']['v2_full'],8)
        self.assertEqual(r['hardware_summary']['v2_refill'],8)
        self.assertEqual(r['hardware_summary']['v2_row_load'],8868)

    def test_missing_identity_terminal_and_summary_rejected(self):
        for old in (SCOPE,BINDING,TERMINAL,'Core Test *** SUCCESS *** (tohost = 0)','UVM_ERROR : 0'):
            with self.subTest(old=old),self.assertRaises(ValueError):check(self.text.replace(old,''))
        with self.assertRaises(ValueError):check(self.text.replace(TERMINAL,TERMINAL+'\n'+TERMINAL))

    def test_output_csr_native_command_negative_checks(self):
        for old,new in (('errors=0','errors=1'),('vstart=0','vstart=1'),('vcsr=5','vcsr=3'),
                        ('fcsr=9','fcsr=0'),('words=256','words=255'),
                        ('read_fault=0','read_fault=1'),('kv_external_bytes=32768','kv_external_bytes=32766'),
                        ('seq=1 ','seq=2 '),('v2_column_panel=1','v2_column_panel=0'),
                        ('UVM_ERROR : 0','UVM_ERROR : 1')):
            with self.subTest(old=old),self.assertRaises(ValueError):check(self.text.replace(old,new,1))

    def test_observer_counts_and_perturbation_gate(self):
        text=self.text.replace('id=12 calls=1 cycles=0','id=12 calls=0 cycles=0',1)
        with self.assertRaises(ValueError):check(text)
        r=check(fixture(.06))
        self.assertFalse(r['quantitative_phase_fractions_allowed'])
        self.assertTrue(all(t['exclusive_phase_means'] is None for t in r['measured']))

    def test_paired_row_digest_change_and_trailing_work_rejected(self):
        old='F16_REAL_ROW phase=0 trial=1 row=0 hash=0000000000000000'
        with self.assertRaises(ValueError):check(self.text.replace(old,old[:-1]+'1'))
        extra='\n'+next(line for line in self.text.splitlines() if line.startswith('[AKV_PERF] '))
        with self.assertRaises(ValueError):check(self.text+extra)
        for terminal in ('Core Test *** FAILED *** (tohost = 1)',
                         'Core Test *** SUCCESS *** (tohost = 1)',
                         'Core Test *** SUCCESS *** (tohost = 0)'):
            with self.subTest(terminal=terminal),self.assertRaises(ValueError):check(self.text+'\n'+terminal)

    def test_actual_prefill_and_decode_not_interchangeable(self):
        for old,new in (('prefill=64','prefill=4'),('decode_visible=137','decode_visible=64'),
                        ('pair_heads=1','pair_heads=0'),('probed=1','probed=0')):
            with self.subTest(old=old),self.assertRaises(ValueError):check(self.text.replace(old,new,1))


if __name__=='__main__':unittest.main()
