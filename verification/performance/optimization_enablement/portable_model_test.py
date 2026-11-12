"""Synthetic checker acceptance/rejection tests, not model evidence."""
import unittest
from portable_model_check import check

MODEL = dict(vocabulary=6, layers=2, q_heads=32, kv_heads=1)
SYMBOLS = dict(qbs=0x1000, features=0x2000)


def fixture():
    lines = []
    for mode in (0, 1):
        lines += ['PORTABLE_ARM_BEGIN mode=' + str(mode),
            'PORTABLE_ENV mode=' + str(mode) + ' portable=' + ('0' if mode == 0 else 'unset') + ' master=unset emulate=unset qbs=unset',
            'Trace 0: 0xaa [0/1000/0/0] qbs', 'Trace 0: 0xbb [0/1000/0/0] qbs']
        if mode:
            lines += ['Trace 0: 0xcc [0/2000/0/0] features'] * 8
            lines += ['GGML_RISCV_AKV_EXEC mode=decode kernel=v2 kv_heads=1 q_rows=32 gqa_rows=32 head_dim=64 active_kv=4 attention_macs=16384 groups=4 portable=1 softcap=0 max_bias=8 sinks=0'] * 2
        lines += ['GGML_RISCV_AKV_FALLBACK mode=prefill reason=feature portable=0'] * 2
        if not mode:
            lines += ['GGML_RISCV_AKV_FALLBACK mode=decode reason=feature portable=0'] * 2
        lines += ['GGML_RISCV_QBS_EXEC type=' + kind + ' native_qbexec=1 emulated_commands=0' for kind in ('Q4_K', 'Q6_K')]
        lines += ['GGML_RISCV_AKV_COVERAGE candidate_ops=4 executed_ops=' + str(mode*2) + ' groups=' + str(mode*8) +
            ' executed_decode=' + str(mode*2) + ' executed_prefill=0 fallback_feature=' + str((2-mode)*2) + ' fallback_size=0']
        for step in (0, 1):
            lines += ['PORTABLE_DECODE step=' + str(step) + ' rows=' + str(3 if step == 0 else 1) +
                ' rc=0 before_fcsr=1 before_vcsr=5 before_vstart=0 fcsr=1 vcsr=5 vstart=0',
                'PORTABLE_TOKEN step=' + str(step) + ' token=1']
        text = 'The answer is X\n'
        lines += ['PORTABLE_STDOUT_BEGIN mode=' + str(mode) + ' bytes=' + str(len(text)), text[:-1], '',
                  'PORTABLE_STDOUT_END mode=' + str(mode)]
        for step in (0, 1):
            lines += ['PORTABLE_LOGITS_BEGIN mode=' + str(mode) + ' step=' + str(step) + ' values=6',
                'PORTABLE_BITS index=0 00000000 40a00000 3f800000 40000000 40400000 40800000',
                'PORTABLE_LOGITS_END mode=' + str(mode) + ' step=' + str(step)]
        lines += ['PORTABLE_ARM_END mode=' + str(mode) + ' status=0']
    return lines + ['GUEST_TEST_EXIT=0']


