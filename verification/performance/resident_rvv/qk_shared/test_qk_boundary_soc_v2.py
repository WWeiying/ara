#!/usr/bin/env python3
"""Focused successor identity/environment/commands tests; never runs simv."""
import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import qk_boundary_soc_v2 as q


class Successor(unittest.TestCase):
    def setUp(self):
        self.out = q.OUT / 'stage3_qk_boundary_v2_fixture_not_created'
        self.plan = dict(environment=dict(VCS_HOME='/vcs', VCS_ARCH_OVERRIDE='linux',
            SNPSLMD_LICENSE_FILE='27000@host', LM_LICENSE_FILE='/licenses/file',
            LD_LIBRARY_PATH=':/a:/a::/b', HOME='/home/user', PRIVATE_TOKEN='do-not-copy'))

    def test_environment_allowlist(self):
        env = q.environment(self.plan, self.out)
        self.assertEqual(env['LD_LIBRARY_PATH'], '/vcs/linux64/lib:/a:/b')
        self.assertNotIn('PRIVATE_TOKEN', env)
        self.assertEqual(env['PATH'], '/usr/bin:/bin')
        self.assertEqual(env['READELF'], '/usr/bin/readelf')
        self.assertEqual(env['LC_ALL'], 'C')
        self.assertEqual(env['PYTHONPATH'], str(self.out / 'inputs/verification'))

    def test_missing_license_rejected(self):
        for name in ('VCS_HOME', 'VCS_ARCH_OVERRIDE', 'SNPSLMD_LICENSE_FILE'):
            p = copy.deepcopy(self.plan); del p['environment'][name]
            with self.assertRaises(ValueError): q.environment(p, self.out)

    def test_newline_environment_rejected(self):
        self.plan['environment']['VCS_HOME'] = '/vcs\nextra'
        with self.assertRaises(ValueError): q.environment(self.plan, self.out)

    def test_service_explicit_environment_and_direct_worker(self):
        env = q.environment(self.plan, self.out)
        s = dict(environment=env, python=str(Path(sys.executable).resolve()))
        argv = q.service_argv(self.out, s, 'abc')
        self.assertIn('--property=RuntimeMaxSec=7200', argv)
        self.assertIn('--property=KillMode=control-group', argv)
        self.assertIn('--setenv=SNPSLMD_LICENSE_FILE=27000@host', argv)
        self.assertIn(str(self.out / 'inputs/qk_boundary_soc_v2.py'), argv)
        self.assertIn('--parent-reviewed', argv)
        self.assertEqual(argv[-2:], ['--review-sha256', 'abc'])
        self.assertNotIn('/bin/sh', argv)

    def test_frozen_firmware_and_checkers(self):
        old, checker, cases = q.frozen_modules()
        self.assertEqual(q.b.sha(Path(checker.__file__)), q.CHECKER_SHA)
        self.assertEqual(q.b.sha(Path(old.__file__)), q.RUNNER_SHA)
        self.assertEqual(cases.QK, 0x0605705b)
        self.assertTrue(Path(old.__file__).is_relative_to(q.SOFTWARE))
        self.assertEqual(old.SIM_SECONDS, q.SIM_SECONDS)

    def test_import_isolation(self):
        sentinel = sys.modules.get('cases')
        q.frozen_modules()
        self.assertIs(sys.modules.get('cases'), sentinel)

    def test_actual_firmware_contract(self):
        _, checker, _ = q.frozen_modules()
        sw, vectors, _ = checker.checked_build(q.SOFTWARE)
        self.assertEqual(sw['successful_qk'], 24)
        s = next(s for s in vectors['cases'] if s['kind'] == 'query_bounds')
        self.assertEqual((s['query_base'], s['heads'], s['context_queries'], s['recovery']['query_base']), (6, 2, 7, 5))

    def test_real_shared_contract_not_old_schema(self):
        self.assertTrue(callable(q.b.checked_build))
        self.assertEqual(q.b.sha(Path(q.b.__file__)), q.BUILDER_SHA)
        self.assertEqual(q.b.CPU_OVERLAY['after_sha256'], 'ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249')

    def test_firmware_copies_require_original_bytes(self):
        sw = q.b.read(q.SOFTWARE / 'build.json')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            shutil.copytree(q.SOFTWARE / 'inputs/qk_boundary', out / 'inputs/qk_boundary')
            q.verify_firmware_copy(out, sw)
            (out / 'inputs/qk_boundary/check.py').write_text('# altered checker\n')
            with self.assertRaises(ValueError): q.verify_firmware_copy(out, sw)

    def test_extra_firmware_copy_rejected(self):
        sw = q.b.read(q.SOFTWARE / 'build.json')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            shutil.copytree(q.SOFTWARE / 'inputs/qk_boundary', out / 'inputs/qk_boundary')
            (out / 'inputs/qk_boundary/extra.py').write_text('# unreviewed\n')
            with self.assertRaises(ValueError): q.verify_firmware_copy(out, sw)

    def test_software_identity_not_translated(self):
        with self.assertRaises(ValueError): q.collect(Path('/not-used'), Path('/different/build'))

    def test_output_unique_signoff_namespace(self):
        self.assertEqual(q.output_path(self.out), self.out)
        for path in (q.OUT / 'old_run', Path('/tmp/stage3_qk_boundary_v2_bad')):
            with self.assertRaises(ValueError): q.output_path(path)

    def test_frozen_recipes_preserved(self):
        old, _, _ = q.frozen_modules()
        soc = dict(simv='/image/simv')
        sw = dict(elf='/firmware/qk.elf')
        commands = old.recipes(self.out, soc, sw, q.SOFTWARE)
        self.assertIn('+RESIDENT_PV_PERF', commands['simulation'])
        self.assertIn('+RESIDENT_PV_WATCHDOG', commands['simulation'])
        self.assertIn('--require-events', commands['protocol'])
        self.assertIn('--require-axi-write', commands['protocol'])
        self.assertEqual(commands['boundary'][2], str(self.out / 'inputs/qk_boundary/check.py'))

    def test_scoped_exceptions_unchanged(self):
        from types import SimpleNamespace
        old, _, cases = q.frozen_modules()
        vectors = q.b.read(q.SOFTWARE / 'vectors/vectors.json')
        expected = []
        for s in cases.attempts(vectors['cases']):
            if not (s['error'] and s['kind'] in ('fs_off', 'vs_off')):
                expected.append((s['instruction'], s['error']))
            if s['id'] == 0: expected.append((cases.QK, 0))
        events = []
        for i, (word, error) in enumerate(expected):
            events += [(2*i, 1, 0, word, 0, 0, 0), (2*i+1, 0, 0, 0, 1, 0, error)]
        uvm = SimpleNamespace(_CONTRACT_EVENT=None, _events=lambda *args: (events, []))
        proof = dict(contract_counts=dict(exceptions=10))
        self.assertEqual(old.scoped_exceptions('', vectors, proof, uvm)['qk_requests'], 34)
        events[-1] = (*events[-1][:-1], 1)
        with self.assertRaises(ValueError): old.scoped_exceptions('', vectors, proof, uvm)

    def test_schema_adapter_calls_shared_checker(self):
        # A rejected shared contract cannot fall through to the old schema.
        with patch.object(q.b, 'checked_build', side_effect=ValueError('shared contract rejected')) as checked:
            with self.assertRaisesRegex(ValueError, 'shared contract rejected'):
                q.collect(q.OUT / 'stage3_soc_fixture')
            checked.assert_called_once()


if __name__ == '__main__':
    unittest.main()
