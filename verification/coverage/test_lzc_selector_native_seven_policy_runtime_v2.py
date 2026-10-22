import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import lzc_selector_native_seven_policy_runtime_v2 as subject


class SerializedRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((subject.SIX_OUTPUT / 'config.json').read_bytes())
        cls.plan = json.loads((subject.PLAN_OUTPUT / 'application-plan.json').read_bytes())
        cls.serialized = (subject.PLAN_OUTPUT / 'combined-seven-proposal.el').read_bytes()
        cls.original = (subject.SIX_OUTPUT / 'combined.el').read_bytes()
        cls.candidate = (Path(cls.plan['source_proof']).parent / 'candidate60.el').read_bytes()
        cls.native = cls.original + cls.candidate

    def decode(self, raw):
        return subject.decode_json_native(raw, self.config, self.plan['condition_native_records'],
                                          self.original, self.candidate)

    def test_actual_frozen_serialization_regression_not_raw_byte_fixture(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            path = Path(temporary) / 'proposal.el'
            # Reproduce the frozen producer's exact writer, including JSON quoting.
            subject.frozen.write(path, self.native.decode('ascii'))
            self.assertEqual(path.read_bytes(), self.serialized)
            self.assertEqual(subject.digest_bytes(path.read_bytes()), subject.SERIALIZED_SHA)
            with self.assertRaisesRegex(ValueError, 'Invalid header'):
                subject.seven.split_seven(path.read_bytes(), self.config, self.plan['condition_native_records'])
            self.assertEqual(self.decode(path.read_bytes()), self.native)

    def test_public_known_artifact_decodes_once_and_exact_both_components(self):
        loads = json.loads
        with patch.object(subject.json, 'loads', wraps=loads) as spy:
            native = subject.decoded_proposal(subject.PLAN_OUTPUT, self.plan, self.config)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(native, self.native)
        self.assertEqual(subject.digest_bytes(native), subject.NATIVE_SHA)

    def test_non_string_malformed_double_encoding_and_non_ascii_rejected(self):
        bad = (self.native, b'{broken', b'null', b'{}', b'[]', b'42',
               json.dumps(self.serialized.decode('ascii')).encode(),
               json.dumps(self.native.decode('ascii') + '\u00e9').encode())
        for raw in bad:
            with self.subTest(prefix=raw[:40]), self.assertRaises((ValueError, UnicodeError)):
                self.decode(raw)

    def test_exact_signatures_reject_false_duplicate_foreign_and_native_id(self):
        records = self.plan['condition_native_records']
        bad = (self.original + self.candidate + self.candidate,
               self.original + self.candidate.replace(b'(2 "1")', b'(2 "0")', 1),
               self.original + self.candidate.replace(records[0]['scope'].encode(), b'ara_tb.unapproved', 1),
               self.original + self.candidate.replace(b'Condition 20 ', b'Condition 9999 ', 1),
               self.original.replace(b'Branch ', b'Branch 9999 ', 1) + self.candidate,
               self.native + b'// ignored syntax still must not change exact component bytes\n')
        for native in bad:
            with self.subTest(prefix=native[:40]), self.assertRaises(ValueError):
                self.decode(json.dumps(native.decode('ascii')).encode())

    def test_public_gate_rejects_unsealed_scope_plan_component_and_artifact_drift(self):
        with self.assertRaisesRegex(ValueError, 'directory'):
            subject.decoded_proposal(subject.PLAN_OUTPUT.with_name('unknown-copy'), self.plan, self.config)
        for update in ({'six_config_sha256': '0' * 64},
                       {'pins': dict(self.plan['pins'], **{str(subject.PLAN_OUTPUT / 'combined-seven-proposal.el'): '0' * 64})}):
            with self.assertRaises(ValueError):
                subject.decoded_proposal(subject.PLAN_OUTPUT, dict(self.plan, **update), self.config)
        original_read = Path.read_bytes
        artifact = subject.PLAN_OUTPUT / 'combined-seven-proposal.el'
        def read(path):
            return self.serialized + b'\n' if path == artifact else original_read(path)
        with patch.object(Path, 'read_bytes', read), self.assertRaisesRegex(ValueError, 'artifact bytes'):
            subject.decoded_proposal(subject.PLAN_OUTPUT, self.plan, self.config)

    def test_source_adapter_no_frozen_mutation_retains_actual_tcl(self):
        self.assertIs(subject.prepare.__globals__, subject.__dict__)
        self.assertIs(subject.verify.__globals__['read_config'], subject.read_config)
        self.assertIs(subject.prior.verify.__globals__['read_config'], subject.prior.read_config)
        self.assertEqual(subject.TCL, subject.prior.TCL)
        self.assertEqual(subject.frozen.sha(Path(subject.prior.__file__)), subject.PRIOR_SHA)
        self.assertIn('decoded_proposal', subject.prepare.__code__.co_names)
        self.assertIn('verify_serialization_binding', subject.read_config.__code__.co_names)

    def test_actual_serialized_prepare_check_double_pin_no_eda_and_omission_rejected(self):
        # Mock only expensive inherited checks/hashes, not serialized/native bytes.
        known = dict(self.config['pins'], **self.plan['pins'])
        real_sha = subject.frozen.sha
        def cached_sha(path):
            return known.get(str(path)) or real_sha(path)
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            output = subject.frozen.OUT / (Path(temporary).name + '-runtime-v2-test')
            try:
                with patch.object(subject.six, 'read_config', return_value=(None, self.config)), \
                     patch.object(subject.frozen, 'sha', side_effect=cached_sha), \
                     patch.object(subprocess, 'Popen', side_effect=AssertionError('NO_EDA')):
                    runtime = subject.prepare(output, subject.SIX_OUTPUT, subject.SIX_SEAL,
                                              subject.PLAN_OUTPUT, subject.PLAN_SEAL, True)
                    self.assertEqual((output / 'combined-seven.el').read_bytes(), self.native)
                    self.assertEqual(runtime['pins'][str(subject.PLAN_OUTPUT / 'combined-seven-proposal.el')], subject.SERIALIZED_SHA)
                    self.assertEqual(runtime['pins'][str(output / 'combined-seven.el')], subject.NATIVE_SHA)
                    seal = real_sha(output / 'runtime-plan.json')
                    _, derived = subject.read_config(output, seal)
                    self.assertEqual(derived['groups'], self.config['groups'])
                    self.assertEqual(derived['inputs'], self.config['inputs'])
                    self.assertEqual((runtime['targets'], runtime['protected'], runtime['audited']), (5868, 17702, 23570))
                    self.assertEqual(runtime['command'], self.config['command'][:-1] + [str(subject.TCL)])
                    self.assertFalse(runtime['native_X_semantics_measured'])
                    self.assertFalse(runtime['application_approval'])
                    self.assertEqual(runtime['serialized_native_binding']['json_decode_passes'], 1)
                    for key in (str(subject.PLAN_OUTPUT / 'combined-seven-proposal.el'), str(output / 'combined-seven.el')):
                        altered = copy.deepcopy(runtime)
                        del altered['pins'][key]
                        subject.frozen.write(output / 'runtime-plan.json', altered)
                        with self.assertRaises(ValueError):
                            subject.read_config(output, real_sha(output / 'runtime-plan.json'))
                    altered = copy.deepcopy(runtime)
                    altered['serialized_native_binding']['json_decode_passes'] = 2
                    subject.frozen.write(output / 'runtime-plan.json', altered)
                    with self.assertRaisesRegex(ValueError, 'provenance'):
                        subject.read_config(output, real_sha(output / 'runtime-plan.json'))
            finally:
                if output.exists():
                    shutil.rmtree(output)

    def test_prepare_wrong_seal_rejected_before_inherited_check(self):
        with patch.object(subject.six, 'read_config', side_effect=AssertionError('MUST_NOT_CHECK')):
            with self.assertRaisesRegex(ValueError, 'sealed724'):
                subject.prepare(subject.frozen.OUT / 'NEVER_PREPARED', subject.SIX_OUTPUT, 'wrong',
                                subject.PLAN_OUTPUT, subject.PLAN_SEAL, True)


if __name__ == '__main__':
    unittest.main()
