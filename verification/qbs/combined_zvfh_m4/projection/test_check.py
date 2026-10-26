import csv
from pathlib import Path
import tempfile
import unittest

from check import INFO, check_contract, check_output, check_trace, fnv

HERE = Path(__file__).resolve().parent
CONTRACT = dict(shape=[4, 1536, 1536], golden_fcsr=1, oracle_atol=2e-4, oracle_rtol=2e-5,
                activation_bytes=7008, context_capacity=4672, wide=0, segment=256,
                weight_integrity='before_after_abba_exact_vector_compare',
                digests=dict(input='12b17711649c6f58', weights='0123456789abcdef', packed='0caa346e033cfef9'))


def fixture():
    lines = ['Q8K_CURRENT_BEGIN ' + ' '.join(f'info{i}={word}' for i, word in enumerate(INFO))]
    for index in range(4):
        used = int(index in (1, 2))
        lines.append(f'Q8K_CURRENT_TRIAL id={index} path={"canonical" if used else "generic"} '
                     f'admit=10 prep=20 execute=100 total=130 used={used} context=0 wide=0 segment=256 commands=48 '
                     'prep_fcsr=1 final_fcsr=1 prep_vcsr=5 final_vcsr=5 input=12b17711649c6f58 '
                     'weights=0123456789abcdef packed=0caa346e033cfef9 output=fbb83bb6df5ca009 errors=0')
    lines.append('Q8K_CURRENT_INTEGRITY scope=before_after_abba method=exact_vector_compare bytes=1327104 '
                 'reference=0123456789abcdef before_equal=1 after_equal=1 errors=0')
    lines.append('Q8K_CURRENT_RESULT errors=0 m=4 n=1536 k=1536 outputs=6144 trials=4 commands=192 '
                 'planner=current_sdk context=direct checks=bytes_bsums_oracle_canaries_input')
    return '\n'.join(lines)


def trace_rows():
    config = dict(event='config', insn='00000000', arch_seq=0, vl=0, vd=0, eew=0,
                  be='00', lane=0, addr=0, vstart=0, nr_lanes=4, vlen_bits=1024)
    rows = [config]
    for index in range(192):
        allocation = dict(config, event='alloc', insn='06b5045b', arch_seq=index+1, vl=128, vd=8, eew=2)
        rows.append(allocation)
        rows.extend(dict(allocation, event='write', lane=lane, addr=address, be='ff')
                    for address in range(32, 48) for lane in range(4))
    return rows


