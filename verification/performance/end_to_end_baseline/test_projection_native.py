import unittest

from check_projection_native import SCOPE, check, checksum


def fixture(wide):
    golden = [bytes([i])*2048 for i in range(3)]
    rows = [SCOPE]
    for trial in range(2):
        for command in range(12):
            rows.append('[QBS_PERF] seq=%d m=4 n=32 vlen=1024 lanes=4 success=1 fault=0 '
                        'validation_fault=0 read_fault=0 useful_pairs=262144 dot_active_cycles=%d '
                        'activation_access=0 busy_cycles=10000' % (trial*12+command+1, 4096 if wide else 8192))
        for part in range(3):
            rows.append(f'MATRIX_NATIVE_PART trial={trial} part={part} profile={(1,1,2)[part]} '
                        f'admission=10 execution=40000 fcsr=9 vcsr=5 checksum={checksum(golden[part])} errors=0')
        rows.append(f'MATRIX_NATIVE_TRIAL id={trial} preparation=100 admission=30 execution=120000 region=120200 commands=12 errors=0')
    rows.append('MATRIX_NATIVE_RESULT trials=2 commands=24 outputs=3072 errors=0')
    return '\n'.join(rows)+'\n', golden


class ProjectionNativeTests(unittest.TestCase):
    def test_paired_work_and_stage_totals(self):
        for wide in (0, 1):
            log, golden = fixture(wide)
            measured = check(log, wide, golden)
            self.assertEqual(measured['useful_pairs'], 6291456)
            self.assertEqual(measured['execution_cycles'], 240000)

    def test_reject_wrong_config_work_state_result_or_timing(self):
        log, golden = fixture(0)
        for broken in (log.replace('dot_active_cycles=8192', 'dot_active_cycles=4096', 1),
                       log.replace('seq=2 ', 'seq=1 ', 1), log.replace('fcsr=9', 'fcsr=8', 1),
                       log.replace('execution=120000', 'execution=120001', 1),
                       log.replace('checksum=', 'checksum=1', 1), log.replace('errors=0', 'errors=1', 1),
                       log.replace('useful_pairs=262144', 'useful_pairs=262143', 1), log+log,
                       log.replace('outputs=3072 errors=0', 'outputs=3072 errors=1')):
            with self.assertRaises(ValueError): check(broken, 0, golden)


if __name__ == '__main__': unittest.main()