class Checker(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(check(fixture(), SYMBOLS, MODEL)['portable_groups'], 8)

    def reject(self, old, new):
        rows = fixture()
        rows[rows.index(old)] = new
        with self.assertRaises(ValueError):
            check(rows, SYMBOLS, MODEL)

    def test_rejections(self):
        for old, new in (
            ('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1'),
            ('Trace 0: 0xaa [0/1000/0/0] qbs', 'generatedTrace 0: 0xaa [0/1000/0/0] qbs'),
            ('Trace 0: 0xcc [0/2000/0/0] features', 'ignored'),
            ('Trace 0: 0xaa [0/1000/0/0] qbs', 'Trace 0: 0xaa [0/3000/0/0] unfiltered'),
            ('GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=0', 'GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=1'),
            ('GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=0', 'GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=2 emulated_commands=0'),
            ('PORTABLE_TOKEN step=0 token=1', 'PORTABLE_TOKEN step=0 token=2'),
            ('PORTABLE_LOGITS_BEGIN mode=0 step=0 values=6', 'PORTABLE_LOGITS_BEGIN mode=0 step=0 values=5'),
            ('PORTABLE_BITS index=0 00000000 40a00000 3f800000 40000000 40400000 40800000', 'PORTABLE_BITS index=0 7f800000 40a00000 3f800000 40000000 40400000 40800000'),
            ('PORTABLE_DECODE step=1 rows=1 rc=0 before_fcsr=1 before_vcsr=5 before_vstart=0 fcsr=1 vcsr=5 vstart=0',
             'PORTABLE_DECODE step=1 rows=1 rc=0 before_fcsr=1 before_vcsr=5 before_vstart=0 fcsr=0 vcsr=5 vstart=0'),
            ('PORTABLE_DECODE step=1 rows=1 rc=0 before_fcsr=1 before_vcsr=5 before_vstart=0 fcsr=1 vcsr=5 vstart=0',
             'PORTABLE_DECODE step=1 rows=1 rc=0 before_fcsr=1 before_vcsr=5 before_vstart=0 fcsr=1 vcsr=5 vstart=1'),
            ('PORTABLE_ENV mode=1 portable=unset master=unset emulate=unset qbs=unset', 'PORTABLE_ENV mode=1 portable=1 master=unset emulate=unset qbs=unset'),
            ('PORTABLE_STDOUT_END mode=0', 'ignored'),
            ('PORTABLE_ARM_END mode=0 status=0', 'PORTABLE_ARM_END mode=0 status=1')):
            with self.subTest(old=old, new=new):
                self.reject(old, new)

    def test_shape_and_feature_rejections(self):
        source = next(row for row in fixture() if row.startswith('GGML_RISCV_AKV_EXEC '))
        for old, new in (('max_bias=8', 'max_bias=0'), ('q_rows=32', 'q_rows=8'),
                         ('groups=4', 'groups=1'), ('portable=1', 'portable=0'), ('head_dim=64', 'head_dim=256'),
                         ('attention_macs=16384', 'attention_macs=1')):
            with self.subTest(old=old):
                self.reject(source, source.replace(old, new))

    def test_tag4_rejected(self):
        rows = fixture()
        rows.insert(2, 'GGML_RISCV_QBS_M4_SELECTED source=cache tag=4 event=compute_rvv k=1536')
        with self.assertRaises(ValueError):
            check(rows, SYMBOLS, MODEL)

    def test_cancelled_block(self):
        rows = fixture()
        i = rows.index('Trace 0: 0xcc [0/2000/0/0] features')
        rows[i:i] = ['Trace 0: 0xdd [0/2000/0/0] features', 'Stopped execution of TB chain before 0xdd [2000] ignored']
        self.assertEqual(check(rows, SYMBOLS, MODEL)['native_entries'][1]['features'], 8)

    def test_cancelled_unpaired(self):
        self.reject('Trace 0: 0xcc [0/2000/0/0] features', 'Stopped execution of TB chain before 0xdd [2000] ignored')

    def test_prefill_exact_decode_bounded(self):
        rows = fixture()
        i = rows.index('PORTABLE_LOGITS_BEGIN mode=1 step=1 values=6') + 1
        rows[i] = rows[i].replace('3f800000', '3f800001')
        self.assertFalse(check(rows, SYMBOLS, MODEL)['numerical'][1]['bitwise_equal'])
        rows = fixture()
        i = rows.index('PORTABLE_LOGITS_BEGIN mode=1 step=0 values=6') + 1
        rows[i] = rows[i].replace('3f800000', '3f800001')
        with self.assertRaises(ValueError):
            check(rows, SYMBOLS, MODEL)


if __name__ == '__main__':
    unittest.main(verbosity=2)
