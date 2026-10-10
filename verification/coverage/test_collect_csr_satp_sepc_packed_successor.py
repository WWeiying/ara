import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

import collect_csr_satp_sepc_packed_successor as p


class ConsumerTests(unittest.TestCase):
    def test_exact_original_body_all_gates_unchanged(self):
        fn = p.consumer({})
        self.assertIs(fn.__code__, p.original.collect.__code__)
        for name in ('runner', 'life', 'terminal_gate', 'scalar_gate', 'architecture', 'primitive',
                     'vector_commit', 'coverage', 'raw_gain', 'require', 'spike_trace', '__file__'):
            self.assertIs(fn.__globals__[name], p.original.collect.__globals__[name])
        self.assertIs(fn.__globals__['wave_audit'], p.adapter.wave_audit)
        self.assertEqual(fn.__globals__['subprocess'].STDOUT, subprocess.STDOUT)

    def cache_fixture(self, directory):
        root = Path(directory); cached = root/'sealed.vcd'; cached.write_bytes(b'bound-test-vcd\n')
        out = root/'out'; out.mkdir(); run = root/'run'
        record = dict(output=str(out), run=str(run), cached_vcd=str(cached), cached_vcd_sha256=p.life.digest(cached))
        command = [str(p.original.runner.converter.CONVERTER), '-splitpacked', str(run/'csr-owner.vpd'), str(out/'csr-owner.vcd')]
        kwargs = dict(stdout=io.StringIO(), stderr=subprocess.STDOUT, check=True, timeout=120)
        return record, command, kwargs

    def test_exact_cache_substitution_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, cmd, kw = self.cache_fixture(tmp)
            self.assertEqual(p.cached_converter(r, cmd, **kw).returncode, 0)
            self.assertEqual((Path(r['output'])/'csr-owner.vcd').read_bytes(), Path(r['cached_vcd']).read_bytes())
            self.assertIn('NO_CONVERTER_EXECUTION', kw['stdout'].getvalue())

    def test_cache_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, cmd, kw = self.cache_fixture(tmp); Path(r['cached_vcd']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'drift'): p.cached_converter(r, cmd, **kw)

    def test_other_subprocess_forbidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, cmd, kw = self.cache_fixture(tmp)
            with self.assertRaisesRegex(ValueError, 'exact'): p.cached_converter(r, ['simv'], **kw)

    def test_wrong_conversion_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, cmd, kw = self.cache_fixture(tmp); cmd[2] += '.foreign'
            with self.assertRaisesRegex(ValueError, 'exact'): p.cached_converter(r, cmd, **kw)

    def test_bool_timeout_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, cmd, kw = self.cache_fixture(tmp); kw['timeout'] = True
            with self.assertRaisesRegex(ValueError, 'exact'): p.cached_converter(r, cmd, **kw)

    def test_existing_destination_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, cmd, kw = self.cache_fixture(tmp); target = Path(r['output'])/'csr-owner.vcd'; target.write_bytes(b'keep')
            with self.assertRaises(FileExistsError): p.cached_converter(r, cmd, **kw)
            self.assertEqual(target.read_bytes(), b'keep')


class ActualPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        token = uuid.uuid4().hex
        cls.plan = p.life.OUT / ('csr-packed-successor-unittest-' + token + '.json')
        cls.out = p.life.OUT / ('csr-packed-successor-unittest-' + token)
        cls.record = p.prepare(p.adapter.packed.RUN, p.RUN_SEAL, cls.out, cls.plan)
        cls.seal = p.life.digest(cls.plan)

    @classmethod
    def tearDownClass(cls):
        cls.plan.unlink()

    def test_actual_prepare_verify_no_qualification(self):
        self.assertEqual(p.verify(self.plan, self.seal), self.record)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.record['qualification_performed'])
        self.assertIn(str(p.CACHE), self.record['input_pins'])
        self.assertIn(str(p.adapter.packed.RUN/'csr-owner.vpd'), self.record['input_pins'])

    def test_omitted_pin_rejected(self):
        bad = copy.deepcopy(self.record); bad['input_pins'].pop(str(p.CACHE))
        with patch.object(p.life, 'read_bound', return_value=bad):
            # Only the plan read is mocked; subsequent reads are unnecessary for this mutation test.
            with patch.object(p, 'manifest', return_value=self.record):
                with self.assertRaisesRegex(ValueError, 'drift'): p.verify(self.plan, self.seal)

    def test_wrong_run_seal_rejected(self):
        with self.assertRaisesRegex(ValueError, 'executed'): p.manifest(p.adapter.packed.RUN, '0'*64, self.out)

    def test_immutable_evidence_required(self):
        with patch.object(p, 'EVIDENCE_SHA', '0'*64):
            with self.assertRaises(ValueError): p.manifest(p.adapter.packed.RUN, p.RUN_SEAL, self.out)

    def test_collect_does_not_run_without_verified_plan(self):
        with patch.object(p, 'verify', side_effect=ValueError('rejected')), patch.object(p, 'consumer') as consumer:
            with self.assertRaises(ValueError): p.collect(self.plan, self.seal)
            consumer.assert_not_called()


if __name__ == '__main__': unittest.main()
