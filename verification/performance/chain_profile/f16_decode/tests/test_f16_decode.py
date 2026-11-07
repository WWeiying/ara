import struct
import subprocess
import sys
import tempfile
import unittest
from functools import partial
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import build
import check

MEMORY = dict(data_hash=123, query_hash=456, guard_hash=789, guard_bytes=5704)
check_log = partial(check.check_log, memory_expected=MEMORY)


def fixture():
    lines = ['CHAIN_F16_SHAPE d=128 qheads=2 kvheads=1 tokens=137 capacity=256 tile=64 vlenb=128']
    for t, profile in enumerate(check.ORDER):
        begin = 1000 + t * 1000
        lines.append(f'CHAIN_F16_TRIAL trial={t} profile={profile} begin={begin} '
                     f'returned={begin+500} end={begin+510} fcsr=1 vcsr=0 vstart=0 groups=1 errors=0')
        lines.append(f'CHAIN_F16_MEMORY trial={t} data_hash=7b query_hash=1c8 guard_hash=315 guard_bytes=5704')
        for i in range(13):
            before = begin + 10 + i * 30 if profile else 0
            after = before + 20 if profile else 0
            lines.append(f'CHAIN_F16_SPAN trial={t} slot={i} before={before} after={after}')
        for i in range(256):
            lines.append(f'CHAIN_F16_OUT trial={t} index={i} bits=3f800000')
    for s in range(8):
        lines.append(f'CHAIN_F16_CAL sample={s} total=200')
        for i in range(13):
            lines.append(f'CHAIN_F16_EMPTY sample={s} slot={i} cycles=3')
    lines.append('CHAIN_F16_DONE trials=4 errors=0')
    return '\n'.join(lines), struct.pack('<256f', *([1.0] * 256))


def hardware_fixture():
    rows = []
    for index, expected in enumerate(check.expected_commands()):
        row = dict(expected, seq=index+1, success=1, busy_cycles=1, fault=0,
            validation_fault=0, validation_error=0, read_fault=0, full=0, refill=0,
            v2_column_panel=0, v2_rejected=0, context_ready=int(expected['command'] != 3))
        rows.append('[AKV_PERF] ' + ' '.join(f'{k}={v}' for k, v in row.items()))
    return '\n'.join(rows)


