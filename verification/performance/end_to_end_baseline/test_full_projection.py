from pathlib import Path
import unittest

from full_projection import SCOPE, N, check, native_source, golden_source
from check_projection_native import checksum

HERE = Path(__file__).resolve().parent


def fixture(wide):
    golden = [bytes([i])*4*n*4 for i,n in enumerate(N)]
    lines = [SCOPE]; busy = 6000 if wide else 10000
    for i in range(128):
        lines.append(f'[QBS_PERF] seq={i+1} m=4 n=32 vlen=1024 lanes=4 success=1 fault=0 validation_fault=0 read_fault=0 '
                     f'useful_pairs=262144 dot_active_cycles={4096 if wide else 8192} activation_access=0 '
                     f'weight_bytes={36864 if i<96 else 53760} activation_bytes=9344 busy_cycles={busy}')
    for part,n in enumerate(N):
        lines.append(f'MATRIX_FULL_PART trial=0 part={part} profile={(1,1,2)[part]} n={n} admission=10 '
                     f'execution={n//32*busy+100} fcsr=9 vcsr=5 checksum={checksum(golden[part])} errors=0')
    execution = 128*busy+300
    lines.append(f'MATRIX_FULL_TRIAL id=0 preparation=1000 admission=30 execution={execution} region={execution+1100} commands=128 errors=0')
    lines.append('MATRIX_FULL_RESULT trials=1 commands=128 outputs=16384 errors=0')
    return '\n'.join(lines)+'\n', golden


class FullProjectionTests(unittest.TestCase):
    def test_geometry_oracle_and_caller_transform(self):
        original = (HERE/'projection_native.cpp').read_text(); full = native_source(original)
        self.assertIn(SCOPE, full)
        self.assertNotIn('MATRIX_NATIVE_',full)
        self.assertIn('M*n[part]*sizeof(float)',full)
        self.assertIn('i < sizeof(output[part])',full)
        self.assertIn('commands != 128',full)
        oracle = golden_source((HERE/'projection_golden.c').read_text(),'/absolute/qbs_ref.h')
        self.assertIn('output+row*n+start',oracle)
        self.assertIn('name, output, M*n*sizeof(float)',oracle)
        with self.assertRaises(ValueError): native_source(original.replace('N=128','N=64'))

    def test_actual_full_work_not_prefix(self):
        for wide in (0,1):
            text,golden = fixture(wide); result = check(text,wide,golden)
            self.assertEqual(result['useful_pairs'],33554432)
            self.assertTrue(result['full_n'])
            self.assertEqual(result['qbs_commands'],128)

    def test_reject_shape_result_work_and_timing_drift(self):
        text,golden = fixture(0)
        for broken in (text.replace('nq=2048','nq=128'), text.replace('seq=2 ','seq=1 ',1),
                       text.replace('n=1024','n=128',1), text.replace('fcsr=9','fcsr=8',1),
                       text.replace('weight_bytes=36864','weight_bytes=36865',1),
                       text.replace('errors=0','errors=1',1), text+text):
            with self.assertRaises(ValueError): check(broken,0,golden)
        with self.assertRaises(ValueError): check(text,1,golden)


if __name__=='__main__': unittest.main()
