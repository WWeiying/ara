import unittest

from check_decode_matched_activity import check, ACCESS, K, PROFILE, COUNTERS, WAIT, PHASES, CONTEXT_COUNTERS
from test_decode_matched import fixture
from check_projection_native import fields


def activity_fixture(width):
    text, *oracle = fixture()
    text = text.replace('execution=80', 'execution=100000').replace('execution=560', 'execution=700000')
    text = text.replace('region=680', 'region=700120')
    records = []
    for trial in range(2):
        for part, accesses in enumerate(ACCESS):
            blocks, profile = K[part] // 256, PROFILE[part]
            for tile, access in enumerate(accesses):
                reused = int(access in (2, 3)); activation = blocks * 292
                weight = 32 * blocks * (144 if profile == 1 else 210)
                c = {k: 0 for k in (*COUNTERS, *WAIT, *CONTEXT_COUNTERS)}
                c.update(seq=trial*14+part*2+tile+1, m=1, n=32, vlen=1024, lanes=4,
                    success=1, fault=0, validation_fault=0, read_fault=0, useful_pairs=8192*blocks,
                    dot_active_cycles=256*blocks, activation_access=access, activation_bytes=activation,
                    weight_bytes=weight, payload_bytes=16+weight+(0 if reused else activation),
                    context_fill_count=int(access==1), context_reuse_count=reused,
                    context_reuse_block_count=blocks if reused else 0,
                    context_read_bytes=activation if reused else 0,
                    activation_axi_bytes_saved=activation if reused else 0,
                    ar=1+8*blocks+(0 if reused else blocks),
                    read_ranges=1+8*blocks+(0 if reused else blocks))
                weight_beats = (36 if profile==1 else 53) if width==128 else (18 if profile==1 else 27)
                c['r_beats'] = 1+8*blocks*weight_beats+(0 if reused else blocks*19)
                c['busy_cycles'] = c['r_beats']+10000
                c.update({'phase_'+p+'_cycles': c['busy_cycles'] if i==0 else 0 for i,p in enumerate(PHASES)})
                records.append('[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in c.items()))
    return text+'\n'+'\n'.join(records), oracle


class MatchedActivityTests(unittest.TestCase):
    def test_both_physical_widths_and_all_native_work(self):
        for width in (128, 256):
            text, oracle = activity_fixture(width)
            result = check(text, width, *oracle)
            self.assertTrue(result['native_work_checked'])
            self.assertEqual(len(result['native_activity']), 14)

    def test_wrong_geometry_context_or_service_rejected(self):
        text, oracle = activity_fixture(128)
        for a,b in (('seq=1 ', 'seq=2 '), ('n=32 ', 'n=16 '),
                    ('activation_access=1 ', 'activation_access=0 '),
                    ('weight_bytes=36864 ', 'weight_bytes=36863 '),
                    ('context_fill_count=1 ', 'context_fill_count=0 ')):
            self.assertIn(a,text)
            with self.subTest(a=a), self.assertRaises(ValueError): check(text.replace(a,b,1),128,*oracle)
        with self.assertRaises(ValueError): check(text,256,*oracle)
        with self.assertRaises(ValueError): check(text+'\n[QBS_PERF] seq=29',128,*oracle)

    def test_dot_issue_cannot_exceed_busy_even_with_consistent_phase_sum(self):
        text, oracle = activity_fixture(256)
        lines = text.splitlines()
        index = next(i for i,line in enumerate(lines) if line.startswith('[QBS_PERF] '))
        command = fields(lines[index], '[QBS_PERF]')
        command['busy_cycles'] = command['r_beats']
        self.assertLess(command['busy_cycles'], command['dot_active_cycles'])
        for p in PHASES: command['phase_'+p+'_cycles'] = 0
        command['phase_'+PHASES[0]+'_cycles'] = command['busy_cycles']
        lines[index] = '[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in command.items())
        with self.assertRaisesRegex(ValueError, 'phase/wait accounting'):
            check('\n'.join(lines),256,*oracle)


if __name__=='__main__': unittest.main()