class CheckerTests(unittest.TestCase):
    def test_complete_log_and_zero_measured_delta_not_assumed(self):
        log, golden = fixture()
        result = check_log(log, golden, golden)
        self.assertEqual(result['probe_delta_cycles'], 0)
        self.assertEqual(result['empty_interval_median'], 3)
        self.assertEqual(result['workcounts']['refill'], 2)
        self.assertEqual(result['phase_profiles'][0]['outside_spans'], 250)

    def test_signed_nonzero_overhead(self):
        log, golden = fixture()
        log = log.replace('end=2510', 'end=2550').replace('end=3510', 'end=3550')
        self.assertEqual(check_log(log, golden, golden)['probe_delta_cycles'], 40)

    def test_rejects_faults_and_incomplete_evidence(self):
        log, golden = fixture()
        corruptions = [
            log.replace('tile=64', 'tile=32'),
            log.replace('tokens=137', 'tokens=128'),
            log.replace('errors=0', 'errors=1', 1),
            log.replace('groups=1', 'groups=0', 1),
            log.replace('fcsr=1', 'fcsr=17', 1),
            log.replace('vcsr=0', 'vcsr=1', 1),
            log.replace('vstart=0', 'vstart=1', 1),
            log.replace('end=1510', 'end=1500'),
            log.replace('bits=3f800000', 'bits=7fc00000', 1),
            log.replace('bits=3f800000', 'bits=3f800001', 1),
            log.replace('trial=0 slot=0 before=0', 'trial=0 slot=0 before=5'),
            log.replace('trial=1 slot=0 before=2010 after=2030',
                        'trial=1 slot=0 before=2010 after=3000'),
            log.replace('CHAIN_F16_DONE trials=4 errors=0', ''),
            log + '\nCHAIN_F16_DONE trials=4 errors=0',
            log + '\nCHAIN_F16_OUT trial=0 index=0 bits=3f800000',
            log.replace('sample=0 slot=0 cycles=3', 'sample=0 slot=0 cycles=0'),
            log.replace('guard_hash=315', 'guard_hash=314', 1),
            log.replace('data_hash=7b', 'data_hash=7c', 1),
            log.replace('query_hash=1c8', 'query_hash=1c9', 1),
        ]
        for n, altered in enumerate(corruptions):
            with self.subTest(n=n), self.assertRaises(ValueError):
                check_log(altered, golden, golden)

    def test_numerical_reference_checked_independently(self):
        log, golden = fixture()
        wrong = struct.pack('<256f', *([1.1] * 256))
        for refs in ((wrong, golden), (golden, wrong)):
            with self.assertRaisesRegex(ValueError, 'Numerical'):
                check_log(log, *refs)

    def test_extra_span_and_bad_trial_order(self):
        log, golden = fixture()
        for changed in (log + '\nCHAIN_F16_SPAN trial=4 slot=0 before=0 after=0',
                        log.replace('trial=1 profile=1', 'trial=1 profile=0'),
                        log.replace('trial=2 slot=12', 'trial=2 slot=13')):
            with self.assertRaises(ValueError):
                check_log(changed, golden, golden)

    def test_hardware_workcounts_and_lifecycle(self):
        log = hardware_fixture()
        result = check.check_hardware_work(log)
        self.assertEqual(result['commands'], 4184)
        self.assertEqual(result['totals']['v2_refill'], 8)
        self.assertEqual(result['totals']['kv_external_bytes'], 4*137*128*4)
        for changed in (log.replace('seq=1 ', 'seq=2 ', 1),
                        log.replace('success=1', 'success=0', 1),
                        log.replace('kv_external_bytes=32768', 'kv_external_bytes=16384', 1),
                        log.replace('replay_bytes=128', 'replay_bytes=64', 1),
                        '\n'.join(log.splitlines()[:-1]), log + '\n' + log.splitlines()[0]):
            with self.assertRaises(ValueError):
                check.check_hardware_work(changed)

    def test_runner_interface_requires_full_functional_and_hardware_evidence(self):
        import re
        log, golden = fixture()
        log = re.sub(r'(begin|returned|end|before|after)=(\d+)',
                     lambda m: m[1] + '=' + str(int(m[2])*10), log)
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            directory = Path(tmp)
            captured, native = directory / 'captured.bin', directory / 'native.bin'
            captured.write_bytes(golden)
            native.write_bytes(golden)
            build_file = directory / 'build.json'
            build_file.write_text('{}')
            manifest = dict(shape=dict(query_head_indices=[0, 1], kv_head_index=0, kv_heads=1),
                golden=dict(captured=str(captured), native_tile64=str(native)), memory_expected=MEMORY,
                elf_sha256='elf', source_pins_sha256='pins', image_contract={})
            path = directory / 'run.log'
            with patch.object(check, 'verify_build', return_value=manifest):
                path.write_text(log)
                with self.assertRaisesRegex(ValueError, 'work evidence'):
                    check.check_run(path, directory)
                path.write_text(hardware_fixture() + '\n' + log)
                result = check.check_run(path, directory)
                self.assertEqual(result['state'], 'PASS')
                self.assertEqual(result['complete_calls'], 4)
                self.assertIn('phase', result)
                self.assertIn('overhead', result)

    def test_vector_workcounts(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            path = Path(tmp) / 'trace.csv'
            header = 'event,insn,nr_lanes,vlen_bits\nconfig,0,4,1024\n'
            payload = 'alloc,0005745b,4,1024\n' * (4*3*2*128)
            payload += 'alloc,0205345b,4,1024\n' * (4*2*137)
            path.write_text(header + payload)
            self.assertEqual(check.check_vector_workcounts(path)['v_row_commands'], 1096)
            path.write_text(header + payload + 'alloc,0205345b,4,1024\n')
            with self.assertRaises(ValueError):
                check.check_vector_workcounts(path)


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = subprocess.check_output(['git', '-C', str(build.ROOT), 'show',
            'HEAD:software/akv/src/akv_v2_native_riscv.c'], text=True)

    def test_additive_transform_preserves_arithmetic_and_fences(self):
        changed, receipt = build.instrument(self.source)
        self.assertTrue(receipt['reversible'])
        self.assertEqual(changed.count('fence'), self.source.count('fence'))
        self.assertEqual(changed.count('F16_BEGIN('), 5)
        self.assertEqual(changed.count('F16_END('), 5)
        self.assertNotIn('printf', changed)
        for operation in ('__riscv_vfmacc', '__riscv_vfmul', '__builtin_expf', 'store_outputs('):
            self.assertEqual(changed.count(operation), self.source.count(operation))

    def test_fails_on_source_anchor_drift(self):
        with self.assertRaises(ValueError):
            build.instrument(self.source.replace('      issue_refill(tile_start);',
                                                  '      issue_refill(tile_start + 1);'))

    def test_integer_probe_only(self):
        text = (HERE / 'probe.h').read_text()
        self.assertIn('rdcycle %0', text)
        self.assertIn('sd %0', text)
        for forbidden in ('fence ', 'printf(', 'malloc(', '__riscv_', 'float '):
            self.assertNotIn(forbidden, text)

    def test_original_capture_mapping_and_shape(self):
        receipt = build.validate_data(build.DATA)
        self.assertEqual(receipt['phases']['decode']['visible_prefixes'], [137])
        self.assertEqual(build.SHAPE['tile_lengths'], [64, 64, 9])
        self.assertEqual(build.SHAPE['qk_scalar_fmas'], 35072)
        self.assertEqual(build.SHAPE['k_column_commands'], 768)


if __name__ == '__main__':
    unittest.main()