class SliceCheckerTests(unittest.TestCase):
    def test_complete_abba(self):
        report = check_output(fixture(), CONTRACT)
        self.assertEqual(report['state'], 'GUEST_CHECKS_PASS')
        self.assertEqual(report['sums']['canonical']['total'], 260)
        self.assertEqual(report['slice_speedup'], 1.0)

    def test_protocol_mutations(self):
        for old, new in (('id=1', 'id=2'), ('path=canonical', 'path=generic'), ('used=1', 'used=0'),
                         ('total=130', 'total=129'), ('prep=20', 'prep=0'), ('admit=10', 'admit=-1'),
                         ('context=0', 'context=1'), ('wide=0', 'wide=1'), ('segment=256', 'segment=4'),
                         ('commands=48', 'commands=47'), ('errors=0', 'errors=1'),
                         ('prep_fcsr=1', 'prep_fcsr=0'), ('final_fcsr=1', 'final_fcsr=2'),
                         ('final_vcsr=5', 'final_vcsr=3'), ('prep_vcsr=5', 'prep_vcsr=3'),
                         ('input=12b17711649c6f58', 'input=02b17711649c6f58'),
                         ('weights=0123456789abcdef', 'weights=1123456789abcdef'),
                         ('reference=0123456789abcdef', 'reference=1123456789abcdef'),
                         ('before_equal=1', 'before_equal=0'), ('after_equal=1', 'after_equal=0'),
                         ('bytes=1327104', 'bytes=1327103'),
                         ('packed=0caa346e033cfef9', 'packed=1caa346e033cfef9'),
                         ('output=fbb83bb6df5ca009', 'output=fbb83bb6df5ca008'),
                         ('info3=0000000100001240', 'info3=0000000000000000'),
                         ('outputs=6144', 'outputs=6143'), ('used=0', 'used=0 extra=1')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_output(fixture().replace(old, new, 1), CONTRACT)

    def test_missing_extra_and_failure(self):
        lines = fixture().splitlines()
        for index in range(len(lines)):
            for bad in (lines[:index]+lines[index+1:], lines[:index]+[lines[index]]+lines[index:]):
                with self.assertRaises(ValueError):
                    check_output('\n'.join(bad), CONTRACT)
        for marker in ('Q8K_CURRENT_UNKNOWN', 'UVM_ERROR', 'Kernel panic', 'Q8K_CURRENT_FAIL reason=plan'):
            with self.assertRaises(ValueError):
                check_output(fixture()+'\n'+marker, CONTRACT)

    def test_contract_drift(self):
        for key, value in (('shape', [4, 1536, 1024]), ('golden_fcsr', 0), ('oracle_atol', 0.1),
                           ('context_capacity', 7008), ('segment', 4), ('wide', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_contract(dict(CONTRACT, **{key: value}))

    def test_fnv_known(self):
        self.assertEqual(fnv(b''), 'cbf29ce484222325')
        self.assertEqual(fnv(b'a'), 'af63dc4c8601ec8c')

    def test_raw_canonical_uvm_summaries(self):
        # Exact zero-summary formatting from a canonical run.vcs.log.
        summary = '\nUVM_ERROR :    0\nUVM_FATAL :    0\n'
        self.assertEqual(check_output(fixture() + summary, CONTRACT)['state'], 'GUEST_CHECKS_PASS')
        for diagnostic in ('UVM_ERROR :    1', 'UVM_FATAL :    2', 'UVM_ERROR : 01',
                           'UVM_FATAL : 0 trailing text', 'prefix UVM_ERROR : 0',
                           'UVM_ERROR @ 100: reporter [CHECK] broken', 'UVM_FATAL [CHECK] broken',
                           'Error: simulator error', 'Fatal-[VCS] simulator failure'):
            with self.subTest(diagnostic=diagnostic), self.assertRaises(ValueError):
                check_output(fixture() + '\n' + diagnostic + summary, CONTRACT)

    def test_exact_trace_and_mutations(self):
        rows = trace_rows()
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / 'trace.csv'
            def check(values):
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(values)
                return check_trace(path)
            self.assertEqual(check(rows), dict(commands=192, result_bytes=98304))
            variants = [rows[1:], rows[:-1], rows + rows[1:66]]
            for index, key, value in ((0, 'vlen_bits', 128), (1, 'insn', '00b5045b'),
                                     (1, 'vl', 127), (2, 'be', '00'), (2, 'addr', 31),
                                     (2, 'arch_seq', 0), (2, 'vstart', 1), (3, 'lane', 0)):
                mutated = rows.copy()
                mutated[index] = dict(rows[index], **{key: value})
                variants.append(mutated)
            for index, bad in enumerate(variants):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    check(bad)

    def test_only_production_kernel(self):
        source = (HERE / 'projection.cpp').read_text()
        self.assertIn('#include "arch/riscv/q8_K-m4.h"', source)
        self.assertIn('ggml_riscv_q8_K_m4::quantize(', source)
        self.assertIn('qbs_plan_create_segmented_r4(', source)
        self.assertIn('qbs_execute(', source)
        self.assertNotIn('qbs_q8k_m4_prepare_candidate', source)
        self.assertNotIn('qbs_q8k_m4_prepare_vla_candidate', source)


if __name__ == '__main__':
    unittest.main()
