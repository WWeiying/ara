"""Host-only probe transformation and strict raw-observation contract tests."""
import copy
from pathlib import Path
import unittest

from audit import digest
import build_output_phase as build
from check_output_phase import CALLS, PHASES, SCOPE, check


def fixture():
    lines = [SCOPE]
    for trial, probed in enumerate((0,1,1,0)):
        lines.append(f'OUTPUT_PHASE_BEGIN trial={trial} probed={probed}')
        for i in range(8):
            m = 4 if i%2 == 0 else 2
            command = dict(seq=trial*8+i+1,m=m,n=32,vlen=1024,lanes=4,success=1,
                fault=0,validation_fault=0,read_fault=0,weight_bytes=32*136,
                useful_pairs=m*32*128,activation_access=0,busy_cycles=1000)
            lines.append('[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in command.items()))
        stats = dict(trial=trial,probed=probed,timer_reads=46 if probed else 0)
        for name, calls, cycles in zip(PHASES,CALLS,(100,2000,16000,40000,30000,1000,12000)):
            stats[name+'_cycles'] = cycles if probed else 0
            stats[name+'_calls'] = calls if probed else 0
        lines.append('OUTPUT_PHASE_STATS '+' '.join(f'{k}={v}' for k,v in stats.items()))
        lines.append(f'OUTPUT_PHASE_RESULT trial={trial} probed={probed} '
            f'cycles={103000 if probed else 100000} commands=8 groups=1 values=128 panels=4 '
            'key_bytes=17408 fcsr=9 vcsr=5 vstart=0 errors=0 hex='+'00000000'*768)
    lines.append('OUTPUT_PHASE_SUITE_PASS')
    return '\n'.join(lines), bytes(1536*4)


class RawContractTests(unittest.TestCase):
    def test_normal_and_nested_accounting(self):
        result = check(*fixture())
        self.assertTrue(result['paired_bitexact'])
        self.assertTrue(result['quantitative_phase_fractions_allowed'])
        self.assertAlmostEqual(result['measured_perturbation'],0.03)
        self.assertEqual(result['trials'][1]['exclusive_phase_cycles'],89100)
        self.assertFalse(result['independent_protocol_checked'])
        self.assertFalse(result['optimization_speedup_claim'])

    def test_large_measured_perturbation_no_quantitative_fractions(self):
        text, golden = fixture()
        result = check(text.replace('cycles=103000','cycles=110000'),golden)
        self.assertFalse(result['quantitative_phase_fractions_allowed'])
        # A layout-induced negative perturbation is not automatically harmless.
        result = check(text.replace('cycles=103000','cycles=93000'),golden)
        self.assertFalse(result['quantitative_phase_fractions_allowed'])

    def test_reject_malformed_or_missing_observations(self):
        text, golden = fixture()
        changes = [
            ('timer_reads=46','timer_reads=44'),
            ('qk_calls=4','qk_calls=8'),
            ('quantize_calls=1','quantize_calls=6'),
            ('binding_calls=8','binding_calls=7'),
            ('binding_cycles=12000','binding_cycles=17000'),
            ('binding_cycles=12000','binding_cycles=7000'),
            ('coefficients_cycles=40000','coefficients_cycles=80000'),
            ('pv_cycles=30000','pv_cycles=0'),
            ('init_cycles=0','init_cycles=1'),
            ('fcsr=9','fcsr=8'),
            ('vcsr=5','vcsr=3'),
            ('vstart=0','vstart=1'),
            ('errors=0','errors=1'),
            ('commands=8','commands=7'),
            ('groups=1','groups=0'),
            ('values=128','values=127'),
            ('panels=4','panels=8'),
            ('key_bytes=17408','key_bytes=17407'),
            ('weight_bytes=4352','weight_bytes=2304'),
            ('activation_access=0','activation_access=1'),
            ('success=1','success=0'),
            ('seq=1 ','seq=2 '),
            ('probed=1','probed=0'),
            ('OUTPUT_PHASE_SUITE_PASS',''),
        ]
        for before, after in changes:
            with self.subTest(change=before):
                self.assertIn(before,text)
                with self.assertRaises((AssertionError,ValueError)):
                    check(text.replace(before,after,1),golden)

    def test_reject_bit_difference_even_within_numeric_tolerance(self):
        text, golden = fixture()
        location = text.index('OUTPUT_PHASE_RESULT trial=1')
        altered = text[:location]+text[location:].replace('hex=00000000','hex=00000001',1)
        with self.assertRaises((AssertionError,ValueError)):
            check(altered,golden)

    def test_reject_changed_golden(self):
        text, golden = fixture()
        import struct
        golden = struct.pack('<f',1.0)+golden[4:]
        with self.assertRaises((AssertionError,ValueError)):
            check(text,golden)

    def test_reject_duplicate_noise_and_old_fixture_substitution(self):
        text, golden = fixture()
        stats = next(s for s in text.splitlines() if s.startswith('OUTPUT_PHASE_STATS'))
        extras = ('Fatal: injected','Error: injected','UVM_ERROR @ 0: injected',
                  'OUTPUT_PHASE_FAIL','OUTPUT_PHASE_UNKNOWN x=1',
                  'OUTPUT_GQA6_SUITE_PASS','OUTPUT_PHASE_SUITE_PASS',SCOPE,
                  'OUTPUT_PHASE_BEGIN trial=4 probed=0','[QBS_PERF] seq=33')
        for extra in extras:
            with self.subTest(extra=extra), self.assertRaises((AssertionError,ValueError)):
                check(text+'\n'+extra,golden)
        with self.assertRaises((AssertionError,ValueError)):
            check(text.replace(stats,stats+'\n'+stats,1),golden)
        with self.assertRaises((AssertionError,ValueError)):
            check(text.replace('timer_reads=0','timer_reads=0 timer_reads=0',1),golden)


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.sources = {p:(build.ROOT/p).read_text() for p in build.SOURCE_SHAS}

    def test_include_mapping_respects_directory_not_string_prefix(self):
        out = Path('/tmp/output-phase-test')
        remap = lambda p: build.remap_input(p,{},out)
        self.assertEqual(remap('-I'+str(build.ROOT)),'-I'+str(out/'inputs/main'))
        self.assertEqual(remap('-I'+str(build.VERIFY/'apps/common')),
                         '-I'+str(out/'inputs/verify/apps/common'))
        sibling = '-I'+str(build.ROOT)+'_unrelated'
        self.assertEqual(remap(sibling),sibling)
        self.assertEqual(remap('-I/usr/include'),'-I/usr/include')

    def test_pinned_original_sources_and_insertion_only_full_files(self):
        for path, sha in build.SOURCE_SHAS.items():
            self.assertEqual(digest(build.ROOT/path),sha)
        result, operations = build.transform_sources(self.sources)
        self.assertEqual(len(operations),10)
        for path, source in self.sources.items():
            retained = [line for line in result[path].splitlines() if not (
                'const uint64_t phase_' in line or 'output_phase_end(' in line or
                line == '#include "verification/performance/end_to_end_baseline/output_phase_probe.h"')]
            self.assertEqual(retained,source.splitlines())
        original = self.sources[build.Q+'output_tile/online.h']
        changed = result[build.Q+'output_tile/online.h']
        self.assertEqual(changed.count('expf('),original.count('expf('))
        self.assertEqual(changed.count('expf('),2)

    def test_missing_and_ambiguous_anchors_fail_closed(self):
        for path, before, _ in build.transforms():
            for change in ('missing','duplicate'):
                sources = copy.copy(self.sources)
                sources[path] = (sources[path].replace(before,'',1) if change == 'missing'
                                 else sources[path]+'\n'+before)
                with self.subTest(path=path,change=change):
                    with self.assertRaises((AssertionError,ValueError)):
                        build.transform_sources(sources)

    def test_no_per_exp_timer_and_caller_completion_contract(self):
        caller = (Path(__file__).parent/'output_phase_main.c').read_text()
        probe = (Path(__file__).parent/'output_phase_probe.h').read_text()
        self.assertIn('const unsigned order[] = {0,1,1,0}',caller)
        self.assertIn('const unsigned expected_calls[] = {1,1,4,4,4,1,8}',caller)
        self.assertIn('output_phase_stamp()-begin',caller)
        self.assertIn('else errors+=bits(y)!=bits(baseline[row][d])',caller)
        self.assertIn('fc!=9 || vc!=5 || start!=0',caller)
        self.assertIn('csrr %1,vcsr; frcsr %2; csrr %3,vstart; fence rw,rw; rdcycle %0',probe)
        for _, before, after in build.transforms():
            self.assertNotIn('expf(',before)
            self.assertNotIn('expf(',after)


if __name__ == '__main__':
    unittest.main()
