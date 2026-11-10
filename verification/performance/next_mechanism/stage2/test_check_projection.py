import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('stage2_projection_check', Path(__file__).with_name('check_projection.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def fixture(enabled):
    build = dict(m=8, k=2048, n=32, trials=[4, 8, 8, 4], build_id='test', full_output_width=False)
    lines = []
    seq = 0
    for mode in build['trials']:
        for _ in range(2):
            seq += 1
            tn = 16 if mode == 8 else 32
            p = dict(seq=seq, success=1, fault=0, validation_fault=0, read_fault=0,
                     validation_error=0, busy_cycles=10, m=mode, n=tn, vlen=1024, lanes=4,
                     weight_bytes=tn*8*144, activation_bytes=mode*8*292, useful_pairs=262144,
                     dot_active_cycles=4096 if enabled and mode == 8 else 8192,
                     pair_capacity=262144, tiles=64, activation_access=0, context_fill_count=0,
                     context_reuse_count=0, context_validation_fault_count=0,
                     **{k: 0 for k in check.PHASES})
            p['phase_compute_cycles'] = 10
            lines.append('[QBS_PERF] ' + ' '.join(f'{k}={v}' for k, v in p.items()))
    lines.append('STAGE2_PROJECTION_META id=test m=8 k=2048 n=32 trials=4 whole_model=0')
    for trial, mode in enumerate(build['trials']):
        lines.append(f'STAGE2_PROJECTION_TRIAL id={trial} mode={mode} status=0 commands=2 context=0 '
                     'quant=1 pack=1 plan=1 execute=20 drain=1 total=24 flags=1 expected_flags=1 '
                     'q8_bad=0 output_bad=0 guards_bad=0')
        for row in range(8):
            for col in range(32):
                lines.append(f'STAGE2_PROJECTION_OUTPUT trial={trial} row={row} col={col} bits=3f800000')
    lines += ['STAGE2_PROJECTION_PASS errors=0', 'Core Test *** SUCCESS ***']
    return '\n'.join(lines), build, struct.pack('<256I', *([0x3f800000]*256))


class TestProjectionChecker(unittest.TestCase):
    def test_baseline_and_candidate(self):
        for enabled in (0, 1):
            text, build, expected = fixture(enabled)
            result = check.check(text, build, expected, 0, enabled)
            self.assertEqual(result['outputs_bit_exact'], 1024)

    def test_reject_missing_bad_duplicate_or_work_mismatch(self):
        text, build, expected = fixture(1)
        for changed in (text.replace('bits=3f800000', 'bits=3f800001', 1),
                        text.replace('q8_bad=0', 'q8_bad=1', 1),
                        text.replace('dot_active_cycles=4096', 'dot_active_cycles=8192', 1),
                        text.replace('seq=1 ', 'seq=2 ', 1),
                        text.replace('STAGE2_PROJECTION_PASS errors=0', ''),
                        text + '\nSTAGE2_PROJECTION_PASS errors=0',
                        text.replace('col=0 bits=3f800000', 'col=1 bits=3f800000', 1)):
            with self.subTest(changed=changed[:50]), self.assertRaises(ValueError):
                check.check(changed, build, expected, 0, 1)


if __name__ == '__main__':
    unittest.main()
