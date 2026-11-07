import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import check_successor as successor

spec = importlib.util.spec_from_file_location('chain_f16_original_test_fixtures',
                                             HERE / 'tests/test_f16_decode.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SeverityTests(unittest.TestCase):
    def test_only_exact_whole_line_zero_summaries_are_accepted(self):
        for text in ('UVM_ERROR : 0', 'UVM_FATAL : 0',
                     '  UVM_ERROR     :    0  \n\tUVM_FATAL : 0\t',
                     'UVM_ERROR : 0\r\nUVM_FATAL : 0\r\n'):
            with self.subTest(text=text):
                result = successor.classify_severities(text)
                self.assertEqual(result['nonzero_summaries'], 0)
                self.assertTrue(result['independent_uvm_gate_required'])

    def test_nonzero_summaries_are_rejected(self):
        for severity in ('UVM_ERROR', 'UVM_FATAL'):
            for count in ('1', '2', '10', '01', '-1'):
                with self.subTest(severity=severity, count=count), self.assertRaises(ValueError):
                    successor.classify_severities(severity + ' : ' + count)

    def test_real_events_rejected_even_with_zero_summary(self):
        for event in ('UVM_ERROR tb.sv(12) @ 100: reporter [CHECK] bad value',
                      'UVM_FATAL @ 0: reporter [FAIL] stopped',
                      'UVM_ERROR: actual error', 'UVM_FATAL: actual failure',
                      'prefix UVM_ERROR : 0', 'prefix UVM_FATAL : 0',
                      'UVM_ERROR : 0 [real event]', 'UVM_FATAL : 0 trailing',
                      'UVM_ERROR : 0 UVM_FATAL : 1'):
            for text in (event, 'UVM_ERROR : 0\n' + event + '\nUVM_FATAL : 0'):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    successor.classify_severities(text)

    def test_near_zero_formats_are_not_relaxed(self):
        for count in ('00', '+0', '-0', '0.0', '0x0', '', 'zero', '0\x00', '0 # ignored'):
            with self.subTest(count=count), self.assertRaises(ValueError):
                successor.classify_severities('UVM_ERROR : ' + count)


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hardware = fixtures.hardware_fixture()

    def test_original_defect_reproduced_without_changing_original_module(self):
        original = fixtures.check.check_hardware_work
        with self.assertRaises(ValueError):
            original(self.hardware + '\nUVM_ERROR : 0\nUVM_FATAL : 0')
        private = successor._load_predecessor()
        result = private.check_hardware_work(self.hardware + '\nUVM_ERROR : 0\nUVM_FATAL : 0')
        self.assertEqual(result['commands'], 4184)
        self.assertEqual(result['uvm_severity_classification']['strict_zero_summary_lines'],
                         dict(UVM_ERROR=1, UVM_FATAL=1))
        self.assertIs(fixtures.check.check_hardware_work, original)
        self.assertIs(fixtures.check.re, re)
        with self.assertRaises(ValueError):
            original(self.hardware + '\nUVM_ERROR : 0')

    def test_private_module_instances_do_not_share_changes(self):
        first, second = successor._load_predecessor(), successor._load_predecessor()
        self.assertIsNot(first, second)
        self.assertIsNot(first.re, second.re)
        first.expected_commands = lambda: []
        self.assertEqual(second.check_hardware_work(self.hardware)['complete_calls'], 4)

    def test_retains_original_hardware_and_simulator_failures(self):
        private = successor._load_predecessor()
        valid = self.hardware + '\nUVM_ERROR : 0\nUVM_FATAL : 0'
        for changed in (valid.replace('success=1', 'success=0', 1),
                        valid.replace('seq=1 ', 'seq=2 ', 1),
                        valid.replace('kv_external_bytes=32768', 'kv_external_bytes=16384', 1),
                        '\n'.join(valid.splitlines()[1:]),
                        valid + '\nUVM_ERROR : 1', valid + '\nUVM_FATAL : 1',
                        valid + '\nUVM_ERROR @ 10: reporter [FAIL] mismatch',
                        valid + '\nUVM_FATAL @ 10: reporter [FAIL] stopped',
                        valid + '\nFatal: stopped', valid + '\nError: stopped',
                        valid + '\nTIMEOUT'):
            with self.subTest(tail=changed[-80:]), self.assertRaises(ValueError):
                private.check_hardware_work(changed)

    def test_pinned_predecessor_drift_is_rejected(self):
        with patch.object(Path, 'read_bytes', return_value=b'changed source'):
            with self.assertRaisesRegex(ValueError, 'identity drift'):
                successor._load_predecessor()

    def test_real_build03_pins_still_verify(self):
        build_dir = HERE.parents[4] / 'ara_dsa_signoff_integration/verification/out/chain_f16_build_20261107_profile03'
        build = successor._load_predecessor().verify_build(build_dir / 'build.json')
        pins = json.loads(Path(build['source_pins']).read_text())
        self.assertEqual(pins[str(successor.PREDECESSOR)], successor.PREDECESSOR_SHA256)
        self.assertEqual(sha(build_dir / 'build.json'),
                         '7d8420964cd6d702a077746af7b23da0e2c9371417ab640d076c9190b869a061')

    def test_full_runner_metadata_unchanged_evidence_and_negative_gates(self):
        log, golden = fixtures.fixture()
        log = re.sub(r'(begin|returned|end|before|after)=(\d+)',
                     lambda m: m[1] + '=' + str(int(m[2])*10), log)
        raw = self.hardware + '\n' + log + '\nUVM_ERROR : 0\nUVM_FATAL : 0\n'
        private = successor._load_predecessor()
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            directory = Path(tmp)
            captured, native = directory / 'captured.bin', directory / 'native.bin'
            captured.write_bytes(golden)
            native.write_bytes(golden)
            build = directory / 'build.json'
            build.write_text('{}')
            receipt = directory / 'original-receipt.json'
            receipt.write_text('{"state": "ORIGINAL_RECEIPT"}\n')
            manifest = dict(shape=dict(query_head_indices=[0, 1], kv_head_index=0, kv_heads=1),
                golden=dict(captured=str(captured), native_tile64=str(native)),
                memory_expected=fixtures.MEMORY, elf_sha256='elf',
                source_pins_sha256='pins', image_contract={})
            path = directory / 'run.log'
            path.write_text(raw)
            before = {p: sha(p) for p in (path, build, captured, native, receipt)}
            with patch.object(successor, '_load_predecessor', return_value=private), \
                 patch.object(private, 'verify_build', return_value=manifest):
                result = successor.check_run(path, directory)
                self.assertEqual(result['state'], 'PASS')
                self.assertEqual(result['complete_calls'], 4)
                self.assertIn('phase', result)
                self.assertIn('overhead', result)
                self.assertEqual(result['checker_identity']['sha256'], sha(successor.__file__))
                self.assertEqual(result['predecessor_checker']['sha256'], successor.PREDECESSOR_SHA256)
                self.assertIn('sealed checker', result['successor_reason'])
                self.assertFalse(result['independent_protocol_checked'])
                self.assertTrue(result['independent_uvm_gate_required'])
                self.assertEqual(result['log_sha256'], before[path])
                self.assertEqual({p: sha(p) for p in before}, before)
                for changed in (raw.replace('bits=3f800000', 'bits=7fc00000', 1),
                                raw.replace('fcsr=1', 'fcsr=17', 1),
                                raw.replace('guard_hash=315', 'guard_hash=314', 1),
                                raw.replace('end=15100', 'end=15000', 1),
                                raw.replace('sample=0 slot=0 cycles=3', 'sample=0 slot=0 cycles=0'),
                                raw.replace('UVM_ERROR : 0', 'UVM_ERROR : 1'),
                                raw + '\nUVM_FATAL @ 100: reporter [FAIL] stopped'):
                    path.write_text(changed)
                    with self.subTest(tail=changed[-80:]), self.assertRaises(ValueError):
                        successor.check_run(path, directory)
                self.assertEqual(sha(receipt), before[receipt])
                self.assertEqual(sha(build), before[build])


if __name__ == '__main__':
    unittest.main()
