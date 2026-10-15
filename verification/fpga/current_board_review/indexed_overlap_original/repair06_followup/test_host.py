#!/usr/bin/env python3
"""Focused host negatives. No service, simulator, or build launch."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import coordinator as c


def fixture():
    plan = c.read(c.PRE / 'plan.json')
    data = dict(status='PASS_3_REFERENCE03_FULL50_M6', aborted=False, pins_unchanged=True,
                plan_sha256=c.PRE_SHA, image_sha256=c.IMAGE_SHA,
                results=[dict(name=x['id'], status='PASS', returncode=0, elapsed_s=1) for x in plan['cases']],
                evidence_pins={'placeholder': 'only for header test'})
    return plan, data


class Tests(unittest.TestCase):
    def test_exact_three_pass_header_and_false_pass(self):
        plan, data = fixture()
        c.terminal_header(data, plan, c.PRE_SHA, 'PASS_3_REFERENCE03_FULL50_M6')
        for key, value in [('aborted', True), ('pins_unchanged', False), ('status', 'PASS'),
                           ('plan_sha256', 'bad'), ('image_sha256', 'bad'), ('evidence_pins', {})]:
            bad = copy.deepcopy(data); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.terminal_header(bad, plan, c.PRE_SHA, 'PASS_3_REFERENCE03_FULL50_M6')

    def test_partial_duplicate_timeout_nonzero_terminal(self):
        plan, data = fixture()
        variants = []
        bad = copy.deepcopy(data); bad['results'].pop(); variants.append(bad)
        bad = copy.deepcopy(data); bad['results'][2] = bad['results'][0]; variants.append(bad)
        for key, value in [('status', 'TIMEOUT'), ('returncode', 15), ('elapsed_s', 4201)]:
            bad = copy.deepcopy(data); bad['results'][0][key] = value; variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError): c.terminal_header(bad, plan, c.PRE_SHA, 'PASS_3_REFERENCE03_FULL50_M6')

    def test_real_file_hash_and_stale_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'source.sv'; path.write_text('pinned-source')
            pins = {str(path): c.sha(path)}; c.verify(pins)
            path.write_text('stale-source')
            with self.assertRaises(ValueError): c.verify(pins)
            path.unlink()
            with self.assertRaises(FileNotFoundError): c.verify(pins)

    def test_missing_and_partial_terminal_never_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'complete.json'
            with self.assertRaises(FileNotFoundError): c.read(path)
            path.write_text('{"status":')
            with self.assertRaises(ValueError): c.read(path)
            path.write_text('{"status":"PASS_3_REFERENCE03_FULL50_M6"}')
            with self.assertRaises(KeyError):
                c.terminal_header(c.read(path), fixture()[0], c.PRE_SHA, 'PASS_3_REFERENCE03_FULL50_M6')

    def test_actual_owner_and_foreign_cgroup(self):
        props = dict(Id=c.UNIT, LoadState='loaded', ActiveState='active', SubState='running',
                     MainPID='101', ControlGroup='/user/' + c.UNIT)
        c.owner_proof(props, 101, props['ControlGroup'])
        for key, value in [('MainPID', '102'), ('ControlGroup', '/alien'), ('Id', c.PRE_UNIT),
                           ('LoadState', 'not-found'), ('ActiveState', 'inactive')]:
            bad = dict(props); bad[key] = value
            with self.assertRaises(ValueError): c.owner_proof(bad, 101, props['ControlGroup'])

    def test_predecessor_live_simv_and_foreign_output_owner(self):
        row = dict(pid=12, comm='simv', argv=['/m6/simv', '+COMMIT_TRACE=' + str(c.PRE) + '/pilot/test.csv'],
                   cgroup='0::/user/' + c.PRE_UNIT)
        self.assertEqual(c.owned_rows([row], c.PRE, c.PRE_UNIT), [row])
        bad = dict(row, cgroup='0::/user/other.service')
        with self.assertRaises(ValueError): c.owned_rows([bad], c.PRE, c.PRE_UNIT)
        external = dict(row, argv=['/m6/simv', '+COMMIT_TRACE=/somewhere/trace.csv'], cgroup='0::/other')
        self.assertEqual(c.owned_rows([external], c.PRE, c.PRE_UNIT), [])

    def test_gc_not_historical_success_and_loaded_timeout_refused(self):
        worker = SimpleNamespace(bus_environment=lambda: {})
        text = f'Id={c.PRE_UNIT}\nLoadState=not-found\nActiveState=inactive\nMainPID=0\nResult=success\n'
        with patch.object(c.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='', stdout=text)), \
             patch.object(c, 'processes', return_value=[]):
            quiet, proof = c.predecessor_state(worker)
            self.assertTrue(quiet); self.assertFalse(proof['historical_service_exit_verified'])
        text = text.replace('not-found', 'loaded').replace('Result=success', 'Result=timeout')
        with patch.object(c.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='', stdout=text)), \
             patch.object(c, 'processes', return_value=[]):
            with self.assertRaises(ValueError): c.predecessor_state(worker)

    def test_exact_evidence_membership(self):
        plan, _ = fixture()
        paths = c.expected_evidence(plan, c.PRE, True)
        self.assertEqual(len(paths), 29)
        self.assertIn(str(c.PRE / 'pilot/tests/d32m2_i64_fault_ov1/work/indexed_first_round.fsdb'), paths)
        self.assertEqual(sum(p.endswith('commit_trace.csv') for p in paths), 3)
        self.assertEqual(sum(p.endswith('indexed_analysis.json') for p in paths), 3)

    def test_exclusive_file_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'plan.json'; c.save(path, {'original': True})
            with self.assertRaises(FileExistsError): c.save(path, {'original': False})
            self.assertEqual(c.read(path), {'original': True})

    def test_no_authorization_no_child_and_finite_budgets(self):
        with patch.object(c.subprocess, 'Popen') as launch:
            with self.assertRaises(ValueError): c.run(Path('/unused'), None, False)
            launch.assert_not_called()
        self.assertEqual((c.WAIT_SECONDS, c.SLEEP_SECONDS, c.REG_SECONDS), (10800, 120, 21600))
        self.assertGreaterEqual(c.SERVICE_SECONDS, c.WAIT_SECONDS + c.REG_SECONDS + 600)
        self.assertNotIn('systemd-run', c.regression_command())


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    c.save(c.HERE / 'host_final.json', dict(status='HOST_PASS_NOT_DUT' if result.wasSuccessful() else 'HOST_FAIL',
        tests=result.testsRun, failures=[(str(t), s) for t, s in result.failures],
        errors=[(str(t), s) for t, s in result.errors], simulator_started=False, service_started=False,
        pins={str(c.HERE / name): c.sha(c.HERE / name) for name in ('coordinator.py', 'test_host.py', 'README.md')}))
    raise SystemExit(not result.wasSuccessful())
